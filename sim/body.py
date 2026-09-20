"""Minimal 2D fly body: turns brain output rates into movement. This is the ONLY
hand-written behaviour; everything upstream of these descending neurons is connectome.
Tune the constants here for game feel."""
import math, random
from dataclasses import dataclass

TURN_GAIN = 0.035      # rad/s per Hz of left-right steering difference
RIGHT_TURN_GAIN = 2.2  # FUDGE (findings, trap 2): the right eye -> DNa02 pathway of this one animal
                       # is weaker (62 Hz vs 138 Hz for the same stimulus). Scaled up so the two
                       # eyes pull equally hard; without it the fly always veers left.
BASE_SPEED = 40.0      # px/s, fly always ambles forward
WALK_GAIN = 1.0        # px/s per Hz of DNp09
ESCAPE_HZ = 60.0       # giant fiber rate that triggers a jump
JUMP_DIST = 180.0      # px
JUMP_COOLDOWN = 1.5    # s
JUMP_AWAY = math.radians(70)   # takeoff angle away from the threatened side
JUMP_SCATTER = math.radians(30)  # +- random scatter on the takeoff angle (real escapes vary)
FEED_HZ = 30.0         # MN9 rate that counts as "proboscis out"
TURN_TAU = 0.4         # s: FUDGE, turning inertia. The steering neurons flip several times a
                       # second when two objects pull opposite ways; the body smooths that so the
                       # fly does not jitter. The brain's indecision stays visible in the labels.


@dataclass
class Fly:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0   # radians, 0 = +x, counter-clockwise positive (left turn = +)
    cooldown: float = 0.0
    feeding: bool = False
    jumped: bool = False
    turn_rate: float = 0.0  # rad/s, smoothed

    def update(self, out: dict, dt_s: float):
        mean = lambda k: (out[k]["left"] + out[k]["right"]) / 2
        steer = (out["turn"]["left"] - RIGHT_TURN_GAIN * out["turn"]["right"]) + 0.5 * (out["turn_aux"]["left"] - out["turn_aux"]["right"])
        self.turn_rate += (TURN_GAIN * steer - self.turn_rate) * min(1.0, dt_s / TURN_TAU)
        self.heading += self.turn_rate * dt_s
        self.feeding = mean("feed") > FEED_HZ
        self.cooldown = max(0.0, self.cooldown - dt_s)
        self.jumped = False
        if mean("escape") > ESCAPE_HZ and self.cooldown == 0:
            # Takeoff direction. The brain says which side the threat is on (the escape
            # descending neurons fire much more on the threatened side); the legs push off away
            # from it. In a real fly that leg computation lives in the ventral nerve cord, which
            # is not part of the simulated brain, so it is hand-written here.
            side = (out["escape"]["left"] + out["escape_aux"]["left"]) - (out["escape"]["right"] + out["escape_aux"]["right"])
            away = -JUMP_AWAY if side > 20 else JUMP_AWAY if side < -20 else 0.0   # threat left -> jump right
            self.heading += away + random.uniform(-JUMP_SCATTER, JUMP_SCATTER)
            self.turn_rate = 0.0
            self.x += JUMP_DIST * math.cos(self.heading); self.y += JUMP_DIST * math.sin(self.heading)
            self.cooldown = JUMP_COOLDOWN; self.jumped = True
        speed = 0.0 if self.feeding else BASE_SPEED + WALK_GAIN * mean("walk")
        self.x += speed * math.cos(self.heading) * dt_s
        self.y += speed * math.sin(self.heading) * dt_s
