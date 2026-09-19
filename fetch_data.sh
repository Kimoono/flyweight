#!/usr/bin/env bash
# Downloads the connectome (~190 MB) and the FlyWire annotations (~35 MB) into data/upstream/.
set -euo pipefail
mkdir -p "$(dirname "$0")/data/upstream" && cd "$(dirname "$0")/data/upstream"
[ -d Drosophila_brain_model ] || git clone --depth 1 https://github.com/philshiu/Drosophila_brain_model.git
[ -d flywire_annotations ]    || git clone --depth 1 https://github.com/flyconnectome/flywire_annotations.git
echo "OK. Next: python sim/build_neurons.py && python sim/brain.py 0.5"
