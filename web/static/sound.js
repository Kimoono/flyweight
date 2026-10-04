// Sound on the beamer (the phones stay silent). Web Audio: every file is decoded once into a buffer,
// one-shots get a fresh source per play, loops keep one source and fade their gain in and out.
// Browsers keep audio suspended until someone clicks or presses a key on the page; `unlock()` runs on
// the first gesture and the header hint in index.html says so. Key M mutes. `window.sound` in the
// console tunes the mix at the venue: sound.mix.horn = 0.4 etc.
const FILES = {
  boing: "Boing.mp3", horn: "Danger_horn.mp3", flyWalk: "Fly_walk.mp3",
  nom: "Nom_nom.mp3", spiderWalk: "Spider_walk.mp3", scream: "Wilhelm_scream.mp3", disgust: "Disgust.mp3",
};
const TAKES = ["boing", "disgust"];   // files that hold several takes with silence between them
const BITTER_GRACE = 250; // ms off the drop before the disgust loop stops (the rim of a drop is not a clean edge)
const POUNCE_R = 130;     // must match sim/world.py: inside this the spider lunges (faster steps)
const FADE = 0.04;        // s, time constant of loop fades: no clicks, but still tight to the action

// Boing.mp3 and Disgust.mp3 hold several takes with silence between them. Find where each one starts: a run of
// sound (above peak - 40 dB, 10 ms windows, gaps up to 100 ms bridged) that gets loud (within 20 dB of
// the peak). Quieter runs are clicks or tails, not takes. A one-shot take plays up to the next start.
function variations(buf) {
  const a = buf.getChannelData(0), win = Math.round(buf.sampleRate * 0.01), n = Math.floor(a.length / win), db = new Float32Array(n);
  for (let i = 0; i < n; i++) { let s = 0; for (let j = i * win; j < (i + 1) * win; j++) s += a[j] * a[j]; db[i] = 10 * Math.log10(s / win + 1e-12); }
  const peak = Math.max(...db), runs = [];
  for (let i = 0; i < n; i++) {
    if (db[i] < peak - 40) continue;
    const last = runs[runs.length - 1];
    if (last && i - last.end <= 10) { last.end = i; last.max = Math.max(last.max, db[i]); }
    else runs.push({ start: i, end: i, max: db[i] });
  }
  const starts = runs.filter((r) => r.max >= peak - 20).map((r) => r.start * 0.01);
  return starts.map((s, k) => ({ at: s, len: (starts[k + 1] ?? buf.duration) - s }));
}

export class Sound {
  constructor() {
    this.mix = { boing: 0.9, horn: 0.55, flyWalk: 0.5, nom: 0.7, spiderWalk: 0.7, scream: 0.9, disgust: 0.9 };
    this.buffers = {}; this.loops = {}; this.takes = {}; this.muted = false;
    this.fly = { x: null, y: null, speed: 0, jumped: false, bitterAt: -1e9 };
    try { this.ctx = new AudioContext(); } catch (e) { console.warn("sound off: no Web Audio", e); return; }
    this.master = this.ctx.createGain(); this.master.connect(this.ctx.destination);
    this.ctx.onstatechange = () => this.onchange?.();
    this.ready = Promise.all(Object.entries(FILES).map(([k, f]) => this.load(k, "/static/audio/" + f)));
    for (const ev of ["pointerdown", "keydown"]) addEventListener(ev, () => this.unlock());
    addEventListener("keydown", (e) => { if (e.key === "m" || e.key === "M") this.setMuted(!this.muted); });
  }

  async load(key, url) {
    try {
      this.buffers[key] = await this.ctx.decodeAudioData(await (await fetch(url)).arrayBuffer());
      if (TAKES.includes(key)) { const t = this.takes[key] = variations(this.buffers[key]); t.last = -1; console.log(`sound: ${key} takes at`, t.map((v) => v.at.toFixed(2)).join(", "), "s"); }
    } catch (e) { console.warn("sound: could not load", url, e); }
  }

