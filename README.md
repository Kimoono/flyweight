# Fly by Committee

A party game for ~20 people where teams *become the senses* of a simulated fruit fly.
The fly's decisions come from a simulation of the real, fully mapped fruit fly brain
(FlyWire connectome, 138,639 neurons). Nobody steers the fly — you can only feed its senses.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./fetch_data.sh                 # connectome + annotations, ~225 MB
python sim/build_neurons.py     # regenerates data/neurons.json (already included)
python sim/brain.py 0.5         # smoke test + speed benchmark
python sim/demo_autopilot.py    # brain steers a fly to a target, headless
python server.py                # the game: beamer page on /, phones on /play (QR in terminal)
```

What exists today: the simulator (`sim/brain.py`), a tiny body model (`sim/body.py`),
the neuron lists (`data/neurons.json`), the test results (`docs/findings.md`) and the
first playable slice: `server.py` + `web/` (arena on the beamer, hold-to-fire phone
controller). What needs building: game rules, heats, host page, voting, brain view — see `CLAUDE.md`.

## Licences
Simulator model: Shiu et al., MIT. FlyWire connectome data: **non-commercial use**, cite
Dorkenwald et al. 2024 and Schlegel et al. 2024. Fine for an internal workshop; don't ship it in a product.
