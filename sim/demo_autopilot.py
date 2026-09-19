"""Headless closed-loop check: an 'autopilot' plays the eye players. If the target is
to the fly's left it holds the LEFT EYE button, else the RIGHT EYE button. The brain
does the steering. Prints the distance to target shrinking. Also usable as demo mode."""
import math, time
from brain import Brain
from body import Fly

TICK_MS = 50
br = Brain(dt=0.5); fly = Fly(); target = (300.0, 250.0)
t0 = time.time()
for tick in range(200):
    dx, dy = target[0] - fly.x, target[1] - fly.y
    dist = math.hypot(dx, dy)
    if dist < 25: print(f"reached target at t={tick*TICK_MS/1000:.1f}s"); break
    bearing = (math.atan2(dy, dx) - fly.heading + math.pi) % (2 * math.pi) - math.pi
    side = "left" if bearing > 0 else "right"
    hz = 150 if abs(bearing) > 0.15 else 0          # release the button when roughly on course
    br.set_input({"eye_target": {side: hz}})
    out, _ = br.step(TICK_MS); fly.update(out, TICK_MS / 1000)
    if tick % 10 == 0:
        print(f"t={tick*TICK_MS/1000:4.1f}s dist={dist:6.1f} bearing={math.degrees(bearing):6.1f} button={side if hz else '-':5s} turn L/R={out['turn']['left']:.0f}/{out['turn']['right']:.0f}")
print(f"wall {time.time()-t0:.1f}s for {tick*TICK_MS/1000:.1f}s simulated")
