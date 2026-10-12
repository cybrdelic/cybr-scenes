#!/bin/bash
set -euo pipefail
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then
  echo "Unset MATERIAL_PATH_MAP_FILE; this portable package uses local generated assets." >&2
  exit 2
fi
case "${1:-preview}" in preview|build-only|render-only) ;;
  *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;;
esac
cd "$(dirname "$0")"
# Fail before expensive rebuilding/rendering if preview postprocessing cannot run.
if [ "${1:-preview}" != "build-only" ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to the official OIDN 2.5.1 oidnDenoise executable}"
  if [ ! -f "$OIDN_BIN" ] || [ ! -x "$OIDN_BIN" ]; then
    echo "OIDN_BIN must name an existing executable before preview work starts." >&2
    exit 2
  fi
fi
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2
mkdir -p discrete_grains_r5/{preview,receipts,deliverables,captures} far_road_r5d/bake road_scene_r6/{preview,receipts,deliverables,captures}
# Verify exact approved cache bytes; never overwrite them with a regenerated approximation.
python verify_pinned_inputs.py
if [ "${1:-preview}" != "render-only" ]; then
blender -b -t 2 --python-exit-code 1 --python discrete_grains_r5/src/build_diagnostic.py
python discrete_grains_r5/asphalt/source/generate_native4096.py
blender -b discrete_grains_r5/preview/diagnostic_d.blend -t 2 --python-exit-code 1 --python far_road_r5d/bake/bake_r5d.py
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/build_scene.py -- context 1200 32 --build-only
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_weather_layer.py
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_sediment_patches.py
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_erosion_network.py
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_eroded_ridges.py
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_shoulder_dust.py
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/relief_correction/prepare_tiled_relief_r2.py -- --source road_scene_r6/preview/road_r6_r2_dust.blend --output road_scene_r6/relief_correction/road_r6_s_coupled.blend --height discrete_grains_r5/asphalt/native4096/GeometryHeight.npy
# Serialized S bytes may vary, but its exact structural fingerprint must match.
blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_runoff_shoulder_y.py -- --source-fingerprint road_scene_r6/receipts/flow_source_fingerprint.json
fi
if [ "${1:-preview}" = "build-only" ]; then exit 0; fi
: "${OIDN_BIN:?Set OIDN_BIN to the official OIDN 2.5.1 oidnDenoise executable}"
python road_scene_r6/src/render_checkpoint_y.py
