"""Headless check: does the brain, fed by the world through senses.py, hunt, eat and flee
on its own? Runs the same world twice: senses connected, and blind (no input)."""
import math, sys, time
from brain import Brain
from body import Fly
from senses import encode, bearing
import world as WM
from world import World, W, H
WM.N_DROPS = 5   # the headless demo keeps the world's own drops

TICK_MS = 50; SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
br = Brain(dt=0.5)

def run(label, connected):
    br.reset(); fly = Fly(x=W / 2, y=H / 2, heading=0.0); world = World()
    fainted_until = 0.0; jumps = feeding_ticks = 0; faints = 0; t0 = time.time()
    print(f"\n=== {label} ({SECONDS:.0f} s simulated)")
    for tick in range(int(SECONDS * 1000 / TICK_MS)):
        t = tick * TICK_MS / 1000
        if t < fainted_until:
            out = {n: {"left": 0.0, "right": 0.0} for n in br.output_names}; active = 0; seen = ["fainted"]
        else:
            d = world.on_drop(fly)
            rates, seen = encode(fly, world.drop_xy(), world.hazards(fly), bool(d and d["sugar"]), bool(d and d["bitter"])) if connected else ({}, [])
            br.set_input(rates); out, active = br.step(TICK_MS)
            if active > 3000:
                br.reset(); fainted_until = t + 2.0; faints += 1; world.events.append((t, "FAINT"))
            elif world.fly_dead <= 0:
                fly.update(out, TICK_MS / 1000)
        world.update(fly, TICK_MS / 1000, t)
        jumps += fly.jumped; feeding_ticks += fly.feeding
        if tick % 40 == 0:   # every 2 s
            nd = min(world.drop_xy(), key=lambda d: math.hypot(d[0] - fly.x, d[1] - fly.y)) if world.drops else (fly.x, fly.y)
            dd = math.hypot(nd[0] - fly.x, nd[1] - fly.y); db = math.degrees(bearing(fly, *nd))
            sd = math.hypot(world.spider[0] - fly.x, world.spider[1] - fly.y)
            ev = " ".join(e for tt, e in world.events if t - 2 <= tt < t)
            print(f"t={t:5.1f}s fly=({fly.x:4.0f},{fly.y:4.0f}) drop {dd:4.0f}px @{db:+4.0f}deg spider {sd:4.0f}px | "
                  f"senses {','.join(seen) or '-':22s} | turn {out['turn']['left']:3.0f}/{out['turn']['right']:3.0f} "
                  f"esc {(out['escape']['left']+out['escape']['right'])/2:3.0f} feed {(out['feed']['left']+out['feed']['right'])/2:3.0f} "
                  f"act {active:4d} | {ev}")
    print(f"--- {label}: drops eaten {sum(world.score.values())}, caught by spider {world.caught}, jumps {jumps}, "
          f"feeding {feeding_ticks * TICK_MS / 1000:.1f} s, faints {faints}, wall {time.time() - t0:.0f} s")

run("SENSES CONNECTED", True)
run("BLIND (no input)", False)
