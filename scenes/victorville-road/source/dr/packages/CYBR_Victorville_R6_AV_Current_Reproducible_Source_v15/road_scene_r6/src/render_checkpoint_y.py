#!/usr/bin/env python3
"""Replay only the packaged Y preview jobs using their exact captured pipelines.

No implicit native or 4K render. Requires a built Y scene and OIDN_BIN. A fresh
run produces fresh receipts; the historical evidence is never overwritten.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--role', choices=('all', 'lenses', 'context'), default='all')
    p.add_argument('--tag', default='y_rebuilt')
    a = p.parse_args()
    if not a.tag.replace('_', '').replace('-', '').isalnum():
        raise ValueError('Tag must be an alphanumeric name with optional _ or -')
    if os.environ.get('MATERIAL_PATH_MAP_FILE'):
        raise ValueError('Unset MATERIAL_PATH_MAP_FILE for this portable checkpoint')
    oidn = os.environ.get('OIDN_BIN')
    if not oidn or not Path(oidn).is_file() or not os.access(oidn, os.X_OK):
        raise ValueError('Set OIDN_BIN to the official OIDN 2.5.1 oidnDenoise executable')
    scene = ROOT / 'preview/road_r6_y_wet_connected.blend'
    scene_sha = digest(scene)
    templates = json.loads((ROOT / 'receipts/y_render_templates.json').read_text())
    env = dict(os.environ, OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    for row in templates['captures']:
        if a.role not in ('all', row['role']):
            continue
        pipeline = ROOT / 'checkpoint_pipeline_sources' / row['pipeline_sha256']
        for name, expected in row['pipeline_files_sha256'].items():
            if digest(pipeline / name) != expected:
                raise RuntimeError('Checkpoint pipeline changed: ' + name)
        name = a.tag + '_' + row['role'] + '_preview'
        capture = ROOT / 'captures' / name
        capture.mkdir(parents=True, exist_ok=False)
        job = dict(row['settings'], source=str(scene), source_sha256=scene_sha,
                   output=str(capture / 'INTERNAL_PANEL.png'))
        (capture / 'job.json').write_text(json.dumps(job, indent=2) + '\n')
        resource = capture / 'resource_receipt.json'
        subprocess.run([sys.executable, str(pipeline / 'bounded_clean_run.py'),
                        str(capture / 'job.json'), str(capture / 'run.log'),
                        str(resource), str(job['rss_cap_mib'])], env=env, check=True)
        result = json.loads(resource.read_text())
        if result.get('resource_contract_passed') is not True or result.get('exit_code') != 0:
            raise RuntimeError('Render did not satisfy the resource contract; preserve its evidence')
        clean = capture / 'CLEAN_OIDN_PANEL.png'
        target = ROOT / 'preview' / (name + '.png')
        if target.exists():
            raise FileExistsError('Preserve existing preview: ' + str(target))
        shutil.copy2(clean, target)
        ready = dict(path=str(target), bytes=target.stat().st_size, sha256=digest(target),
                     scene_sha256=scene_sha, resolution=[job['width'], job['height']],
                     samples=job['samples'], status='Fresh actual render; visual review remains separate')
        (ROOT / 'receipts' / (name + '_ready.json')).write_text(json.dumps(ready, indent=2) + '\n')
        print(json.dumps(ready), flush=True)

if __name__ == '__main__':
    main()
