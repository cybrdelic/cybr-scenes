#!/usr/bin/env python3
"""Exact AQ contact tests and unchanged AO receiver-gate tests on tiny fixtures."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import numpy as np

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--receipt',type=Path)
    a=p.parse_args();snapshot=a.snapshot.resolve()
    with tempfile.TemporaryDirectory(prefix='aq_contact_pure_') as folder:
        target=Path(folder)
        for path in snapshot.glob('*.py'):shutil.copyfile(path,target/path.name)
        shutil.copyfile(HERE/'originals/test_continuous_contact_aq.py',target/'test_continuous_contact_aq.py')
        shutil.copyfile(HERE.parent/'checkpoint_tests_al/originals/test_contact_bank_continuity_al.py',target/'test_contact_bank_continuity_al.py')
        result=subprocess.run([sys.executable,'-m','unittest','test_continuous_contact_aq','-v'],cwd=target,
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True,text=True,timeout=120)
        print(result.stdout+result.stderr)
        assert result.returncode==0 and 'Ran 6 tests' in result.stderr
    sys.path.insert(0,str(snapshot))
    spec=importlib.util.spec_from_file_location('aq_exact_ao_model',snapshot/'flow_sediment_model_ao.py')
    model=importlib.util.module_from_spec(spec);sys.modules[spec.name]=model;spec.loader.exec_module(model)
    original=HERE/'originals/test_refined_film_event_ao.py'
    tree=ast.parse(original.read_text())
    selected=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ('line_adjacency','gate','ReceiverGateTests')]
    assert len(selected)==3
    namespace={'np':np,'model':model,'unittest':unittest}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(original),'exec'),namespace)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(namespace['ReceiverGateTests'])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful() and result.testsRun==7 and not result.skipped
    report=dict(passed=True,tests_run=13,contact_tests=6,unchanged_AO_receiver_gate_tests=7,
        snapshot_sha256=snapshot.name,CPU_threads=1,blender_executed=False,rendered=False,
        full_1281x89_solver_rerun=False,
        scope='Original six tiny AQ contact fixtures; unchanged seven receiver-gate fixtures extracted from original test definitions. Historical AO integration/serialization suites are not counted as rerun.')
    if a.receipt:a.receipt.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
