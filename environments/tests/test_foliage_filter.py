import sys,unittest,tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.foliage_filter import leaf_pass
from cybr_scenes import SCENES,render_command,ROOT
class FoliageTests(unittest.TestCase):
 def guides(self):
  shape=(13,13);normal=np.zeros((*shape,3),dtype='f4');normal[:,:,2]=1;normal[:,::2,2]=-1
  albedo=np.full((*shape,3),.1,dtype='f4');depth=np.full(shape,10,dtype='f4');variance=np.ones(shape,dtype='f4');material=np.full(shape,9,dtype='f4')
  return normal,albedo,depth,variance,material
 def test_two_sided_constant_radiance_is_preserved(self):
  g=self.guides();rgb=np.full((13,13,3),.24,dtype='f4');out=leaf_pass(rgb,*g,1)
  np.testing.assert_allclose(out,rgb,atol=1e-7)
 def test_isolated_zero_sample_leaf_is_not_locked_black(self):
  g=self.guides();rgb=np.full((13,13,3),.24,dtype='f4');rgb[6,6]=0
  out=leaf_pass(rgb,*g,1);self.assertGreater(float(out[6,6,0]),.16);self.assertLessEqual(float(out.max()),.240001)
 def test_unrelated_material_and_sky_are_untouched(self):
  g=list(self.guides());g[-1][:3]=-1;g[-1][3:6]=6
  rgb=np.random.default_rng(122).random((13,13,3),dtype='f4');out=leaf_pass(rgb,*g,1)
  np.testing.assert_array_equal(out[:6],rgb[:6])
 def test_hot_sun_flag_uses_native_two_argument_form(self):
  s=SCENES['desert-hot-springs'];command,_,_=render_command(s,ROOT/'build/hot_r2',ROOT/s['upgraded_mesh'],Path('/tmp/test'),8,8,1,1,1)
  i=command.index('--sun');self.assertEqual(command[i+1],'-0.80,0.40,0.28');self.assertFalse(any(str(x).startswith('--sun=') for x in command))
if __name__=='__main__':unittest.main()
