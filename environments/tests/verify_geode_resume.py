"""Opt-in full-original-geometry resume parity. Requires generated Geode inputs.

Runs serially under the same memory limits as the original render supervisor.
This is a comparison harness, not a substitute scene or final image delivery.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

RAW = ('.pfm', '_reflection.pfm', '_volume.pfm', '.ppm', '.guides',
       '_reflection.guides', '_primary.guides', '.samples', '.spectral')
PNG = ('.png', '_unfiltered.png', '_reflection.png', '_volume.png',
       '_transmission_and_surfaces.png')
PREFLIGHT = 3 * 1024**3
FLOOR = 805306368
RSS_LIMIT = 2500000000


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, directory, env, name, expected=0):
    available = psutil.virtual_memory().available
    if available < PREFLIGHT:
        raise RuntimeError(f'Need {PREFLIGHT} available bytes, observed {available}; no process launched')
    record = {'argv': [str(x) for x in command], 'samples': [], 'expected_exit': expected}
    started = time.monotonic()
    with (directory / (name + '.log')).open('x', encoding='utf-8') as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        record['pid'] = proc.pid
        print(json.dumps({'phase': name, 'pid': proc.pid}), flush=True)
        owned = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                rss = owned.memory_info().rss
            except psutil.NoSuchProcess:
                break
            free = psutil.virtual_memory().available
            record['samples'].append({'seconds': round(time.monotonic()-started, 3),
                                      'rss': rss, 'host_available': free})
            if rss > RSS_LIMIT or free < FLOOR:
                record['guard_stop'] = True
                owned.terminate()
                break
            time.sleep(1)
        record['exit'] = proc.wait()
    record['seconds'] = time.monotonic()-started
    (directory / (name + '.json')).write_text(json.dumps(record, indent=2))
    if record.get('guard_stop') or record['exit'] != expected:
        raise RuntimeError(f'{name} did not finish as required; partial files retained')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('reference', 'renderer', 'mesh', 'atlas', 'source-root', 'output'):
        parser.add_argument('--' + option, required=True, type=Path)
    args = parser.parse_args()
    for key, value in vars(args).items():
        setattr(args, key, value.resolve())
    # Every invocation owns a new directory; previous proof/partials are retained.
    args.output.mkdir(parents=False, exist_ok=False)
    env = os.environ.copy()
    env.update(CYBR_SURFACE_ATLAS=str(args.atlas), OMP_NUM_THREADS='4',
               OPENBLAS_NUM_THREADS='1')
    finish = args.source_root / 'environments/engines/geode/finish_v3.py'
    proof = {'purpose': 'Exact resumed original Geode, no substitute geometry',
             'reference_binary_sha256': sha(args.reference),
             'resume_binary_sha256': sha(args.renderer), 'mesh_sha256': sha(args.mesh),
             'atlas_sha256': sha(args.atlas), 'finisher_sha256': sha(finish),
             'textures': {p.name: sha(p) for p in sorted((args.mesh.parent/'textures').glob('*.cvtex'))},
             'cases': []}
    for width, height, stop in ((480, 320, 160), (96, 19, 16)):
        case = args.output / f'{width}x{height}'
        case.mkdir()
        baseline, resumed = case/'baseline', case/'resumed'
        baseline.mkdir()
        resumed.mkdir()
        common = ['--w', str(width), '--h', str(height), '--spp', '16', '--depth', '24',
                  '--threads', '4', '--seed', '735041', '--exposure', '1.4']
        before = [str(args.reference), str(args.mesh), str(baseline/'hero'), *common]
        after = [str(args.renderer), str(args.mesh), str(resumed/'hero'), *common,
                 '--source-root', str(args.source_root), '--checkpoint-dir', str(resumed/'checkpoints')]
        run(before, baseline, env, 'reference')
        run(after + ['--stop-after-checkpoint', str(stop)], resumed, env, 'interrupted', 75)
        assert not (resumed/'hero.json').exists(), 'Interrupted output must not be advertised as final'
        # Native CLI must reject a changed numerical setting before BVH loading.
        changed = after + ['--resume', '--spp', '17']
        run(changed, resumed, env, 'wrong-config', 1)
        rejected = (resumed/'wrong-config.log').read_text()
        assert 'identity mismatch' in rejected and 'BVH equivalence' not in rejected
        run(after + ['--resume'], resumed, env, 'resumed')
        for directory in (baseline, resumed):
            run([sys.executable, str(finish), str(directory/'hero'), '--exposure', '1.4'],
                directory, env, 'finish')
        files = {}
        for suffix in RAW + PNG:
            left, right = baseline/('hero'+suffix), resumed/('hero'+suffix)
            files[suffix] = {'before': sha(left), 'after': sha(right),
                             'bytes': right.stat().st_size()}
            assert files[suffix]['before'] == files[suffix]['after'], f'Byte mismatch {suffix}'
        a, b = (json.loads((d/'hero.json').read_text()) for d in (baseline, resumed))
        a.pop('seconds'); b.pop('seconds')
        assert a == b, 'Native/finished metadata differs beyond elapsed time'
        assert b['nonfinite_path_samples'] == 0
        proof['cases'].append({'width': width, 'height': height, 'spp': 16, 'stop_row': stop,
                               'metadata_equal_except_seconds': True, 'files': files})
        (args.output/'comparison.json').write_text(json.dumps(proof, indent=2))
    proof['all_bit_exact'] = True
    (args.output/'comparison.json').write_text(json.dumps(proof, indent=2))
    print(json.dumps({'all_bit_exact': True, 'cases': len(proof['cases'])}), flush=True)


if __name__ == '__main__':
    main()
