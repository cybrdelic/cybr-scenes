#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-preview}" in preview|build-only|render-only) ;; *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;; esac
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then echo "Unset MATERIAL_PATH_MAP_FILE." >&2; exit 2; fi
python road_scene_r6/src/render_checkpoint_av.py --check-sources
if [ "${1:-preview}" != build-only ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to official OIDN 2.5.1 oidnDenoise}"
  test -f "$OIDN_BIN" && test -x "$OIDN_BIN"
fi
if [ "${1:-preview}" != render-only ]; then bash regenerate_z_v9.sh build-only; fi
if [ "${1:-preview}" != build-only ]; then python road_scene_r6/src/render_checkpoint_av.py; fi
