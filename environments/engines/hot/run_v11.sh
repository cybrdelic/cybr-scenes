#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=5
python cybr-geo/examples/desert_hot_springs/render.py --out output --stem final --width 1920 --height 1280 --spp 128 --water-spp 320 --depth 12 --no-glb --no-clouds --indirect-clamp 0 --sun=-0.80,0.40,0.28 --exposure 1.90 --white-balance 5750 --opaque-filter-strength .50
python cybr-geo/examples/desert_hot_springs/run_checks_v11.py --out output/tests
python cybr-geo/examples/desert_hot_springs/verify_v11.py --out output --views final
OPENCV_IO_ENABLE_OPENEXR=1 python cybr-geo/examples/desert_hot_springs/export_exr.py output/final.pfm output/final_linear.exr
