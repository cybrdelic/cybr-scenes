"""Test real deformation math, binary preservation and failure handling."""
from pathlib import Path
import sys,unittest,tempfile,struct
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.enhance_geometry import wave,deform,mineral_deform,curl_litter,layout,sha
class GeometryTests(unittest.TestCase):
 def setUp(self):self.rng=np.random.default_rng(731)
 def test_wave_gradient(self):
  p=self.rng.uniform(-4,4,(100,3)).astype('f4');a=.027;freq=(1.1,2.2,3.3);ph=(.3,.2,.1)
  h,g=wave(p,a,freq,ph);fd=np.empty_like(g);eps=1e-3
  for i in range(3):
   e=np.eye(3,dtype='f4')[i]*eps;fd[:,i]=(wave(p+e,a,freq,ph)[0]-wave(p-e,a,freq,ph)[0])/(2*eps)
  np.testing.assert_allclose(g,fd,atol=1.2e-5,rtol=2e-3)
 def test_inverse_transpose(self):
  p=self.rng.normal(size=(300,3)).astype('f4');n=self.rng.normal(size=(300,3)).astype('f4');n/=np.linalg.norm(n,axis=1)[:,None]
  h,g=wave(p,.02,(2.3,3.1,1.9),(.1,.2,.3));e=np.array([0,0,1.],dtype='f4')
  _,nn,det=deform(p,n,h,g,e);J=np.eye(3)[None]+e[None,:,None]*g[:,None,:]
  check=np.linalg.solve(J.transpose(0,2,1),n[...,None])[...,0];check/=np.linalg.norm(check,axis=1)[:,None]
  np.testing.assert_allclose(nn,check,atol=3e-7);self.assertGreater(det,.8)
 def test_six_noninverting_world_deformations(self):
  p=self.rng.uniform(-20,20,(10000,3)).astype('f4');n=self.rng.normal(size=p.shape).astype('f4');n/=np.linalg.norm(n,axis=1)[:,None]
  for scene in ['sandstone-passage','basalt-tide','fernwater','desert-hot-springs','drowned-geode','obsidian-reach']:
   with self.subTest(scene=scene):
    pp,nn,det,disp=mineral_deform(p,n,scene)
    self.assertTrue(np.isfinite(pp).all());self.assertGreater(det,.4);self.assertLess(disp,.044)
    np.testing.assert_allclose(np.linalg.norm(nn,axis=1),1,atol=2e-7)
 def test_litter_endpoints(self):
  f=np.array([[0,0,0,1,0,0,0,1,0,0,0,1,.1,.04,4,11]],dtype='f4').repeat(3,axis=0)
  p=np.array([[0,0,0],[.1,0,0],[.05,.02,0]],dtype='f4');n=np.tile([0,0,1.],(3,1)).astype('f4')
  pp,nn,det,disp=curl_litter(p,n,f);np.testing.assert_allclose(pp[:2],p[:2],atol=1e-8);self.assertGreater(pp[2,2],0)
 def test_inversion_is_rejected(self):
  with self.assertRaises(ValueError):deform(np.zeros((1,3)),np.array([[0.,0,1.]]),np.ones(1),np.array([[0.,0,-2.]]),[0,0,1])
 def test_native_layout_headers(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'x';p.write_bytes(struct.pack('<I',7)+b'\0'*560)
   self.assertEqual(layout(p,'fernwater')[:3],(4,7,20))
   p.write_bytes(b'CVR2'+struct.pack('<I',7)+b'\0'*1008)
   self.assertEqual(layout(p,'drowned-geode')[:3],(8,7,36))
   p.write_bytes(b'FAIL'+b'\0'*80)
   with self.assertRaises(ValueError):layout(p,'drowned-geode')
class StreamAssemblyTests(unittest.TestCase):
 def test_disk_spool_and_exact_native_roundtrip(self):
  root=Path(__file__).resolve().parents[1]
  sys.path.insert(0,str(root/'engines/hot/cybr-geo/src'))
  sys.path.insert(0,str(root/'engines/hot/cybr-geo/examples/desert_hot_springs'))
  from cybrgeo import Part,Assembly,Material
  from stream_scene_r2 import PartSpool,roundtrip_to_native
  with tempfile.TemporaryDirectory() as directory:
   d=Path(directory);v=np.array([[0.,0,0],[1000,0,0],[0,1000,0]],dtype='f8');f=np.array([[0,1,2]],dtype='i8');n=np.tile([0.,0,1],(3,1))
   p=Part('Known_triangle',v.copy(),f.copy(),n.copy());p=PartSpool(d/'spool').store(p)
   self.assertIsInstance(p.vertices,np.memmap);self.assertFalse(p.vertices.flags.writeable)
   np.testing.assert_array_equal(p.vertices,v)
   Assembly('Spool_test',[p],[Material()]).save(d/'scene')
   report=roundtrip_to_native(d/'scene',d/'scene.meshbin',1)
   a=np.fromfile(d/'scene.meshbin',dtype='<f4',offset=4).reshape(1,20)
   np.testing.assert_array_equal(a[0,:9],(v*.001).astype('f4').ravel());np.testing.assert_array_equal(a[0,9:18],n.ravel())
   self.assertTrue(report['actual_cybrgeo_part_roundtrip']);self.assertEqual(report['triangles'],1)
   with (d/'scene/meshes.npz').open('ab') as out:out.write(b'bad')
   with self.assertRaises(ValueError):roundtrip_to_native(d/'scene',d/'bad.meshbin',1)
if __name__=='__main__':unittest.main(verbosity=2)
