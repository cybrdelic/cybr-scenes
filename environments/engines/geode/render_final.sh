#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p output_v3
./cathedral_v3 assets/built_v3/scene.meshbin output_v3/Drowned_Geode_V3 \
  --w 1800 --h 1200 --spp 64 --adaptive --depth 24 --threads "${THREADS:-4}" \
  --seed 735041 --exposure 1.4
OPENBLAS_NUM_THREADS=1 python finish_v3.py output_v3/Drowned_Geode_V3 --exposure 1.4
