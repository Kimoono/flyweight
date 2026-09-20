"""The arena: sugar drops, a spider, walls, score. Game rules only; no fly behaviour here.
The fly's decisions come from brain.py via body.py; what the fly senses comes from senses.py."""
import math, random
from dataclasses import dataclass, field

W, H = 1600.0, 900.0
DROP_R = 28.0          # px: standing on a drop
EAT_S = 1.5            # s of feeding to finish a drop
N_DROPS = 5
# The spider is an ambush predator. It waits (or wanders slowly toward a target), charges when
# the fly comes inside its sight, gives up when the fly gets away, and rests after a catch.
SIGHT_R = 260.0        # px: the fly inside this = the spider charges
CHARGE_SPEED = 70.0    # px/s: faster than a walking fly (40 px/s); only a jump gets away
WANDER_SPEED = 15.0    # px/s while waiting
GIVE_UP_R = 420.0      # px: fly this far away while hunting = the spider gives up
HUNT_MAX_S = 6.0       # s: a charge never lasts longer than this
REST_S = 3.0           # s: after giving up or a catch
CATCH_R = 30.0
FLY_DEAD_S = 1.5       # the fly lies still after a catch, then respawns


@dataclass
class World:
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    drops: list = field(default_factory=list)
    spider: list = field(default_factory=lambda: [W * 0.85, H * 0.85])
    spider_state: str = "wait"      # wait | hunt | rest
    spider_target: list | None = None   # where it wanders to while waiting (spectator vote later)
    spider_timer: float = 0.0       # time in the current state
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

    @property
    def spider_closing(self):
        return self.spider_state == "hunt"

    def hazards(self, fly):
        return [(self.spider[0], self.spider[1], self.spider_closing)]

    def set_spider_target(self, x, y):
        self.spider_target = [min(max(x, 60), W - 60), min(max(y, 60), H - 60)]

    def _move_spider_toward(self, x, y, speed, dt):
        sx, sy = self.spider
        d = math.hypot(x - sx, y - sy)
        if d < 1e-6:
            return d
        step = min(speed * dt, d)
        self.spider[0] += (x - sx) / d * step; self.spider[1] += (y - sy) / d * step
        return d

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
        # spider: ambush predator (see constants above)
        dist = math.hypot(fly.x - self.spider[0], fly.y - self.spider[1])
        self.spider_timer += dt
        if self.spider_state == "wait":
            if dist < SIGHT_R:
                self.spider_state, self.spider_timer = "hunt", 0.0; self.events.append((t, "SPIDER!"))
            else:
                if self.spider_target is None or self.spider_timer > 8.0:
                    self.spider_target = [self.rng.uniform(60, W - 60), self.rng.uniform(60, H - 60)]; self.spider_timer = 0.0
                if self._move_spider_toward(self.spider_target[0], self.spider_target[1], WANDER_SPEED, dt) < 5:
                    self.spider_target = None
        elif self.spider_state == "hunt":
            dist = self._move_spider_toward(fly.x, fly.y, CHARGE_SPEED, dt)
            if dist < CATCH_R:
                self.caught += 1; self.events.append((t, "CAUGHT"))
                self.fly_dead = FLY_DEAD_S; self.eating = 0.0
                self.spider_state, self.spider_timer = "rest", -FLY_DEAD_S   # rests REST_S after the fly respawns
            elif dist > GIVE_UP_R or self.spider_timer > HUNT_MAX_S:
                self.spider_state, self.spider_timer = "rest", 0.0
        elif self.spider_state == "rest" and self.spider_timer > REST_S:
            self.spider_state, self.spider_timer, self.spider_target = "wait", 0.0, None
