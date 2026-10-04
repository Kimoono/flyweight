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

## Does the fly ever walk? (22 Sep 2026)
Kimoono: "the graphic shows WALK, but is this ever triggered?" No. The beamer's WALK label read
DNp09, and nothing the game feeds the brain drives it. Mean Hz over 400 ms from a fresh brain:

| stimulus | turn | turn_aux | DNp09 | escape | escape_aux | backward (MDN) | feed | **DNg100** |
|---|---|---|---|---|---|---|---|---|
| eye left 150 | 69 | 14 | **0** | 0 | 0 | 0 | 0 | **39** |
| eye both 150 | 52 | 14 | **0** | 0 | 0 | 0 | 21 | 62 |
| shadow left 150 | 2 | 22 | 8 | 138 | 85 | 3 | 0 | 26 |
| shadow both 150 | 0 | 0 | 0 | 180 | 152 | 9 | 0 | - |
| sugar both 40 | 0 | 1 | 0 | 0 | 0 | 0 | 55 | **0** |
| bitter both 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| motion both 150 | 1 | 41 | 70 | 1 | 19 | 8 | 0 | 88 |
| sound both 150 | 0 | 0 | 0 | 35 | 6 | 0 | 0 | - |
| antenna touch 150 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

DNp09 needs the `motion` sense (LC9), which `senses.py` never drove. Wiring it up (movement
slipping across the eye) is runaway-safe - 5 seeds x 10 s at 100 Hz both sides, 0/5, worst tick
916 active; with eyes 150 + sugar 40 on top, 0/5, worst 1,613 - but it is a minor input: counting
only things that move by themselves, it fires in 5-8% of arena ticks and DNp09 averages 0.1 Hz.
Counting self-motion instead put a loop in the game (movement -> WALK -> faster, turnier fly ->
more movement): 93% of ticks, fly at 110 px/s, past the spider's 70 px/s charge, 0 drops eaten in
40 s vs 3 before. Discounting self-motion (real flies do) removed it.

**The useful find is DNg100**, the only cell type known to act as a descending command neuron for
walking, and the top driver of rhythmic leg motor activity in VNC connectome simulations (Cell,
3 Sep 2026, pmc.ncbi.nlm.nih.gov/articles/PMC13142387). FlyWire has 2 of them, and they answer
to the game's own senses: a drop in view 39 Hz, a moving spider 54, looming 26, sugar 0, bitter 0.
So `walk` now means DNg100 and the old DNp09 is `walk_aux`.

## Brain-driven movement (22 Sep 2026)
Kimoono: "most of its movement is programmed. I want the brain to control it." `BASE_SPEED = 40` px/s
of unconditional amble is gone; forward speed is now `WALK_GAIN` (1.0) px/s per Hz of DNg100,
smoothed over 0.25 s and capped at 70 px/s (the spider's charge speed - at 110 px/s the chase
stopped being a chase). No command from the brain, no movement.

That exposed a conflict with the circling fix. Two measurements: the eye drive went silent when
the drop was dead ahead (the lateral dead zone), and DNg100 has a knee at about 60 Hz of eye input
(40 Hz -> 0, 60 -> 10, 150 -> 39) while the graded drive ran at 37-80 Hz. The fly could only walk
while turning, and stopped when it lined up. Driving both eyes when centred does not work either:
equal input gives turn 95/5 (trap 2), a hard left veer. So the eye encoding lost its grading and
its dead zone - one target, full rate on its side, always. 60 s in the arena, 4 drops, spider live:

| eye encoding | DNg100 | firing | speed | motionless | turning | eaten |
|---|---|---|---|---|---|---|
| graded + dead zone | 2-3 Hz | 7-9% of ticks | 2-3 px/s | 85-89% | 2-3 circles | 0 |
| **full rate, no dead zone** | 36-40 Hz | 93-94% | 34-36 px/s | 1-2% | 17 circles | 3 |

Steering now overshoots, so the fly weaves toward a drop instead of gliding in: 17 full circles of
accumulated heading per 60 s, against 2-3 with the dead zone. The weave is the brain's own
indecision and it still arrives (3 drops per 60 s, against 4-5 for the old programmed amble; single
runs, noisy). If the weave looks bad on the beamer, damp it in body.py (`TURN_TAU` up, `TURN_GAIN`
down) rather than by quietening the eye, which is what broke walking in the first place.

Still hand-written, and unavoidably: px/s per Hz, rad/s per Hz, the 70 deg takeoff angle (the brain
gives the side, we give the angle), the jump distance and thresholds, and the leg rhythm itself -
walking gaits live in the ventral nerve cord, which FlyWire does not contain. The VNC paper above
found the rhythm comes from three interneurons, and that driving DNg100 in a cord simulation still
does not produce a tripod gait without proprioception and biomechanics.

