#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOCK="${DH_HEAVY_LOCK:-${CYBR_HEAVY_LOCK:-/tmp/cybr-heavy.lock}}"
OUT="${DH_OUTPUT_DIR:-$ROOT/output}"
mkdir -p "$OUT"
flock -x "$LOCK" python "$ROOT/run_bounded_stage.py" "$OUT/regeneration.log" "$OUT/regeneration_guard.json" 180 env OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 DH_OUTPUT_DIR="$OUT" python "$ROOT/regenerate_two_specimens.py"
