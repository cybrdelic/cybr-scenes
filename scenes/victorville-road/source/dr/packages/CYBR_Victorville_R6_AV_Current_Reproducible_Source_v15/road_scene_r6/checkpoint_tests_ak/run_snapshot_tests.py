#!/usr/bin/env python3
"""Run pure regressions against one explicitly selected immutable source snapshot.
No renderer, scene load, full terrain solve or saved historical field is used.
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
    p.add_argument('--generation',choices=['AI','AJ','AK'],required=True)
    p.add_argument('--receipt',type=Path)
    a=p.parse_args();snapshot=a.snapshot.resolve();sys.path.insert(0,str(snapshot))
    suite=unittest.TestSuite();names=['test_sediment_surface_ai','test_transported_grain_exposure']
    if a.generation in ('AJ','AK'):names.append('test_retained_top_proxy_aj')
    for name in names:
        module=load(name,HERE/'originals'/(name+'.py'))
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    edge=load('test_runoff_edge_support_ai',HERE/'originals/test_runoff_edge_support_ai.py')
    # Original tests 14/15 require external historical fields or their old
    # filesystem layout. Pure support/contact behavior is covered by tests 1-13.
    edge_names=unittest.defaultTestLoader.getTestCaseNames(edge.EdgeSupportTests)
    for name in edge_names:
        if not name.startswith(('test_14_','test_15_')):suite.addTest(edge.EdgeSupportTests(name))
    if a.generation=='AK':
        module=load('test_substrate_portable',HERE/'test_substrate_portable.py')
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),generation=a.generation,
        snapshot_sha256=snapshot.name,CPU_threads=1,blender_executed=False,rendered=False,
        full_saved_domain_solver_rerun=False,
        omitted_historical_tests=['runoff test 14 actual AH fields/topology',
            'runoff test 15 original filesystem layout','original substrate tests requiring AH_FIELDS.npz',
            'AE actual saved terrain/resolution comparison suite'],
        scope='Pure unit regressions; synthetic AK foundation and tiny spatial-inventory solve. Historical actual-foundation receipts retained separately.')
    if a.receipt:
        with a.receipt.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
