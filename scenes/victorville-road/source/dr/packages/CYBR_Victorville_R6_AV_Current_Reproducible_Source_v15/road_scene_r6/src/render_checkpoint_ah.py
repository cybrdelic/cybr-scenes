#!/usr/bin/env python3
"""Replay packaged component previews with pinned helpers in a portable layout.

Captured source files are never patched. Each fresh run stages its own pipeline
and sibling src directories, so the captured parent.parent/src lookup is valid.
This is a replay tool, not evidence that a fresh end-to-end rebuild has passed.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT.parent
TEMPLATES = ROOT / 'receipts/integrated_render_templates_ah.json'
# These inherited builders write fresh output reports at historical filenames.
# They are not build inputs. Original evidence is preserved and verified separately.
REGENERATED_REPORTS = {
    'discrete_grains_r5/receipts/geometry_d.json',
    'road_scene_r6/receipts/scene_e.json',
    'road_scene_r6/receipts/weather_layer_i.json',
    'road_scene_r6/receipts/sediment_patches_k.json',
    'road_scene_r6/receipts/erosion_network_l.json',
    'road_scene_r6/receipts/rocky_ridges_o.json',
    'road_scene_r6/receipts/shoulder_dust_r2.json',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_path(relative):
    path = (PACKAGE / relative).resolve()
    require(path.is_relative_to(PACKAGE.resolve()), 'Package path escapes its root')
    return path


def verify_lock():
    lock = json.loads((PACKAGE / 'SOURCE_LOCK.json').read_text())
    for relative, expected in lock['files'].items():
        immutable = ('historical_receipts_ah/' + relative
                     if relative in REGENERATED_REPORTS else relative)
        if relative in REGENERATED_REPORTS:
            require(lock['files'].get(immutable) == expected,
                    'Historical output report preservation mismatch: ' + relative)
        path = local_path(immutable)
        require(path.is_file() and not path.is_symlink(), 'Missing source input: ' + relative)
        require(digest(path) == expected, 'Source lock mismatch: ' + relative)
    return lock


def stage_pipeline(row, runtime, root=ROOT):
    """No Blender work. Copy the exact source snapshot and verify each new copy."""
    snapshot = root / 'checkpoint_pipeline_sources' / row['pipeline_sha256']
    pipeline = runtime / 'pipeline'
    helpers = runtime / 'src'
    pipeline.mkdir(parents=True, exist_ok=False)
    helpers.mkdir(exist_ok=False)
    for name, expected in row['pipeline_files_sha256'].items():
        require(Path(name).name == name, 'Snapshot names must be flat')
        source = snapshot / name
        require(digest(source) == expected, 'Captured snapshot mismatch: ' + name)
        target = pipeline / name
        shutil.copyfile(source, target)
        target.chmod(0o755 if name.endswith('.sh') else 0o644)
        require(digest(target) == expected, 'Staged snapshot mismatch: ' + name)
        if name in row['component_helper_names']:
            shutil.copyfile(source, helpers / name)
            require(digest(helpers / name) == expected, 'Staged helper mismatch: ' + name)
    require(set(row['component_helper_names']) <= set(row['captured_pipeline_files_sha256']),
            'A helper was not part of the captured pipeline')
    captured = row['captured_pipeline_files_sha256']
    calculated = hashlib.sha256(json.dumps(captured, sort_keys=True).encode()).hexdigest()
    require(calculated == row['pipeline_sha256'], 'Captured manifest digest mismatch')
    # Prove the lookup used by the unmodified captured render.py resolves here.
    for name in row['component_helper_names']:
        require(digest(pipeline.parent / 'src' / name) == captured[name],
                'Captured parent.parent/src resolution mismatch: ' + name)
    (pipeline / 'manifest.json').write_text(json.dumps(captured, indent=2) + '\n')
    return pipeline


def build_job(row, scene, scene_sha, capture):
    job = copy.deepcopy(row['settings'])
    job.update(source=str(scene), source_sha256=scene_sha,
               output=str(capture / 'INTERNAL_PANEL.png'))
    for relocation in row.get('input_relocations', []):
        path = local_path(relocation['package_path'])
        require(path.is_file() and digest(path) == relocation['sha256'],
                'Generated input differs from captured input: ' + relocation['package_path'])
        cursor = job
        for key in relocation['job_key_path'][:-1]:
            cursor = cursor[key]
        cursor[relocation['job_key_path'][-1]] = str(path)
    return job


def admit_scene(scene, run, env):
    before = digest(scene)
    receipt = run / 'source_admission.json'
    command = [os.environ.get('BLENDER_BIN', 'blender'), '-b', '-t', '2',
               '--python-exit-code', '1', '--python',
               str(ROOT / 'src/validate_checkpoint_source_ah.py'), '--',
               '--source', str(scene), '--receipt', str(receipt)]
    # Validation-only never changes the source or executes component/model code.
    start = time.monotonic()
    peak = 0.0
    reason = None
    with (run / 'source_admission.log').open('x') as log:
        process = subprocess.Popen(command, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        while process.poll() is None:
            listing = subprocess.run(['ps','-eo','pid=,ppid=,rss='],
                                     capture_output=True, text=True, check=True)
            rows = [tuple(map(int, line.split())) for line in listing.stdout.splitlines()]
            owned = {process.pid}
            for _ in range(16):
                expanded = owned | {pid for pid, parent, rss in rows if parent in owned}
                if expanded == owned:
                    break
                owned = expanded
            peak = max(peak, sum(rss for pid,parent,rss in rows if pid in owned) / 1024)
            if peak > 4096:
                reason = 'Admission RSS cap exceeded'
            elif time.monotonic() - start > 600:
                reason = 'Admission time cap exceeded'
            if reason:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(.25)
        code = process.wait()
    kernel_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    passed = code == 0 and reason is None and max(peak,kernel_peak) <= 4096
    resources = dict(exit_code=code,stop_reason=reason,peak_process_tree_RSS_MiB=peak,
                     kernel_max_child_RSS_MiB=kernel_peak,RSS_cap_MiB=4096,CPU_threads=2,
                     elapsed_seconds=time.monotonic()-start,resource_contract_passed=passed)
    (run / 'source_admission_resources.json').write_text(json.dumps(resources,indent=2)+'\n')
    require(passed, 'Source admission failed its resource contract; preserve the run evidence')
    result = json.loads(receipt.read_text())
    require(result['semantic_match'] is True and result['scene_written'] is False,
            'Strict source admission did not pass')
    require(result['actual_source_sha256'] == before == digest(scene),
            'Source changed during admission')
    return before, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', default='all', help='all, edge, baseline, or context if packaged')
    parser.add_argument('--tag', default='components_rebuilt')
    parser.add_argument('--source', type=Path, default=ROOT / 'preview/road_r6_z_runoff_film.blend')
    parser.add_argument('--check-sources', action='store_true',
                        help='Verify source lock only; no build, scene load, or render')
    args = parser.parse_args()
    require(not os.environ.get('MATERIAL_PATH_MAP_FILE'), 'Unset MATERIAL_PATH_MAP_FILE')
    verify_lock()
    template = json.loads(TEMPLATES.read_text())
    if args.check_sources:
        print(json.dumps(dict(source_lock_passed=True, captures=[x['name'] for x in template['captures']],
                              end_to_end_rebuild_verified=False)))
        return
    rows = [r for r in template['captures'] if args.role in ('all', r['role'])]
    require(bool(rows), 'No packaged capture has that role')
    require(args.tag.replace('_', '').replace('-', '').isalnum(), 'Use an alphanumeric run tag')
    oidn = os.environ.get('OIDN_BIN', '')
    require(oidn and Path(oidn).is_file() and os.access(oidn, os.X_OK),
            'Set OIDN_BIN to the official OIDN 2.5.1 oidnDenoise executable')
    source = args.source.resolve()
    require(source.is_file(), 'Build the Z prerequisite first')
    for row in rows:
        for relocation in row.get('input_relocations', []):
            path = local_path(relocation['package_path'])
            require(path.is_file() and digest(path) == relocation['sha256'],
                    'Generate the exact native input before admission: ' + relocation['package_path'])
    run = ROOT / 'captures' / args.tag
    run.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    scene_sha, admission = admit_scene(source, run, env)
    for row in rows:
        capture = run / row['role']
        capture.mkdir(exist_ok=False)
        pipeline = stage_pipeline(row, capture / 'runtime')
        job = build_job(row, source, scene_sha, capture)
        job_path = capture / 'job.json'
        job_path.write_text(json.dumps(job, indent=2) + '\n')
        resource = capture / 'resource_receipt.json'
        subprocess.run([sys.executable, str(pipeline / 'bounded_clean_run.py'), str(job_path),
                        str(capture / 'run.log'), str(resource), str(job['rss_cap_mib'])],
                       env=env, check=True)
        result = json.loads(resource.read_text())
        require(result.get('resource_contract_passed') is True and result.get('exit_code') == 0,
                'Render failed its resource contract; retain this run for diagnosis')
        clean = capture / 'CLEAN_OIDN_PANEL.png'
        clean_receipt = json.loads(clean.with_suffix('.png.json').read_text())
        require(clean_receipt['pipeline']['sha256'] == row['pipeline_sha256'],
                'Fresh capture used different code from the selected historical snapshot')
        require(clean_receipt['source_sha256'] == scene_sha == digest(source),
                'Source changed during render')
        ready = dict(role=row['role'], path=str(clean), bytes=clean.stat().st_size,
                     sha256=digest(clean), source_sha256=scene_sha,
                     semantic_source_admission=admission, historical_capture=row['name'],
                     status='Fresh actual render; separate visual review required')
        (capture / 'ready.json').write_text(json.dumps(ready, indent=2) + '\n')
        print(json.dumps(ready), flush=True)


if __name__ == '__main__':
    main()
