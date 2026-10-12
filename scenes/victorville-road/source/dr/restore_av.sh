#!/bin/bash
set -euo pipefail
R=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
P="$R/packages/CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15"
cd "$P"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1
export LD_PRELOAD=/lib/x86_64-linux-gnu/libjemalloc.so.2
export MALLOC_CONF=narenas:2,dirty_decay_ms:0,muzzy_decay_ms:0,abort_conf:true
unset MATERIAL_PATH_MAP_FILE
mkdir -p discrete_grains_r5/{preview,receipts,deliverables,captures} far_road_r5d/bake road_scene_r6/{preview,receipts,deliverables,captures}
run() {
 name=$1; shift
 test ! -e "$R/logs/${name}_guard.json"
 echo "ROAD_RECOVERY_QUEUED $name"
 flock -x "${CYBR_HEAVY_LOCK:-$R/cybr-heavy.lock}" taskset -c 0,1 python3 -B "$R/helpers/run_bounded_stage.py" "$R/logs/$name.log" "$R/logs/${name}_guard.json" 900 "$@"
 echo "ROAD_RECOVERY_TERMINAL $name"
}
case "${1:-initial}" in
initial)
 run 01_r5d blender -b -t 2 --python-exit-code 1 --python discrete_grains_r5/src/build_diagnostic.py
 run 02_asphalt python3 discrete_grains_r5/asphalt/source/generate_native4096.py
 run 03_bake blender -b discrete_grains_r5/preview/diagnostic_d.blend -t 2 --python-exit-code 1 --python far_road_r5d/bake/bake_r5d.py
 run 04_scene blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/build_scene.py -- context 1200 32 --build-only
 ;;
continued)
 run 05_weather blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_weather_layer.py
 run 06_sediment blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_sediment_patches.py
 run 07_erosion blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_erosion_network.py
 run 08_ridges blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_eroded_ridges.py
 run 09_dust blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_shoulder_dust.py
 run 10_metric_relief blender -b -t 2 --python-exit-code 1 --python road_scene_r6/relief_correction/prepare_tiled_relief_r2.py -- --source road_scene_r6/preview/road_r6_r2_dust.blend --output road_scene_r6/relief_correction/road_r6_s_coupled.blend --height discrete_grains_r5/asphalt/native4096/GeometryHeight.npy
 run 11_runoff_y blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_runoff_shoulder_y.py -- --source-fingerprint road_scene_r6/receipts/flow_source_fingerprint.json
 run 12_film_z blender -b -t 2 --python-exit-code 1 --python road_scene_r6/src/prepare_runoff_film_z_portable.py
 ;;
av)
 run 13_av_raw python3 "$R/helpers/replay_av_raw.py" --package "$P" --tag av_recovery_oct12
 ;;
*) exit 2;;
esac
