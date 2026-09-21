#!/usr/bin/env bash
# Reproduce the delivered image. Run from any working directory.
set -euo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
THREADS="${THREADS:-5}"
if [[ "$#" -ne 0 ]]; then
  echo "render.sh reproduces the delivered settings; use the native CLI for custom camera/output settings." >&2
  exit 2
fi
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
ctest --test-dir build --output-on-failure
mkdir -p renders
./build/observatory --mesh scene/observatory.cvr2 --out renders/reproduction \
  --width 1800 --height 1200 --spp 96 --adaptive --depth 12 \
  --aperture .004 --threads "$THREADS" --bands
./build/observatory --mesh scene/observatory.cvr2 --out renders/reproduction \
  --width 1800 --height 1200 --threads "$THREADS" --guides-only
python3 finish.py renders/reproduction
