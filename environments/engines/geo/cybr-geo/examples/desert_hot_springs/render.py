"""Build, compile, trace and finish the actual CYBR GEO desert scene.

This entry point is deliberately separate from the existing product/studio
renderer. It does not silently replace a user's renderer defaults.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from scene_inputs import fingerprint, current_scene_matches

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def call(command: list[str], log: Path) -> None:
    """Record the exact command, stream its output, and fail on errors."""
    print('+', ' '.join(command), flush=True)
    with log.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps({'command': command}) + '\n')
        stream.flush()
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end='', flush=True)
            stream.write(line)
            stream.flush()
        code = process.wait()
    if code:
        raise RuntimeError(f'Command exited with {code}; inspect {log}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=REPO.parent / 'output')
    parser.add_argument('--view', choices=['hero', 'detail', 'overhead', 'low'], default='hero')
    parser.add_argument('--stem', default=None, help='Output filename stem; camera still selected by --view')
    parser.add_argument('--sun', default=None, help='Comma-separated xyz sun direction; positive z required')
    parser.add_argument('--opaque-filter-strength', type=float, default=.55)
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--height', type=int, default=800)
    parser.add_argument('--spp', type=int, default=96)
    parser.add_argument('--water-spp', type=int, default=256)
    parser.add_argument('--indirect-clamp', type=float, default=0.0)
    parser.add_argument('--depth', type=int, default=12)
    parser.add_argument('--threads', type=int, default=max(1, min(5, os.cpu_count() or 1)))
    parser.add_argument('--seed', type=int, default=20260914)
    parser.add_argument('--scene-seed', type=int, default=20260914)
    parser.add_argument('--exposure', type=float, default=1.15)
    parser.add_argument('--white-balance', type=float, default=5700.)
    parser.add_argument('--aperture', type=float, default=0.001)
    parser.add_argument('--rebuild-scene', action='store_true')
    parser.add_argument('--no-glb', action='store_true')
    parser.add_argument('--no-steam', action='store_true')
    parser.add_argument('--no-clouds', action='store_true')
    parser.add_argument('--no-water', action='store_true')
    parser.add_argument('--water-absorption', type=float, default=1.0)
    parser.add_argument('--filter-passes', type=int, choices=[0, 1, 2, 3], default=2)
    parser.add_argument('--no-spectral-buffer', action='store_true')
    args = parser.parse_args()
    if min(args.width, args.height, args.spp, args.depth, args.threads) <= 0:
        parser.error('Image dimensions, samples, depth and threads must be positive')
    if args.aperture < 0 or args.water_absorption < 0 or args.exposure <= 0 or args.water_spp < 0 or args.indirect_clamp < 0:
        parser.error('Aperture and absorption must be nonnegative; exposure must be positive')
    if sys.platform != 'linux':
        parser.error('This delivery was tested on Linux. Use Linux or WSL with g++/OpenMP.')
    compiler = shutil.which('g++')
    if not compiler:
        parser.error('g++ was not found. Install a C++17 compiler with OpenMP support.')
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if args.rebuild_scene or not current_scene_matches(root,args.scene_seed):
        cmd = [sys.executable, str(HERE / 'build_scene.py'), '--out', str(root),
               '--seed', str(args.scene_seed)]
        if args.no_glb:
            cmd.append('--no-glb')
        call(cmd, root / 'build.log')
        (root/'scene_inputs.json').write_text(json.dumps(fingerprint(args.scene_seed),indent=2)+'\n')
    sources = [REPO / 'native' / name for name in ('spectral_desert.cpp', 'spectral_geometry.h', 'single_scatter_sky.h', 'photographic_grain.h', 'broadband_ripples.h', 'landscape_materials_v11.h', 'granular_relief_v11.h', 'steam_volume_v11.h', 'exponential_haze_v10.h', 'cloud_volume_v9.h', 'specular_reflection_connection.h')]
    source_hash = hashlib.sha256(b''.join(path.read_bytes() for path in sources)).hexdigest()
    binary = root / f'spectral_desert_{source_hash[:16]}'
    compile_command = [compiler, '-std=c++17', '-O3', '-march=native', '-fopenmp',
                       str(sources[0]), '-o', str(binary)]
    if not binary.is_file():
        call(compile_command, root / 'compile.log')
    test = subprocess.run([str(binary), '--self-test'], check=True, capture_output=True, text=True)
    test_report = json.loads(test.stdout)
    if not test_report.get('passed'):
        raise RuntimeError('Optical self-check failed')
    (root / 'optics_tests.json').write_text(json.dumps(test_report, indent=2) + '\n')
    label = args.stem or args.view
    if Path(label).name != label or not label:parser.error('Output stem must be a simple filename')
    if not 0 <= args.opaque_filter_strength <= 1:parser.error('Opaque filtering strength must be between 0 and 1')
    stem = root / label
    command = [str(binary), str(root / 'scene.meshbin'), str(stem),
               '--w', str(args.width), '--h', str(args.height), '--spp', str(args.spp),
               '--depth', str(args.depth), '--water-spp', str(args.water_spp),
               '--indirect-clamp', str(args.indirect_clamp), '--threads', str(args.threads),
               '--view', args.view, '--seed', str(args.seed), '--exposure', str(args.exposure),
               '--aperture', str(args.aperture), '--water-absorption', str(args.water_absorption),
               '--grain', str(HERE/'assets/gravel_periodic.pgm'), '--relief', str(HERE/'assets/granular_relief.bin')]
    for enabled, flag in [(args.no_clouds, '--no-clouds'), (args.no_steam, '--no-steam'), (args.no_water, '--no-water'),
                          (args.no_spectral_buffer, '--no-bands')]:
        if enabled:
            command.append(flag)
    if args.sun is not None:command += ['--sun', args.sun]
    call(command, root / f'{label}_render.log')
    call([sys.executable, str(HERE / 'finish.py'), str(stem), '--passes', str(args.filter_passes), '--white-balance', str(args.white_balance), '--opaque-filter-strength', str(args.opaque_filter_strength)],
         root / f'{label}_finish.log')
    receipt = {'source_hash': source_hash, 'compile_command': compile_command,
               'compiler_version': subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
               'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
               'render_command': command, 'elapsed_total_seconds': time.monotonic() - started,
               'python': sys.version,
               'packages': {n: importlib.metadata.version(n) for n in
                            ['numpy', 'scipy', 'trimesh', 'Pillow', 'numba', 'scikit-image']},
               'upstream_defaults_modified': False, 'pushed_to_github': False,
               'scene_inputs_fingerprint':fingerprint(args.scene_seed)['fingerprint'],
               'mesh_sha256': __import__('build_scene_v4').stream_hash(root / 'scene.meshbin')}
    (root / f'{label}_run_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Completed: {stem}.png', flush=True)


if __name__ == '__main__':
    main()
