"""Tiny source-only invariant tests; no Blender, renderer, files, or global RNG."""
from dataclasses import replace, fields
import unittest
import numpy as np

from stable_catalog import (CatalogSpec, Prototype, CatalogLimitError, build_catalog,
                            build_candidates, candidate_block, concatenate_batches,
                            pack_candidates, physical_count, select_view, world_cells,
                            lod_fraction, select_view_indices)


class StableCatalogTests(unittest.TestCase):
    def setUp(self):
        self.prototypes = [Prototype(13, 0, 0, 43.25, .041),
                           Prototype(297, 1, 1, 61.75, .026),
                           Prototype(885, 2, 1, 29.2, .021)]
        self.spec = CatalogSpec(seed=2610100225, cell_size=.5,
                                bounds=(-1., 1., -1., 1.),
                                thinning_by_band={0: .9, 1: .72},
                                catalog_epoch="tiny-fixture-v1",
                                source_pins={"geometry": "fixture-unchanged", "recipe": "fixture-v1"},
                                max_virtual_candidates=9000, max_catalog_candidates=8000,
                                max_grid_bins=10000, chunk_size=11)
        self.blockers = np.array([[0., 0., .2], [-.6, .3, .11], [3., 3., .02]])

    def assert_same(self, a, b):
        self.assertEqual(len(a), len(b))
        for f in fields(a):
            aa, bb = getattr(a, f.name), getattr(b, f.name)
            self.assertEqual(aa.dtype, bb.dtype, f.name)
            self.assertEqual(aa.tobytes(), bb.tobytes(), f.name)

    def assert_common_payload(self, a, b):
        common, ia, ib = np.intersect1d(a.ids, b.ids, return_indices=True)
        self.assertGreater(len(common), 0)
        self.assert_same(a.take(ia), b.take(ib))

    def test_identity_v1_golden_vector(self):
        a = candidate_block(2610100225, self.prototypes[0], (-2, 1), .5, 0, 3)
        np.testing.assert_array_equal(a.ids, np.array([8366825416933162250, 9374484820994477094, 17574060294370507301], dtype="u8"))
        expected_xy = np.array([[-.5862184421682604, .7737430003113956], [-.8684633348033555, .8645413009388572], [-.7584996489453296, .6164070205701091]])
        self.assertEqual(a.xy.tobytes(), expected_xy.tobytes())
        expected_yaw = np.array([4.559284687042236, 2.6964643001556396, 2.3200910091400146], dtype="f4")
        self.assertEqual(a.yaw.tobytes(), expected_yaw.tobytes())

    def test_reordered_evaluation_and_chunking_are_bitwise_equal(self):
        a = build_catalog(self.spec, self.prototypes, self.blockers)
        b = build_catalog(replace(self.spec, chunk_size=3), self.prototypes[::-1], self.blockers[::-1],
                          cell_order=np.arange(len(world_cells(self.spec)))[::-1])
        self.assert_same(a.grains, b.grains)
        np.testing.assert_array_equal(a.rejected_ids, b.rejected_ids)
        np.testing.assert_array_equal(a.rejection_reason, b.rejection_reason)
        self.assertEqual(a.provenance, b.provenance)
        self.assertEqual(a.report, b.report)
        candidates, _ = build_candidates(self.spec, self.prototypes)
        order = np.arange(len(candidates))[::-1]
        ca, ra, _ = pack_candidates(candidates, self.blockers)
        cb, rb, _ = pack_candidates(candidates.take(order), self.blockers[::-1])
        self.assert_same(ca, cb)
        np.testing.assert_array_equal(ra, rb)

    def test_unrelated_early_quotas_cannot_shift_random_draws(self):
        p, q = self.prototypes[:2]
        candidate_block(self.spec.seed, p, (-11, 15), self.spec.cell_size, 0, 2)
        a = candidate_block(self.spec.seed, q, (3, -7), self.spec.cell_size, 0, 31)
        candidate_block(self.spec.seed, p, (-11, 15), self.spec.cell_size, 0, 89)
        b = candidate_block(self.spec.seed, q, (3, -7), self.spec.cell_size, 0, 31)
        self.assert_same(a, b)
        parts = [candidate_block(self.spec.seed, q, (3, -7), self.spec.cell_size, 0, 7),
                 candidate_block(self.spec.seed, q, (3, -7), self.spec.cell_size, 7, 31)]
        self.assert_same(a, concatenate_batches(parts))
        self.assertTrue(np.all(a.xy[:, 0] >= 1.5))
        self.assertTrue(np.all(a.xy[:, 0] < 2.))
        self.assertTrue(np.all(a.xy[:, 1] >= -3.5))
        self.assertTrue(np.all(a.xy[:, 1] < -3.))

    def test_catalog_thinning_preserves_virtual_identity_and_payload(self):
        low = replace(self.spec, thinning_by_band={0: .25, 1: .2})
        lo, _ = build_candidates(low, self.prototypes)
        hi, _ = build_candidates(self.spec, self.prototypes)
        self.assertTrue(set(lo.ids).issubset(set(hi.ids)))
        self.assert_common_payload(lo, hi)
        a = build_catalog(low, self.prototypes, self.blockers)
        b = build_catalog(self.spec, self.prototypes, self.blockers)
        self.assert_common_payload(a.grains, b.grains)
        self.assertNotEqual(a.provenance["catalog_fingerprint_sha256"], b.provenance["catalog_fingerprint_sha256"])
        # Packed membership across changed thinning is deliberately NOT promised nested.

    def test_lod_probabilities_and_render_budgets(self):
        catalog = build_catalog(self.spec, self.prototypes, self.blockers)
        all_visible = np.ones(len(catalog.grains), dtype=bool)
        low = select_view(catalog.grains, all_visible, .23)
        high = select_view(catalog.grains, all_visible, .79)
        self.assertTrue(set(low.ids).issubset(set(high.ids)))
        self.assert_common_payload(low, high)
        a = select_view(catalog.grains, all_visible, .79, max_instances=19)
        b = select_view(catalog.grains, all_visible, .79, max_instances=43)
        indices = select_view_indices(catalog.grains, all_visible, .79, max_instances=19)
        self.assert_same(a, catalog.grains.take(indices))
        self.assertEqual(len(a), 19)
        self.assertEqual(len(b), 43)
        self.assertTrue(set(a.ids).issubset(set(b.ids)))
        self.assert_common_payload(a, b)
        self.assertEqual(len(select_view(catalog.grains, all_visible, 1., max_instances=0)), 0)
        self.assert_same(catalog.grains, select_view(catalog.grains, all_visible, 1.))

    def test_two_geometric_cameras_and_resolutions_keep_payload(self):
        catalog = build_catalog(self.spec, self.prototypes, self.blockers)
        original_bytes = catalog.grains.xy.tobytes()
        def camera(center, resolution, budget):
            # A downward-looking perspective camera two metres above a z=0 plane.
            # Same physical FOV across resolutions; translated second camera.
            q = catalog.grains.xy - np.asarray(center)
            depth = 2.
            width, height = resolution
            focal_px = width / 2.
            uv = q / depth * focal_px + np.array([width, height]) / 2
            visible = ((uv[:, 0] >= 0) & (uv[:, 0] < width) &
                       (uv[:, 1] >= 0) & (uv[:, 1] < height))
            diameter_px = 2 * catalog.grains.radius * focal_px / depth
            probability = lod_fraction(diameter_px)
            return select_view(catalog.grains, visible, probability, max_instances=budget)
        a = camera((-.35, -.1), (24, 16), 170)
        b = camera((.25, .1), (48, 32), 250)
        self.assert_common_payload(a, b)
        self.assertEqual(catalog.grains.xy.tobytes(), original_bytes)
        self.assertEqual(len(np.intersect1d(a.ids, catalog.rejected_ids)), 0)
        self.assertEqual(len(np.intersect1d(b.ids, catalog.rejected_ids)), 0)

    def test_original_blocker_acceptance_precedes_every_view(self):
        a = build_catalog(self.spec, self.prototypes, self.blockers)
        self.assertGreater(a.report["original_blocker_rejections"], 0)
        for block in self.blockers:
            d2 = np.sum((a.grains.xy - block[:2]) ** 2, axis=1)
            self.assertTrue(np.all(d2 >= (a.grains.radius + block[2]) ** 2))
        for i in range(len(a.grains)):
            d2 = np.sum((a.grains.xy[i+1:] - a.grains.xy[i]) ** 2, axis=1)
            self.assertTrue(np.all(d2 >= (a.grains.radius[i+1:] + a.grains.radius[i]) ** 2))
        accepted = a.grains.ids.copy()
        for visibility in [a.grains.xy[:, 0] > 0, a.grains.xy[:, 0] <= 0, np.zeros(len(a.grains), bool)]:
            selected = select_view(a.grains, visibility, .7, max_instances=37)
            self.assertTrue(set(selected.ids).issubset(set(accepted)))
        np.testing.assert_array_equal(accepted, a.grains.ids)

    def test_typed_grid_matches_brute_force_and_one_bin(self):
        candidates, _ = build_candidates(self.spec, self.prototypes)
        a, reasons, _ = pack_candidates(candidates, self.blockers)
        b, reduced, diagnostics = pack_candidates(candidates, self.blockers, max_grid_bins=1)
        self.assertEqual(diagnostics["grid_bins"], 1)
        self.assert_same(a, b)
        np.testing.assert_array_equal(reasons, reduced)
        expected = np.zeros(len(a), np.uint8)
        for i in range(len(a)):
            if np.any(np.sum((self.blockers[:, :2] - a.xy[i])**2, axis=1) < (self.blockers[:, 2] + a.radius[i])**2):
                expected[i] = 1
            else:
                prior = np.flatnonzero(expected[:i] == 0)
                if np.any(np.sum((a.xy[prior] - a.xy[i])**2, axis=1) < (a.radius[prior] + a.radius[i])**2):
                    expected[i] = 2
        np.testing.assert_array_equal(reasons, expected)

    def test_target_and_achieved_density_are_distinct_and_honest(self):
        a = build_catalog(self.spec, self.prototypes, self.blockers)
        self.assertAlmostEqual(a.report["target_physical_density_per_m2"], 134.2)
        self.assertEqual(a.report["achieved_display_catalog_density_per_m2"], len(a.grains) / 4)
        self.assertLess(a.report["achieved_display_catalog_density_per_m2"], a.report["target_physical_density_per_m2"])
        self.assertEqual(a.report["catalog_attempt_count"], len(a.grains) + len(a.rejected_ids))
        for p, row in zip(self.prototypes, a.report["prototypes"]):
            self.assertAlmostEqual(row["expected_physical_count_in_scope"], p.density_per_m2 * 4)
        cells = world_cells(self.spec)
        for p in self.prototypes:
            expectation = p.density_per_m2 * self.spec.cell_size**2
            counts = [physical_count(self.spec.seed, p, cell, self.spec.cell_size) for cell in cells]
            self.assertTrue(set(counts).issubset({int(np.floor(expectation)), int(np.ceil(expectation))}))

    def test_safe_numeric_and_count_matrix_bounds(self):
        with self.assertRaises(ValueError):
            Prototype(1, 0, 0, 1., 1e200)
        with self.assertRaises(CatalogLimitError):
            build_candidates(replace(self.spec, max_count_entries=3), self.prototypes)
        candidates, _ = build_candidates(self.spec, self.prototypes)
        with self.assertRaises(ValueError):
            pack_candidates(candidates, [[1e200, 0, 1e200]])
        a = build_catalog(self.spec, self.prototypes, [[0., 0., .1], [-0., 0., .1]])
        b = build_catalog(self.spec, self.prototypes, [[-0., 0., .1], [0., 0., .1]])
        self.assertEqual(a.provenance, b.provenance)

    def test_fixed_bounds_origin_and_failure_bounds(self):
        # Non-cell-aligned scope must not move a shared ID or rescale its cell.
        full, _ = build_candidates(self.spec, self.prototypes)
        clipped, _ = build_candidates(replace(self.spec, bounds=(-.91, .73, -.84, .88)), self.prototypes)
        self.assert_common_payload(full, clipped)
        self.assertTrue(set(clipped.ids).issubset(set(full.ids)))
        with self.assertRaises(CatalogLimitError):
            build_catalog(replace(self.spec, max_virtual_candidates=3), self.prototypes)
        with self.assertRaises(CatalogLimitError):
            build_catalog(replace(self.spec, max_catalog_candidates=3), self.prototypes)
        with self.assertRaises(ValueError):
            build_candidates(self.spec, self.prototypes, cell_order=[0])
        with self.assertRaises(ValueError):
            pack_candidates(full, [[0, 0, -1]])
        with self.assertRaises(ValueError):
            full.xy[0, 0] = 5


if __name__ == "__main__":
    unittest.main(verbosity=2)