## The compass does not hold (22 Sep 2026): no working memory either
Kimoono asked whether the brain can remember anything. Two tests. (1) Switch a stimulus off: activity
is at a tenth one 50 ms window later and at exactly zero in the next one, for eye, shadow and
sugar input alike - no after-image, no persistence anywhere in 138,639 neurons. (2) The head-
direction ring attractor, the fly's compass and the one memory that needs no plasticity: all 47
EPG neurons are in the model and their positions form a flat ring (PCA spread 76,695 / 54,529 /
5,200). Planting a bump in one sector - 45 and 90 deg sectors, 150/250/400 Hz, 300 ms and 1,000 ms
- never survives the stimulus: EPG spikes go from ~290 per 50 ms window to 0 in the next window,
every time. The bump also never recruits a neighbour while it is driven (exactly the 23 stimulated
cells fire, no more), so the ring is not behaving like a ring at all.

Why this is interesting rather than embarrassing: the connectome gives the wiring, including 6.03 M
inhibitory of 15.09 M connections, but this model sets every synapse to one global constant times
its contact count. A ring attractor is a balance of excitation against inhibition, and that balance
cannot survive a single brain-wide guess. Good debrief line: we have the complete wiring diagram of
a brain and it still is not enough - no learning (no plasticity), no memory (no persistence), and
the compass will not hold a heading. Consistent with the Jenga result that removing the 5,177
Kenyon cells of the memory centre breaks no reflex.

## Two spiders, one per half (22 Sep 2026)
Kimoono's idea, and it costs nothing: `world.Spider` is a dataclass now and `World.spiders` a list,
each with its own lair, state machine and timer, hunting independently (a catch breaks the loop so
two cannot claim the same fly). Lairs are on the grid - vertically centred, an eighth of the width
in from each side wall, i.e. (200, 450) and (1400, 450) - deterministic, so the halves mirror each
other and players can learn the map. `N_SPIDERS = 1` restores the old single centre-line lair.
Respawn moved to the middle of the arena, 600 px from either lair. Costs no measurable brain time
(20.0 ticks/s, 33 ms/tick with both). 60 s, 4 drops, 2 seeds per row:

| layout | eaten | caught | charges | inside a ring | middle third |
|---|---|---|---|---|---|
| 1 spider, centre line, sight 260 (before) | 4, 5 | 3, 0 | - | 59%, 35% | 56%, 59% |
| 2 at quarter positions, sight 260 | 5, 5 | 1, 0 | - | 33%, 26% | 57%, 48% |
| 2 on the grid, sight 260 | 5, 5 | **0, 0** | 1, 2 | 8%, 36% | 81%, 47% |
| 2 on the grid, sight 340 | 5, 5 | 0, 1 | 3, 3 | 33%, 40% | 77%, 70% |
| 2 on the grid, sight 420 | 5, 5 | 0, 1 | 2, 4 | 37%, 61% | 84%, 77% |

Two spiders are not deadlier than one - the old single lair sat in the horizontal centre, where the
fly lives, while grid lairs sit in ground it rarely enters. At sight 260 they are decoration (1-2
charges a minute, no catches); 340 is where they start participating.

**The bigger find is scale.** The fly spends 47-84% of its time in the middle third of the board.
At ~39 px/s with a weaving path its net progress is 10-20 px/s, so crossing 1600 px takes over a
minute and most of the arena is unreachable inside a 90 s heat: sugar placed deep in a half is
nearly worthless and the outer quarters go unused. Arena size (`W, H` in world.py is the single
source of truth - the server sends it and both pages scale to it) and weave damping (`TURN_TAU`)
are being measured together with the sight radius. Note vision reaches 700 px, so in a 1200-wide
arena the fly can see most of the board at once.

Side effect of brain-driven speed, measured: a fly standing on bitter with **nothing in view** has
DNg100 = 0, so it stops until the puddle expires (10 s). With a drop in view it walks off normally
(39 Hz). A sulk, not a glue trap - kept on purpose.

## Vinegar is a grenade, not a lure (22 Sep 2026)
`smell_vinegar` (ORN_DM1, 68 neurons) is marked BROKEN in build_neurons.py. Measured properly, to
see whether a low rate could be a long-range attractant (smell works at a distance; sugar needs
the fly standing on the drop): there is no safe rate. 400 ms from a fresh brain, **vinegar LEFT at
10 Hz** already puts 8,152 neurons in the seizure; 40 Hz gives 8,160, both sides at 150 Hz gives
8,231. Held 10 s, 5 seeds per rate (the "Sustained input" protocol): 20, 40, 80 and 150 Hz all
ignite **5/5, every one at 0.0 s** - the first tick. During the seizure `turn` reads 22-30 Hz of
noise and DNg100 reads 0, so the fly would not even walk.

