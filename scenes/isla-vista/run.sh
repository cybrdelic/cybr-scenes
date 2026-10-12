#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p evidence/stages
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMBA_NUM_THREADS=2
export CYBR_LIGHT_CACHE="${CYBR_LIGHT_CACHE:-$PWD/.native-cache}"
phase="${1:-verify}"
lock="${CYBR_HEAVY_LOCK:-/tmp/cybr-heavy.lock}"
flock -w 900 "$lock" taskset -c "${CYBR_CPUS:-0,1}" python tools/run_lagoon_stage.py \
  --log "evidence/stages/${phase}.log" --receipt "evidence/stages/${phase}-guard.json" \
  --seconds 900 -- python replay.py "$@"
