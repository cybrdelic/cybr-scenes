#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
export MALLOC_CONF=narenas:2,dirty_decay_ms:0,muzzy_decay_ms:0,abort_conf:true
export LD_PRELOAD=/lib/x86_64-linux-gnu/libjemalloc.so.2
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
PKG="$ROOT/unpacked/CYBR_Victorville_CB_Current_Source_Extension_v1"
AV="$ROOT/unpacked/CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15/road_scene_r6/captures/av_recovery_oct12/av_outward/ASSEMBLED_SCENE_AV.blend"
case "${1:-}" in
 ca)
 flock -x "${CYBR_HEAVY_LOCK:-$ROOT/cybr-heavy.lock}" taskset -c 0,1 python3 "$ROOT/helpers/run_bounded_stage.py" "$ROOT/logs/14_ca_payload.log" "$ROOT/logs/14_ca_payload_guard.json" 480 python3 -B "$PKG/ca_source/road_scene_r6/src/regenerate_metric_pavement_ca.py" --av-scene "$AV" --output-dir "$ROOT/generated_ca"
 ;;
 cb)
 flock -x "${CYBR_HEAVY_LOCK:-$ROOT/cybr-heavy.lock}" taskset -c 0,1 python3 "$ROOT/helpers/run_bounded_stage.py" "$ROOT/logs/15_cb_payload.log" "$ROOT/logs/15_cb_payload_guard.json" 300 python3 -B "$PKG/road_scene_r6/src/regenerate_continuous_edge_cb.py" --ca-data "$ROOT/generated_ca" --height "$PKG/inputs/GeometryHeight.npy" --output-dir "$ROOT/generated_cb"
 ;;
 *) echo 'Select exactly one separately locked stage: ca or cb' >&2; exit 2;;
esac