Use: a one-per-heat **stink bomb** that faints the fly on purpose - instant, 100% reliable, ~1 late
tick, and the most spectacular thing on the beamer (the whole brain flashes, the watchdog trips,
"THE FLY FAINTED"). Two cautions: (1) the honest framing is that this is a MODEL artefact, not
biology - real flies are attracted to vinegar, and this pathway simply has no gain control in the
model; do not tell the room vinegar makes flies faint. (2) A fainted fly does not move but the
world keeps running, so gassing the fly inside a spider's sight ring is a guaranteed kill; decide
whether that is a play or an exploit before someone finds it in a heat.

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

## Circling (22 Sep 2026): drops around the fly and it turns on the spot
Kimoono, clicking around with two /play windows: "when placing drops around the fly it often
starts circling on the spot". Reproduced headless (4 drops at 250 px in a ring, 15 s):

| eye encoding | both eyes driven | steering sign flips | reaches a drop |
|---|---|---|---|
| all visible drops (old) | 77% of ticks | 67 | never (2 runs, 15 and 20 s) |
| one target at a time (new) | 0% | 13-15 | after 10.7-12.1 s |

Cause, both in `senses.py`: (1) the encoder drove the eye on *every* visible drop's side, so
drops on both sides held both eyes at full rate and the steering difference flipped sign
several times a second - this brain has no winner-take-all to settle it; (2) distance was not
in the formula at all, only bearing, and the rate GROWS with bearing, so turning toward a drop
weakened its own signal while the drop behind grew louder. A limit cycle.

Fix (`senses.Eyes`, a FUDGE in the same category as `RIGHT_TURN_GAIN`): the fly attends to one
drop, the nearest, kept until it is gone or another is 1.5x closer; the dead zone straight
ahead became a fixed sideways miss distance (10 px) instead of a fixed angle; and a target is
remembered 1.5 s after it leaves the field of view. That last part is needed: with single-target
attention the fly commits, walks past the drop, and then cannot see it (anything behind the fly
is outside the 150 deg FOV), so the first version walked off the screen in a straight line.
The brain still steers; we now choose what it looks at. Through the server, ring of 4 drops:
3 eaten in 35 s, 20.0 ticks/s held, brain 35-40 ms/tick.

Not fixed, and still true: the fly meanders (about 3 full turns of accumulated heading per 15 s)
and a single drop 300 px away takes 11-14 s to reach. Single runs are noisy: the brain is
stochastic, and these are one run per variant.

## Playtest fixes (20 Sep 2026, after Kimoono watched world mode)
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
- **Ambush spider** (Kimoono: "the spider should not always see the fly"). The spider now waits or
  wanders at 15 px/s, charges at 70 px/s when the fly is inside its 260 px sight, gives up when
  the fly is 420 px away or after 6 s, and rests 3 s. Its sight ring is always drawn: faint
  while waiting, red and filled while hunting. `World.set_spider_target(x, y)` is the hook for
  the spectator vote. 120 s run: 2 encounters (1 catch, 1 escape), 7 jumps instead of 35.
  Drops eaten per 120 s run vary 2-9 between runs; single runs are noisy.
- **Jump direction** (Kimoono: the fly jumped straight into the spider, endless "GOT YOU"). The
  brain lateralises the threat (shadow left: DNp01 172/108, DNp02/04/11 170/0) but the takeoff
  direction is computed in the legs/ventral nerve cord, which the simulated brain does not
  include, so `body.py` now jumps ~70 deg away from the side whose escape neurons fire more,
  with +-30 deg scatter. Ambush test, spider waiting on the path to a drop, 12 seeds:
  old rule 12/12 caught, new rule 0/12 caught (headings after the jump 47-98 deg off the path).

## MaleCNS drop-in check (20 Sep 2026): a brain WITH a ventral nerve cord
Kimoono asked whether a whole-nervous-system model exists. It does: Janelia FlyEM MaleCNS v1.0
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
- **The spider could never catch a fly in the open** (Kimoono: only at the walls). Two changes:
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

