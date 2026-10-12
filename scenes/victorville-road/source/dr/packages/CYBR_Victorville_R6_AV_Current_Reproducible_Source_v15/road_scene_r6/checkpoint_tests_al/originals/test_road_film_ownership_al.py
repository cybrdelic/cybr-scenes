import unittest,numpy as np
from road_film_ownership_al import split_inventory
class Ownership(unittest.TestCase):
 def fields(self):return dict(x_m=np.arange(4)*.025,y_m=np.arange(3)*.025,pavement=np.array([[0,0,1,1]]*3,dtype=bool),remaining_mobile_class_thickness_m=np.arange(36).reshape(3,4,3)*1e-6)
 def test_split_and_preserve(self):
  f=self.fields();before=f['remaining_mobile_class_thickness_m'].copy();r,s,d=split_inventory(f);np.testing.assert_array_equal(r+s,before);np.testing.assert_array_equal(f['remaining_mobile_class_thickness_m'],before);self.assertTrue(d['conserved_split']);self.assertTrue(np.all(r[:,0:2]==0));np.testing.assert_array_equal(r[:,2:],before[:,2:]);self.assertTrue(np.all(s[:,2:]==0))
 def test_positive_volume(self):
  r,s,d=split_inventory(self.fields());np.testing.assert_allclose(np.array(d['pavement_owned_by_class_m3'])+d['soil_owned_by_class_m3'],d['total_by_class_m3'],rtol=1e-14)
 def test_bad_stock(self):
  f=self.fields();f['remaining_mobile_class_thickness_m'][0,0,0]=-1
  with self.assertRaises(ValueError):split_inventory(f)
 def test_bad_ownership(self):
  f=self.fields();f['pavement']=np.ones((3,4))*.5
  with self.assertRaises(ValueError):split_inventory(f)
 def test_shapes(self):
  f=self.fields();f['pavement']=np.ones((2,4))
  with self.assertRaises(ValueError):split_inventory(f)
 def test_axes(self):
  f=self.fields();f['x_m'][2]+=.001
  with self.assertRaises(ValueError):split_inventory(f)
if __name__=='__main__':unittest.main()
