"""Compile and execute the native component checks shipped with this revision.

These tests do not establish full-render accuracy or visual photorealism.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=REPO / 'output')
    args = parser.parse_args()
    compiler = shutil.which('g++')
    if compiler is None:
        parser.error('g++ with C++17/OpenMP support is required')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    tests = [
        ('test_cloud_volume_v9', 'cloud_volume_tests', []),
        ('test_reflectance_calibration_v9', 'reflectance_calibration_tests', []),
        ('test_photographic_grain', 'grain_tests', [str(HERE / 'assets/gravel_periodic.pgm')]),
        ('test_spectral_desert_v5', 'v5_optical_regression', []),
        ('test_broadband_ripples', 'ripple_tests', []),
        ('test_water_medium', 'water_medium_tests', []),
        ('test_water_microfacet', 'water_microfacet_tests', []),
        ('test_reflected_connection', 'reflected_connection_tests', []),
        ('test_legacy_water_connection', 'legacy_water_connection_comparison', []),
    ]
    reports = {}
    for name, report_name, parameters in tests:
        binary = out / name
        command = [compiler, '-std=c++17', '-O3', '-fopenmp',
                   str(REPO / 'native' / (name + '.cpp')), '-o', str(binary)]
        subprocess.run(command, check=True)
        result = subprocess.run([str(binary), *parameters], check=True,
                                capture_output=True, text=True)
        report = json.loads(result.stdout)
        report['execution']={'compile_command':command,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'test_source_sha256':hashlib.sha256((REPO/'native'/(name+'.cpp')).read_bytes()).hexdigest()}
        if not report.get('passed', False):
            raise RuntimeError(f'Native component check failed: {name}')
        reports[report_name] = report
        (out / (report_name + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    subprocess.run([__import__('sys').executable, str(HERE / 'test_shoreline_continuity.py'), '--out', str(out)], check=True)
    subprocess.run([__import__('sys').executable, str(HERE / 'test_connected_vegetation.py'), '--out', str(out)], check=True)
    summary = {'scope': 'Limited native component checks, not full light transport or photorealism',
               'renderer_source_hash':hashlib.sha256(b''.join((REPO/'native'/n).read_bytes() for n in ('spectral_desert.cpp','spectral_geometry.h','single_scatter_sky.h','photographic_grain.h','broadband_ripples.h','scale_aware_landscape_v9.h','cloud_volume_v9.h','specular_reflection_connection.h'))).hexdigest(),
               'reports': reports, 'passed': True}
    (out / 'native_component_checks.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
