#!/usr/bin/env python3
"""Replay pinned AP progress captures; strict inherited Z admission stays on.

Default is AP context only; the AP detail is an explicit diagnostic. Source checking never launches
Blender. A replay is not proof of a fresh complete clean-directory rebuild.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from render_checkpoint_ah import (ROOT, digest, require, local_path, verify_lock,
                                  stage_pipeline as inherited_stage_pipeline, build_job, admit_scene)

TEMPLATES = ROOT / 'receipts/integrated_render_templates_ap.json'


VEGETATION_HELPERS = ('layered_scrub_ap.py', 'desert_scrub.py')

def stage_pipeline(row, runtime, root=ROOT):
    """Keep captured sources exact, including AP's sibling vegetation lookup."""
    import shutil
    pipeline = inherited_stage_pipeline(row, runtime, root=root)
    if row.get('generation') == 'AP':
        vegetation = pipeline.parent / 'vegetation'
        vegetation.mkdir(exist_ok=False)
        for name in VEGETATION_HELPERS:
            expected = row['captured_pipeline_files_sha256'][name]
            source = root / 'checkpoint_pipeline_sources' / row['pipeline_sha256'] / name
            require(digest(source) == expected, 'AP vegetation source mismatch: ' + name)
            shutil.copyfile(source, vegetation / name)
            require(digest(vegetation / name) == expected, 'AP vegetation lookup mismatch: ' + name)
    return pipeline


def selected_rows(template, role, name=None):
    rows = template['captures']
    if name:
        result = [r for r in rows if r['name'] == name]
    elif role == 'latest':
        result = [r for r in rows if r.get('generation') == 'AP' and r.get('default_latest') is True]
    else:
        result = [r for r in rows if role in ('all', r['role'])]
    require(bool(result), 'No packaged capture matches that selection')
    for row in result:
        cap = row['settings']['rss_cap_mib']
        require(type(cap) is int and 0 < cap <= 4480, 'Unsupported declared capture cap')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--role', default='latest', help='latest, all, or a role listed by --check-sources')
    p.add_argument('--capture', help='Exact historical capture name; overrides --role')
    p.add_argument('--tag', default='ap_context_rebuilt')
    p.add_argument('--source', type=Path, default=ROOT / 'preview/road_r6_z_runoff_film.blend')
    p.add_argument('--check-sources', action='store_true')
    args = p.parse_args()
    require(not os.environ.get('MATERIAL_PATH_MAP_FILE'), 'Unset MATERIAL_PATH_MAP_FILE')
    verify_lock()
    template = json.loads(TEMPLATES.read_text())
    old_template = json.loads((ROOT/'receipts/integrated_render_templates_ah.json').read_text())
    require(template['source_admission'] == old_template['source_admission'],
            'AP admission must be the exact inherited strict Z contract')
    rows = selected_rows(template, args.role, args.capture)
    if args.check_sources:
        print(json.dumps(dict(source_lock_passed=True, exact_inherited_Z_admission=True,
            captures=[dict(name=r['name'],role=r['role'],cap_MiB=r['settings']['rss_cap_mib'],
                           status=r.get('status','historical capture'))
                      for r in template['captures']],
            selected=[r['name'] for r in rows], end_to_end_rebuild_verified=False)))
        return
    require(args.tag.replace('_', '').replace('-', '').isalnum(), 'Use an alphanumeric run tag')
    oidn = os.environ.get('OIDN_BIN', '')
    require(oidn and Path(oidn).is_file() and os.access(oidn, os.X_OK),
            'Set OIDN_BIN to the official OIDN 2.5.1 oidnDenoise executable')
    source = args.source.resolve()
    require(source.is_file(), 'Build the inherited Z prerequisite first')
    for row in rows:
        for relocation in row.get('input_relocations', []):
            path = local_path(relocation['package_path'])
            require(path.is_file() and digest(path) == relocation['sha256'],
                    'Generate the exact native input before admission: ' + relocation['package_path'])
    run = ROOT/'captures'/args.tag
    run.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
    scene_sha, admission = admit_scene(source, run, env)
    for row in rows:
        capture = run/row['role'];capture.mkdir(exist_ok=False)
        pipeline = stage_pipeline(row,capture/'runtime')
        job = build_job(row,source,scene_sha,capture)
        job_path = capture/'job.json';job_path.write_text(json.dumps(job,indent=2)+'\n')
        receipt = capture/'resource_receipt.json'
        subprocess.run([sys.executable,str(pipeline/'bounded_clean_run.py'),str(job_path),
                        str(capture/'run.log'),str(receipt),str(job['rss_cap_mib'])],env=env,check=True)
        result=json.loads(receipt.read_text())
        require(result.get('resource_contract_passed') is True and result.get('exit_code') == 0,
                'Capture failed its resource contract; retain the evidence')
        clean=capture/'CLEAN_OIDN_PANEL.png';report=json.loads(clean.with_suffix('.png.json').read_text())
        require(report['pipeline']['sha256']==row['pipeline_sha256'],'Replay source differs from pinned snapshot')
        require(report['source_sha256']==scene_sha==digest(source),'Source changed during render')
        ready=dict(role=row['role'],path=str(clean),bytes=clean.stat().st_size,sha256=digest(clean),
                   source_sha256=scene_sha,semantic_source_admission=admission,
                   historical_capture=row['name'],status='Fresh actual render; separate visual review required')
        (capture/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
        print(json.dumps(ready),flush=True)

if __name__=='__main__':main()
