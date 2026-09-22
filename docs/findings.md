# What the brain actually does (tested 19 Sep 2026)

Method: stimulate one sensory group on one side with Poisson spikes (150 Hz unless noted),
simulate 400 ms of the full v783 brain, read mean firing rate (Hz) of descending/motor
neurons as `left/right`. Reproduce with `python sim/brain.py 0.1`.

| Input | Active neurons | Key outputs (left/right Hz) | Meaning |
|---|---|---|---|
| eye_target LEFT (LC10a) | ~510 | turn DNa02 **138/0**, DNa01 22/5 | turns TOWARD object |
| eye_target RIGHT | ~660 | turn DNa02 **0/62** | turns toward (weaker on the right) |
| shadow LEFT (LPLC2+LC4) | ~860 | escape DNp01 **172/108**, DNa01 0/48, DNa02 0/10, DNp02/04/11 170/0 | jump + turn AWAY |
| LPLC2 RIGHT alone | ~680 | DNp01 100/155, DNa02 42/0, DNa01 22/0 | mirror image |
| motion LC9 LEFT / RIGHT | ~770 / ~960 | walk DNp09 **85/0** / **0/128** | forward drive |
| sugar both sides @80 Hz | ~545 | feed MN9 **65/90** | proboscis out |
| sugar + bitter | ~780 | feed **0/0** (5/12 with sugar one-sided) | bitter vetoes feeding |
| sugar LEFT @150 Hz | ~480 | feed 75/112 | fine |
| sugar RIGHT @150 or 100 Hz | **~8,400** | generic runaway signature | TRAP, see below |
| sugar RIGHT @50 Hz | ~215 | feed 15/15 | fine |
| sound (JO) RIGHT | ~335 | DNp01 0/70 | real pathway (JO -> giant fiber) but LEFT gives nothing: asymmetric, experimental |
| antenna touch, eye bristles, wind | 100-900 | none of our readouts | need grooming DNs (not yet identified in annotations) |
| any smell / heat / cold / humidity | **~8,100-8,200** | always DNa02 ~45/0, DNg13 ~65/38 ... | BROKEN, see below |

