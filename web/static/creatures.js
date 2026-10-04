// 3D creatures on top of the 2D arena. A transparent WebGL canvas sits over the arena canvas; an
// orthographic camera looks straight down and covers exactly the same world rectangle as the 2D
// transform in index.html (world px in, screen px out), so a creature at world (x, y) lands on the
// pixel where the 2D layer would have drawn it. The 2D layer keeps drawing everything else (rings,
// drops, trail, eating arc, shadows, flashes).
// If WebGL is missing, a model fails to load, or the context is lost, `spidersReady` / `flyReady`
// are false and the 2D layer falls back to its hand-drawn bodies: the game never depends on this file.
import * as THREE from "/static/vendor/three/build/three.module.js";
import { GLTFLoader } from "/static/vendor/three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "/static/vendor/three/examples/jsm/utils/SkeletonUtils.js";

// Both models: glTF is Y-up and they face +Z (Blender's -Y front). `span` is the longest side of the
// footprint in world px. `stride` is how many px one Walk cycle carries the body: the clips have no
// root motion, so this choice sets the clip speed at every movement speed and stops the feet sliding.
const MODELS = {
  spider: { url: "/static/spider_01.glb", prefix: /^Spider_/, span: 70, stride: 70 },
  fly:    { url: "/static/Fly_01.glb",    prefix: /^Fly_/,    span: 80, stride: 30 },
};
const POUNCE_R = 130;        // must match sim/world.py: inside this the spider lunges
const FADE_S = 0.15;
// Drops are procedural: a squashed glossy dome on a puddle. Sugar is clear green syrup, bitter a murky
// matte yellow puddle, a spoiled drop is the syrup gone grey with a bitter splat on top. Colours keep the
// phone's sugar/bitter hues (play.html) so a tap and what appears on the floor match.
const DROP = { dome: 12, puddle: 24, land: 0.3, gone: 0.15 };   // radii in world px, animation seconds

