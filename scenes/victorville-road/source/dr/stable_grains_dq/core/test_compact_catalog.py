"""Strict <=10,000-candidate parity tests against the unchanged frozen core."""
from dataclasses import fields, replace
import hashlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import stable_catalog as ref
import compact_catalog as compact

FROZEN_SHA256 = "c50333339f4f4fe92c6ce03cf10704cec83812f7cb89db07b99906504f9e044c"


class CompactParityTests(unittest.TestCase):
    def setUp(self):
        self.prototypes = [ref.Prototype(13, 0, 0, 43.25, .041),
                           ref.Prototype(297, 1, 1, 61.75, .026),
                           ref.Prototype(885, 2, 2, 29.2, .021)]
        self.spec = ref.CatalogSpec(seed=2610100225, cell_size=.5, bounds=(-1., 1., -1., 1.),
                                   thinning_by_band={0: 1., 1: 1., 2: 1.}, catalog_epoch="compact-parity-v1",
                                   source_pins={"geometry": "unchanged-tiny-fixture"}, max_virtual_candidates=9000,
                                   max_catalog_candidates=8000, max_grid_bins=10000, chunk_size=31)
        self.blockers = np.array([[0., 0., .2], [-.6, .3, .11], [3., 3., .02]])

    def assert_payload(self, a, b):
        for f in fields(a):
            aa, bb = getattr(a, f.name), getattr(b, f.name)
            self.assertEqual(aa.shape, bb.shape, f.name)
            self.assertEqual(aa.dtype, bb.dtype, f.name)
            self.assertEqual(aa.tobytes(), bb.tobytes(), f.name)

    def assert_parity(self, spec=None, prototypes=None, blockers=None, **kwargs):
        spec = spec or self.spec
        prototypes = self.prototypes if prototypes is None else prototypes
        blockers = self.blockers if blockers is None else blockers
        expected = ref.build_catalog(spec, prototypes, blockers, backend=kwargs.get("backend", "numpy"))
        actual = compact.build_compact_catalog(spec, prototypes, blockers, **kwargs)
        self.assertLessEqual(actual.serial_map.virtual_count, 10000)
        self.assert_payload(expected.grains, compact.reconstruct(actual).grains)
        rejected = compact.reconstruct(actual, statuses=(2, 3))
        self.assertEqual(expected.rejected_ids.tobytes(), rejected.grains.ids.tobytes())
        self.assertEqual(expected.rejection_reason.tobytes(), rejected.rejection_reason.tobytes())
        all_candidates, _ = ref.build_candidates(spec, prototypes)
        all_expected, reason, _ = ref.pack_candidates(all_candidates, blockers, max_grid_bins=spec.max_grid_bins,
                                                     backend=kwargs.get("backend", "numpy"))
        all_actual = compact.reconstruct(actual, statuses=(1, 2, 3))
        self.assert_payload(all_expected, all_actual.grains)
        self.assertEqual(reason.tobytes(), all_actual.rejection_reason.tobytes())
        self.assertEqual(expected.provenance, actual.provenance)
        self.assertEqual(expected.report, actual.report)
        return actual

    def test_00_frozen_core_unchanged(self):
        self.assertEqual(hashlib.sha256(Path(ref.__file__).read_bytes()).hexdigest(), FROZEN_SHA256)

    def test_dense_exact_payload_and_rejections(self):
        actual = self.assert_parity()
        self.assertEqual(actual.status2.nbytes, (actual.serial_map.virtual_count + 3) // 4)
        self.assertFalse(actual.status2.flags.writeable)
        self.assertGreater(actual.report["original_blocker_rejections"], 0)
        self.assertGreater(actual.report["catalog_packing_rejections"], 0)
        self.assertTrue(all(not isinstance(getattr(actual, f.name), ref.GrainArrays) for f in fields(actual)))

    def test_reordered_evaluation_prototypes_blockers_and_chunks(self):
        baseline = self.assert_parity()
        group_count = len(baseline.serial_map.group_cell)
        changed = self.assert_parity(spec=replace(self.spec, chunk_size=7), prototypes=self.prototypes[::-1],
                                     blockers=self.blockers[::-1], group_order=np.arange(group_count)[::-1])
        self.assertEqual(baseline.status2.tobytes(), changed.status2.tobytes())
        self.assertEqual(baseline.serial_map.prefix.tobytes(), changed.serial_map.prefix.tobytes())
        self.assert_payload(compact.reconstruct(baseline).grains, compact.reconstruct(changed).grains)

    def test_partial_scope_and_thinning(self):
        partial = replace(self.spec, bounds=(-.91, .73, -.84, .88), chunk_size=13)
        actual = self.assert_parity(spec=partial)
        self.assertLess(actual.report["virtual_count_in_scope"], actual.serial_map.virtual_count)
        self.assert_parity(spec=replace(partial, thinning_by_band={0: .5, 1: .25, 2: .7}))

    def test_empty_catalog_and_zero_count_groups(self):
        pp = [replace(p, density_per_m2=0.) for p in self.prototypes]
        self.assert_parity(prototypes=pp)
        self.assert_parity(spec=replace(self.spec, thinning_by_band={0: 0., 1: 0., 2: 0.}))
        self.assert_parity(prototypes=[self.prototypes[0], replace(self.prototypes[1], density_per_m2=0.), self.prototypes[2]])

    def test_one_bin_and_blockers_outside_scope(self):
        blockers = np.array([[-1.1, -.1, .4], [1.2, .3, .5], [0., 0., .2]])
        self.assert_parity(spec=replace(self.spec, max_grid_bins=1), blockers=blockers)

    def test_two_cameras_resolutions_and_budgets(self):
        actual = self.assert_parity()
        a = compact.reconstruct(actual).grains
        b = ref.build_catalog(self.spec, self.prototypes, self.blockers).grains
        selections = []
        for center, resolution, budget in [((-.35, -.1), (24, 16), 90), ((.25, .1), (48, 32), 160)]:
            width, height = resolution
            uv = (a.xy - center) / 2 * (width / 2) + np.array([width, height]) / 2
            visible = (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
            probability = ref.lod_fraction(2 * a.radius * (width / 2) / 2)
            selected = ref.select_view(a, visible, probability, max_instances=budget)
            self.assert_payload(selected, ref.select_view(b, visible, probability, max_instances=budget))
            selections.append(selected)
        common, ia, ib = np.intersect1d(selections[0].ids, selections[1].ids, return_indices=True)
        self.assertGreater(len(common), 0)
        self.assert_payload(selections[0].take(ia), selections[1].take(ib))

    def test_status_persistence_and_reconstruction(self):
        actual = self.assert_parity()
        # Persist only packed status bytes; reconstruct the serial map from pinned inputs.
        buffer = io.BytesIO()
        np.savez(buffer, status2=actual.status2)
        buffer.seek(0)
        with np.load(buffer, allow_pickle=False) as archive:
            restored_status = archive["status2"]
        serial_map = compact.build_serial_map(self.spec, self.prototypes)
        restored = replace(actual, status2=restored_status, serial_map=serial_map)
        self.assert_payload(compact.reconstruct(actual).grains, compact.reconstruct(restored).grains)
        self.assertEqual(hashlib.sha256(restored.status2.tobytes()).hexdigest(), actual.storage["status_sha256"])

    def test_explicit_allocation_and_reconstruction_guards(self):
        with patch.object(ref, "world_cells", side_effect=AssertionError("must not allocate before refusal")):
            with self.assertRaises(ref.CatalogLimitError):
                compact.build_compact_catalog(self.spec, self.prototypes, limits=compact.CompactLimits(max_rss_bytes=1))
            with self.assertRaises(ref.CatalogLimitError):
                compact.build_compact_catalog(replace(self.spec, max_count_entries=1), self.prototypes)
        with self.assertRaises(ref.CatalogLimitError):
            compact.build_compact_catalog(replace(self.spec, max_catalog_candidates=2), self.prototypes)
        with self.assertRaises(ref.CatalogLimitError):
            compact.build_compact_catalog(replace(self.spec, chunk_size=262145), self.prototypes)
        with self.assertRaises(ref.CatalogLimitError):
            compact.build_compact_catalog(self.spec, self.prototypes, self.blockers,
                                          limits=compact.CompactLimits(max_original_blockers=1))
        actual = compact.build_compact_catalog(self.spec, self.prototypes)
        with self.assertRaises(ref.CatalogLimitError):
            compact.reconstruct(actual, max_candidates=1)
        with self.assertRaises(ValueError):
            actual.status_at([actual.serial_map.virtual_count])

    def test_cross_band_duplicate_id_guard(self):
        records = np.array([(7, 0), (7, 500)], dtype=compact.RECORD_DTYPE)
        records.sort(order=["id", "serial"], kind="quicksort")
        with self.assertRaises(ValueError):
            compact.validate_sorted_ids(records, chunk_size=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
