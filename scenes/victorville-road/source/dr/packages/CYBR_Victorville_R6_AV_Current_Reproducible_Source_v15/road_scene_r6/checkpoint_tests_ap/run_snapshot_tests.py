#!/usr/bin/env python3
"""Small CPU1 AP field/sampler and original offline scrub checks, no Blender."""
import argparse
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

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--receipt', type=Path)
    args = p.parse_args()
    snapshot = args.snapshot.resolve()
    sys.path.insert(0, str(snapshot))
    module = load('road_margin_composition_ap', snapshot/'road_margin_composition_ap.py')
    class FieldsTests(unittest.TestCase):
        def setUp(self):
            x,y = np.meshgrid(np.linspace(-12.,-3.,43),np.linspace(-1.,86.,47))
            self.xy=np.column_stack((x.ravel(),y.ravel()))
        def test_finite_bounded_and_deterministic(self):
            a=module.fields(self.xy);b=module.fields(self.xy)
            self.assertEqual(set(a),{'coarse','fines','plants','gate','graded','receiving','channel'})
            for key,value in a.items():
                self.assertTrue(np.isfinite(value).all())
                self.assertTrue(((value>=0)&(value<=1)).all())
                np.testing.assert_array_equal(value,b[key])
        def test_input_arrays_unchanged(self):
            original=self.xy.copy();g=np.full_like(self.xy,.0123);before=g.copy()
            module.fields(self.xy,g)
            np.testing.assert_array_equal(self.xy,original)
            np.testing.assert_array_equal(g,before)
        def test_chunking_is_consistent(self):
            full=module.fields(self.xy)
            chunks=[module.fields(a) for a in np.array_split(self.xy,9)]
            for key,value in full.items():
                np.testing.assert_allclose(value,np.concatenate([v[key] for v in chunks]),rtol=0,atol=2e-14)
        def test_road_and_outside_corridor_are_gated(self):
            points=np.array([[-3.,1.],[-3.2,4.],[-4.,-1.],[-4.,86.],[-14.,5.]])
            values=module.fields(points)
            for key in ('gate','coarse','fines','plants'):
                np.testing.assert_array_equal(values[key],np.zeros(len(points)))
        def test_zero_gradient_default(self):
            a=module.fields(self.xy);b=module.fields(self.xy,np.zeros_like(self.xy))
            for key in a:np.testing.assert_array_equal(a[key],b[key])
        def test_slope_has_real_effect(self):
            flat=module.fields(self.xy)
            steep=module.fields(self.xy,np.tile([.18,.06],(len(self.xy),1)))
            self.assertGreater(np.max(np.abs(flat['receiving']-steep['receiving'])),.01)
        def test_empty_domain(self):
            for value in module.fields(np.empty((0,2))).values():self.assertEqual(value.shape,(0,))
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FieldsTests)
    sampler=load('test_sample_final_surface_an',HERE/'originals/test_sample_final_surface_an.py')
    # Only the class used by AP's ground sampler is counted as AP regression.
    sampler_classes=[v for v in vars(sampler).values() if isinstance(v,type) and
                     issubclass(v,unittest.TestCase) and v.__name__=='ExactSurfaceTests']
    assert len(sampler_classes)==1,'Expected the original exact triangle sampler test class'
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(sampler_classes[0]))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful() and not result.skipped
    with tempfile.TemporaryDirectory(prefix='ap_scrub_pure_') as temp:
        root=Path(temp)
        for name in ('layered_scrub_ap.py','desert_scrub.py'):
            shutil.copyfile(snapshot/name,root/name)
        shutil.copyfile(HERE/'originals/test_layered_scrub_ap_offline.py',root/'test_layered_scrub_ap_offline.py')
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([sys.executable,str(root/'test_layered_scrub_ap_offline.py')],env=env,check=True,capture_output=True,text=True,timeout=120)
        scrub=json.loads((root/'layered_scrub_ap_offline_receipt.json').read_text())
    assert scrub['status']=='passed' and len(scrub['variants'])==6
    historical=json.loads((HERE/'originals/layered_scrub_ap_offline_receipt.json').read_text())
    assert scrub==historical,'Exact original offline scrub output changed'
    report=dict(passed=True,tests_run=result.testsRun,failures=0,errors=0,skipped=0,
        scrub_variants_checked=6,scrub_vertices= scrub['total_vertices'],
        exact_original_scrub_receipt_reproduced=True,snapshot_sha256=snapshot.name,
        CPU_threads=1,blender_executed=False,rendered=False,full_saved_domain_solver_rerun=False,
        scope='Tiny authored field fixtures; AP exact triangle sampler; original offline shrub geometry. No dynamics, site realism, visual acceptance or fresh end-to-end rebuild claim.')
    if args.receipt:args.receipt.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
