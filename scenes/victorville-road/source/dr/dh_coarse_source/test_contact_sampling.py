import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dg_native_roles_a/runtime/src'))
from context_mesh_refine_ab import SourceSampler
from check_terrain_contact import supported_heights,sample_indices
class Tests(unittest.TestCase):
 def setUp(self):
  self.co=np.array([[0.,0.,.2],[1.,0.,.3],[0.,1.,.4],[3.,0.,.5],[4.,0.,.6],[3.,1.,.7]])
  self.s=SourceSampler(self.co,np.array([[0,1,2],[3,4,5]]),np.array([0,1]),cell_m=.2)
 def test_actual_planes_and_gaps(self):
  xy=np.array([[.2,.3],[.9,.9],[2.,.2],[-1.,0.],[3.2,.3]])
  z=supported_heights(self.s,xy)
  np.testing.assert_allclose(z[[0,4]],[.28,.58]);self.assertTrue(np.isnan(z[[1,2,3]]).all())
 def test_invalid_error_is_not_hidden(self):
  with self.assertRaises(AssertionError):supported_heights(self.s,[[np.nan,0]])
  class Broken:
   def height(self,xy):raise ValueError('Unexpected determinant failure')
  with self.assertRaisesRegex(ValueError,'Unexpected'):supported_heights(Broken(),[[0,0]])
 def test_empty_and_shape(self):
  self.assertEqual(supported_heights(self.s,np.empty((0,2))).shape,(0,))
 def test_footprint_and_lowest_samples(self):
  r=np.random.default_rng(14).random((10000,3));r[9500]=[.99,.99,-3]
  ids=sample_indices(r);self.assertLessEqual(len(ids),512);self.assertIn(9500,ids)
if __name__=='__main__':unittest.main()
