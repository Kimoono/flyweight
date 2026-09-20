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
python sim/build_positions.py   # regenerates data/positions.bin for the brain view (already included)
python sim/build_blocks.py      # regenerates data/blocks.json for Neuron Jenga (already included)
python sim/brain.py 0.5         # smoke test + speed benchmark
python sim/demo_autopilot.py    # brain steers a fly to a target, headless
python server.py                # the game: beamer on /, phones on /play (QR in terminal), Neuron Jenga on /host
```

What exists today: the simulator (`sim/brain.py`), a tiny body model (`sim/body.py`),
the neuron lists (`data/neurons.json`), the test results (`docs/findings.md`) and the game:
`server.py` + `web/`. Two players lure one fly ("Lure the fly": sugar on your half, bitter on
theirs, a spider with a lair, 90 s heats, leaderboard), the beamer shows the arena, the live
brain view with slow-motion replay, and `/host` runs heats (and Neuron Jenga as a finale).
Still to do: balance, sound, a dress rehearsal on real phones — see `CLAUDE.md`.

## Licences
Simulator model: Shiu et al., MIT. FlyWire connectome data: **non-commercial use**, cite
Dorkenwald et al. 2024 and Schlegel et al. 2024. Fine for an internal workshop; don't ship it in a product.
