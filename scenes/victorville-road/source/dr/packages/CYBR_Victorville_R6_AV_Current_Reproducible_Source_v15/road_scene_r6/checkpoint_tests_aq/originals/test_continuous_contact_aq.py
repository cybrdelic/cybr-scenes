"""Bounded pure CPU AQ tests: no Blender, scene, render, or source writes."""
import unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
import continuous_contact_aq as aq
from metric_edge_strip_aa import TriangleSampler
from test_contact_bank_continuity_al import grid


def fixture():
    ys=np.unique(np.r_[np.arange(-.5,16.01,.1),.3,3.6,6.2,12.])
    ground=grid(np.linspace(-4.1,-3.15,39),ys,
                lambda x,y:.0802+.01*y+.03*(x+3.2))
    road=grid(np.linspace(-3.2,-2.95,11),ys,
              lambda x,y:.08+.01*y+.02*(x+3.2))
    return *ground,*road


class ContactTests(unittest.TestCase):
    def test_full_visible_gate(self):
        s=aq.ContactSpec();ys=np.linspace(0,15,101)
        np.testing.assert_array_equal(aq.gate(np.c_[np.full(len(ys),-3.2),ys],s),1.)
        np.testing.assert_array_equal(aq.gate([[-3.2,-.35],[-3.2,15.65],[-3.95,3]],s),0.)

    def test_exact_overlap_detects_interior_missed_by_vertices(self):
        # Road central pit: all three soil vertices clear the road, the interior does not.
        rc=np.array([[0.,0.,1.],[1,0,1],[0,1,1],[.3,.3,-1]])
        rt=np.array([[0,1,3],[1,2,3],[2,0,3]])
        road=TriangleSampler(rc,rt,cell=.25)
        co=np.array([[0.,0.,0.],[1,0,0],[0,1,0.]])
        tr=np.array([[0,1,2]]);correction=np.zeros(3)
        r=aq.overlap_constraints(co,tr,road,(-.1,1.1,-.1,1.1),.0008,correction)
        self.assertGreater(r['penetrating_overlap_polygons'],0)
        self.assertTrue(np.all(correction>1.))
        co[:,2]-=correction
        final=aq.overlap_constraints(co,tr,road,(-.1,1.1,-.1,1.1))
        self.assertEqual(final['penetrating_overlap_polygons'],0)
        self.assertGreaterEqual(final['minimum_linear_mesh_clearance_m'],.0008)

    def test_complete_plan_source_identity_and_connected_exposure(self):
        args=fixture();copies=[a.copy() for a in args]
        p=aq.plan_contact(*args)
        for a,b in zip(args,copies):np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(p.before[:,:2],p.after[:,:2])
        self.assertGreater(p.report['changed_vertices'],500)
        self.assertEqual(p.report['exact_triangle_clearance']['penetrating_overlap_polygons'],0)
        self.assertGreater(p.report['near_flush_profile_fraction'],.5)
        self.assertGreater(p.report['exposed_profile_fraction'],.01)
        for lo,hi in ((0,2),(2,8.2),(8.2,15)):
            changed=(p.before[:,1]>=lo)&(p.before[:,1]<=hi)&(p.delta_m!=0)
            self.assertTrue(np.any(changed))
        self.assertFalse(p.report['periodic_or_random_edge_pattern'])
        self.assertLessEqual(np.max(abs(p.delta_m)),.040001)

    def test_exact_actual_triangle_delta_and_float32(self):
        args=list(fixture());args[0]=args[0].astype('f4');p=aq.plan_contact(*args)
        q=np.array([[-3.4,1.111],[-3.4,9.121],[-3.25,14.55]])
        from context_mesh_refine_ab import SourceSampler
        final=SourceSampler(p.after,p.local_triangles,np.arange(len(p.local_triangles)))
        np.testing.assert_allclose(p.height_shift(q),final.height(q)-p.sampler.height(q),atol=1e-16)
        self.assertEqual(p.after.dtype,np.float32)
        self.assertTrue(np.isnan(p.height_shift([[-3.,4.]]))[0])

    def test_invalid_scope_and_memory_limit_fail(self):
        for s in (replace(aq.ContactSpec(),visible_y_max_m=8.2),replace(aq.ContactSpec(),extra_buffer_cap_mib=251),replace(aq.ContactSpec(),max_movement_m=.05)):
            with self.assertRaises(ValueError):s.validate()

    def test_source_only_adapter(self):
        source=(Path(__file__).parent/'continuous_contact_aq.py').read_text()
        for bad in ('open_mainfile','save_as_mainfile','bpy.ops.render','np.random','sin('):self.assertNotIn(bad,source)
        self.assertIn('overlap_constraints',source)
        self.assertIn('move_retained(scene,plan)',source)
        self.assertLess(source.index("normals=_read(mesh.corner_normals"),source.index("mesh.vertices.foreach_set('co'"))


if __name__=='__main__':unittest.main(verbosity=2)
