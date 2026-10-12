import unittest
import numpy as np
from metric_margin_fragments_as import build_fragment,audit_fragment

class FragmentContract(unittest.TestCase):
 def test_closed_metric_bodies(self):
  for i in range(40):
   r=audit_fragment(build_fragment(i));self.assertGreater(r['solid_volume_m3'],0);self.assertLess(r['dimensions_m'][2],.20)
 def test_exact_deterministic_geometry(self):
  for i in range(4):
   a,b=build_fragment(i),build_fragment(i);np.testing.assert_array_equal(a.vertices,b.vertices);np.testing.assert_array_equal(a.faces,b.faces)
 def test_four_distinct_aspect_families(self):
  rows=[build_fragment(i) for i in range(40)];self.assertEqual({r.family for r in rows},{'slab','block','splinter','broken_lump'})
  spl=[np.ptp(r.vertices[:,1])/np.ptp(r.vertices[:,0]) for r in rows if r.family=='splinter'];self.assertLess(np.median(spl),.5)
 def test_minimum_datum_and_physical_weathering(self):
  for i in range(40):
   r=build_fragment(i);self.assertEqual(float(r.vertices[:,2].min()),0);self.assertLessEqual(r.weathering_width_m,.0018);self.assertGreaterEqual(r.weathering_width_m,.00055)
 def test_bounded_distinct_mineral_materials(self):
  rows=[build_fragment(i) for i in range(40)];self.assertGreaterEqual(len({r.mineral for r in rows}),6)
  for r in rows:self.assertTrue(np.all((r.color>=0)&(r.color<=1)));self.assertTrue(np.all((r.roughness>=.45)&(r.roughness<=.9)))

if __name__=='__main__':unittest.main()
