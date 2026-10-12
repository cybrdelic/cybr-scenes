"""Pure CPU geometry/provenance checks; no scene load, render or source writes."""
import json,time,resource,unittest
from pathlib import Path
from dataclasses import replace
import numpy as np
from fractured_boundary_ar import *
from test_metric_edge_strip_aa import fixture


class FractureTests(unittest.TestCase):
    def test_float32_source_keeps_exact_exterior_collars(self):
        y=np.array([-.3,0.,1.,2.,5.,9.,15.,15.4],np.float32)
        co=np.array([(x,v,.1+.01*v) for v in y for x in (-3.2,-2.9)],np.float32)
        tri=[]
        for i in range(len(y)-1):
            a=2*i;tri.extend([[a,a+1,a+3],[a,a+3,a+2]])
        spec=FractureSpec();yy,xx=actual_left_boundary(co,np.array(tri,np.int32),spec)
        self.assertEqual(yy.dtype,np.float64)
        self.assertEqual(float(yy[0]),spec.y_min_m)
        self.assertEqual(float(yy[-1]),spec.y_max_m)
        np.testing.assert_allclose(xx,float(np.float32(-3.2)),atol=1e-12)

    def test_upper_majorant_removes_periodic_scallops(self):
        y=np.linspace(-.12,15.12,501);x=-3.2+.014*np.sin(y*15)+.005*np.sin(y*63)
        top,h=upper_envelope(y,x)
        self.assertTrue(np.all(top>=x-1e-12));self.assertLess(len(h),30)
        self.assertGreater(np.max(top-x),.03)
        self.assertTrue(np.all(np.diff(np.diff(top[h])/np.diff(y[h]))<1e-9))

    def test_exact_subsets_and_conforming_original_edges(self):
        co,tri,tp,polys=fixture()
        y=np.array([-.05,.07,.113,.169,.271,.433,.607,.827,1.011,1.229,1.397,1.61,1.81,2.05])
        x=np.array([-3.2,-3.182,-3.17,-3.187,-3.171,-3.19,-3.176,-3.18,-3.166,-3.183,-3.165,-3.181,-3.177,-3.19])
        b=Boundary(y,x,y,np.full(len(y),-3.2),{})
        s=FractureSpec(max_additions=12000,max_triangles=20000)
        p=clip_actual_triangles(co,tri,tp,len(polys),b,s)
        allco=np.r_[co,p.additions]
        np.testing.assert_allclose(p.additions,np.einsum('ni,nij->nj',p.addition_weights,co[tri[p.addition_triangle]]),atol=1e-15)
        np.testing.assert_allclose(allco[p.triangles],np.einsum('nki,nij->nkj',p.corner_weights,co[tri[p.triangle_source]]),atol=1e-14)
        t=np.r_[tri[np.isin(tp,p.keep_polygons)],p.triangles]
        q=allco[t];cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);self.assertTrue(np.all(cross[:,2]>1e-14))
        edges,uses=np.unique(np.sort(np.concatenate([t[:,[j,(j+1)%3]] for j in range(3)]),axis=1),axis=0,return_counts=True)
        self.assertTrue(np.all(uses<=2))
        # Every internal edge endpoint lies on fully propagated source topology.
        open_edges=edges[uses==1];q=allco[open_edges];mid=q.mean(1)
        onnew=(abs(mid[:,0]-b.x_edge(mid[:,1]))<1e-8)&(mid[:,1]>=y[0])&(mid[:,1]<=y[-1])
        onold=(abs(mid[:,0]-(-3.2+.004*mid[:,1]))<1e-8)|(abs(mid[:,0]+2.9)<1e-8)|(abs(mid[:,1]+.1)<1e-8)|(abs(mid[:,1]-2.1)<1e-8)
        # Collar cut at two endpoints can expose a short cross-section.
        oncap=(abs(mid[:,1]-y[0])<1e-8)|(abs(mid[:,1]-y[-1])<1e-8)
        self.assertTrue(np.all(onnew|onold|oncap),str(mid[~(onnew|onold|oncap)]))
        self.assertTrue(np.all(p.corner_weights>=-1e-9));np.testing.assert_allclose(p.corner_weights.sum(2),1,atol=1e-12)
        for k in range(3):
            m=(q:=allco[p.triangles[:,k]])[:,1];inside=(m>y[0]+1e-10)&(m<y[-1]-1e-10);self.assertTrue(np.all(q[inside,0]>=b.x_edge(m[inside])-1e-10))

    def test_vertical_section_source_provenance(self):
        co=np.array([[-3.21,-.3,0],[-3.21,.3,0],[-3.15,.3,-.04],[-3.15,-.3,-.04]])
        tri=np.array([[0,1,2],[0,2,3]]);b=Boundary(np.array([-.2,0,.2]),np.array([-3.19,-3.17,-3.19]),np.array([-.2,.2]),np.array([-3.21,-3.21]),{})
        p=clip_actual_triangles(co,tri,np.arange(2),2,b,FractureSpec(max_additions=1000,max_triangles=2000))
        self.assertGreater(len(p.triangles),0)
        np.testing.assert_allclose(np.r_[co,p.additions][p.triangles],np.einsum('nki,nij->nkj',p.corner_weights,co[tri[p.triangle_source]]),atol=1e-14)

    def test_retained_and_split_boolean_edge_metadata(self):
        from types import SimpleNamespace
        co,tri,tp,polys=fixture()
        b=Boundary(np.array([0.,.7,1.3,2.]),np.array([-3.18,-3.16,-3.18,-3.17]),np.array([0.,2.]),np.array([-3.2,-3.2]),{})
        p=clip_actual_triangles(co,tri,tp,len(polys),b,FractureSpec(max_additions=10000,max_triangles=20000))
        oldedges=np.unique(np.sort(np.concatenate([tri[:,[j,(j+1)%3]] for j in range(3)]),axis=1),axis=0)
        final=np.r_[tri[np.isin(tp,p.keep_polygons)],p.triangles]
        newedges=np.unique(np.sort(np.concatenate([final[:,[j,(j+1)%3]] for j in range(3)]),axis=1),axis=0)
        class Data:
            def __init__(self,a):self.a=np.asarray(a)
            def __len__(self):return len(self.a)
            def foreach_get(self,prop,out):out[:]=self.a.ravel()
            def foreach_set(self,prop,values):self.a=np.asarray(values).copy()
        class Attributes(dict):
            def new(self,name,kind,domain):
                a=SimpleNamespace(data=Data(np.zeros(len(newedges),bool)));self[name]=a;return a
        values=np.arange(len(oldedges))%3==0
        old=SimpleNamespace(vertices=co,edges=Data(oldedges),attributes={'sharp_edge':SimpleNamespace(data=Data(values))})
        new=SimpleNamespace(vertices=np.r_[co,p.additions],edges=Data(newedges),attributes=Attributes())
        r=inherit_edge_metadata(old,new,tri,p,{'sharp_edge':('EDGE','BOOLEAN','value',True,1,bool)})
        self.assertGreater(r['split_edges_inherited'],0)
        result=new.attributes['sharp_edge'].data.a
        lookup={tuple(e):bool(v) for e,v in zip(oldedges,values)}
        for edge,value in zip(newedges,result):
            if tuple(edge) in lookup:self.assertEqual(bool(value),lookup[tuple(edge)])
        self.assertTrue(result.any())

    def test_legitimate_fully_clipped_owner(self):
        co=np.array([[-3.3,.1,.1],[-3.2,.2,.1],[-3.3,.4,.12]])
        tri=np.array([[0,1,2]],np.int32);before=co.copy()
        b=Boundary(np.array([-.12,15.12]),np.array([-3.15,-3.15]),np.array([-.12,15.12]),np.array([-3.3,-3.3]),{})
        p=clip_actual_triangles(co,tri,np.array([0],np.int32),1,b,FractureSpec(max_additions=100,max_triangles=100))
        self.assertEqual(p.triangles.shape,(0,3));self.assertEqual(p.additions.shape,(0,3));self.assertEqual(len(p.keep_polygons),0)
        np.testing.assert_array_equal(co,before)

    def test_caps_fail_before_unbounded_output(self):
        co,tri,tp,polys=fixture();b=Boundary(np.array([0,1,2]),np.array([-3.17,-3.16,-3.17]),np.array([0,2]),np.array([-3.2,-3.2]),{})
        with self.assertRaises(ValueError):clip_actual_triangles(co,tri,tp,len(polys),b,FractureSpec(max_additions=1,max_triangles=1))


if __name__=='__main__':unittest.main(verbosity=2)
