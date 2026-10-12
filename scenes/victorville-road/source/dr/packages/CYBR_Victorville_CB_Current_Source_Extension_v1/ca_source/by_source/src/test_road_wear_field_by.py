import unittest
import numpy as np
from road_wear_field_by import fields,polygon_inset,PATCHES
class WearField(unittest.TestCase):
 def test_metric_footprints(self):
  for p in PATCHES:
   c=np.mean(p,axis=0); self.assertGreater(float(polygon_inset(*c,p)),.25);self.assertAlmostEqual(float(fields(*c)['repair']),1)
  self.assertEqual(float(fields(-2.6,0)['repair']),0)
 def test_no_tiling_or_camera_dependency(self):
  x=np.linspace(-3.1,3.1,503);y=np.linspace(-.5,35,503)
  a=fields(x,y)
  for k,v in a.items():
   self.assertTrue(np.isfinite(v).all());self.assertGreaterEqual(v.min(),0);self.assertLessEqual(v.max(),1)
   np.testing.assert_array_equal(v,fields(x.reshape(1,-1),y.reshape(1,-1))[k][0])
 def test_repair_paint_and_age_agree(self):
  c=np.mean(PATCHES[0],axis=0);f=fields(*c);self.assertEqual(float(f['age']),0);self.assertEqual(float(f['paint_retention']),0)
 def test_traffic_broad_not_black_stripe(self):
  x=np.linspace(.01,3.1,6000);f=fields(x,np.zeros_like(x));width=np.count_nonzero(f['traffic']>.5)*(x[1]-x[0]);self.assertGreater(width,.5);self.assertLess(width,.9)
if __name__=='__main__':unittest.main()