Steering direction is literature-backed: unilateral DNa02 activation produces ipsilateral
turning (Rayshubskiy et al., eLife, https://elifesciences.org/articles/102230). LC10a = courtship
pursuit neurons (Ribeiro et al. 2018). LPLC2/LC4 -> giant fiber = looming escape (Ache et al. 2019).
Sugar -> MN9 and bitter suppression are validated in Shiu et al. 2024 itself.

## Trap 1: the olfactory runaway ("seizure")
Any input that reaches the antennal lobe - even 3 heat neurons, even at 20 Hz - ignites the same
~8,000 neurons (3,300 Kenyon cells, antennal-lobe projection + local neurons, lateral horn,
dopamine neurons) with an identical output signature regardless of stimulus or side. It is a
model artefact: this LIF model has no graded/presynaptic inhibition, which the real olfactory
system relies on. Strong one-sided sugar (>= 100 Hz on the right) reaches it too.
Consequences: no smell sense in the game; cap sugar at 80 Hz; add a watchdog
(if active neurons in a tick > ~3,000, call `brain.reset()` and show a "fly fainted" gag).

## Trap 2: left/right are not mirror images
It is one real animal's brain, reconstructed with small errors. Right eye_target gives 62 Hz
where left gives 138 Hz. Normalise per side in `body.py` if it makes the game unfair.

## Speed (cloud box, 2 slow cores, pure numpy)
dt=0.1 ms: ~4.8 s wall per simulated second. dt=0.25: ~2.0. **dt=0.5: ~1.0** with the same behaviour.
Closed loop with 50 ms ticks ran at ~2x slower than real time there. Not yet measured on Apple Silicon.

## Sustained input (tested 19 Sep 2026, dt = 0.5 ms, 50 ms ticks)
The table above uses 400 ms windows. In the game a button is *held* for seconds, and the
olfactory runaway is stochastic: it ignites with some probability per second that depends on
the taste input rate. 5 seeds x 10 s per row, "runaway" = > 3000 neurons active in one tick.

| Held input | Runaway trials | Feeding (MN9 mean > 30 Hz) |
|---|---|---|
| sugar both @80 Hz | **5/5** (after 0.2-6.9 s) | - |
| sugar both @60 Hz | 1/5 (after 4 s) | 92% of ticks, 70 Hz |
| sugar both @50 Hz | 0/5 | 88% of ticks, 67 Hz |
| **sugar both @40 Hz** (game) | 0/5 | 79% of ticks, 60 Hz |
| bitter both @150 Hz | **4/5** (after 1.1-8.5 s) | - |
| bitter both @100 Hz | 0/5 | 0 |
| **bitter both @60 Hz** (game) | 0/5 | 0 |
| sugar 40 + bitter 60 | 0/5 | 0 (bitter still vetoes) |
| eye_target L or R @150, shadow L or R @150, both eyes, both shadows | 0 in 8 s each | - |
| all six buttons at once | runaway after ~0.4 s | - |

Consequences: game rates are sugar 40 Hz, bitter 60 Hz (server.py BUTTONS). Everyone holding
everything at once still faints the fly - that is the watchdog's job and it is funny.
Per-tick active counts in normal play stay < 2000; the runaway sits at 7,000-9,000, so the
3,000 watchdog threshold has margin on both sides. A runaway tick also costs ~2x brain time
(85-90 ms), so the reset matters for the tick rate too.

## No resting state: the background-drive experiment (20 Sep 2026, negative result)
Question: can a low Poisson "spontaneous activity" drive on every neuron outside the olfactory
runaway set give the fly idle behaviour, so it does not just walk in a straight line?
Method: ignite the runaway twice (sugar right 150 Hz, vinegar) and record who fires: 8,586
neurons. Drive the other 129,734 (minus taste/smell/touch sensory neurons) with Poisson hits
that respect the refractory period, at 0.001-3 Hz per neuron, 10-20 s each, dt 0.5 ms.

| Rate per neuron | Hits per 50 ms tick | Result |
|---|---|---|
| 0.001 Hz | ~6 | silent: 2-11 neurons active, all outputs 0 |
| 0.003 Hz | ~19 | silent for 8.5 s, then the olfactory set ignites (7,300 active) |
| 0.01 Hz | ~65 | same, ignites at 8.5 s |
| 0.03 Hz | ~195 | ignites within the first 100 ms |
| 0.1-3 Hz, or 10% of neurons at 1-10 Hz | 650+ | ignites in the first tick |

There is no middle ground: below ~20 stray spikes per tick the network does nothing (the
occasional 20 Hz blip in DNa02 is one spike), and any spike that leaks into the olfactory set
starts the seizure. The model has no graded inhibition to hold a resting state, so idle
behaviour cannot come from the brain without changing the model itself. Also, drawing Poisson
hits for 130k neurons every 0.5 ms step costs ~70 ms extra per 50 ms tick (100 vs 32 ms),
which would break the 20 ticks/s loop. Conclusion: the fly is a reflex machine; idle
"personality" has to come from the world (things to see) or from many players in conflict,
not from spontaneous brain activity.

## Neuron Jenga (20 Sep 2026): what breaks when you pull a block
Removed from the game on 22 Sep 2026; the code (`Brain.silence()/restore()`,
`sim/build_blocks.py`, the /host panel) is in git history up to commit 3135234. The results
below still describe the brain. `Brain.silence(indices)` killed neurons (they never fire, their output synapses are zeroed);
`Brain.restore()` undid it. Blocks were defined in `sim/build_blocks.py` from the annotation
classes. Reflex test = 400 ms of one stimulus from a fresh brain: eye L/R 150 Hz -> DNa02
L/R, shadow L 150 Hz -> mean DNp01, sugar 40 Hz -> mean MN9, motion 150 Hz -> mean DNp09.
Intact baseline: 140 / 88 / 136 / 60 / 69 Hz. Verdict OK >= 50% of baseline, WEAK >= 20%,
BROKEN below that.

| Block pulled | Neurons | TURN L | TURN R | PANIC! | HUNGRY | WALK |
|---|---|---|---|---|---|---|
| The giant fibre (DNp01) | 2 | ok | ok | **broken** | ok | ok |
| The steering pair (DNa02) | 2 | **broken** | **broken** | ok | ok | ok |
| All brain-to-body cables (descending) | 1,299 | broken | broken | broken | ok | broken |
| Mouth & neck motor neurons | 105 | ok | ok | ok | **broken** | ok |
| Taste sensors | 408 | ok | ok | ok | **broken** | ok |
| Object detectors (visual projection) | 8,038 | broken | broken | broken | ok | broken |
| The optic lobes | 77,530 | ok | ok | ok | ok | ok |
| Memory centre (Kenyon cells) | 5,177 | ok | ok | ok | ok | ok |
| Dopamine neurons | 331 | ok | ok | ok | ok | ok |
| Smell centre | 3,431 | ok | ok | ok | ok | ok |
| Navigation centre (central complex) | 2,875 | ok | ok (60) | ok | ok (49) | ok |
| Touch & hearing | 2,656 | ok | ok | ok | ok (32) | ok |
| The whole LEFT half | 69,504 | broken | ok | broken | broken | ok |
| The whole RIGHT half | 68,917 | ok | broken | ok (80) | broken | ok (48) |
| Random 5%, cumulative | 5% / 10% / 15% | ok | ok | ok | weak/ok/weak | ok |
| Random 5%, 4th pull | 20% | **broken** | **broken** | ok | **broken** | ok |

Lessons for the host: half the brain (the optic lobes) can go and nothing changes, because the
game injects its senses at the object-detector neurons behind the optic lobes; two neurons in
the right place break a whole reflex; the memory, smell, dopamine and navigation centres do
nothing for reflexes; feeding needs both halves (the tongue's motor neuron is wired from both
sides); random damage is tolerated up to ~15% and collapses around 20%, so a Jenga round of
"random 5%" pulls lasts 3-4 turns. A check takes ~1.6 s of wall time and pauses the game.

## The world drives the senses (20 Sep 2026): the fly behaves on its own
`sim/senses.py` turns the arena into input rates (a drop in view excites the eye on its side,
an approaching spider within 220 px looms on its side, standing on a drop = sugar 40 Hz);
`sim/world.py` has 5 sugar drops, a spider chasing at 32 px/s, walls, eating (1.5 s of
proboscis on a drop). `python sim/demo_world.py 120` runs the same world with the senses
connected and blind:

| 120 s in the arena | Drops eaten | Caught by spider | Escape jumps | Time feeding |
|---|---|---|---|---|
| senses connected | 9 | 2 | 20 | 15 s |
| blind (no input) | 0 | 5 | 0 | 0 s |

No faints, 0.8 s wall per simulated second including the world. The fly turns toward drops
within ~2 s of seeing them, stops to eat, and jumps away when the spider looms; it gets caught
mostly while feeding (the spider is slower than a walking fly on purpose). Tuning that
mattered: vision range 700 px and 5 drops (with 450 px / 3 drops the fly often saw nothing
and walked straight for 10+ s), and eating progress must not reset when the MN9 rate dips
for a tick. Dead ahead (|bearing| < 0.15 rad) excites neither eye because the two eye
pathways are not mirror images (trap 2).

## Playtest fixes (20 Sep 2026, after Kim watched world mode)
- **Left-right flicker.** With drops on both sides both DNa02 neurons fire and the steering
  difference flips sign ~6 times a second (measured: 96 flips in 15 s in a two-drop scene);
  the strong left pathway makes the left eye look like it is blinking. The brain has no
  winner-take-all, so that indecision is real. Fixes: graded eye input in `senses.py` (rate
  grows with bearing, 25% at the edge of the dead zone, full at 0.8 rad) cut eye on/off
  toggles 97 -> 30; turning inertia in `body.py` (`TURN_TAU` 0.4 s) cut heading reversals
  74 -> ~16 per 15 s with no change in time-to-drop (7.0 s for 300 px). The right steering
  channel is scaled x2.2 (`RIGHT_TURN_GAIN`, trap 2) so both eyes pull equally.
- **Panic with the spider "far away".** 220 px looks small on the beamer, and "closing" was
  computed from the distance, so walking toward a resting spider also loomed. Now the spider
  looms only while it is moving toward the fly, and its threat radius is drawn permanently
  (fills red when it charges). Eye input alone never drives DNp01 (0 Hz under both eyes 150 Hz,
  or eyes + sugar), so every jump has a looming spider behind it.
- **Death.** A catch now freezes the fly on its back for 1.5 s, then respawns it away from the
  spider, which rests 4.5 s.
- 120 s re-run: connected 5 drops / 2 catches / 35 jumps, blind 0 / 3 / 0.
- **Ambush spider** (Kim: "the spider should not always see the fly"). The spider now waits or
  wanders at 15 px/s, charges at 70 px/s when the fly is inside its 260 px sight, gives up when
  the fly is 420 px away or after 6 s, and rests 3 s. Its sight ring is always drawn: faint
  while waiting, red and filled while hunting. `World.set_spider_target(x, y)` is the hook for
  the spectator vote. 120 s run: 2 encounters (1 catch, 1 escape), 7 jumps instead of 35.
  Drops eaten per 120 s run vary 2-9 between runs; single runs are noisy.
- **Jump direction** (Kim: the fly jumped straight into the spider, endless "GOT YOU"). The
  brain lateralises the threat (shadow left: DNp01 172/108, DNp02/04/11 170/0) but the takeoff
  direction is computed in the legs/ventral nerve cord, which the simulated brain does not
  include, so `body.py` now jumps ~70 deg away from the side whose escape neurons fire more,
  with +-30 deg scatter. Ambush test, spider waiting on the path to a drop, 12 seeds:
  old rule 12/12 caught, new rule 0/12 caught (headings after the jump 47-98 deg off the path).

## MaleCNS drop-in check (20 Sep 2026): a brain WITH a ventral nerve cord
Kim asked whether a whole-nervous-system model exists. It does: Janelia FlyEM MaleCNS v1.0
(brain + VNC of one male, 165,122 traced neurons, released June 2026, **CC-BY**) and the
FlyWire BANC (female, 188k neurons, Nov 2025). `sim/build_malecns.py` downloads the MaleCNS
flat tables (no login), builds a cache in our format (ACh +, GABA/Glu -, amines dropped,
>= 5 synapses: 6.06 M connections) and runs our stimuli through the **unchanged** `Brain`.

| Stimulus, 400 ms | MaleCNS result | FlyWire v783 (this game) |
|---|---|---|
| eye_target LEFT | DNa02 **142/0** | 138/0 |
| eye_target RIGHT | DNa02 **0/135** (symmetric!) | 0/62 (lopsided) |
| shadow LEFT | DNp01 288/100, DNp02/04/11 249/0, **TTMn jump muscle 65/15** | DNp01 172/108, no cord |
| motion LEFT | DNp09 142/0 | 85/0 |
| labellar taste (modality unknown) 40-80 Hz | MN9 0 for 5 s | sugar -> MN9 65/90 |
| pharyngeal taste 40 Hz | MN9 100/0 after ~5 s, together with a 6,900-neuron burst | - |

So: the simulator is drop-in compatible, the steering / escape / walking reflexes come out the
same, this male brain turns equally well to both sides, and the cord relays the giant fibre to
the jump muscle. What it does NOT give us:
- **No takeoff direction.** Leg motor neurons fire symmetrically after a one-sided shadow
  (first 300 ms: 1,033 vs 1,120 spikes, 97 vs 104 neurons active). The jump direction still
  has to be hand-written in body.py, or needs a body physics model (NeuroMechFly).
- **No sugar/bitter.** MaleCNS does not annotate taste modality; the labellar taste proxy never
  drives MN9 (FLYCNS, a public MaleCNS spiking model, reports the same difficulty). HUNGRY
  would need a wiring-based proxy.
- **Too slow for the loop as is:** 46-48 ms of brain per 50 ms tick for one sense, 55 ms with
  all senses (FlyWire: 32-43). Needs dt = 1 ms or the Metal port to hold 20 ticks/s.
- **Different activity levels:** 1,200-3,000 neurons active per tick for one sense (FlyWire
  400-700), 5,000 with all senses; the 3,000 watchdog threshold and the seizure traps would
  have to be re-measured (pharyngeal taste showed a burst at 5 s).
Verdict: keep FlyWire for the workshop. MaleCNS is a documented, licence-friendly upgrade
path and a good debrief line ("the legs are in this one, and it still needs a body").
- **The spider could never catch a fly in the open** (Kim: only at the walls). Two changes:
  looming now grows with proximity in `senses.py` (0 at 240 px, full at 70 px), which is how a
  looming object drives a real eye and makes the escape a race instead of a fixed early
  trigger; and the spider lunges inside 130 px. Open-field ambush, 12 seeds each:

  | Lunge speed | Fly walking past | Fly feeding in the ring |
  |---|---|---|
  | none (70 px/s charge) | 0/12 caught | 0/12 |
  | 250 px/s (chosen) | 4/12 | 4/12 |
  | 350 px/s | 6/12 | 4/12 |

  Feeding does not change the odds: the brain's escape response to a shadow is identical on
  sugar (DNp01 135 vs 133 Hz, same 50 ms latency), so a feeding fly jumps just as well; a
  charge only interrupts the meal. Rule added: a catch on your half is the opponent's point.
