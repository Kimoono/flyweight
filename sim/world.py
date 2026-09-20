"""The arena: sugar drops, the spider, walls, score. Game rules only; no fly behaviour here.
The fly's decisions come from brain.py via body.py; what the fly senses comes from senses.py.

Duel rules: the arena has a LEFT and a RIGHT half. A drop eaten on a half scores for that
half. Drops can be spoiled with bitter (the fly walks up, tastes, refuses, leaves)."""
import math, random
from dataclasses import dataclass, field

W, H = 1600.0, 900.0
DROP_R = 28.0          # px: standing on a drop
EAT_S = 1.5            # s of feeding to finish a drop
N_DROPS = 0            # drops the world spawns by itself (0 in a duel: players provide them)
MAX_DROPS = 10
SPOILED_S = 10.0       # a spoiled drop disappears after this long
BITTER_R = 70.0        # px: a bitter tap this close to a sugar drop spoils it, else it makes a bitter puddle

# The spider is an ambush predator with a lair. It waits at home, charges when the fly comes
# inside its sight, gives up when the fly gets away, and walks back home.
SIGHT_R = 260.0        # px: the fly inside this = the spider charges
CHARGE_SPEED = 70.0    # px/s: faster than a walking fly (40 px/s); only a jump gets away
POUNCE_R = 130.0       # px: inside this the spider lunges
POUNCE_SPEED = 250.0   # px/s during the lunge: a race against the fly's escape reflex
RETURN_SPEED = 45.0    # px/s walking home
GIVE_UP_R = 420.0      # px: fly this far away while hunting = the spider gives up
HUNT_MAX_S = 6.0       # s: a charge never lasts longer than this
CATCH_R = 30.0
FLY_DEAD_S = 1.5       # the fly lies still after a catch, then respawns


@dataclass
class World:
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    drops: list = field(default_factory=list)   # dicts: x, y, bitter (bool), sugar (bool), age
    spider: list = field(default_factory=lambda: [W / 2, H * 0.25])
    spider_home: list = field(default_factory=lambda: [W / 2, H * 0.25])
    spider_state: str = "wait"      # wait (at home) | hunt | return
    spider_timer: float = 0.0
    fly_dead: float = 0.0
    eating: float = 0.0
    score: dict = field(default_factory=lambda: {"left": 0, "right": 0})
    caught: int = 0
    events: list = field(default_factory=list)

    def __post_init__(self):
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
        return self.spider_state == "hunt"

    def hazards(self, fly):
        return [(self.spider[0], self.spider[1], self.spider_closing)]

    def set_lair(self, x, y):
        self.spider_home = [x, y]; self.spider = [x, y]; self.spider_state = "wait"; self.spider_timer = 0.0

    def _move_spider_toward(self, x, y, speed, dt):
        sx, sy = self.spider
        d = math.hypot(x - sx, y - sy)
        if d < 1e-6:
            return d
        step = min(speed * dt, d)
        self.spider[0] += (x - sx) / d * step; self.spider[1] += (y - sy) / d * step
        return d

    def reset_round(self, fly):
        """New heat: clear drops, fly to the centre, spider to a fresh lair on the centre line."""
        self.drops = []; self.eating = 0.0; self.fly_dead = 0.0; self.events = []
        self.score = {"left": 0, "right": 0}; self.caught = 0
        fly.x, fly.y, fly.heading, fly.turn_rate, fly.cooldown = W / 2, H / 2, self.rng.uniform(-math.pi, math.pi), 0.0, 0.0
        self.set_lair(W / 2, self.rng.choice([H * 0.2, H * 0.8]))

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
            if self.fly_dead <= 0:                       # respawn at the centre, away from the lair
                fly.x, fly.y = W / 2, H - self.spider_home[1]
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
        # spider
        dist = math.hypot(fly.x - self.spider[0], fly.y - self.spider[1])
        self.spider_timer += dt
        if self.spider_state == "wait":
            if dist < SIGHT_R:
                self.spider_state, self.spider_timer = "hunt", 0.0; self.events.append((t, "SPIDER!"))
        elif self.spider_state == "hunt":
            dist = self._move_spider_toward(fly.x, fly.y, POUNCE_SPEED if dist < POUNCE_R else CHARGE_SPEED, dt)
            if dist < CATCH_R:
                self.caught += 1; self.events.append((t, "CAUGHT"))
                self.score["right" if self.half(fly.x) == "left" else "left"] += 1   # caught on your half = their point
                self.fly_dead = FLY_DEAD_S; self.eating = 0.0
                self.spider_state, self.spider_timer = "return", 0.0
            elif dist > GIVE_UP_R or self.spider_timer > HUNT_MAX_S:
                self.spider_state, self.spider_timer = "return", 0.0
        elif self.spider_state == "return":
            if self._move_spider_toward(self.spider_home[0], self.spider_home[1], RETURN_SPEED, dt) < 3:
                self.spider_state, self.spider_timer = "wait", 0.0