export class Creatures {
  constructor(canvas) {
    this.canvas = canvas; this.ok = false; this.spidersReady = false; this.flyReady = false;
    this.spiders = []; this.fly = null; this.models = {}; this.view = null; this.drops = new Map(); this.dropsReady = false;
    try {
      this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "high-performance" });
    } catch (e) { console.warn("3D creatures off: no WebGL", e); return; }
    this.renderer.setPixelRatio(1);                       // the canvas backing size is already in device px
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 5000);
    this.camera.position.set(0, 0, 2000); this.camera.up.set(0, 1, 0); this.camera.lookAt(0, 0, 0);
    // lit like a stage: strong key from the top-left, a cool rim from the opposite side, warm fill
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3020, 2.4));
    const key = new THREE.DirectionalLight(0xfff4e0, 4.5); key.position.set(-400, 500, 900); this.scene.add(key);
    // shadows: the key light casts them onto an invisible floor that shows nothing but the shadow
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFShadowMap;
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0005; key.shadow.normalBias = 0.5; key.shadow.radius = 3;
    Object.assign(key.shadow.camera, { left: -900, right: 900, top: 700, bottom: -700, near: 100, far: 3000 });
    this.key = key; this.floor = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.ShadowMaterial({ opacity: 0.6 }));
    this.floor.position.z = -0.5; this.floor.receiveShadow = true; this.scene.add(this.floor);
    const rim = new THREE.DirectionalLight(0x9fc4ff, 2.5); rim.position.set(500, -400, 300); this.scene.add(rim);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.35;
    this.ok = true;
    this.dropKit = this.makeDropKit();
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.ok = false; this.flag(); });
    canvas.addEventListener("webglcontextrestored", () => { this.ok = true; this.flag(); });
    this.load("spider"); this.load("fly");
  }

  flag() { this.spidersReady = this.ok && !!this.models.spider; this.flyReady = this.ok && !!this.models.fly; this.dropsReady = this.ok; }

  // Shared geometry and materials for the drops (a handful of instances at most, so no instancing).
  makeDropKit() {
    const dome = new THREE.SphereGeometry(DROP.dome, 24, 16), puddle = new THREE.CircleGeometry(DROP.puddle, 32), splat = new THREE.SphereGeometry(DROP.dome * 0.55, 16, 10);
    // a soft-edged disc texture so puddles fade out instead of ending in a hard rim
    const cv = document.createElement("canvas"); cv.width = cv.height = 128; const g = cv.getContext("2d"), grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0, "rgba(255,255,255,1)"); grad.addColorStop(0.55, "rgba(255,255,255,0.85)"); grad.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grad; g.fillRect(0, 0, 128, 128); const soft = new THREE.CanvasTexture(cv);
    const syrup = new THREE.MeshPhysicalMaterial({ color: 0x8ac926, roughness: 0.12, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.08, transparent: true, opacity: 0.9, emissive: 0x3a6a00, emissiveIntensity: 0.35 });
    const stale = new THREE.MeshPhysicalMaterial({ color: 0x8a9a6a, roughness: 0.5, metalness: 0, clearcoat: 0.3, transparent: true, opacity: 0.85 });
    const sugarPuddle = new THREE.MeshStandardMaterial({ map: soft, color: 0x5f8f1a, roughness: 0.25, transparent: true, opacity: 0.6, emissive: 0x2a4a00, emissiveIntensity: 0.3, depthWrite: false });
    const bitter = new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.95, metalness: 0 });
    const bitterPuddle = new THREE.MeshStandardMaterial({ map: soft, color: 0xb8922a, roughness: 0.95, transparent: true, opacity: 0.9, depthWrite: false });
    const bitterRim = new THREE.MeshStandardMaterial({ color: 0x6b5410, roughness: 1, transparent: true, opacity: 0.45, depthWrite: false });
    const rim = new THREE.RingGeometry(DROP.puddle - 2.5, DROP.puddle + 0.5, 32);
    return { dome, puddle, splat, rim, syrup, stale, sugarPuddle, bitter, bitterPuddle, bitterRim };
  }

  makeDrop(d) {
    const k = this.dropKit, g = new THREE.Group(), spoiled = d.sugar && d.bitter;
    if (d.sugar) {
      const dome = new THREE.Mesh(k.dome, spoiled ? k.stale : k.syrup); dome.scale.z = 0.55; dome.castShadow = true; g.add(dome);
      const pud = new THREE.Mesh(k.puddle, k.sugarPuddle); pud.position.z = 0.3; g.add(pud);
      if (spoiled) { const sp = new THREE.Mesh(k.splat, k.bitter); sp.scale.z = 0.35; sp.position.set(3, -2, DROP.dome * 0.5); g.add(sp); }
      g.userData.dome = dome;
    } else {
      const pud = new THREE.Mesh(k.puddle, k.bitterPuddle); pud.position.z = 0.3; g.add(pud);
      const rim = new THREE.Mesh(k.rim, k.bitterRim); rim.position.z = 0.4; rim.scale.setScalar(0.8); g.add(rim);
      const blob = new THREE.Mesh(k.dome, k.bitter); blob.scale.set(0.6, 0.6, 0.2); blob.castShadow = true; g.add(blob);
    }
    g.position.set(d.x, d.y, 0); g.scale.setScalar(0.001); this.scene.add(g);
    return { g, age: 0, gone: -1, eat: 0 };
  }

  async load(kind) {
    const cfg = MODELS[kind]; let gltf;
    try { gltf = await new GLTFLoader().loadAsync(cfg.url); }
    catch (e) { console.warn("3D", kind, "off: could not load", cfg.url, e); return; }
    // Clips: strip the prefix, drop the ".001" duplicates and "Take 001", and shift each one so it
    // starts at t = 0 (the actions in the .blend do not all start on frame 1). The loader shares one
    // time array between all tracks of a clip, so copy before shifting.
    const clips = {};
    for (const clip of gltf.animations) {
      const name = clip.name.replace(cfg.prefix, "");
      if (/\.\d+$/.test(name) || /^Take/.test(name) || clips[name]) continue;
      const start = Math.min(...clip.tracks.map((t) => t.times[0]));
      for (const t of clip.tracks) { t.times = t.times.slice(); t.shift(-start); }
      clip.resetDuration(); clips[name] = clip;
    }
    // Fit: measure the bind-pose footprint (x, z) and scale its longest side to `span`, feet on the floor.
    const box = new THREE.Box3().setFromObject(gltf.scene), size = new THREE.Vector3(); box.getSize(size);
    const fit = { scale: cfg.span / Math.max(size.x, size.z), cx: (box.min.x + box.max.x) / 2, cz: (box.min.z + box.max.z) / 2, y0: box.min.y };
    const walkScale = (pxPerS) => Math.min(4, Math.max(0, pxPerS * clips.Walk.duration / cfg.stride));
    this.models[kind] = { template: gltf.scene, clips, fit, walkScale };
    this.flag();
    console.log(`3D ${kind} ready:`, Object.keys(clips).join(", "), "footprint", size.x.toFixed(1), "x", size.z.toFixed(1), "height", size.y.toFixed(1));
  }

  make(kind) {
    const { template, clips, fit } = this.models[kind];
    const model = cloneSkinned(template), mats = [];
    model.traverse((o) => { if (o.isMesh) { o.material = o.material.clone(); o.frustumCulled = false; o.castShadow = true; mats.push(o.material); } });
    model.position.set(-fit.cx, -fit.y0, -fit.cz);
    const inner = new THREE.Group(); inner.rotation.x = Math.PI / 2; inner.scale.setScalar(fit.scale); inner.add(model);   // Y-up -> Z-up
    const mid = new THREE.Group(); mid.rotation.z = Math.PI / 2; mid.add(inner);                                            // face +X at heading 0
    const root = new THREE.Group(); root.add(mid); this.scene.add(root);
    const mixer = new THREE.AnimationMixer(model), actions = {};
    for (const [name, clip] of Object.entries(clips)) actions[name] = mixer.clipAction(clip);
    const c = { kind, root, mixer, actions, mats, current: null, heading: 0, x: null, y: null, speed: 0, state: "", tone: "", oneShot: null, dead: false, jumped: false, front: [] };
    // the front of the head: the antenna roots if the rig has them, else the head bone (the 2D proboscis starts there)
    model.traverse((o) => { if (o.isBone && /Antena_[LR]1$/.test(o.name)) c.front.push(o); });
    if (!c.front.length) model.traverse((o) => { if (o.isBone && /Head$/.test(o.name) && !c.front.length) c.front.push(o); });
    mixer.addEventListener("finished", () => { if (!c.dead) { c.oneShot = null; c.state = ""; } });   // re-pick the state clip next sync
    return c;
  }

  play(c, name, timeScale = 1) {
    const next = c.actions[name]; if (!next) return;
    if (c.current === next) { next.timeScale = timeScale; return; }
    next.reset().setEffectiveTimeScale(timeScale).setEffectiveWeight(1).play();
    if (c.current) next.crossFadeFrom(c.current, FADE_S, false);   // no warp: it would reset timeScale to 1 after the fade
    c.current = next;
  }

  playOnce(c, name, hold = false) {
    const a = c.actions[name]; if (!a) return;
    a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = hold;
    if (c.current === a) c.current = null;   // restart even if it is the current one
    this.play(c, name, 1); c.oneShot = name;
  }

  // The fly got caught: the spider nearest to it strikes.
  pounce(fly) {
    if (!this.spidersReady || !this.spiders.length) return;
    let best = null, bd = Infinity;
    for (const sp of this.spiders) { const d = Math.hypot(sp.x - fly.x, sp.y - fly.y); if (d < bd) { bd = d; best = sp; } }
    this.playOnce(best, "Attack_1");
  }

  // World position (arena px) of the front of the fly's head, from the posed skeleton; null if unknown.
  flyHead() {
    const c = this.fly; if (!this.flyReady || !c || !c.front.length) return null;
    const v = new THREE.Vector3(), acc = new THREE.Vector3();
    for (const b of c.front) acc.add(b.getWorldPosition(v));
    acc.divideScalar(c.front.length); return { x: acc.x, y: acc.y };
  }

  tone(c, tone) {
    if (c.tone === tone) return; c.tone = tone;
    for (const m of c.mats) {
      if (tone === "hunt") { m.emissive.set(0xff1a1a); m.emissiveIntensity = 0.35; m.color.setScalar(1); }
      else if (tone === "rest") { m.emissive.set(0x000000); m.color.setScalar(0.55); }
      else { m.emissive.set(0x000000); m.color.setScalar(1); }
    }
  }

  // Called once per state message (20 Hz): positions, headings, clip from the state.
  sync(state) {
    const w = state.world, f = state.fly;
    if (this.dropsReady) {
      const seen = new Set();
      for (const d of w.drops) {
        const key = `${d.x},${d.y},${d.bitter ? 1 : 0}${d.sugar ? 1 : 0}`; seen.add(key);
        let dr = this.drops.get(key); if (!dr) { dr = this.makeDrop(d); this.drops.set(key, dr); }
        // the fly eats the drop it stands on: the dome shrinks with the meal
        dr.eat = w.eating > 0 && Math.hypot(f.x - d.x, f.y - d.y) < 45 ? w.eating : 0;
      }
      for (const [key, dr] of this.drops) if (!seen.has(key) && dr.gone < 0) dr.gone = 0;
    }
    if (this.spidersReady) {
      while (this.spiders.length < w.spiders.length) this.spiders.push(this.make("spider"));
      const ws = this.models.spider.walkScale;
      for (let i = 0; i < w.spiders.length; i++) {
        const s = w.spiders[i], sp = this.spiders[i];
        // heading comes from the sim (positions are rounded to whole px at 20 Hz: deriving it here wobbles)
        if (s.heading !== undefined) sp.heading = s.heading;
        else if (sp.ax === undefined) { sp.ax = s.x; sp.ay = s.y; }
        else if (Math.hypot(s.x - sp.ax, s.y - sp.ay) > 6) { sp.heading = Math.atan2(s.y - sp.ay, s.x - sp.ax); sp.ax = s.x; sp.ay = s.y; }   // older server: heading from the last 6 px of travel
        sp.x = s.x; sp.y = s.y;
        if (sp.oneShot) continue;                                                     // a strike plays out untouched
        const near = Math.hypot(f.x - s.x, f.y - s.y) < POUNCE_R;
        const key = s.state + (s.state === "hunt" && near ? "!" : "");
        if (key !== sp.state) {
          sp.state = key;
          if (s.state === "wait") this.play(sp, Math.random() < 0.35 ? "Idle_long" : "Idle", 1);
          else this.play(sp, "Walk", ws(s.state === "hunt" ? (near ? 250 : 70) : s.state === "return" ? 45 : 15));
        }
        this.tone(sp, s.state === "hunt" ? "hunt" : s.state === "return" ? "rest" : "");
      }
    }
    if (this.flyReady) {
      const c = this.fly || (this.fly = this.make("fly"));
      const moved = c.x === null ? 0 : Math.hypot(f.x - c.x, f.y - c.y);
      c.speed = moved > 100 ? 0 : c.speed + (moved / 0.05 - c.speed) * 0.3;               // px/s, smoothed; a respawn is a teleport, not a sprint
      c.x = f.x; c.y = f.y; c.heading = f.heading;
      const dead = w.fly_dead > 0 || !!state.fainted;
      if (dead !== c.dead) {
        c.dead = dead;
        if (dead) this.playOnce(c, "Death", true); else { c.oneShot = null; c.state = ""; }
      }
      this.tone(c, state.fainted ? "rest" : "");
      if (c.dead) { c.jumped = false; return; }
      if (f.jumped && !c.jumped) { c.jumped = true; this.playOnce(c, "Jump"); }
      else if (!f.jumped) c.jumped = false;
      if (c.oneShot) return;                                                          // a jump plays out untouched
      // walking: the legs follow the speed; a fly that stands still (feeding) keeps its legs still
      this.play(c, "Walk", this.models.fly.walkScale(c.speed < 3 ? 0 : c.speed)); c.state = "walk";
    }
  }

  // Called every frame with the 2D layer's world->screen transform (scale s, origin ox/oy in device px).
  render(dtMs, view, W, H) {
    if (!this.ok || !view) return;
    if (this.canvas.width !== W || this.canvas.height !== H || !this.view || this.view.W !== W || this.view.H !== H) { this.renderer.setSize(W, H, false); this.view = { W, H }; }
    const { s, ox, oy } = view, cam = this.camera;
    cam.left = -ox / s; cam.right = (W - ox) / s; cam.top = oy / s; cam.bottom = (oy - H) / s; cam.updateProjectionMatrix();
    if (!this.lit) { this.lit = true; const k = this.key; const mx = (cam.left + cam.right) / 2, my = (cam.top + cam.bottom) / 2; k.target.position.set(mx, my, 0); k.position.set(mx - 400, my + 500, 900); this.scene.add(k.target); k.shadow.camera.updateProjectionMatrix(); }
    const dt = dtMs / 1000;
    for (const [key, dr] of this.drops) {
      dr.age += dt; let sc;
      if (dr.gone >= 0) { dr.gone += dt; sc = Math.max(0, 1 - dr.gone / DROP.gone); if (dr.gone >= DROP.gone) { this.scene.remove(dr.g); this.drops.delete(key); continue; } }
      else { const t = Math.min(1, dr.age / DROP.land); sc = t < 0.7 ? 1.25 * t / 0.7 : 1.25 - 0.25 * (t - 0.7) / 0.3; }   // land with a little splash
      dr.g.scale.setScalar(Math.max(0.001, sc));
      if (dr.g.userData.dome) dr.g.userData.dome.scale.set(1 - 0.6 * dr.eat, 1 - 0.6 * dr.eat, 0.55 * (1 - 0.7 * dr.eat));
    }
    for (const c of this.fly ? [...this.spiders, this.fly] : this.spiders) {
      c.mixer.update(dt);
      // turn the short way round: the spider eases, the fly follows the brain's heading almost directly
      let d = c.heading - c.root.rotation.z; d = Math.atan2(Math.sin(d), Math.cos(d));
      c.root.rotation.z += d * Math.min(1, dt * (c.kind === "fly" ? 30 : 10));
      c.root.position.set(c.x ?? -1000, c.y ?? -1000, 0);
    }
    this.renderer.render(this.scene, cam);
  }
}
