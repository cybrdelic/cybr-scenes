import unittest
import numpy as np
from sediment_surface_ai import surface_fields,retained_grain_lift,summary

class SurfaceTests(unittest.TestCase):
    def fields(self):
        f={'x_m':np.array([0.,.05,.10]),'y_m':np.array([0.,.05,.10]),'retained_deposit_by_class_m':np.zeros((3,3,3)),'sediment_delta_m':np.zeros((3,3)),'surface_fraction':np.tile([.68,.24,.08],(3,3,1))};return f
    def test_empty_inventory_adds_no_pattern(self):
        f=self.fields();v=surface_fields(np.array([[.02,.03],[.1,.1]]),f)
        np.testing.assert_array_equal(v['lag'],0);np.testing.assert_array_equal(v['fine_coat'],0)
    def test_retained_matrix_in_scour_is_not_a_new_top_blanket(self):
        f=self.fields();f['retained_deposit_by_class_m'][...,0]=.003;f['sediment_delta_m'][:]=-.001
        v=surface_fields(np.array([[.05,.05]]),f);self.assertEqual(v['fine_coat'][0],0)
    def test_net_deposit_and_own_matrix_limit_coating(self):
        f=self.fields();f['retained_deposit_by_class_m'][...,0]=.003;f['sediment_delta_m'][:]=.0001
        v=surface_fields(np.array([[.05,.05]]),f);self.assertAlmostEqual(v['fine_coat'][0],1-np.exp(-.0001/.00035))
    def test_coarse_enrichment_needs_real_scour(self):
        f=self.fields();f['surface_fraction'][...,2]=.4
        self.assertEqual(surface_fields(np.array([[.05,.05]]),f)['lag'][0],0)
        f['sediment_delta_m'][:]=-.001;self.assertAlmostEqual(surface_fields(np.array([[.05,.05]]),f)['lag'][0],1-np.exp(-1))
    def test_lift_bounded_by_buried_body_and_scour(self):
        f=self.fields();f['surface_fraction'][...,2]=.6;f['sediment_delta_m'][:]=-.005
        v=surface_fields(np.array([[.05,.05],[.03,.03]]),f);z=np.array([-.0004,-.002]);a=retained_grain_lift(v,z);self.assertTrue(np.all(a<=-z*.55));self.assertTrue(np.all(a<=.005));self.assertTrue(np.all(a>0))
    def test_outside_unchanged_and_input_bytes_preserved(self):
        f=self.fields();f['sediment_delta_m'][:]=.005;f['retained_deposit_by_class_m'][...,0]=.005;before={k:v.tobytes() for k,v in f.items()};v=surface_fields(np.array([[-.01,.03],[.11,.03]]),f);np.testing.assert_array_equal(v['fine_coat'],0);self.assertEqual(before,{k:v.tobytes() for k,v in f.items()})
if __name__=='__main__':unittest.main()
