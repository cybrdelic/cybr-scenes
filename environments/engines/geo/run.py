#!/usr/bin/env python3
"""Rebuild, render and verify the recovered CYBR GEO three-scene project.

No installed cybrgeo package, previous working directory, credentials or downloaded
scene assets are required. Third-party Python libraries and a C++17 compiler are
listed in requirements.txt and README.md.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT / 'cybr-geo'
TOOLS = REPO / 'examples' / 'three_scenes'
SCENES = ('canyon', 'coast', 'forest')


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def required_files() -> list[Path]:
    relative = ['native/spectral_scenes.cpp', 'native/fernwater_materials_r6.h', 'native/spectral_geometry.h',
                'native/bvh8_recovery.h', 'native/formation_materials_r4.h', 'native/thin_leaf_r4.h',
                'native/photographic_grain.h', 'native/granular_relief_v11.h',
                'src/cybrgeo/core.py', 'src/cybrgeo/__init__.py',
                'examples/three_scenes/build_scenes.py',
                'examples/three_scenes/rebuild_scenes.py', 'examples/three_scenes/fernwater_r6.py',
                'examples/three_scenes/render_scenes.py',
                'examples/three_scenes/finish.py',
                'examples/three_scenes/noise_resolve.py',
                'examples/three_scenes/export_exr.py',
                'examples/three_scenes/verify_outputs.py',
                'examples/desert_hot_springs/assets/gravel_periodic.pgm',
                'examples/desert_hot_springs/assets/granular_relief.bin']
    return [REPO / name for name in relative]


def execute(command: list[str], log: Path) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OPENCV_IO_ENABLE_OPENEXR='1')
    started = time.monotonic()
    print('RUN', ' '.join(command), flush=True)
    with log.open('w', encoding='utf8') as output:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=output,
                                stderr=subprocess.STDOUT)
    receipt = {'command': command, 'cwd': str(ROOT), 'returncode': result.returncode,
               'wall_seconds': time.monotonic() - started, 'log': str(log)}
    if result.returncode:
        print(log.read_text(errors='replace')[-6000:], file=sys.stderr)
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['check', 'test', 'build', 'render', 'verify', 'all'],
                        nargs='?', default='all')
    parser.add_argument('--scene', choices=['all', *SCENES], default='forest')
    parser.add_argument('--quality', choices=['preview', 'production'], default='production')
    parser.add_argument('--threads', type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    parser.add_argument('--glb', action='store_true', help='Also export inspection GLBs (large).')
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('--threads must be positive')
    missing = [str(p.relative_to(ROOT)) for p in required_files() if not p.is_file()]
    if missing:
        raise RuntimeError('Incomplete package: ' + ', '.join(missing))
    sys.path.insert(0, str(TOOLS))
    sys.path.insert(0, str(REPO / 'src'))
    import numpy, scipy, trimesh, PIL, numba, cv2
    from render_scenes import compile_renderer, render
    from verify_outputs import verify_scene
    output = args.output.resolve()
    reports = output / 'verification'
    reports.mkdir(parents=True, exist_ok=True)
    scenes = SCENES if args.scene == 'all' else (args.scene,)
    preview = args.quality == 'preview'
    stem = 'preview' if preview else 'final'
    status = {'scope': 'Build and render completion, not photographic certification',
              'quality': args.quality, 'scenes': {}, 'image_generation': False,
              'required_files_present': True}
    status_file = reports / f'{stem}_pipeline_status.json'
    if args.stage == 'check':
        binary, build = compile_renderer()
        status.update({'compiled_binary': str(binary), 'build': build})
        status_file.write_text(json.dumps(status, indent=2) + '\n')
        print(json.dumps(status, indent=2))
        return
    if args.stage in ('test', 'all'):
        execute([sys.executable, str(ROOT / 'test_project.py')], reports / 'tests.log')
        if args.stage == 'test':
            print((ROOT / 'verification' / 'recovery_tests.json').read_text())
            return
    for scene in scenes:
        # Dense thin-leaf reflection/transmission requires more sampling than opaque rock.
        settings = ((640, 426, 256, 512) if scene == 'forest' else (640, 426, 64, 128)) if preview else ((1920, 1280, 192, 384) if scene == 'forest' else (1920, 1280, 128, 320))
        w, h, spp, water_spp = settings
        state: dict = {}
        status['scenes'][scene] = state
        try:
            if args.stage in ('build', 'all'):
                command = [sys.executable, str(TOOLS / 'rebuild_scenes.py'), '--out', str(output),
                           '--scene', scene]
                if not args.glb:
                    command.append('--no-glb')
                if scene=='forest':
                    command=[sys.executable,str(TOOLS/'fernwater_r6.py'),'--out',str(output)]
                recipe=TOOLS/('fernwater_r6.py' if scene=='forest' else 'rebuild_scenes.py')
                source_hash = digest(recipe)
                state['build'] = execute(command, reports / f'{scene}_build.log')
                if source_hash != digest(recipe):
                    raise RuntimeError('Recipe changed during scene generation')
                receipt = {'recipe_sha256': source_hash,
                           'adapter_sha256': digest(TOOLS / 'build_scenes.py'),
                           'core_sha256': digest(REPO / 'src/cybrgeo/core.py'),
                           **state['build']}
                (output / scene / 'build_receipt.json').write_text(json.dumps(receipt, indent=2))
            if args.stage in ('render', 'all'):
                if not (output / scene / 'scene.meshbin').is_file():
                    raise RuntimeError(f'{scene}: build geometry before rendering')
                state['render'] = render(output, scene, w, h, spp, water_spp,
                                         stem, args.threads, exr=True)
            if args.stage in ('verify', 'all'):
                verification = verify_scene(output / scene, stem)
                if not preview:
                    metadata = verification['render']
                    if (metadata['width'], metadata['height'], metadata['spp'], metadata['water_spp']) != settings:
                        raise RuntimeError('Production budget was changed')
                if not verification['render'].get('photographic_grayscale_albedo_detail'):
                    raise RuntimeError('Grayscale detail not active')
                if not verification['render'].get('granular_relief_enabled'):
                    raise RuntimeError('Relief input not active')
                (reports / f'{scene}_{stem}.json').write_text(json.dumps(verification, indent=2))
                state['verified_integrity'] = True
            state['requested_stage_complete'] = True
        except Exception as error:
            state['error'] = str(error)
            status_file.write_text(json.dumps(status, indent=2) + '\n')
            raise
        status_file.write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps({s: status['scenes'][s].get('requested_stage_complete') for s in scenes}, indent=2))


if __name__ == '__main__':
    main()
