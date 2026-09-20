"""Sensory encoding: what the WORLD does to the fly's sensory neurons. The only place where
the world is turned into input rates (Hz per sense group and side). Like body.py on the
motor side, this is hand-written; everything between the two is connectome.

Rules (deliberately simple, tunable):
- eye_target: an object (sugar drop) in front of the fly within SEE_RANGE excites the eye on
  the side it is on, graded by how far off-centre it is (an object nearly straight ahead
  drives the eye softly, one at 45 degrees or more at full rate). Dead ahead (within DEADBAND)
  excites neither. The graded drive is what stops the fly overshooting and flickering left-right.
- shadow: a hazard (the spider) within LOOM_RANGE that is itself moving toward the fly looms
  on its side. A fly walking toward a resting spider is not looming.
- sugar: the fly is standing on a drop. Capped at SUGAR_HZ (findings: sustained input).
"""
import math

SEE_RANGE = 700.0      # px: how far the eyes notice an object
FOV = math.radians(150)  # half-angle: only what is right behind the fly is unseen
DEADBAND = 0.08        # rad: object straight ahead excites neither eye
EYE_FULL = 0.8         # rad: bearing at which the eye is driven at full rate
EYE_MIN = 0.25         # fraction of EYE_HZ at the edge of the dead zone
EYE_HZ = 150.0
LOOM_RANGE = 220.0     # px: a hazard closer than this, and approaching, is a looming shadow
SHADOW_HZ = 150.0
SUGAR_HZ = 40.0        # findings "Sustained input": >= 60 Hz held for seconds -> seizure
BITTER_HZ = 60.0


def bearing(fly, x, y):
    """Angle of (x, y) relative to the fly's heading: + = left, - = right, in (-pi, pi]."""
    return (math.atan2(y - fly.y, x - fly.x) - fly.heading + math.pi) % (2 * math.pi) - math.pi


def encode(fly, drops, hazards, on_drop, on_bitter=False):
    """drops: [(x, y)], hazards: [(x, y, closing)] with closing = True if getting nearer.
    Returns rates {"eye_target": {"left": Hz, ...}, ...} and a plain-language list of what
    the fly senses, for the beamer."""
    rates, seen = {}, []
    # eyes: nearest visible drop on each side
    for x, y in drops:
        d = math.hypot(x - fly.x, y - fly.y)
        if d > SEE_RANGE:
            continue
        b = bearing(fly, x, y)
        if abs(b) > FOV or abs(b) < DEADBAND:
            continue
        side = "left" if b > 0 else "right"
        hz = EYE_HZ * min(1.0, EYE_MIN + (1 - EYE_MIN) * (abs(b) - DEADBAND) / (EYE_FULL - DEADBAND))
        rates.setdefault("eye_target", {})[side] = max(rates.get("eye_target", {}).get(side, 0), hz)
        if f"drop {side}" not in seen:
            seen.append(f"drop {side}")
    for x, y, closing in hazards:
        d = math.hypot(x - fly.x, y - fly.y)
        if d < LOOM_RANGE and closing:
            side = "left" if bearing(fly, x, y) > 0 else "right"
            rates.setdefault("shadow", {})[side] = SHADOW_HZ
            seen.append(f"shadow {side}")
    if on_drop:
        rates["sugar"] = {"left": SUGAR_HZ, "right": SUGAR_HZ}; seen.append("sugar")
    if on_bitter:
        rates["bitter"] = {"left": BITTER_HZ, "right": BITTER_HZ}; seen.append("bitter")
    return rates, seen
