"""Linux execution controller with bounded polling and disk-backed evidence.

No terminal streaming or notebook kernel is needed for a running job. This is a
project-local controller; it does not repair or modify the hosting chat service.
A killed renderer is restarted at a stage boundary, never described as resuming
its lost samples. Only explicit, successful exits can become 'succeeded'.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

TERMINAL = {'succeeded', 'failed', 'timed_out', 'cancelled', 'interrupted', 'resource_limit'}
MiB = 1024 * 1024
GiB = 1024 * MiB


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(4 * MiB), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, value):
    """Same-directory, fsynced replacement. No shared .tmp filename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def tail(path, lines=15, max_bytes=16384):
    """Read a bounded suffix even when a renderer produces multi-GB logs."""
    try:
        with Path(path).open('rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - max_bytes))
            return '\n'.join(f.read(max_bytes).decode('utf-8', 'replace').splitlines()[-lines:])
    except FileNotFoundError:
        return ''


def proc_info(pid):
    try:
        s = Path(f'/proc/{int(pid)}/stat').read_text()
        fields = s[s.rfind(')') + 2:].split()
        return {'pid': int(pid), 'state': fields[0], 'ppid': int(fields[1]),
                'start_ticks': int(fields[19]), 'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE')}
    except (OSError, ValueError, IndexError):
        return None


