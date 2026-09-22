from pathlib import Path
import sys,unittest,tempfile,json,struct
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cybr_scenes import verify_render,exclusive,SCENES,ROOT,read_pfm
from tools.finish_r2 import demodulate_pass
class PipelineTests(unittest.TestCase):
 def test_scene_registry_complete(self):
  self.assertEqual(len(SCENES),6)
  for scene in SCENES.values():
   self.assertTrue((ROOT/scene['reference']).is_file())
   self.assertNotEqual(scene['mesh'],scene['upgraded_mesh'])
 def test_existing_lock_is_not_deleted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'lock'
   with exclusive(p):
    owner=p.read_text()
    with self.assertRaises(RuntimeError):
     with exclusive(p):pass
    self.assertEqual(p.read_text(),owner)
 def test_albedo_remodulation_identity_and_exclusion(self):
  rng=np.random.default_rng(413);rgb=rng.random((5,8,3),dtype='f4');alb=rng.random(rgb.shape,dtype='f4')
  n=np.zeros_like(rgb);depth=np.ones((5,8),dtype='f4');var=depth.copy();mat=depth.copy();mask=depth.astype(bool);mask[:2]=False
  identity=lambda r,*rest:r.copy()
  out=demodulate_pass(identity,rgb,n,alb,depth,var,mat,1,mask)
  np.testing.assert_allclose(out,rgb,atol=6e-8);np.testing.assert_array_equal(out[:2],rgb[:2])
 def test_negative_display_rgb_is_not_negative_spectral_energy(self):
  with tempfile.TemporaryDirectory() as d:
   stem=Path(d)/'proof';w,h=8,6
   rgb=np.ones((h,w,3),dtype='<f4');rgb[2,2,0]=-.00005
   with stem.with_suffix('.pfm').open('wb') as f:f.write(f'PF\n{w} {h}\n-1.0\n'.encode());f.write(np.flipud(rgb).tobytes())
   pixels=np.arange(h*w*3,dtype=np.uint8).reshape(h,w,3);Image.fromarray(pixels).save(stem.with_suffix('.png'))
   stem.with_suffix('.json').write_text(json.dumps({'triangles':1,'image_generation':False,'nonfinite_path_samples':0}))
   bands=np.ones((h,w,16),dtype='<f4')
   with stem.with_suffix('.spectral').open('wb') as f:f.write(struct.pack('<4I',0x36315053,w,h,16));f.write(bands.tobytes())
   report=verify_render(stem,w,h);self.assertTrue(report['passed']);self.assertEqual(report['negative_linear_rgb_components'],1)
   bands[0,0,0]=-.1
   with stem.with_suffix('.spectral').open('wb') as f:f.write(struct.pack('<4I',0x36315053,w,h,16));f.write(bands.tobytes())
   with self.assertRaises(RuntimeError):verify_render(stem,w,h)
if __name__=='__main__':unittest.main()
