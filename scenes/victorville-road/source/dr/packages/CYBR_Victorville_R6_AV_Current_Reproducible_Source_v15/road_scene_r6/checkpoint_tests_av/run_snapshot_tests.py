#!/usr/bin/env python3
"""Exact AV-source tiny fixture tests; no Blender/actual-domain solve/render."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='av_tiny_fixtures_',dir=HERE) as directory:
        target=Path(directory)
        for path in a.snapshot.glob('*.py'):shutil.copyfile(path,target/path.name)
        for path in (HERE/'originals').glob('*.py'):shutil.copyfile(path,target/path.name)
        # Original morphology includes one historical mutable-assembly pin, which
        # predates AV and is not a geometry fixture. Preserve its exact source;
        # select only the other seven exact original geometry test definitions.
        path=target/'test_metric_margin_fragments_as_fractured_candidate.py'
        tree=ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node,ast.ClassDef):
                node.body=[n for n in node.body if not isinstance(n,ast.FunctionDef) or n.name!='test_stable_baseline_and_pre_task_assembly_pins']
        path.write_text(ast.unparse(tree)+'\n')
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
        command=[sys.executable,'-m','unittest','test_fractured_boundary_ar','test_metric_margin_fragments_as',
                 'test_metric_margin_fragments_as_fractured_candidate','test_refresh_view_grains_au','-v']
        result=subprocess.run(command,cwd=target,env=env,capture_output=True,text=True,timeout=160)
        print(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('AV tiny source fixtures failed')
        result=subprocess.run([sys.executable,'test_soil_rim_bridge_ar.py'],cwd=target,env=env,capture_output=True,text=True,timeout=50)
        print(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('AR soil-rim tiny fixtures failed')
    print(json.dumps(dict(passed=True,snapshot_sha256=a.snapshot.name,CPU_threads=1,blender_executed=False,
        rendered=False,actual_domain_solver_executed=False,historical_AS_assembly_pin_test_not_rerun=True)))

if __name__=='__main__':main()
