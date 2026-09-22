"""Sensory encoding: what the WORLD does to the fly's sensory neurons. The only place where
the world is turned into input rates (Hz per sense group and side). Like body.py on the
motor side, this is hand-written; everything between the two is connectome.

Rules (deliberately simple, tunable):
- eye_target: the fly attends to ONE drop at a time (see Eyes below) and that drop drives the
  eye on the side it is on, at full rate, always. No grading and no dead zone straight ahead:
  both of those made the eye go quiet, and a quiet eye means no walking command, so the fly
  stopped dead the moment it lined up on a drop (findings, "Brain-driven movement"). Steering
  therefore overshoots and the fly weaves its way to a drop - that weave is the brain's own
  indecision, not something written here.
- motion: something out there MOVING, seen by this eye (LC9), graded by how fast it slips
  across the retina. Self-motion is discounted, so in the arena this means the spider. It is the
  only thing that drives DNp09 (walk_aux). It turned out to be a minor input: with self-motion
  discounted it fires in 5-8% of ticks. What actually commands walking is DNg100, and a drop in
  view drives that on its own - see body.py and findings "Does the fly walk?".
- shadow: a hazard (the spider) that is itself moving toward the fly looms on its side, and
  the drive GROWS as it gets closer (a looming object grows on the eye; the escape fires when
  the drive crosses the giant fibre's threshold, so a fast charge is a race). A fly walking
  toward a resting spider is not looming.
- sugar: the fly is standing on a drop. Capped at SUGAR_HZ (findings: sustained input).
"""
import math

SEE_RANGE = 700.0      # px: how far the eyes notice an object
FOV = math.radians(150)  # half-angle: only what is right behind the fly is unseen
EYE_HZ = 150.0         # full rate, and the only rate: DNg100 (the walking command) needs about
                       # 60 Hz of eye input before it fires at all, and our old graded drive of
                       # 37-80 Hz sat under that knee. Measured: eye 40 Hz -> DNg100 0, 60 -> 10,
                       # 150 -> 39.
STICK = 1.5            # keep the current target until another is this many times closer
MEMORY_S = 1.5         # s: keep chasing a target after losing sight of it (it is behind the fly)
MOTION_HZ = 100.0      # cap; sustained motion input was runaway-tested at this rate
MOTION_MIN = 0.1       # rad/s of slip across the eye below which nothing is called movement
MOTION_FULL = 0.6      # rad/s of slip that drives the eye at MOTION_HZ (the spider charging at
                       # 70 px/s, 120 px away, slips at about this rate)
LOOM_RANGE = 240.0     # px: an approaching hazard starts to loom here (weakly)
LOOM_NEAR = 70.0       # px: full-rate looming from here inwards
SHADOW_HZ = 150.0
SUGAR_HZ = 40.0        # findings "Sustained input": >= 60 Hz held for seconds -> seizure
BITTER_HZ = 60.0


def bearing(fly, x, y):
    """Angle of (x, y) relative to the fly's heading: + = left, - = right, in (-pi, pi]."""
    return (math.atan2(y - fly.y, x - fly.x) - fly.heading + math.pi) % (2 * math.pi) - math.pi


