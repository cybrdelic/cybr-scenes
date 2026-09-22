"""Run the newly added V11 component checks; render validation is separate.

Example:
  python cybr-geo/examples/desert_hot_springs/run_checks_v11.py --out output/tests
  python cybr-geo/examples/desert_hot_springs/verify_v11.py --out output --views final

Passing component checks do not establish photographic realism or complete
reference-integrator accuracy. The sky check is convergence evidence, not a
measured-atmosphere validation or a blanket pass/fail test.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('output/tests'))
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(args.compiler)
    if compiler is None:
        parser.error(f'C++ compiler not found: {args.compiler}')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    reports: dict[str, object] = {}
    commands: list[list[str]] = []

    def execute(command: list[str], report_name: str | None = None) -> None:
        commands.append(command)
        result = subprocess.run(command, cwd=REPO, env=env, check=True,
                                text=True, capture_output=True)
        if result.stderr:
            (out / f'{report_name or "compile"}.stderr.log').write_text(result.stderr)
        if report_name is not None:
            data = json.loads(result.stdout)
            (out / f'{report_name}.json').write_text(json.dumps(data, indent=2) + '\n')
            reports[report_name] = data
            if data.get('passed') is False:
                raise RuntimeError(f'{report_name} returned passed=false')

    execute([sys.executable, str(HERE / 'test_streaming_scene_io.py')], 'scene_io')
    for source, name in [('test_materials_v11.cpp', 'materials'),
                         ('test_steam_grid_v11.cpp', 'steam_grid')]:
        binary = out / f'check_{name}'
        execute([compiler, '-std=c++17', '-O2', '-fopenmp',
                 str(REPO / 'native' / source), '-o', str(binary)])
        # These tests accept the scalar grain and reconstructed microrelief
        # assets on their command line. The steam test ignores asset args.
        execute([str(binary), str(HERE / 'assets/granular_relief.bin'),
                 str(HERE / 'assets/gravel_periodic.pgm')], name)
    execute([sys.executable, str(HERE / 'test_sky_quadrature.py')], 'sky_quadrature')
    (out / 'check_commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    print(json.dumps({'completed': list(reports),
                      'component_checks_passed': all(
                          report.get('passed', True) for report in reports.values()),
                      'numerical_checks_certify_photorealism': False}, indent=2))


if __name__ == '__main__':
    main()
