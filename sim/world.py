"""The arena: sugar drops, the spider, walls, score. Game rules only; no fly behaviour here.
The fly's decisions come from brain.py via body.py; what the fly senses comes from senses.py.

Duel rules: the arena has a LEFT and a RIGHT half. A drop eaten on a half scores for that
half. Drops can be spoiled with bitter (the fly walks up, tastes, refuses, leaves)."""
import math, random
from dataclasses import dataclass, field

# 1200x675 since 22 Sep 2026, not 1600x900. The fly walks at ~39 px/s and weaves, so its net
# progress is 10-20 px/s: on the old board most of the arena was unreachable inside a 90 s heat,
# sugar placed deep in a half was worthless and the outer quarters went unused. Shrinking does not
# make the fly explore (coverage 18% -> 22%), it brings the action to it: meals per 60 s went 5 ->
# 7-8 and catches 0-2 -> 3-4. 1000x560 is too small - the fly is inside a spider's sight ring 91%
# of the time. Both web pages scale to whatever this says (the server sends it).
W, H = 1200.0, 675.0
DROP_R = 28.0          # px: standing on a drop
EAT_S = 1.5            # s of feeding to finish a drop
N_DROPS = 0            # drops the world spawns by itself (0 in a duel: players provide them)
MAX_DROPS = 10
SPOILED_S = 10.0       # a spoiled drop disappears after this long
BITTER_R = 70.0        # px: a bitter tap this close to a sugar drop spoils it, else it makes a bitter puddle

# The spider is an ambush predator with a lair. It waits at home, charges when the fly comes
# inside its sight, gives up when the fly gets away, and walks back home. There is one per half
# (Kim, 22 Sep 2026), so the halves are the dangerous ground and the centre line is the corridor:
# a charge pushes the fly into the other half or against a wall, and both players have a predator
# to bait it toward. N_SPIDERS = 1 puts a single lair back on the centre line.
N_SPIDERS = 2          # one lair per half
SIGHT_R = 260.0        # px: the fly inside this = the spider charges
CHARGE_SPEED = 70.0    # px/s: faster than a walking fly (40 px/s); only a jump gets away
POUNCE_R = 130.0       # px: inside this the spider lunges
POUNCE_SPEED = 250.0   # px/s during the lunge: a race against the fly's escape reflex
RETURN_SPEED = 45.0    # px/s walking home
GIVE_UP_R = 420.0      # px: fly this far away while hunting = the spider gives up
# How far a spider strays from its lair. Requirement (Kim, 22 Sep 2026): NO point of the arena may
# be permanently safe, i.e. every point must fall inside some spider's sight ring at some moment.
# Coverage reach = WANDER_R + SIGHT_R, and the hardest points are the middle of the top and bottom
# edges, (W/2, 0) and (W/2, H), which lie hypot(3W/8, H/2) from either lair. So the radius is
# derived, not tuned: change the arena or the sight radius and coverage still holds. Note the
# instantaneous danger is SIGHT_R while the reach is the sum, so to make the game less lethal
# without leaving safe pockets, lower SIGHT_R and this grows to compensate.
COVER_MARGIN = 15.0    # px of slack on the worst-covered point
WANDER_R = math.hypot(3 * W / 8, H / 2) - SIGHT_R + COVER_MARGIN
WANDER_SPEED = 15.0    # px/s: strolling, not hunting
PAUSE_S = (1.0, 3.0)   # s: it sits still between strolls (it is an ambush predator)
HUNT_MAX_S = 6.0       # s: a charge never lasts longer than this
QUIET_S = 3.0          # s after ANY hunt ends before another may start. With the board fully
                       # covered, a fly escaping one ring is usually already inside the other, so
                       # without this the two spiders hand it back and forth and the fly is pinned
                       # (Kim, playing 22 Sep 2026). Only one spider may hunt at a time, and after a
                       # hunt ends nobody charges for QUIET_S: pressure comes in waves.
CATCH_R = 30.0
FLY_DEAD_S = 1.5       # the fly lies still after a catch, then respawns


