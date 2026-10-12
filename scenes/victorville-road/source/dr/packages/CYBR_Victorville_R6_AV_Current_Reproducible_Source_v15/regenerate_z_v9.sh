#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-preview}" in preview|build-only|render-only) ;; *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;; esac
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then echo "Unset MATERIAL_PATH_MAP_FILE for this portable package." >&2; exit 2; fi
if [ "${1:-preview}" != "build-only" ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to the official OIDN 2.5.1 oidnDenoise executable}"
  if [ ! -f "$OIDN_BIN" ] || [ ! -x "$OIDN_BIN" ]; then echo "OIDN_BIN must be an existing executable before preview work starts." >&2; exit 2; fi
fi
python verify_pinned_inputs.py
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
if [ "${1:-preview}" != "render-only" ]; then
  bash regenerate_y.sh build-only
  # Complete pinned semantic Y prerequisite is mandatory. Never bypass a mismatch.
  blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_runoff_film_z_portable.py
fi
if [ "${1:-preview}" = "build-only" ]; then exit 0; fi
python road_scene_r6/src/render_checkpoint_z.py
