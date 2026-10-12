#!/bin/bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
JOB="$1"
MODE=$(python3 "$ROOT/capture_modes.py" mode "$JOB")
WORKBENCH_RAW=$(python3 "$ROOT/capture_modes.py" workbench "$JOB")
OUT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["output"])' "$JOB")
MARK=$(mktemp "$ROOT/.clean_start.XXXXXX")
bash "$ROOT/render.sh" "$JOB"
test "$OUT.json" -nt "$MARK"
if [ "$WORKBENCH_RAW" != yes ]; then
python3 - "$OUT.json" "$MARK" <<'PY'
import json,pathlib,sys
r=json.load(open(sys.argv[1]));marker=pathlib.Path(sys.argv[2]).stat().st_mtime_ns
assert len(r['guide_paths'])==3,'Three fresh render guides are required'
for p in map(pathlib.Path,r['guide_paths']+list(r.get('transport_paths',{}).values())):assert p.is_file() and p.stat().st_mtime_ns>marker,'Missing or stale render guide: '+str(p)
PY
fi
PIPE_ROOT=$(python3 "$ROOT/verify_pipeline_snapshot.py" "$OUT.json")
echo "VERIFIED_PIPELINE_SNAPSHOT $PIPE_ROOT"
if [ "$WORKBENCH_RAW" = yes ]; then
  "${BLENDER_BIN:-blender}" -b -t 1 --python-exit-code 1 --python "$PIPE_ROOT/oidn_image_bridge.py" -- inspect_png "$OUT.json"
  test "$OUT.native.json" -nt "$MARK"
  python3 "$ROOT/verify_pipeline_snapshot.py" "$OUT.json" >/dev/null
  python3 "$PIPE_ROOT/raw_receipt.py" "$OUT.json"
  RAW_IMAGE=$(python3 "$PIPE_ROOT/capture_modes.py" image "$JOB")
  test "$RAW_IMAGE" -nt "$MARK"; test "$RAW_IMAGE.json" -nt "$MARK"
  exit 0
fi
if [ "$MODE" = component-recombined ]; then
  COMPONENT_POLICY=$(python3 "$PIPE_ROOT/capture_modes.py" component-policy "$JOB")
  "${BLENDER_BIN:-blender}" -b -t 1 --python-exit-code 1 --python "$PIPE_ROOT/component_image_bridge.py" -- export "$OUT.json"
  D="${OUT%.png}_guides/components"
  for FILE in remainder.pfm albedo.pfm normal.pfm export_receipt.json linear_component_accounting.npz; do test "$D/$FILE" -nt "$MARK"; done
  "${OIDN_BIN:-$ROOT/tools/oidn-2.5.1.x86_64.linux/bin/oidnDenoise}" -d cpu --hdr "$D/remainder.pfm" --alb "$D/albedo.pfm" --nrm "$D/normal.pfm" -o "$D/denoised_remainder.pfm" --threads 2 --maxmem 2048 -q high -v 2 | tee "$D/oidn.log"
  test "$D/denoised_remainder.pfm" -nt "$MARK"
  if [ "$COMPONENT_POLICY" = filter_both ]; then
    test "$D/transmission.pfm" -nt "$MARK"
    "${OIDN_BIN:-$ROOT/tools/oidn-2.5.1.x86_64.linux/bin/oidnDenoise}" -d cpu --hdr "$D/transmission.pfm" --alb "$D/albedo.pfm" --nrm "$D/normal.pfm" -o "$D/denoised_transmission.pfm" --threads 2 --maxmem 2048 -q high -v 2 | tee "$D/oidn_transmission.log"
    test "$D/denoised_transmission.pfm" -nt "$MARK"
  fi
  "${BLENDER_BIN:-blender}" -b -t 1 --python-exit-code 1 --python "$PIPE_ROOT/component_image_bridge.py" -- import "$OUT.json"
  test "$D/component_receipt.json" -nt "$MARK"
  python3 "$ROOT/verify_pipeline_snapshot.py" "$OUT.json" >/dev/null
  python3 "$PIPE_ROOT/component_receipt.py" "$OUT.json"
  COMPONENT_IMAGE=$(python3 "$PIPE_ROOT/capture_modes.py" image "$JOB")
  test "$COMPONENT_IMAGE" -nt "$MARK"; test "$COMPONENT_IMAGE.json" -nt "$MARK"
  exit 0
fi
"${BLENDER_BIN:-blender}" -b -t 1 --python-exit-code 1 --python "$PIPE_ROOT/oidn_image_bridge.py" -- export "$OUT.json"
D="${OUT%.png}_guides"
for FILE in beauty.pfm albedo.pfm normal.pfm png_roundtrip_check.json guide_contract.json; do test "$D/$FILE" -nt "$MARK"; done
if [ "$MODE" = unfiltered ]; then
  python3 "$ROOT/verify_pipeline_snapshot.py" "$OUT.json" >/dev/null
  python3 "$PIPE_ROOT/raw_receipt.py" "$OUT.json"
  RAW_IMAGE=$(python3 "$PIPE_ROOT/capture_modes.py" image "$JOB")
  test "$RAW_IMAGE" -nt "$MARK"; test "$RAW_IMAGE.json" -nt "$MARK"
  exit 0
fi
"${OIDN_BIN:-$ROOT/tools/oidn-2.5.1.x86_64.linux/bin/oidnDenoise}" -d cpu --hdr "$D/beauty.pfm" --alb "$D/albedo.pfm" --nrm "$D/normal.pfm" -o "$D/denoised.pfm" --threads 2 --maxmem 2048 -q high -v 2 | tee "$D/oidn.log"
test "$D/denoised.pfm" -nt "$MARK"
"${BLENDER_BIN:-blender}" -b -t 1 --python-exit-code 1 --python "$PIPE_ROOT/oidn_image_bridge.py" -- import "$OUT.json"
test "$D/denoised_linear.exr" -nt "$MARK"
CLEAN=$(python3 - "$OUT" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]);print(p.parent/('CLEAN_OIDN_'+p.stem.removeprefix('INTERNAL_')+'.png'))
PY
)
test "$CLEAN" -nt "$MARK"
python3 "$ROOT/verify_pipeline_snapshot.py" "$OUT.json" >/dev/null
python3 "$PIPE_ROOT/clean_receipt.py" "$OUT.json"
test "$CLEAN.json" -nt "$MARK"
