#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
action="${1:-}"
shift || true
if [[ "$action" == setup ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt ../vendor/light-scene-compat
  exit
fi
PY="${CYBR_PYTHON:-$ROOT/.venv/bin/python}"
# Pin CPU arithmetic before the first NumPy import, including direct build runs.
export OPENBLAS_CORETYPE=Haswell
export NPY_DISABLE_CPU_FEATURES=AVX512F,AVX512CD,AVX512_KNL,AVX512_KNM,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL,AVX512_SPR
"$PY" tools/check_replay_cpu_profile.py evidence/whole-iv-recovery-stages/CPU_PROFILE.json
export CYBR_LIGHT_CACHE="$ROOT/native-cache"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMBA_NUM_THREADS=2
export CYBR_HEAVY_LOCK="${CYBR_HEAVY_LOCK:-$ROOT/../cybr-heavy.lock}"
export PYTHONPATH="$ROOT:$ROOT/tools/installed_light_bootstrap:$ROOT/whole-iv-vendor${PYTHONPATH:+:$PYTHONPATH}"
case "$action" in
  fetch|verify) "$PY" whole_inputs.py "$action"; "$PY" tools/link_installed_runtime.py ;;
  coastal) mkdir -p evidence/input-guards; flock -w 1800 "$CYBR_HEAVY_LOCK" taskset -c 0,1 "$PY" tools/run_lagoon_stage.py --log evidence/input-guards/coastal.log --receipt evidence/input-guards/coastal.json --seconds 900 -- "$PY" whole_inputs.py coastal ;;
  build) "$PY" tools/link_installed_runtime.py; "$PY" tools/recover_whole_iv_stages.py --start "${1:-1}" --end "${2:-64}" ;;
  repair-path-uv) mkdir -p evidence/input-guards; flock -w 1800 "$CYBR_HEAVY_LOCK" taskset -c 0,1 "$PY" tools/run_lagoon_stage.py --log evidence/input-guards/uv-rebase.log --receipt evidence/input-guards/uv-rebase.json --seconds 900 -- "$PY" tools/replay_retained_iv_script.py rebase_recovered_path_uv.py ;;
  facades-v2) "$PY" tools/replay_facades_v2.py "$@" ;;
  hedges-v1) "$PY" tools/replay_mapped_hedges_v1.py "$@" ;;
  profile-sabado) "$PY" tools/replay_sabado_profile.py "$@" ;;
  frontage) view="${1:?Choose sabado or del-playa}"; mkdir -p evidence/input-guards; flock -w 1800 "$CYBR_HEAVY_LOCK" taskset -c 0,1 "$PY" tools/run_lagoon_stage.py --log "evidence/input-guards/$view.log" --receipt "evidence/input-guards/$view.json" --seconds 900 -- "$PY" tools/replay_retained_iv_script.py capture_recovered_frontages.py "$view" --width 600 --spp 32 --street-trees ;;
  *) echo 'Usage: ./run.sh setup|fetch|verify|coastal|build [start end]|repair-path-uv|frontage sabado|frontage del-playa|profile-sabado build|profile-sabado render [--spp 32|128]|facades-v2 build|facades-v2 render [--spp 32|128]|facades-v2 close|hedges-v1 build|hedges-v1 render|hedges-v1 baseline' >&2; exit 2 ;;
esac
