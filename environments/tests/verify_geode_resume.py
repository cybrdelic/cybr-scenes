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


def _matching_process(token):
    """A recycled PID never inherits ownership of an earlier child."""
    try:
        proc = psutil.Process(token['pid'])
        if proc.create_time() != token['created'] or not proc.is_running():
            return None
        if proc.status() == psutil.STATUS_ZOMBIE:
            return None
        return proc
    except psutil.NoSuchProcess:
        return None


def _observe(owned, root, include_children):
    for token in tuple(owned.values()):
        proc = _matching_process(token)
        if proc is None or not include_children:
            continue
        try:
            children = proc.children(recursive=True)
        except psutil.NoSuchProcess:
            continue
        for child in children:
            try:
                created = child.create_time()
                if created < root['created']:
                    raise RuntimeError('Descendant predates owned root')
                owned.setdefault((child.pid, created), {
                    'pid': child.pid, 'created': created, 'parent': child.ppid()})
            except psutil.NoSuchProcess:
                continue
    live = []
    for token in owned.values():
        proc = _matching_process(token)
        if proc is None:
            continue
        try:
            live.append((token, proc, proc.memory_info().rss))
        except psutil.NoSuchProcess:
            continue
    return live


def _cleanup_owned(owned, root, include_children, grace=2):
    """Freeze observed owners before finding late children; signal identities only."""
    def captured():
        try:
            return _observe(owned, root, include_children)
        except Exception:
            # A failed observation must not prevent cleanup of known identities.
            result = []
            for token in owned.values():
                proc = _matching_process(token)
                if proc is not None:
                    result.append((token, proc, 0))
            return result

    # Repeated discovery catches children spawned during the first observation.
    for _ in range(2):
        for _, proc, _ in captured():
            try:
                proc.suspend()
            except psutil.NoSuchProcess:
                pass
    live = captured()
    processes = []
    for token, _, _ in reversed(live):
        proc = _matching_process(token)
        if proc is not None:
            try:
                proc.terminate()
                # POSIX SIGTERM cannot complete while a process is stopped.
                if os.name != 'nt':
                    proc.resume()
                processes.append(proc)
            except psutil.NoSuchProcess:
                pass
    _, alive = psutil.wait_procs(processes, timeout=grace)
    for proc in alive:
        try:
            token = owned.get((proc.pid, proc.create_time()))
            if token is not None and _matching_process(token) is not None:
                proc.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=grace)
    return [token for token in owned.values() if _matching_process(token) is not None]


def run(command, directory, env, name, expected=0, *, preflight_bytes=PREFLIGHT,
        floor_bytes=FLOOR, rss_limit_bytes=RSS_LIMIT, process_tree=False,
        sample_interval=1.0, timeout_seconds=None):
    """Guard verification commands; tree mode sums and owns observed descendants.

    This is not a security sandbox. Programs must not deliberately escape their
    ancestry between samples. All captured identities survive parent exit in the
    ownership ledger, and remaining children make completion fail closed.
    """
    if min(preflight_bytes, floor_bytes) < 0 or rss_limit_bytes <= 0 or sample_interval <= 0:
        raise ValueError('Invalid memory or polling limits')
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError('Timeout must be positive')
    directory = Path(directory)
    if Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('Receipt name must be a simple filename')
    receipt = directory / (name + '.json')
    if receipt.exists():
        raise FileExistsError(f'Existing receipt preserved: {receipt}')
    available = psutil.virtual_memory().available
    if available < preflight_bytes:
        raise RuntimeError(f'Need {preflight_bytes} available bytes, observed {available}; no process launched')
    record = {'argv': [str(x) for x in command], 'samples': [], 'expected_exit': expected,
              'completed': False, 'process_tree': process_tree, 'owned': [],
              'limits': {'preflight_bytes': preflight_bytes, 'floor_bytes': floor_bytes,
                         'rss_limit_bytes': rss_limit_bytes, 'timeout_seconds': timeout_seconds},
              'peak_rss_bytes': 0}
    started = time.monotonic()
    owned = {}; root = None; proc = None
    with (directory / (name + '.log')).open('x', encoding='utf-8') as log:
        try:
            proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            record['pid'] = proc.pid
            root = {'pid': proc.pid, 'created': psutil.Process(proc.pid).create_time(),
                    'parent': os.getpid()}
            owned[(root['pid'], root['created'])] = root
            print(json.dumps({'phase': name, 'pid': proc.pid}), flush=True)
            while True:
                live = _observe(owned, root, process_tree)
                rss = sum(row[2] for row in live)
                free = psutil.virtual_memory().available
                elapsed = time.monotonic()-started
                record['peak_rss_bytes'] = max(record['peak_rss_bytes'], rss)
                record['samples'].append({'seconds': round(elapsed, 3), 'rss': rss,
                    'host_available': free, 'pids': [row[0]['pid'] for row in live]})
                if rss > rss_limit_bytes or free < floor_bytes:
                    record['guard_stop'] = 'rss_limit' if rss > rss_limit_bytes else 'host_floor'
                    break
                if timeout_seconds is not None and elapsed > timeout_seconds:
                    record['guard_stop'] = 'timeout'
                    break
                if proc.poll() is not None:
                    if process_tree and any(row[0]['pid'] != proc.pid for row in live):
                        record['guard_stop'] = 'parent_exited_with_live_children'
                    break
                time.sleep(sample_interval)
        except BaseException as error:
            record['supervisor_exception'] = type(error).__name__
            raise
        finally:
            if root is not None and (record.get('guard_stop') or record.get('supervisor_exception')):
                record['cleanup_remaining'] = _cleanup_owned(owned, root, process_tree)
            if proc is not None:
                record['exit'] = proc.wait(timeout=5)
            record['owned'] = list(owned.values())
            record['seconds'] = time.monotonic()-started
            record['completed'] = (not record.get('guard_stop') and
                not record.get('supervisor_exception') and record.get('exit') == expected)
            with receipt.open('x', encoding='utf-8') as stream:
                json.dump(record, stream, indent=2)
    if not record['completed']:
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
