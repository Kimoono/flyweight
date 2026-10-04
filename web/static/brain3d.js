// The brain view in 3D. A WebGL canvas (#brain3d) sits under the 2D brain canvas: it draws the
// 138,639 neurons as a point cloud and the spikes as additive dots, the 2D canvas on top keeps the
// rings, the plain-word labels with their leader lines and the replay overlay, projected through the
// same camera every frame. Drag rotates, the wheel zooms, a double-click or F snaps back to the front
// view; left alone the camera sways slowly so the room can see it is a solid object.
// If WebGL is missing or the context is lost, `ready` is false and index.html draws the flat view it
// always had: the game never depends on this file.
import * as THREE from "/static/vendor/three/build/three.module.js";

// positions.bin is FlyWire voxel space (4 x 4 x 40 nm): z is 10x coarser than x and y. Without this
// the rotated brain is a pancake 7% as deep as it is wide instead of a third.
const Z_SCALE = 10;
const UNIT = 1 / 1000;          // world units per voxel: the brain becomes ~204 x 98 x 70 units
const CAP = 32768;              // spike dots per frame: five ticks of fade x 4000 events per tick
const FOV = 30;

const CLOUD_VS = `
  attribute vec4 rgba;
  uniform float pointSize, refDist;
  varying vec4 vColor;
  void main() {
    vColor = rgba;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = pointSize * clamp(refDist / -mv.z, 0.5, 2.0);
  }`;
const CLOUD_FS = `
  varying vec4 vColor;
  void main() { gl_FragColor = vColor; }`;
const SPIKE_VS = `
  attribute vec4 rgba;
  attribute float psize;
  uniform float refDist;
  varying vec4 vColor;
  void main() {
    vColor = rgba;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = psize * clamp(refDist / -mv.z, 0.5, 2.0);
  }`;
const SPIKE_FS = `
  varying vec4 vColor;
  void main() {
    float r = length(gl_PointCoord - 0.5) * 2.0;
    if (r > 1.0) discard;
    gl_FragColor = vec4(vColor.rgb, vColor.a * (1.0 - smoothstep(0.55, 1.0, r)));
  }`;

