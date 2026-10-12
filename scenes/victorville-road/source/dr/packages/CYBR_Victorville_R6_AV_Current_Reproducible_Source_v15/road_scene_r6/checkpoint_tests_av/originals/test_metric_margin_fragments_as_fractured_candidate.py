import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from metric_margin_fragments_as import build_fragment as build_stock
from metric_margin_fragments_as_fractured_candidate import build_fragment, audit_fragment

ROOT = Path(__file__).resolve().parents[1]

class FracturedCandidateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = [build_fragment(i) for i in range(40)]
        cls.stock = [build_stock(i) for i in range(40)]

    def test_closed_oriented_positive_genus_zero_concave_analytical_solids(self):
        for f in self.bank:
            r = audit_fragment(f)
            self.assertTrue(r['analytical_solid_boundary_verified'])
            self.assertGreater(r['convex_deficit_fraction'], .0001)
            self.assertLess(r['removed_volume_fraction'], .15)

    def test_metric_targets_families_no_inflation_or_instance_scaling(self):
        for a, b in zip(self.stock, self.bank):
            da, db = np.ptp(a.vertices,axis=0), np.ptp(b.vertices,axis=0)
            self.assertTrue(np.all(db <= da + 2e-9))
            self.assertTrue(np.all(db >= da * .7))
            self.assertEqual(a.nominal_length_m, b.nominal_length_m)
            self.assertEqual(a.weathering_width_m, b.weathering_width_m)
            self.assertEqual(a.family, b.family)
            self.assertEqual(b.vertices[:,2].min(), 0.)
            np.testing.assert_allclose(b.vertices[:,:2].min(0)+b.vertices[:,:2].max(0),0,atol=1e-15)
        self.assertEqual({f.family for f in self.bank}, {'block','slab','splinter','broken_lump'})
        self.assertLess(np.median([np.ptp(f.vertices[:,1])/np.ptp(f.vertices[:,0]) for f in self.bank if f.family=='splinter']),.5)

    def test_every_boundary_stays_inside_authored_fracture_blank(self):
        for f in self.bank:
            p=f.vertices+f.stock_coordinate_offset_m
            h=f.retained_blank_planes
            self.assertLess(np.max(p @ h[:, :3].T + h[:, 3]), 2e-9)

    def test_determinism(self):
        for i in (0, 4, 15, 18, 33, 39):
            b = build_fragment(i)
            for key in ('vertices','faces','color','roughness'):
                np.testing.assert_array_equal(getattr(self.bank[i],key), getattr(b,key))

    def test_material_field_identity_and_linkage(self):
        for a, b in zip(self.stock, self.bank):
            self.assertEqual(a.mineral, b.mineral)
            za = a.vertices[:,2]
            zb = b.vertices[:,2]+b.stock_coordinate_offset_m[2]
            xa, xb = np.c_[za*0+1, za, za**2], np.c_[zb*0+1, zb, zb**2]
            for key in ('color', 'roughness'):
                expected = xb @ np.linalg.lstsq(xa, getattr(a,key), rcond=None)[0]
                np.testing.assert_allclose(getattr(b,key), expected, atol=2e-12, rtol=0)

    def test_index_33_is_reauthored_mass_with_open_outer_ridge_events(self):
        a, b = self.stock[33], self.bank[33]
        r = audit_fragment(b)
        self.assertEqual(b.family, 'block')
        self.assertEqual(len(b.spalls), 3)
        self.assertGreater(r['primary_fracture_face_count'], 20)
        self.assertGreater(r['convex_deficit_fraction'], .003)
        self.assertGreater(len(b.faces), len(a.faces))
        for event in b.spalls:
            p=np.array(event['site_m'])
            self.assertGreater(np.linalg.norm(p[:2]/b.stock_dimensions_m[:2]), .38)

    def test_bounded_event_geometry_weathering_and_storage(self):
        total = 0
        for f in self.bank:
            for e in f.spalls:
                self.assertLessEqual(e['depth_m'], .025)
                self.assertGreater(e['depth_m'], 0)
            self.assertTrue(all(.00055 <= w <= .0018 for w in f.new_edge_setbacks_m))
            total += sum(getattr(f,k).nbytes for k in ('vertices','faces','color','roughness'))
        self.assertLess(total, 20 * 1024**2)

    def test_stable_baseline_and_pre_task_assembly_pins(self):
        # The old API fixture predates the pre-task assembly revision. Its
        # generator pin remains valid; assembly below had mtime 09:38:57 UTC,
        # before this morphology task began at 09:53:45 UTC.
        recorded=json.loads((ROOT/'receipts/as_api_fixture.json').read_text())['source_sha256']
        pins={'metric_margin_fragments_as.py':recorded['metric_margin_fragments_as.py'],
              'assemble_metric_fragments_as.py':'c3138a0ac51b01bf6d9a91ae7d2b6d450175e58babdf1e380993f903753ab445'}
        for name,sha in pins.items():
            self.assertEqual(hashlib.sha256((ROOT/'src'/name).read_bytes()).hexdigest(),sha)

if __name__ == '__main__':
    unittest.main()
