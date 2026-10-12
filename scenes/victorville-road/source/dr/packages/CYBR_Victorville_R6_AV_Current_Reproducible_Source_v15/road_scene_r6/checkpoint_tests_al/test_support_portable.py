"""Small synthetic triangle-overlap and captured-adapter checks; no saved fields."""
import ast
import inspect
import unittest
import numpy as np
import contact_bank_continuity_al as bank
from contact_triangle_clearance_al import exact_clearance
from metric_edge_strip_aa import TriangleSampler


class ExactOverlap(unittest.TestCase):
    def scene(self, reverse=False):
        road = np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.],[.5,.5,-.01]])
        tri = np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])
        if reverse: tri = tri[:,::-1]
        sampler = TriangleSampler(road,tri,cell=.25,max_bucket_entries=50000)
        co = np.array([[-2.,-2.,-.005],[4.,-2.,-.005],[-2.,4.,-.005]])
        return co,np.array([[0,1,2]]),sampler

    def test_interior_intersection_finds_penetration(self):
        co,tri,sampler = self.scene()
        r = exact_clearance(co,tri,sampler,(0.,1.,0.,1.))
        self.assertEqual(r['penetrating_overlap_polygons'],4)
        self.assertAlmostEqual(r['minimum_linear_mesh_clearance_m'],-.005)
        self.assertAlmostEqual(r['overlap_area_m2'],1.)

    def test_road_winding_and_roi_clipping(self):
        args = self.scene(); reversed_args = self.scene(True)
        a = exact_clearance(*args,(.1,.4,.1,.4))
        b = exact_clearance(*reversed_args,(.1,.4,.1,.4))
        self.assertAlmostEqual(a['overlap_area_m2'],.09)
        self.assertAlmostEqual(a['minimum_linear_mesh_clearance_m'],b['minimum_linear_mesh_clearance_m'])
        self.assertEqual(a['penetrating_overlap_polygons'],b['penetrating_overlap_polygons'])

    def test_clear_and_no_overlap_are_distinct(self):
        co,tri,sampler = self.scene(); co[:,2] = -.02
        r = exact_clearance(co,tri,sampler,(0.,1.,0.,1.))
        self.assertEqual(r['penetrating_overlap_polygons'],0)
        self.assertAlmostEqual(r['minimum_linear_mesh_clearance_m'],.01)
        r = exact_clearance(co,tri,sampler,(8.,9.,8.,9.))
        self.assertEqual(r['overlap_polygons'],0)
        self.assertIsNone(r['minimum_linear_mesh_clearance_m'])

    def test_adapter_preserves_normals_before_geometry_update(self):
        source = inspect.getsource(bank.apply)
        ast.parse(source)
        self.assertLess(source.index('normals = _read(mesh.corner_normals'),source.index('mesh.vertices.foreach_set'))
        self.assertIn('update_normals',source)
        for forbidden in ('open_mainfile','save_as_mainfile','bpy.ops.render'):
            self.assertNotIn(forbidden,source)

    def test_captured_plan_keeps_exact_overlap_rejection(self):
        source = inspect.getsource(bank.plan_bank)
        self.assertIn('exact_clearance',source)
        self.assertIn("exact['penetrating_overlap_polygons']==0",source)
        self.assertIn('Exact bank/road intersection audit found penetration',source)
