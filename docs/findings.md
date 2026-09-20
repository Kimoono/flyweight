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