  get running() { return this.ctx?.state === "running"; }
  unlock() { if (this.ctx && !this.running) this.ctx.resume(); }
  setMuted(m) { this.muted = m; if (this.ctx) this.master.gain.setTargetAtTime(m ? 0 : 1, this.ctx.currentTime, FADE); this.onchange?.(); }

  // One-shot: the whole file, or a slice of it.
  shot(key, at = 0, len) {
    const buf = this.buffers[key]; if (!buf || !this.running) return;
    const src = this.ctx.createBufferSource(), g = this.ctx.createGain();
    src.buffer = buf; g.gain.value = this.mix[key]; src.connect(g).connect(this.master);
    src.start(0, at, len);
  }
  // A random take, never the same one twice in a row; null if the file has no takes.
  pick(key) {
    const t = this.takes[key]; if (!t?.length) return null;
    let k = Math.floor(Math.random() * t.length); if (k === t.last && t.length > 1) k = (k + 1) % t.length;
    t.last = k; return t[k];
  }
  take(key) { const v = this.pick(key); v ? this.shot(key, v.at, v.len) : this.shot(key); }

  // Loop: on/off with a fade, optional playback rate. `from(duration)` gives the offset each run starts
  // at; the loop still wraps over the whole file.
  loop(key, on, rate = 1, from = () => 0) {
    const buf = this.buffers[key]; if (!buf || !this.running) return;
    let l = this.loops[key];
    if (on && !l) {
      const src = this.ctx.createBufferSource(), g = this.ctx.createGain();
      src.buffer = buf; src.loop = true; g.gain.value = 0; src.connect(g).connect(this.master);
      src.start(0, from(buf.duration));
      g.gain.setTargetAtTime(this.mix[key], this.ctx.currentTime, FADE);
      l = this.loops[key] = { src, g };
    } else if (!on && l) {
      const t = this.ctx.currentTime; l.g.gain.setTargetAtTime(0, t, FADE); l.src.stop(t + 6 * FADE);
      delete this.loops[key]; return;
    }
    if (l) l.src.playbackRate.setTargetAtTime(rate, this.ctx.currentTime, 0.1);
  }

  // Called once per state message (20 Hz) with the events that fired this tick.
  sync(state, events) {
    if (!this.ctx) return;
    const w = state.world, f = state.fly, fly = this.fly;
    const moved = fly.x === null ? 0 : Math.hypot(f.x - fly.x, f.y - fly.y);
    fly.speed = moved > 100 ? fly.speed : fly.speed + (moved / 0.05 - fly.speed) * 0.3;   // px/s, smoothed; jumps and respawns are teleports
    fly.x = f.x; fly.y = f.y;
    const dead = w.fly_dead || !!state.fainted;
    if (events.includes("SPIDER!")) this.shot("horn");
    if (events.includes("CAUGHT")) this.shot("scream");
    if (f.jumped && !fly.jumped && !dead) this.take("boing");
    fly.jumped = f.jumped;
    // disgust: loops while the fly stands on a bitter drop (a decoy or a spoiled sugar drop), starting at a
    // random take and running on through the file (wrapping to the start); it stops 250 ms after it steps off
    const now = performance.now();
    if (!dead && (state.senses || []).includes("bitter")) fly.bitterAt = now;
    this.loop("disgust", !dead && now - fly.bitterAt < BITTER_GRACE, 1, () => this.pick("disgust")?.at ?? 0);
    // legs: only while it actually moves (on at 8 px/s, off below 4 so it does not stutter); the steps
    // speed up with the fly (39 px/s = a drop in view, 70 = max)
    const walking = !dead && !f.feeding && fly.speed > (this.loops.flyWalk ? 4 : 8);
    this.loop("flyWalk", walking, Math.min(1.4, Math.max(0.8, fly.speed / 45)));
    // nom: proboscis out on good sugar (the eating timer holds while it pauses, so check feeding too)
    this.loop("nom", !dead && f.feeding && w.eating > 0, 1, (d) => Math.random() * d);
    const hunter = w.spiders.find((s) => s.state === "hunt");
    this.loop("spiderWalk", !!hunter, hunter && Math.hypot(f.x - hunter.x, f.y - hunter.y) < POUNCE_R ? 1.5 : 1);
  }
}
