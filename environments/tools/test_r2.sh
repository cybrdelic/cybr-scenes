#!/usr/bin/env bash
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd);cd "$ROOT"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2
g++ -std=c++17 -O2 -Ishared tests/surface_atlas.cpp -o build/test-surface-atlas
build/test-surface-atlas assets/mineral_detail.cdt > evidence/test-surface-atlas.json
g++ -std=c++17 -O2 -march=native -fopenmp -Ishared -Iengines/obsidian/include tests/environment_sampling.cpp -o build/test-environment-sampling
(cd engines/obsidian; ../../build/test-environment-sampling) > evidence/test-environment-sampling.json
python -m unittest discover -s tests -v > evidence/test-geometry.log 2>&1