def identity(pid):
    info = proc_info(pid)
    if not info or info['state'] == 'Z':
        return None
    info.pop('rss_bytes')
    info.pop('ppid')
    info.pop('state')
    info['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    info['pid_namespace'] = os.readlink('/proc/self/ns/pid')
    return info


def alive(token):
    return isinstance(token, dict) and token == identity(token.get('pid', -1))


def process_tree(pid):
    rows = {}
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            row = proc_info(int(p.name))
            if row:
                rows[row['pid']] = row
    if pid not in rows:
        return []
    selected, frontier = [pid], [pid]
    while frontier:
        parents = set(frontier)
        frontier = [n for n, r in rows.items() if r['ppid'] in parents and n not in selected]
        selected.extend(frontier)
    return [rows[n] for n in selected]


def terminate_tree(pid, grace=1.5):
    """Stop verified descendants, including child renderers in new sessions."""
    victims = [(r['pid'], r['start_ticks']) for r in process_tree(pid)]
    # Parents first: prevent supervisors from launching replacement children.
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        for n, start in victims:
            r = proc_info(n)
            if r and r['start_ticks'] == start and n != os.getpid():
                try:
                    os.kill(n, sig)
                except ProcessLookupError:
                    pass
        if sig == signal.SIGTERM:
            end = time.monotonic() + grace
            while time.monotonic() < end:
                if not any((r := proc_info(n)) and r['start_ticks'] == st and r['state'] != 'Z' for n, st in victims):
                    break
                time.sleep(.05)


@contextlib.contextmanager
def owned_lock(path):
    """Kernel-released lock; a killed owner's leftover file is harmless.

    The inode is deliberately NOT unlinked. Unlinking a flock file permits a
    third process to lock a new inode while an existing owner holds the old one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+', encoding='utf-8') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'Another live process owns {path}') from exc
        try:
            f.seek(0)
            f.truncate()
            json.dump({'owner': identity(os.getpid()), 'acquired_at': utc()}, f)
            f.flush()
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def resource_limits():
    host = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, rest = line.split(':', 1)
        host[key] = int(rest.strip().split()[0]) * 1024
    mem = Path('/sys/fs/cgroup/memory.max')
    current = Path('/sys/fs/cgroup/memory.current')
    limit = host['MemTotal']
    if mem.exists() and mem.read_text().strip() != 'max':
        limit = min(limit, int(mem.read_text()))
    quota = len(os.sched_getaffinity(0))
    cpu = Path('/sys/fs/cgroup/cpu.max')
    if cpu.exists():
        q, period = cpu.read_text().split()
        if q != 'max':
            quota = min(quota, max(1, math.ceil(int(q) / int(period))))
    return {'memory_limit_bytes': limit,
            'cgroup_memory_current_bytes': int(current.read_text()) if current.exists() else None,
            'host_available_bytes': host.get('MemAvailable'), 'cpu_budget': quota}


def thread_environment(requested=4, base=None):
    if not 1 <= int(requested) <= 256:
        raise ValueError('Threads must be in [1, 256]')
    threads = min(int(requested), resource_limits()['cpu_budget'])
    env = dict(os.environ if base is None else base)
    env.update(OMP_NUM_THREADS=str(threads), NUMBA_NUM_THREADS=str(threads),
               OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', BLIS_NUM_THREADS='1',
               NUMEXPR_NUM_THREADS=str(threads), VECLIB_MAXIMUM_THREADS='1',
               PYTHONUNBUFFERED='1')
    return env


def doctor(project):
    project = Path(project).resolve()
    errors = []
    result = {'checked_at': utc(), 'project': str(project), 'project_exists': project.is_dir(),
              'user_id': os.getuid(), 'python': sys.executable, 'g++': shutil.which('g++'),
              'resource_limits': resource_limits()}
    try:
        with tempfile.TemporaryDirectory(prefix='.exec-probe-', dir=project) as d:
            p = Path(d) / 'roundtrip.json'
            atomic_json(p, {'verified': True})
            assert read_json(p)['verified']
            result['disk_roundtrip'] = 'passed'
    except Exception as exc:
        errors.append(f'Project is not writable: {exc}')
    try:
        p = subprocess.run([sys.executable, '-c', 'print("SUBPROCESS_OK")'], timeout=5,
                           capture_output=True, text=True, check=True)
        result['subprocess'] = p.stdout.strip()
    except Exception as exc:
        errors.append(f'Subprocess probe: {exc}')
    for rel in ['cybr_scenes.py', 'scenes.json']:
        if not (project / rel).is_file():
            errors.append(f'Missing source file: {rel}')
    result.update(errors=errors, passed=not errors)
    return result


def supervise(command, cwd, log, state_path, *, env=None, timeout=14400,
              memory_bytes=None, cancel_path=None, heartbeat=.75):
    """Synchronous worker with durable heartbeat, resource samples and exit state."""
    command = list(map(str, command))
    cwd, log, state_path = Path(cwd).resolve(), Path(log).resolve(), Path(state_path).resolve()
    if not command or not cwd.is_dir() or timeout <= 0:
        raise ValueError('Nonempty argv, existing cwd and positive timeout required')
    if memory_bytes is not None and memory_bytes <= 0:
        raise ValueError('Memory budget must be positive')
    log.parent.mkdir(parents=True, exist_ok=True)
    # A fresh attempt must not append to archived native output: several native
    # checks emit one JSON document and counters must belong to this run only.
    if log.exists():
        history = log.parent / '.execution-history' / (log.stem + '-' + uuid.uuid4().hex)
        history.mkdir(parents=True, exist_ok=False)
        for prior in {log, state_path, log.with_suffix('.command.json')}:
            if prior.is_file():
                shutil.copy2(prior, history / prior.name)
    start = time.monotonic()
    record = {'schema': 1, 'state': 'starting', 'command': command, 'cwd': str(cwd),
              'started_at': utc(), 'started_unix': time.time(), 'supervisor': identity(os.getpid()),
              'log': str(log), 'timeout_seconds': timeout, 'memory_budget_bytes': memory_bytes,
              'peak_tree_rss_bytes': 0, 'returncode': None, 'completed': False}
    atomic_json(state_path, record)
    p = None
    descendants = {}
    try:
        with log.open('wb', buffering=0) as output:
            p = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 start_new_session=True, close_fds=True)
            record.update(state='running', child=identity(p.pid), pid=p.pid)
            reason = None
            while True:
                rows = process_tree(p.pid)
                for r in rows:
                    descendants[(r['pid'], r['start_ticks'])] = True
                rss = sum(r['rss_bytes'] for r in rows)
                record.update(heartbeat_at=utc(), elapsed_seconds=time.monotonic() - start,
                              tree_rss_bytes=rss, descendant_count=max(0, len(rows)-1),
                              peak_tree_rss_bytes=max(record['peak_tree_rss_bytes'], rss),
                              log_bytes=log.stat().st_size,
                              log_silent_seconds=max(0., time.time() - log.stat().st_mtime))
                code = p.poll()
                if code is not None:
                    break
                if cancel_path and Path(cancel_path).exists():
                    reason = 'cancelled'
                elif time.monotonic() - start >= timeout:
                    reason = 'timed_out'
                elif memory_bytes and rss > memory_bytes:
                    reason = 'resource_limit'
                if reason:
                    record.update(state=reason, termination_requested_at=utc())
                    atomic_json(state_path, record)
                    terminate_tree(p.pid)
                    code = p.wait(timeout=5)
                    break
                atomic_json(state_path, record)
                time.sleep(heartbeat)
            record.update(returncode=code, state=reason or ('succeeded' if code == 0 else 'failed'))
    except BaseException as exc:
        if p is not None and p.poll() is None:
            terminate_tree(p.pid)
            p.wait(timeout=5)
        record.update(state='interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed',
                      error=f'{type(exc).__name__}: {exc}', returncode=p.returncode if p else None)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        record.update(finished_at=utc(), elapsed_seconds=time.monotonic() - start,
                      completed=record['state'] == 'succeeded', log_sha256=sha256(log) if log.exists() else None)
        # A command must not leave owned child processes working after completion.
        for n, st in descendants:
            r = proc_info(n)
            if r and r['start_ticks'] == st and r['state'] != 'Z':
                terminate_tree(n, grace=.3)
        atomic_json(state_path, record)
    return record


def run_recorded(command, cwd, log, threads=4, timeout=14400):
    """Compatibility adapter for CYBR's existing compile/render/export calls."""
    log = Path(log)
    env = thread_environment(threads)
    root = Path(__file__).resolve().parent
    env['CYBR_SURFACE_ATLAS'] = str(root / 'assets/mineral_detail.cdt')
    print(f'[{utc()}] STEP_START {log.stem}: ' + ' '.join(map(str, command)), flush=True)
    record = supervise(command, cwd, log, log.with_suffix('.execution.json'), env=env, timeout=timeout)
    print(f'[{utc()}] STEP_END {log.stem}: {record["state"]} ({record["elapsed_seconds"]:.2f}s)', flush=True)
    record.update(seconds=record['elapsed_seconds'],
                  environment={k:env[k] for k in ['OMP_NUM_THREADS','NUMBA_NUM_THREADS','OPENBLAS_NUM_THREADS','CYBR_SURFACE_ATLAS']},
                  executed_command=list(map(str, command)))
    atomic_json(log.with_suffix('.command.json'), record)
    if record['state'] != 'succeeded':
        raise RuntimeError(f"{record['state']} (exit {record['returncode']}): {log}\n{tail(log)}")
    return record


def job_directory(root, job_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', job_id) or job_id in {'.', '..'}:
        raise ValueError('Job ID must be 1–80 safe filename characters')
    return Path(root).resolve() / job_id


def job_status(root, job_id):
    folder = job_directory(root, job_id)
    spec = read_json(folder / 'spec.json')
    state = read_json(folder / 'state.json') if (folder / 'state.json').exists() else {'state':'starting', 'started_unix':spec['created_unix']}
    if state['state'] not in TERMINAL and not alive(state.get('supervisor')):
        if time.time() - state.get('started_unix', spec['created_unix']) > 10:
            # A status reader only reconciles if the original supervisor no longer
            # owns its kernel lock. This avoids racing its final status write.
            try:
                with owned_lock(folder / 'supervisor.lock'):
                    if (folder / 'state.json').exists():
                        state = read_json(folder / 'state.json')
                    if state['state'] not in TERMINAL and not alive(state.get('supervisor')):
                        if alive(state.get('child')):
                            state.update(state='interrupted', completed=False,
                                         error='Supervisor missing; stopping verified orphan child')
                            terminate_tree(state['child']['pid'])
                        else:
                            state.update(state='interrupted', completed=False,
                                         error='Supervisor/process is absent. No completion receipt exists.')
                        state['reconciled_at'] = utc()
                        atomic_json(folder / 'state.json', state)
            except RuntimeError:
                pass
    state.update(job_id=job_id, state_file=str(folder/'state.json'),
                 tail=tail(folder/'output.log'))
    return state


def start_job(root, job_id, command, cwd, threads=4, timeout=14400, memory_bytes=None):
    folder = job_directory(root, job_id)
    cwd = Path(cwd).resolve()
    if not cwd.is_dir() or not command or timeout <= 0:
        raise ValueError('Existing working directory, argv and positive timeout required')
    thread_environment(threads)  # Validate before creating a job directory.
    if memory_bytes is not None and memory_bytes <= 0:
        raise ValueError('Memory budget must be positive')
    if memory_bytes is None:
        memory_bytes = int(resource_limits()['memory_limit_bytes'] * .82)
    folder.mkdir(parents=True, exist_ok=False)
    spec = {'schema':1, 'created_at':utc(), 'created_unix':time.time(), 'job_id':job_id,
            'cwd':str(cwd), 'command':list(map(str,command)), 'threads':threads,
            'timeout':timeout, 'memory_bytes':memory_bytes}
    atomic_json(folder/'spec.json', spec)
    with (folder/'supervisor.log').open('ab', buffering=0) as output:
        p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_worker', str(folder)],
                             cwd=cwd, stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
    # Keep and reap the launcher handle without blocking short control calls.
    threading.Thread(target=p.wait, daemon=True).start()
    atomic_json(folder/'launch.json', {'pid':p.pid, 'identity':identity(p.pid), 'launched_at':utc()})
    # Only a short handshake; the expensive command is never awaited here.
    end = time.monotonic() + 1.5
    while time.monotonic() < end and not (folder/'state.json').exists() and p.poll() is None:
        time.sleep(.025)
    return job_status(root, job_id)


def worker(folder):
    folder = Path(folder).resolve()
    spec = read_json(folder/'spec.json')
    with owned_lock(folder/'supervisor.lock'):
        state = supervise(spec['command'], spec['cwd'], folder/'output.log', folder/'state.json',
                          env=thread_environment(spec['threads']), timeout=spec['timeout'],
                          memory_bytes=spec['memory_bytes'], cancel_path=folder/'cancel.request')
    return 0 if state['state'] == 'succeeded' else 1


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '_worker':
        raise SystemExit('Use execctl.py, not the worker entrypoint.')
    raise SystemExit(worker(sys.argv[2]))