@dataclass
class Spider:
    x: float
    y: float
    home_x: float
    home_y: float
    state: str = "wander"      # wander (strolling near the lair) | wait (sitting still) | hunt | return
    timer: float = 0.0
    pause: float = 0.0         # how long this sit-still lasts
    tx: float = 0.0            # where it is strolling to
    ty: float = 0.0

    @property
    def closing(self):
        return self.state == "hunt"

    def move_toward(self, x, y, speed, dt):
        d = math.hypot(x - self.x, y - self.y)
        if d < 1e-6:
            return d
        step = min(speed * dt, d)
        self.x += (x - self.x) / d * step; self.y += (y - self.y) / d * step
        return d


@dataclass
class World:
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    drops: list = field(default_factory=list)   # dicts: x, y, bitter (bool), sugar (bool), age
    spiders: list = field(default_factory=list)   # one per half; set_lairs() fills it
    fly_dead: float = 0.0
    eating: float = 0.0
    hunt_quiet: float = 0.0         # s left of the no-charging window
    score: dict = field(default_factory=lambda: {"left": 0, "right": 0})
    caught: int = 0
    events: list = field(default_factory=list)

    def __post_init__(self):
        if not self.spiders:
            self.set_lairs()
        while len(self.drops) < N_DROPS:
            self.add_drop(self.rng.uniform(100, W - 100), self.rng.uniform(100, H - 100))

    # ---- drops
    def add_drop(self, x, y, bitter=False):
        """A sugar drop, or (bitter=True) a bitter tap: spoils a sugar drop within BITTER_R,
        otherwise leaves a bitter puddle. Returns what happened."""
        x, y = min(max(x, 20), W - 20), min(max(y, 20), H - 20)
        if bitter:
            near = [d for d in self.drops if d["sugar"] and not d["bitter"] and math.hypot(d["x"] - x, d["y"] - y) < BITTER_R]
            if near:
                d = min(near, key=lambda d: math.hypot(d["x"] - x, d["y"] - y)); d["bitter"] = True; d["age"] = 0.0
                return "spoiled"
        if len(self.drops) >= MAX_DROPS:
            self.drops.pop(0)
        self.drops.append({"x": x, "y": y, "bitter": bitter, "sugar": not bitter, "age": 0.0})
        return "bitter" if bitter else "sugar"

    def drop_xy(self):
        return [(d["x"], d["y"]) for d in self.drops]

    def on_drop(self, fly):
        for d in self.drops:
            if math.hypot(d["x"] - fly.x, d["y"] - fly.y) < DROP_R:
                return d
        return None

    @staticmethod
    def half(x):
        return "left" if x < W / 2 else "right"

    # ---- spider
    @property
    def spider_closing(self):
        return any(sp.closing for sp in self.spiders)

    def hazards(self, fly):
        return [(sp.x, sp.y, sp.closing) for sp in self.spiders]

    def wander_target(self, sp):
        """A new spot to stroll to: uniform inside the WANDER_R disc around its lair, clamped to
        the arena."""
        a, r = self.rng.uniform(0, 2 * math.pi), WANDER_R * math.sqrt(self.rng.random())
        sp.tx = min(max(sp.home_x + r * math.cos(a), 20), W - 20)
        sp.ty = min(max(sp.home_y + r * math.sin(a), 20), H - 20)

    def set_lairs(self):
        """On the grid (Kim, 22 Sep 2026): vertically centred, an eighth of the width in from each
        side wall. Deterministic, so both halves are mirror images and players can learn the map.
        The outer quarters are then the dangerous ground and the middle ~680 px is the safe
        corridor, which is also the contested one. With N_SPIDERS = 1 the single lair goes back on
        the centre line at a random height."""
        self.spiders = []
        if N_SPIDERS == 1:
            y = self.rng.choice([H * 0.3, H * 0.7])
            sp = Spider(W / 2, y, W / 2, y)
            self.wander_target(sp)
            self.spiders = [sp]
            return
        for i in range(N_SPIDERS):
            x = W / 8 if i % 2 == 0 else W * 7 / 8
            sp = Spider(x, H / 2, x, H / 2)
            self.wander_target(sp)
            self.spiders.append(sp)

    def reset_round(self, fly):
        """New heat: clear drops, fly to the centre, spider to a fresh lair on the centre line."""
        self.drops = []; self.eating = 0.0; self.fly_dead = 0.0; self.events = []; self.hunt_quiet = 0.0
        self.score = {"left": 0, "right": 0}; self.caught = 0
        fly.x, fly.y, fly.heading, fly.turn_rate, fly.cooldown = W / 2, H / 2, self.rng.uniform(-math.pi, math.pi), 0.0, 0.0
        self.set_lairs()

    # ---- tick
    def update(self, fly, dt, t):
        """Call after fly.update(). Applies walls, eating, the spider, death and respawn."""
        if fly.x < 0 or fly.x > W:
            fly.heading = math.pi - fly.heading; fly.x = min(max(fly.x, 0), W)
        if fly.y < 0 or fly.y > H:
            fly.heading = -fly.heading; fly.y = min(max(fly.y, 0), H)
        for d in self.drops:
            d["age"] += dt
        self.drops = [d for d in self.drops if not (d["bitter"] and d["age"] > SPOILED_S)]
        if self.fly_dead > 0:
            self.fly_dead -= dt
            if self.fly_dead <= 0:                       # respawn in the middle: 430+ px from every lair
                fly.x, fly.y = W / 2, H / 2
                fly.heading = self.rng.uniform(-math.pi, math.pi); fly.turn_rate = 0.0; fly.cooldown = 0.0
            return
        # eating (only unspoiled sugar counts; the brain refuses spoiled drops by itself)
        d = self.on_drop(fly)
        if d is None or not d["sugar"] or d["bitter"]:
            self.eating = 0.0
        elif fly.feeding:
            self.eating += dt
            if self.eating >= EAT_S:
                self.drops.remove(d); self.score[self.half(d["x"])] += 1; self.eating = 0.0
                self.events.append((t, "EAT"))
                if len([x for x in self.drops if x["sugar"]]) < N_DROPS:
                    self.add_drop(self.rng.uniform(100, W - 100), self.rng.uniform(100, H - 100))
        # spiders: one hunter at a time, a quiet window between hunts, and a catch ends the tick
        self.hunt_quiet = max(0.0, self.hunt_quiet - dt)
        busy = any(sp.state == "hunt" for sp in self.spiders)
        for sp in self.spiders:
            dist = math.hypot(fly.x - sp.x, fly.y - sp.y)
            sp.timer += dt
            if sp.state in ("wander", "wait"):
                if dist < SIGHT_R and not busy and self.hunt_quiet <= 0:
                    sp.state, sp.timer, busy = "hunt", 0.0, True; self.events.append((t, "SPIDER!"))
                elif sp.state == "wait":
                    if sp.timer > sp.pause:
                        self.wander_target(sp); sp.state, sp.timer = "wander", 0.0
                elif sp.move_toward(sp.tx, sp.ty, WANDER_SPEED, dt) < 5:
                    sp.state, sp.timer, sp.pause = "wait", 0.0, self.rng.uniform(*PAUSE_S)
            elif sp.state == "hunt":
                dist = sp.move_toward(fly.x, fly.y, POUNCE_SPEED if dist < POUNCE_R else CHARGE_SPEED, dt)
                if dist < CATCH_R:
                    self.caught += 1; self.events.append((t, "CAUGHT"))
                    self.score["right" if self.half(fly.x) == "left" else "left"] += 1   # caught on your half = their point
                    self.fly_dead = FLY_DEAD_S; self.eating = 0.0
                    sp.state, sp.timer = "return", 0.0
                    self.hunt_quiet = QUIET_S
                    break
                elif dist > GIVE_UP_R or sp.timer > HUNT_MAX_S:
                    sp.state, sp.timer = "return", 0.0
                    self.hunt_quiet = QUIET_S
            elif sp.state == "return":
                if sp.move_toward(sp.home_x, sp.home_y, RETURN_SPEED, dt) < 3:
                    self.wander_target(sp); sp.state, sp.timer = "wander", 0.0
