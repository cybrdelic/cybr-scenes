"""Small retained-runtime admission test; no city assets or network required."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from cybrlight.scene_compat import Scene, Meshlets, render
from cybrlight.scene_compat.runtime import compile_renderer, read_pfm
import cybrlight.scene_compat.runtime as runtime


def verify_manifest():
    root = Path(runtime.__file__).parent
    manifest = json.loads((root / 'DEPENDENCY_MANIFEST.json').read_text())
    for name, expected in manifest['files'].items():
        assert '__pycache__' not in name and not name.endswith(('.pyc', '.pyo'))
        data = (root / name).read_bytes()
        assert len(data) == expected['bytes'], name
        assert hashlib.sha256(data).hexdigest() == expected['sha256'], name
    compiler = shutil.which(os.environ.get('CXX', 'g++'))
    assert compiler, 'A C++17/OpenMP compiler is required'
    version = subprocess.check_output([compiler, '--version'])
    native = root / 'native'
    files = [native/'src/main.cpp', *sorted((native/'include').rglob('*.hpp'))]
    source_bytes = b''.join(p.read_bytes() for p in files)
    expected_build_hash = hashlib.sha256(version + source_bytes).hexdigest()
    executable, actual = compile_renderer()
    assert executable.is_file() and actual == expected_build_hash
    return {'files_checked':len(manifest['files']), 'native_source_bytes_sha256':hashlib.sha256(source_bytes).hexdigest(),
            'build_hash':actual, 'recorded_execution_hash':manifest['executed_source_hash'],
            'matches_recorded_execution_toolchain':actual == manifest['executed_source_hash']}


def tiny_scene(directory):
    directory = Path(directory)
    scene = Scene()
    scene.settings(12, 12, 8, 3, 2, 8, 7331, 1.0)
    scene.camera((0,0,3), (0,0,0), (0,1,0), 32)
    material = scene.material('diffuse', (.18,.18,.18))
    scene.emit('environment', (1,1,1), 1)
    scene.emit('environment_flat')
    vertices = np.array([[-2,-2,0],[2,-2,0],[2,2,0],[-2,2,0]], dtype=float)
    faces = np.array([[0,1,2],[0,2,3]])
    records = np.zeros((2,36), dtype='<f4')
    records[:,:9] = vertices[faces].reshape(2,9)
    records[:,9:18] = np.tile([0,0,1], 3)
    records[:,18] = material
    records[:,19] = 7
    records[:,20:26] = (vertices[faces,:2]/4).reshape(2,6)
    records[:,26:35] = 1
    with Meshlets(directory/'plane.clm') as mesh:
        mesh.add(records)
    scene.mesh(directory/'plane.clm')
    report = render(scene, directory/'fixture')
    film = read_pfm(directory/'fixture.pfm')
    assert report['primitives'] == 2
    assert report['invalid_path_samples'] == 0
    assert film.shape == (12,12,3) and np.isfinite(film).all()
    assert float(film.min()) > 0 and float(film.max()) < 2
    assert (directory/'fixture.png').is_file()
    text = (directory/'fixture.cys').read_text()
    assert 'meshlets "plane.clm"' in text
    return {'primitives':report['primitives'], 'invalid_path_samples':report['invalid_path_samples'],
            'finite_pixels':True, 'mean_linear_rgb':film.mean((0,1)).tolist(), 'render_seconds':report['render_seconds']}


def test_scene_compat_manifest():
    verify_manifest()


def test_scene_compat_entrypoint(tmp_path):
    tiny_scene(tmp_path)


if __name__ == '__main__':
    result = {'manifest':verify_manifest()}
    with tempfile.TemporaryDirectory(prefix='cybr-scene-compat-test-') as directory:
        result['fixture'] = tiny_scene(directory)
    result['passed'] = True
    print(json.dumps(result, indent=2))
