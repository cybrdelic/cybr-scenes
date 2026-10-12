import unittest,numpy as np
from history_budget_dg import reconcile,retained_cover
from transported_grain_exposure_dg import allocate_transported_grains,ExposureConfig
class TestBudget(unittest.TestCase):
 def test_prior_consumed_first(self):
  a=reconcile([[.002,.003,.004]],[[.003,.002,0]],[[.001,0,.001]])
  np.testing.assert_allclose(a['available'],[[.001,.001,.005]])
  np.testing.assert_allclose(a['unassigned_erosion'],[[.001,0,0]])
 def test_static_cover_consumption(self):
  np.testing.assert_allclose(retained_cover(np.array([.003,.001,-.005]),np.array([-.001,-.002,.001])),[.002,0,.001])
 def test_no_mutation(self):
  p=np.array([[.001,.002,.003]]);q=p.copy();reconcile(p,p,p);np.testing.assert_array_equal(p,q)
 def test_matrix_geometry_budget_and_determinism(self):
  n=80;kw=dict(xy_m=np.tile([.05,.05],(n,1)),flow_class=np.zeros(n),solid_volume_m3=np.full(n,1e-10),diameter_m=np.full(n,.0003),footprint_area_m2=np.full(n,1e-7),local_z_bounds_m=np.tile([-.0002,.0001],(n,1)),final_surface_m=np.zeros(n),x_m=np.arange(3)*.05,y_m=np.arange(3)*.05,retained_deposit_by_class_m=np.full((3,3,3),.001),net_deposit_m=np.zeros((3,3)),config=ExposureConfig(availability_mode='surviving_deposit_stock'))
  a=allocate_transported_grains(**kw);b=allocate_transported_grains(**kw);np.testing.assert_array_equal(a.transported,b.transported);assert a.transported.any();assert np.all(a.selected_solid_volume_by_cell_class_m3<=a.solid_budget_by_cell_class_m3);assert not a.selected_count_by_cell_class[...,1:].any()
if __name__=='__main__':unittest.main()