export class Brain3D {
  // `canvas` is the WebGL canvas, `surface` the element on top that receives the drags.
  constructor(canvas, surface) {
    this.canvas = canvas; this.ok = false; this.ready = false;
    this.yaw = 0; this.pitch = 0; this.zoom = 1;
    this.sway = 0.3;            // radians of idle yaw sway (0 = still); console: brain3d.sway = 0
    this.swayAfter = 6;         // seconds without a touch before the sway eases in
    this.pointSize = 1.0;       // cloud dot size in device px at the fitted distance
    this.alphaDim = 0.16; this.alphaRole = 0.55;   // cloud alphas: any neuron / a sense or output neuron
    this._amp = 0; this._phase = 0; this._idle = this.swayAfter;
    this._fit = 300; this._W = 1; this._H = 1; this._v = new THREE.Vector3();
    try {
      this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "high-performance" });
    } catch (e) { console.warn("3D brain off: no WebGL", e); return; }
    this.renderer.setPixelRatio(1);                       // the canvas backing size is already in device px
    this.renderer.setClearColor(0x000000, 0);             // the panel colour behind the canvas shows through
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(FOV, 1, 1, 10000);
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.ok = this.ready = false; console.warn("3D brain off: context lost"); });
    this.ok = true;
    this._bindInput(surface);
  }

  // pos: Float32Array xyz per neuron (voxels, NaN = unknown), cls: Uint8Array class per neuron,
  // classes: the CLASSES table from index.html, flipX: mirror x so the fly's left is on the viewer's left.
  setData(pos, cls, classes, flipX) {
    if (!this.ok) return;
    const N = pos.length / 3;
    let mn = [1e12, 1e12, 1e12], mx = [-1e12, -1e12, -1e12];
    for (let i = 0; i < N; i++) { if (isNaN(pos[3 * i])) continue;
      for (let a = 0; a < 3; a++) { const v = pos[3 * i + a]; if (v < mn[a]) mn[a] = v; if (v > mx[a]) mx[a] = v; } }
    const c = [0, 1, 2].map((a) => (mn[a] + mx[a]) / 2);
    // Front view = the flat view: screen x right, screen y up = -file y. The z sign is chosen so the map
    // is a proper rotation (no mirror), so a turn shows the real brain and not its reflection.
    const sx = flipX ? -1 : 1, sz = flipX ? 1 : -1;
    const w = this.wpos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      if (isNaN(pos[3 * i])) { w[3 * i] = w[3 * i + 1] = w[3 * i + 2] = NaN; continue; }
      w[3 * i] = sx * (pos[3 * i] - c[0]) * UNIT;
      w[3 * i + 1] = -(pos[3 * i + 1] - c[1]) * UNIT;
      w[3 * i + 2] = sz * (pos[3 * i + 2] - c[2]) * Z_SCALE * UNIT;
    }
    this.half = [(mx[0] - mn[0]) / 2 * UNIT, (mx[1] - mn[1]) / 2 * UNIT, (mx[2] - mn[2]) / 2 * Z_SCALE * UNIT];
    // static cloud: one point per neuron with a position, tinted by class
    let n = 0; for (let i = 0; i < N; i++) if (!isNaN(w[3 * i])) n++;
    const cp = new Float32Array(n * 3), cc = new Float32Array(n * 4);
    for (let i = 0, j = 0; i < N; i++) {
      if (isNaN(w[3 * i])) continue;
      cp[3 * j] = w[3 * i]; cp[3 * j + 1] = w[3 * i + 1]; cp[3 * j + 2] = w[3 * i + 2];
      const col = classes[cls[i]].colour;
      cc[4 * j] = col[0] / 255; cc[4 * j + 1] = col[1] / 255; cc[4 * j + 2] = col[2] / 255; cc[4 * j + 3] = cls[i] ? this.alphaRole : this.alphaDim;
      j++;
    }
    const cg = new THREE.BufferGeometry();
    cg.setAttribute("position", new THREE.BufferAttribute(cp, 3));
    cg.setAttribute("rgba", new THREE.BufferAttribute(cc, 4));
    this.cloudMat = new THREE.ShaderMaterial({ vertexShader: CLOUD_VS, fragmentShader: CLOUD_FS, transparent: true, depthWrite: false, depthTest: false,
      uniforms: { pointSize: { value: 1 }, refDist: { value: 1 } } });
    if (this.cloud) this.scene.remove(this.cloud);
    this.cloud = new THREE.Points(cg, this.cloudMat); this.cloud.frustumCulled = false; this.scene.add(this.cloud);
    // spikes: a buffer refilled every frame, additive so overlapping flashes add up like the flat view
    this.sp = new Float32Array(CAP * 3); this.sc = new Float32Array(CAP * 4); this.ss = new Float32Array(CAP); this.count = 0;
    const sg = new THREE.BufferGeometry();
    sg.setAttribute("position", new THREE.BufferAttribute(this.sp, 3).setUsage(THREE.DynamicDrawUsage));
    sg.setAttribute("rgba", new THREE.BufferAttribute(this.sc, 4).setUsage(THREE.DynamicDrawUsage));
    sg.setAttribute("psize", new THREE.BufferAttribute(this.ss, 1).setUsage(THREE.DynamicDrawUsage));
    sg.setDrawRange(0, 0);
    this.spikeMat = new THREE.ShaderMaterial({ vertexShader: SPIKE_VS, fragmentShader: SPIKE_FS, transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending, uniforms: { refDist: { value: 1 } } });
    if (this.spikes) this.scene.remove(this.spikes);
    this.spikes = new THREE.Points(sg, this.spikeMat); this.spikes.frustumCulled = false; this.scene.add(this.spikes);
    this.resize(this._W, this._H);
    this.ready = true;
  }

  // W, H in device px. The brain is fitted to the canvas minus the label margins index.html uses.
  resize(W, H) {
    this._W = W; this._H = H;
    if (!this.ok) return;
    this.renderer.setSize(W, H, false);
    this.camera.aspect = W / H; this.camera.updateProjectionMatrix();
    if (!this.half) return;
    const dpr = devicePixelRatio, pad = 30 * dpr, top = 50 * dpr, bottom = 70 * dpr;
    const t = Math.tan(FOV / 2 * Math.PI / 180), [hx, hy, hz] = this.half;
    // a yaw turns depth into width and a pitch turns it into height: fit the worst case of each
    const rh = Math.hypot(hx, hz) * 1.04, rv = Math.hypot(hy, hz) * 1.04;
    this._fit = Math.max(rh / (t * this.camera.aspect * (W - 2 * pad) / W), rv / (t * (H - top - bottom) / H));
  }

  beginSpikes() { this.count = 0; }
  // col: [r, g, b] 0-255, alpha 0-1, size: dot diameter in device px
  addSpike(i, col, alpha, size) {
    const n = this.count; if (n >= CAP) return;
    const w = this.wpos; if (isNaN(w[3 * i])) return;
    this.sp[3 * n] = w[3 * i]; this.sp[3 * n + 1] = w[3 * i + 1]; this.sp[3 * n + 2] = w[3 * i + 2];
    this.sc[4 * n] = col[0] / 255; this.sc[4 * n + 1] = col[1] / 255; this.sc[4 * n + 2] = col[2] / 255; this.sc[4 * n + 3] = alpha;
    this.ss[n] = size; this.count = n + 1;
  }

  // Advance the idle sway and place the camera. Call once per frame before render()/project().
  update(dtMs) {
    if (!this.ready) return;
    const dt = Math.min(0.1, dtMs / 1000);
    this._idle += dt;
    this._amp = this._idle > this.swayAfter ? Math.min(1, this._amp + dt / 3) : Math.max(0, this._amp - dt);
    this._phase += dt * 2 * Math.PI / 30;
    const yaw = this.yaw + this._swayYaw(), pitch = this.pitch + this._swayPitch();
    const d = this._fit / this.zoom, cp = Math.cos(pitch);
    this.camera.position.set(d * Math.sin(yaw) * cp, d * Math.sin(pitch), d * Math.cos(yaw) * cp);
    this.camera.lookAt(0, 0, 0); this.camera.updateMatrixWorld();
    const dpr = devicePixelRatio;
    this.cloudMat.uniforms.pointSize.value = this.pointSize * dpr;
    this.cloudMat.uniforms.refDist.value = this.spikeMat.uniforms.refDist.value = this._fit;
  }
  _swayYaw() { return this._amp * this.sway * Math.sin(this._phase); }
  _swayPitch() { return this._amp * this.sway * 0.35 * Math.sin(this._phase * 0.61); }
  // Fold the current sway into the rest pose so a touch never jumps the view.
  _bake() { this.yaw += this._swayYaw(); this.pitch += this._swayPitch(); this._amp = 0; this._phase = 0; this._idle = 0; }
  front() { this._bake(); this.yaw = 0; this.pitch = 0; this.zoom = 1; }

  render() {
    if (!this.ready) return;
    const g = this.spikes.geometry;
    for (const name of ["position", "rgba", "psize"]) {
      const a = g.getAttribute(name); a.clearUpdateRanges(); a.addUpdateRange(0, this.count * a.itemSize); a.needsUpdate = true;
    }
    g.setDrawRange(0, this.count);
    this.renderer.render(this.scene, this.camera);
  }

  // Screen position (device px) of neuron i through the current camera; [-1e6, -1e6] if unknown.
  project(i) {
    const w = this.wpos; if (isNaN(w[3 * i])) return [-1e6, -1e6];
    const v = this._v.set(w[3 * i], w[3 * i + 1], w[3 * i + 2]).project(this.camera);
    return [(v.x + 1) / 2 * this._W, (1 - v.y) / 2 * this._H];
  }

  _bindInput(el) {
    let drag = null;
    el.addEventListener("pointerdown", (e) => { if (!this.ready) return; this._bake(); drag = { x: e.clientX, y: e.clientY }; el.setPointerCapture(e.pointerId); });
    el.addEventListener("pointermove", (e) => {
      if (!drag) return;
      this.yaw -= (e.clientX - drag.x) * 0.006; this.pitch = Math.max(-1.45, Math.min(1.45, this.pitch + (e.clientY - drag.y) * 0.006));
      drag = { x: e.clientX, y: e.clientY }; this._idle = 0;
    });
    const up = () => { drag = null; this._idle = 0; };
    el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
    el.addEventListener("wheel", (e) => { if (!this.ready) return; e.preventDefault(); this.zoom = Math.max(0.6, Math.min(3, this.zoom * Math.exp(-e.deltaY * 0.0015))); this._idle = 0; }, { passive: false });
    el.addEventListener("dblclick", () => { if (this.ready) this.front(); });
  }
}
