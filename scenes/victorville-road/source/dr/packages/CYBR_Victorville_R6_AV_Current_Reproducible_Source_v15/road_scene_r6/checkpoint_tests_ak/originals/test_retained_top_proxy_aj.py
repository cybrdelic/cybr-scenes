import unittest
import numpy as np
from sediment_surface_ai import surface_fields,SurfaceSpec
from transported_grain_exposure import retained_top_proxy,allocate_transported_grains,ExposureConfig
class RetainedStockTests(unittest.TestCase):
 def test_proxy_is_bounded_per_class_and_total(self):
  d=np.array([[0,0,0],[.003,.002,.001],[.00001,0,0]])
  p,t,f=retained_top_proxy(d);self.assertTrue(np.all(p<=d));self.assertTrue(np.all(p>=0));self.assertTrue(np.all(t<=.0018+1e-15));np.testing.assert_array_equal(f[0],0);np.testing.assert_allclose(f[1:].sum(-1),1)
 def test_net_eroded_retained_fines_remain_available(self):
  d=np.zeros((3,3,3));d[...,0]=.0004
  f={'x_m':np.arange(3)*.05,'y_m':np.arange(3)*.05,'retained_deposit_by_class_m':d,'sediment_delta_m':np.full((3,3),-.002),'surface_fraction':np.tile([.68,.24,.08],(3,3,1))}
  a=surface_fields(np.array([[.05,.05]]),f,SurfaceSpec(include_net_eroded_retained=True));self.assertGreater(a['fine_coat'][0],.6)
 def test_deposited_grain_survives_negative_net_with_no_budget_overshoot(self):
  n=20;d=np.zeros((3,3,3));d[...,1]=.001
  a=allocate_transported_grains(xy_m=np.tile([.05,.05],(n,1)),flow_class=np.ones(n),solid_volume_m3=np.full(n,1e-11),diameter_m=np.full(n,.0005),footprint_area_m2=np.full(n,1e-7),local_z_bounds_m=np.tile([-.0002,.0002],(n,1)),final_surface_m=np.zeros(n),x_m=np.arange(3)*.05,y_m=np.arange(3)*.05,retained_deposit_by_class_m=d,net_deposit_m=np.full((3,3),-.002),config=ExposureConfig(availability_mode='surviving_deposit_stock'))
  self.assertGreater(a.transported.sum(),0);self.assertTrue(np.all(a.selected_solid_volume_by_cell_class_m3<=a.solid_budget_by_cell_class_m3));self.assertGreater(a.receipt['audit']['promoted_without_positive_net_deposit'],0);self.assertFalse(a.receipt['audit']['net_sign_is_availability_gate'])
 def test_invalid_proxy_rejected(self):
  for d in ([-1,0,0],[np.nan,0,0]):
   with self.assertRaises(ValueError):retained_top_proxy(d)
if __name__=='__main__':unittest.main()