class Eyes:
    """What the fly is looking at. Holds the current target between ticks; call encode() once
    per tick.

    FUDGE, like RIGHT_TURN_GAIN in body.py, and for the same kind of reason. Feeding every
    visible drop to the eyes drives both sides at once, and this brain has no winner-take-all
    to settle it: the steering difference flips sign several times a second and the fly circles
    on the spot instead of going anywhere. Measured with four drops around the fly (findings,
    "Circling"): both eyes driven 77% of ticks, 67 sign flips in 15 s, never reaches a drop.
    Attending to one drop at a time - the nearest, kept until it is gone or another gets much
    closer - fixed that.

    So: the brain still does the steering and now the walking too; this class only decides which
    drop the fly looks at. Selecting one target is a game fudge, not a claim about real flies.
    """

    def __init__(self):
        self.target = None      # (x, y) of the drop being chased, or None
        self.lost = 0.0         # s since it was last actually visible
        self.prev = {}          # object -> its (x, y) last tick, for the motion sense

    def _pick(self, fly, drops, dt):
        """The drop to chase this tick, as (x, y, distance, bearing), or None."""
        vis = []
        for x, y in drops:
            d = math.hypot(x - fly.x, y - fly.y)
            b = bearing(fly, x, y)
            if d <= SEE_RANGE and abs(b) <= FOV:
                vis.append((x, y, d, b))
        if vis:
            near = min(vis, key=lambda v: v[2])
            held = None
            if self.target:   # is the drop we were chasing still one of the visible ones?
                held = next((v for v in vis if math.hypot(v[0] - self.target[0], v[1] - self.target[1]) < 1.0), None)
            chosen = held if held and held[2] < STICK * near[2] else near
            self.target, self.lost = (chosen[0], chosen[1]), 0.0
            return chosen
        if self.target:
            # Out of sight, usually because the fly walked past it: anything behind the fly is
            # outside the field of view. Without this the fly sails on and never comes back.
            self.lost += dt
            if self.lost <= MEMORY_S:
                x, y = self.target
                return x, y, math.hypot(x - fly.x, y - fly.y), bearing(fly, x, y)
        self.target = None
        return None

    def _flow(self, fly, things, dt):
        """{side: Hz} for the motion sense: how fast things that move BY THEMSELVES slip across
        the eye. `things` is [(key, x, y)]. Only the object's own velocity counts; the scene
        dragging past while the fly turns and walks is discounted (real flies discount
        self-generated motion). Measured 22 Sep 2026: counting self-motion too put a loop in the
        game - movement -> WALK -> faster, turnier fly -> more movement - which ran the fly at
        110 px/s, past the spider's charge, and it stopped eating altogether. So in practice this
        fires for the spider, which is the only thing in the arena that moves."""
        now, out = {}, {}
        for key, x, y in things:
            now[key] = (x, y)
            d = math.hypot(x - fly.x, y - fly.y)
            b = bearing(fly, x, y)
            if d > SEE_RANGE or abs(b) > FOV or key not in self.prev:
                continue
            px, py = self.prev[key]
            vx, vy = (x - px) / max(dt, 1e-3), (y - py) / max(dt, 1e-3)      # the object's own velocity
            ux, uy = (x - fly.x) / d, (y - fly.y) / d
            slip = abs(-uy * vx + ux * vy) / d                               # rad/s across the eye
            if slip < MOTION_MIN:
                continue
            side = "left" if b > 0 else "right"
            hz = MOTION_HZ * min(1.0, (slip - MOTION_MIN) / (MOTION_FULL - MOTION_MIN))
            out[side] = max(out.get(side, 0.0), hz)
        self.prev = now
        return out

    def encode(self, fly, drops, hazards, on_drop, on_bitter=False, dt=0.05):
        """drops: [(x, y)], hazards: [(x, y, closing)] with closing = True if getting nearer.
        Returns rates {"eye_target": {"left": Hz, ...}, ...} and a plain-language list of what
        the fly senses, for the beamer."""
        rates, seen = {}, []
        chosen = self._pick(fly, drops, dt)
        if chosen:
            side = "left" if chosen[3] > 0 else "right"     # chosen = (x, y, distance, bearing)
            rates["eye_target"] = {side: EYE_HZ}
            seen.append(f"drop {side}")
        flow = self._flow(fly, [(f"d{x:.0f},{y:.0f}", x, y) for x, y in drops]
                               + [(f"h{i}", h[0], h[1]) for i, h in enumerate(hazards)], dt)
        if flow:
            rates["motion"] = flow
            seen.append("movement " + "+".join(sorted(flow)))
        for x, y, closing in hazards:
            d = math.hypot(x - fly.x, y - fly.y)
            if d < LOOM_RANGE and closing:
                side = "left" if bearing(fly, x, y) > 0 else "right"
                hz = SHADOW_HZ * min(1.0, max(0.0, (LOOM_RANGE - d) / (LOOM_RANGE - LOOM_NEAR)))
                if hz > 0:
                    rates.setdefault("shadow", {})[side] = max(rates.get("shadow", {}).get(side, 0), hz)
                    seen.append(f"shadow {side}")
        if on_drop:
            rates["sugar"] = {"left": SUGAR_HZ, "right": SUGAR_HZ}; seen.append("sugar")
        if on_bitter:
            rates["bitter"] = {"left": BITTER_HZ, "right": BITTER_HZ}; seen.append("bitter")
        return rates, seen
