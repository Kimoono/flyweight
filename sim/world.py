"""The arena: sugar drops, a spider, walls, score. Game rules only; no fly behaviour here.
The fly's decisions come from brain.py via body.py; what the fly senses comes from senses.py."""
import math, random
from dataclasses import dataclass, field

W, H = 1600.0, 900.0
DROP_R = 28.0          # px: standing on a drop
EAT_S = 1.5            # s of feeding to finish a drop
N_DROPS = 5
SPIDER_SPEED = 32.0    # px/s: slower than a walking fly (40 px/s), so only a feeding fly gets caught
CATCH_R = 30.0
SPIDER_REST_S = 3.0    # after a catch the spider sits still (fair restart)
FLY_DEAD_S = 1.5       # the fly lies still after a catch, then respawns
LOOM_RANGE = 220.0     # px: the spider's threat radius (senses.py uses the same number)


@dataclass
class World:
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    drops: list = field(default_factory=list)
    spider: list = field(default_factory=lambda: [W * 0.85, H * 0.85])
    spider_closing: bool = False
    spider_rest: float = 0.0
    fly_dead: float = 0.0
    eating: float = 0.0
    score: int = 0
    caught: int = 0
    events: list = field(default_factory=list)

    def __post_init__(self):
        while len(self.drops) < N_DROPS:
            self.drops.append(self.spawn_drop())

    def spawn_drop(self):
        return [self.rng.uniform(100, W - 100), self.rng.uniform(100, H - 100)]

    def on_drop(self, fly):
        for d in self.drops:
            if math.hypot(d[0] - fly.x, d[1] - fly.y) < DROP_R:
                return d
        return None

    def hazards(self, fly):
        return [(self.spider[0], self.spider[1], self.spider_closing)]

    def update(self, fly, dt, t):
        """Call after fly.update(). Applies walls, eating, the spider, death and respawn."""
        if self.fly_dead > 0:
            self.fly_dead -= dt
            if self.fly_dead <= 0:                       # respawn away from the spider
                fly.x, fly.y = W - self.spider[0], H - self.spider[1]
                fly.x = min(max(fly.x, 100), W - 100); fly.y = min(max(fly.y, 100), H - 100)
                fly.heading = self.rng.uniform(-math.pi, math.pi); fly.turn_rate = 0.0; fly.cooldown = 0.0
            return
        # walls: bounce (arena rule)
        if fly.x < 0 or fly.x > W:
            fly.heading = math.pi - fly.heading; fly.x = min(max(fly.x, 0), W)
        if fly.y < 0 or fly.y > H:
            fly.heading = -fly.heading; fly.y = min(max(fly.y, 0), H)
        # eating
        d = self.on_drop(fly)
        if d is None:
            self.eating = 0.0                      # walked off: progress lost
        elif fly.feeding:
            self.eating += dt                      # proboscis out on a drop: progress (MN9 rate flickers, so no reset on a dip)
            if self.eating >= EAT_S:
                self.drops.remove(d); self.drops.append(self.spawn_drop())
                self.score += 1; self.eating = 0.0; self.events.append((t, "EAT"))
        # spider: chases the fly; it looms only while it is moving toward the fly
        sx, sy = self.spider
        dist = math.hypot(fly.x - sx, fly.y - sy)
        self.spider_closing = False
        if self.spider_rest > 0:
            self.spider_rest -= dt
        elif dist > 1e-6:
            step = min(SPIDER_SPEED * dt, dist)
            self.spider[0] += (fly.x - sx) / dist * step; self.spider[1] += (fly.y - sy) / dist * step
            self.spider_closing = True
            if dist < CATCH_R:
                self.caught += 1; self.events.append((t, "CAUGHT"))
                self.fly_dead = FLY_DEAD_S; self.eating = 0.0
                self.spider_rest = SPIDER_REST_S + FLY_DEAD_S; self.spider_closing = False
