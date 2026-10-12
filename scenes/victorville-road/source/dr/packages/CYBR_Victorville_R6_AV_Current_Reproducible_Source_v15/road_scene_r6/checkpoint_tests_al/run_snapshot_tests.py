#!/usr/bin/env python3
"""Run CPU1 synthetic AL checks against an explicitly selected exact snapshot.
Original tests are retained without edits. Only their synthetic bank cases are
selected; their actual historical-cache case is not presented as a fresh test.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--receipt',type=Path)
    a=p.parse_args();snapshot=a.snapshot.resolve();sys.path.insert(0,str(snapshot))
    suite=unittest.TestSuite()
    ownership=load('test_road_film_ownership_al',HERE/'originals/test_road_film_ownership_al.py')
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(ownership))
    has_bank=(snapshot/'contact_bank_continuity_al.py').exists()
    if has_bank:
        bank=load('test_contact_bank_continuity_al',HERE/'originals/test_contact_bank_continuity_al.py')
        omit={'test_actual_cached_road_and_ah_bank_qualify','test_adapter_preserves_normals_before_geometry_update'}
        for name in unittest.defaultTestLoader.getTestCaseNames(bank.BankContinuityTests):
            if name not in omit:suite.addTest(bank.BankContinuityTests(name))
        portable=load('test_support_portable',HERE/'test_support_portable.py')
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(portable))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),skipped=len(result.skipped),generation='AL',snapshot_sha256=snapshot.name,
        CPU_threads=1,blender_executed=False,rendered=False,full_saved_domain_solver_rerun=False,
        bank_tests_included=has_bank,
        omitted_historical_tests=['Original bank test_actual_cached_road_and_ah_bank_qualify; caches intentionally not bundled'],
        replaced_layout_test='Original adapter AST check replaced by inspect.getsource of selected captured adapter',
        scope='Pure ownership regression and synthetic support/overlap geometry. No actual captured AH/topology field solve.')
    if a.receipt:
        with a.receipt.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
