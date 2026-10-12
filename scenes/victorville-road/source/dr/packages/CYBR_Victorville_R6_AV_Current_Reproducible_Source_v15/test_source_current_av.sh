#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python verify_pinned_inputs.py
python road_scene_r6/src/render_checkpoint_av.py --check-sources
python road_scene_r6/src/validate_source_current_av.py
python - <<'TESTS'
import json,subprocess,sys
from pathlib import Path
root=Path('road_scene_r6');row=json.loads((root/'receipts/integrated_render_templates_av.json').read_text())['captures'][0]
snapshot=str(root/'checkpoint_pipeline_sources'/row['pipeline_sha256'])
for generation in ('ak','al','ap','aq','av'):
    command=[sys.executable,str(root/('checkpoint_tests_'+generation)/'run_snapshot_tests.py'),'--snapshot',snapshot]
    if generation=='ak':command+=['--generation','AK']
    subprocess.run(command,check=True)
TESTS
