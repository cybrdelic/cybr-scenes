"""Fast tests independent of a CYBR LIGHT checkout or large scene assets."""
import json,math,struct,tempfile,unittest
from pathlib import Path
import numpy as np
from export_scene import rotate,write_pfm,export,CAMERAS,quartz
from compare import read_pfm,display,reconstruct

class AdapterTests(unittest.TestCase):
    def test_proper_rotation(self):
        r=rotate(np.eye(3)).T
        np.testing.assert_array_equal(r@r.T,np.eye(3));self.assertEqual(np.linalg.det(r),1)
    def test_camera_ray_equivalence(self):
        for width,height in [(720,480),(128,86),(1800,1200)]:
            origin,target,fov=CAMERAS['hero'];f=np.array(target)-origin;f/=np.linalg.norm(f)
            right=np.cross(f,[0,0,1]);right/=np.linalg.norm(right);up=np.cross(right,f)
            nf=rotate(f);nr=np.cross(nf,[0,1,0]);nr/=np.linalg.norm(nr);nu=np.cross(nr,nf)
            ht=math.tan(math.radians(fov/2));vt=ht/(width/height)
            for x,y in [(0,0),(.5,.5),(1,1),(.13,.87)]:
                a=f+right*((2*x-1)*ht)+up*((1-2*y)*vt)
                b=nf+nr*((2*x-1)*vt*width/height)+nu*((1-2*y)*vt)
                np.testing.assert_allclose(rotate(a/np.linalg.norm(a)),b/np.linalg.norm(b),atol=1e-12)
    def test_pfm_exact_orientation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'t.pfm';a=np.arange(36,dtype=np.float32).reshape(3,4,3)/17
            write_pfm(p,a);np.testing.assert_array_equal(a,read_pfm(p))
    def test_display_and_filter_constant(self):
        a=np.full((9,13,3),.2,np.float32);n=np.zeros_like(a);n[:,:,2]=1;d=np.ones(a.shape[:2],np.float32)
        np.testing.assert_allclose(a,reconstruct(a,n,d,d*.01,3),atol=1e-6)
        self.assertEqual(display(a,[1,1,1],1).shape,a.shape)
    def test_minimal_geometry_export(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';(src/'scene').mkdir(parents=True)
            a=np.zeros((1,36),np.float32);a[0,:9]=[0,0,0,1,0,0,0,1,0]
            a[0,9:18]=[0,0,1]*3;a[0,18:20]=[0,42];a[0,20:26]=[0,0,1,0,0,1];a[0,26:35]=[.3,.4,.5]*3;a[0,35]=-1
            (src/'scene/observatory.cvr2').write_bytes(b'CVR2'+struct.pack('<I',1)+a.tobytes())
            meta=export(src,root/'out',96,64,2,4)
            self.assertEqual(meta['accepted_triangles'],1);self.assertEqual(meta['source_objects'],1)
            b=(root/'out/geometry.cybm').read_bytes();self.assertEqual(len(b),112)
            data=np.frombuffer(b[8:104],'<f4');np.testing.assert_array_equal(data[:9],rotate(a[0,:9].reshape(3,3)).ravel())
            self.assertEqual(struct.unpack('<I',b[108:112])[0],42)
            self.assertLess(meta['quartz_cauchy']['max_ior_error_360_830_nm'],.0005)
            with self.assertRaises(ValueError):export(src,src/'overwrite')
    def test_zero_area_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';(src/'scene').mkdir(parents=True)
            a=np.zeros((1,36),np.float32);a[0,9:18]=[0,0,1]*3;a[0,35]=-1
            (src/'scene/observatory.cvr2').write_bytes(b'CVR2'+struct.pack('<I',1)+a.tobytes())
            meta=export(src,root/'out',96,64,2,4);self.assertEqual(meta['accepted_triangles'],0)

if __name__=='__main__':unittest.main()
