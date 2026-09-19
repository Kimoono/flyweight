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