## DISGUST: bitter has a readout after all (23 Sep 2026)
Kimoono: "is there any signal from the brain when the fly is on a bitter drop?" The five labels
said no: bitter 60 Hz leaves turn, walk, escape and feed at 0 (table above), so bitter showed
only as an absence (HUNGRY going dark, DNg100 = 0 with nothing in view). Measured 1 s from a
fresh brain, bitter both sides at the game's 60 Hz: 65 taste cells + **43 downstream neurons**,
almost all in the SEZ (sugar 40 Hz: 379 downstream, 70 descending neurons; bitter: 2 descending,
DNpe007 at 8-20 Hz). The strongest are one pair per side:

| cell type | bitter 60 | sugar 40 | sugar 40 + bitter 60 | eye / shadow 150 |
|---|---|---|---|---|
| **CB0159** (1 per side) | **151 Hz** | 0 | 146 | 0 |
| CB0016 | 91 | 0 | 90 | 0 |
| CB0219 | 61 | 1 | 37 | 0 |

CB0159 follows the bitter input almost one to one and nothing else the game feeds the brain
touches it, so it is now the `disgust` output (build_neurons.py) and the sixth beamer label,
DISGUST, full at 150 Hz. Honesty note: unlike DNa02 / MN9 / the giant fiber, no paper says what
CB0159 does in a real fly; "disgust" is our name for "bitter interneuron that fires only on
bitter". The neurons.json label and any nerd mode must show the cell name, not the claim.

## Splash startle (24 Sep 2026): a drop dumped on the fly makes it jump
Kimoono: drops placed on or just in front of the fly keep it on one half. Reproduced headless: a bot
that drops sugar on the fly every 2 s (the cooldown) scores a point every 2 s and the fly never
moves, because the nearest drop always wins its attention and there is no travel. Luring from
ahead scores half that. Fix, in `senses.py` only: a drop that landed less than 0.15 s ago within
STARTLE_R px looms on the shadow sense on its side (full rate inside STARTLE_NEAR, fading to 0 at
the ring; first built as 150 / 60), like any object falling from above; the giant fibre fires and body.py jumps 180 px, the
drop stays, and the fly has to walk back. Startle off = STARTLE_R forced to 0. 60 s duels, left
bot only, two wandering spiders, 4 seeds each:

| left bot places sugar | startle | left points (4 seeds) | mean | caught | jumps |
|---|---|---|---|---|---|
| on the fly | off | 27, 29, 29, 30 | **28.8** | 2 | 4 |
| on the fly | **on** | 3, 2, 3, 2 | **2.5** | 7 | 115 |
| 160 px ahead | off | 13, 15, 20, 10 | 14.5 | 6 | 19 |
| 160 px ahead | on | 13, 11, 8, 7 | 9.8 | 8 | 39 |
| 250 px ahead | off | 19, 9, 17, 7 | 13.0 | 7 | 16 |
| 250 px ahead | on | 12, 12, 11, 9 | 11.0 | 8 | 19 |

Farming is dead (a factor 11), and it gets the fly caught more often, because a pinball fly
lands in spider rings.

Kimoono: the 150 px ring looks too large. Sweep, same bot, 3 seeds, the bot either on the fly or
just outside the ring:

| ring (full-rate inside) | on the fly | just outside the ring |
|---|---|---|
| 150 / 60 | 2.5 (4 seeds) | 9.8 at 160 px |
| 100 / 40 | 3.0 | 15.0 at 110 px |
| **80 / 30** (chosen) | **1.0** | 15.0 at 90 px |

The ring size does not matter for the exploit: any ring that covers the fly kills the zero-travel
farm, and a drop 90 px away already costs the fly the same ~4 s of weaving that honest luring
costs (15 points a minute either way, against 29 for a drop on its head). So the ring is 80 px,
about the fly plus a drop's width (DROP_R 28), and luring from 160 px is untouched again. Luring from 160 px, right at the ring's edge with the fly's weave, loses
about a third; from 250 px the loss is inside the seed noise. One faint in the 2-seed pilot,
none in 24 runs here (shadow + sugar + eye at the same time is runaway-safe, "Sustained input").
Costs no brain time (the shadow sense already existed). Not a hard rule: the phone draws the
ring around the fly and says "lure from outside", the fly enforces it.

To decide in a playtest: a bitter tap next to the fly on your half now knocks it off your sugar
and it jumps roughly away from the tap's side, so the opponent has an indirect, scattered push.
If that feels like a move button, let only sugar splash (in `World.splashes`). Also still open:
sugar every 2 s against bitter every 4 s means spoiling cannot keep up with feeding.

Found on the way: `Eyes._flow` divided by zero when a drop landed exactly on the fly (distance
0), which would have killed the server's sim thread on a lucky tap. Guarded. `sim/demo_world.py`
still reads `world.spider`, which became `world.spiders` on 22 Sep; it has not run since.
