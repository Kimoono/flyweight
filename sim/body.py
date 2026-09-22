"""Minimal 2D fly body: turns brain output rates into movement. This is the ONLY
hand-written behaviour; everything upstream of these descending neurons is connectome.
Tune the constants here for game feel."""
import math, random
from dataclasses import dataclass

TURN_GAIN = 0.035      # rad/s per Hz of left-right steering difference
RIGHT_TURN_GAIN = 2.2  # FUDGE (findings, trap 2): the right eye -> DNa02 pathway of this one animal
                       # is weaker (62 Hz vs 138 Hz for the same stimulus). Scaled up so the two
                       # eyes pull equally hard; without it the fly always veers left.
# --- Forward speed comes from the brain, not from us (22 Sep 2026).
# It used to be BASE_SPEED = 40 px/s of programmed amble, so most of the fly's movement was
# hand-written. It is now the rate of DNg100, the walking command neuron (see build_neurons.py).
# If the brain sends no command, the fly does not move. Measured, 400 ms per stimulus:
#   nothing 0 Hz | drop in view 39 | standing on sugar 0 | spider looming 26 | spider moving 54
#   | bitter 0.   So: it walks because it saw something, stops to eat, and bitter stops it dead.
WALK_GAIN = 1.0        # px/s per Hz of DNg100. A drop in view gives ~39 px/s, which is where the
                       # old programmed amble was, so the game keeps its feel.
SPEED_MAX = 70.0       # px/s cap. FUDGE for the chase: the spider charges at 70 px/s, and a fly
                       # that outruns the charge ends the game's only real threat (measured at
                       # 110 px/s: never caught in 40 s, and it stopped eating too).
SPEED_TAU = 0.25       # s: smoothing, like TURN_TAU. A population rate read over one 50 ms tick
                       # is noisy, and the legs have inertia.
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
    speed: float = 0.0      # px/s, smoothed; comes from the walking command neuron

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
        # Forward speed: what the walking command neuron is telling the legs to do.
        want = 0.0 if self.feeding else min(SPEED_MAX, WALK_GAIN * mean("walk"))
        self.speed += (want - self.speed) * min(1.0, dt_s / SPEED_TAU)
        self.x += self.speed * math.cos(self.heading) * dt_s
        self.y += self.speed * math.sin(self.heading) * dt_s
