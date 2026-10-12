"""Tiny NumPy-only regression/identity/finite-stock tests; no Blender or artifacts."""
from dataclasses import fields
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import transported_grain_exposure_dq as dq

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parents[1] / 'low_ground_dp_native/runtime/src/transported_grain_exposure_dg.py'
HISTORY = ORIGINAL.with_name('history_budget_dg.py')
SOURCE_SHA = '0019380b537bf35309c25939b8fc1285e2a09036cea6a81e8024822bc788a587'
HISTORY_SHA = '18c5bc3b096c190ad889606508474e1ed24d3dc1823c9e0d46768a08e0410a98'
loader = importlib.util.spec_from_file_location('legacy_dg_for_dq_test', ORIGINAL)
legacy = importlib.util.module_from_spec(loader)
sys.modules[loader.name] = legacy
# Reading the original module must not create/update files beside that source.
previous_bytecode_policy = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    loader.loader.exec_module(legacy)
finally:
    sys.dont_write_bytecode = previous_bytecode_policy

POINT_ARRAYS = ('xy_m', 'flow_class', 'solid_volume_m3', 'diameter_m',
                'footprint_area_m2', 'local_z_bounds_m', 'final_surface_m',
                'local_net_deposit_m', 'candidate_ids')


def fixture(n=1800, mode='surviving_deposit_stock'):
    rng = np.random.default_rng(813709)
    x, y = np.arange(6) * .05, np.arange(5) * .05
    cells = rng.integers(0, len(x) * len(y), n)
    iy, ix = np.divmod(cells, len(x))
    xy = np.c_[x[ix], y[iy]] + rng.uniform(-.024, .024, (n, 2))
    xy[:, 0] = np.clip(xy[:, 0], x[0], x[-1])
    xy[:, 1] = np.clip(xy[:, 1], y[0], y[-1])
    dep = rng.uniform(.00005, .0015, (len(y), len(x), 3))
    net = rng.uniform(-.0015, .003, (len(y), len(x)))
    kwargs = dict(xy_m=xy, flow_class=rng.integers(0, 3, n),
                  solid_volume_m3=rng.uniform(1e-8, 2e-7, n),
                  diameter_m=rng.uniform(.0003, .004, n),
                  footprint_area_m2=rng.uniform(1e-5, 1.2e-4, n),
                  local_z_bounds_m=np.c_[-rng.uniform(.0001, .001, n),
                                        rng.uniform(.0001, .001, n)],
                  final_surface_m=rng.uniform(0, .1, n), x_m=x, y_m=y,
                  retained_deposit_by_class_m=dep, net_deposit_m=net,
                  local_net_deposit_m=rng.uniform(-.0015, .003, n),
                  config=dq.ExposureConfig(availability_mode=mode))
    kwargs['final_surface_m'][::31] = np.nan
    kwargs['local_net_deposit_m'][::47] = np.nan
    # High-bit IDs explicitly exercise unsigned order and lossless identity.
    ids = np.arange(n, dtype='u8') * np.uint64(17293745292385727) + np.uint64(2**63)
    assert len(np.unique(ids)) == n
    counts = np.bincount(cells, minlength=len(x) * len(y)).reshape(len(y), len(x))
    return kwargs, ids, counts, cells


def dq_fixture(*args, **kwargs):
    kw, ids, counts, cells = fixture(*args, **kwargs)
    kw.update(candidate_ids=ids, complete_stock_cell_counts=counts)
    return kw, cells


def take(kwargs, selection):
    return {k: (v[selection] if k in POINT_ARRAYS else v) for k, v in kwargs.items()}


def assert_result_equal(test, a, b):
    for f in fields(a):
        av, bv = getattr(a, f.name), getattr(b, f.name)
        if isinstance(av, np.ndarray):
            np.testing.assert_array_equal(av, bv, err_msg=f.name)
        else:
            test.assertEqual(av, bv, f.name)


class RoleTests(unittest.TestCase):
    def test_legacy_exact_for_modes_seeds_and_empty(self):
        for mode in ('net_positive_only', 'surviving_deposit_stock'):
            for seed in (0, 73181, 2**95 + 17):
                kw, _, _, _ = fixture(mode=mode)
                kw['config'] = dq.ExposureConfig(seed=seed, availability_mode=mode)
                assert_result_equal(self, legacy.allocate_transported_grains(**kw),
                                    dq.allocate_transported_grains(**kw))
                empty = take(kw, np.array([], dtype=int))
                assert_result_equal(self, legacy.allocate_transported_grains(**empty),
                                    dq.allocate_transported_grains(**empty))

    def test_legacy_exact_without_local_net_override(self):
        kw, _, _, _ = fixture(mode='net_positive_only')
        kw.pop('local_net_deposit_m')
        assert_result_equal(self, legacy.allocate_transported_grains(**kw),
                            dq.allocate_transported_grains(**kw))

    def test_id_permutation_exact_roles_and_cell_ledgers(self):
        kw, _ = dq_fixture()
        first = dq.allocate_transported_grains(**kw)
        self.assertTrue(first.transported.any())
        self.assertFalse(first.transported.all())
        perm = np.random.default_rng(747).permutation(len(kw['candidate_ids']))
        second = dq.allocate_transported_grains(**take(kw, perm))
        inv = np.argsort(perm)
        for name in ('transported', 'extra_embedment_m', 'candidate_cell_yx',
                     'local_retained_deposit_m', 'local_net_deposit_m',
                     'local_top_active_layer_fraction'):
            np.testing.assert_array_equal(getattr(first, name), getattr(second, name)[inv])
        self.assertEqual(first.receipt, second.receipt)
        for name in ('selected_solid_volume_by_cell_class_m3',
                     'exposed_planar_area_proxy_by_cell_class_m2',
                     'selected_count_by_cell_class'):
            np.testing.assert_array_equal(getattr(first, name), getattr(second, name))

    def test_complete_cell_y_bands_exact_with_residuals(self):
        kw, cells = dq_fixture()
        base = dq.allocate_transported_grains(**kw)
        kw['remaining_solid_budget_by_cell_class_m3'] = base.solid_budget_by_cell_class_m3 * .43
        kw['remaining_planar_area_target_by_cell_class_m2'] = base.target_planar_area_proxy_by_cell_class_m2 * .37
        whole = dq.allocate_transported_grains(**kw)
        roles = np.zeros_like(whole.transported)
        extra = np.zeros_like(whole.extra_embedment_m)
        volume = np.zeros_like(whole.selected_solid_volume_by_cell_class_m3)
        area = np.zeros_like(volume)
        for rows in ([0, 1], [2], [3, 4]):
            selected = np.flatnonzero(np.isin(cells // len(kw['x_m']), rows))[::-1]
            band = dq.allocate_transported_grains(**take(kw, selected))
            roles[selected] = band.transported
            extra[selected] = band.extra_embedment_m
            volume += band.selected_solid_volume_by_cell_class_m3
            area += band.exposed_planar_area_proxy_by_cell_class_m2
        np.testing.assert_array_equal(roles, whole.transported)
        np.testing.assert_array_equal(extra, whole.extra_embedment_m)
        np.testing.assert_array_equal(volume, whole.selected_solid_volume_by_cell_class_m3)
        np.testing.assert_array_equal(area, whole.exposed_planar_area_proxy_by_cell_class_m2)

    def test_unrelated_candidate_cells_do_not_change_shared_roles(self):
        kw, cells = dq_fixture()
        first = dq.allocate_transported_grains(**kw)
        kept = cells < 6
        changed = take(kw, np.flatnonzero(cells < 18))
        # Remove unrelated rows and perturb another distant complete cell.
        other = changed['xy_m'][:, 1] > .06
        changed['diameter_m'] = changed['diameter_m'].copy()
        changed['diameter_m'][other] *= .1
        changed['solid_volume_m3'] = changed['solid_volume_m3'].copy()
        changed['solid_volume_m3'][other] *= 100
        second = dq.allocate_transported_grains(**changed)
        shared_second = changed['xy_m'][:, 1] < .025
        np.testing.assert_array_equal(first.transported[kept], second.transported[shared_second])
        np.testing.assert_array_equal(first.extra_embedment_m[kept], second.extra_embedment_m[shared_second])

    def test_residual_caps_and_deposit_semantics_and_no_mutation(self):
        kw, _ = dq_fixture()
        physical = dq.allocate_transported_grains(**kw)
        frozen_volume = physical.solid_budget_by_cell_class_m3 * .55
        frozen_area = physical.target_planar_area_proxy_by_cell_class_m2 * .62
        kw['remaining_solid_budget_by_cell_class_m3'] = np.maximum(
            physical.solid_budget_by_cell_class_m3 - frozen_volume, 0)
        kw['remaining_planar_area_target_by_cell_class_m2'] = np.maximum(
            physical.target_planar_area_proxy_by_cell_class_m2 - frozen_area, 0)
        snapshots = {k: v.copy() for k, v in kw.items() if isinstance(v, np.ndarray)}
        residual = dq.allocate_transported_grains(**kw)
        v, a = residual.selected_solid_volume_by_cell_class_m3, residual.exposed_planar_area_proxy_by_cell_class_m2
        self.assertTrue(np.all(v <= kw['remaining_solid_budget_by_cell_class_m3']))
        self.assertTrue(np.all(a <= kw['remaining_planar_area_target_by_cell_class_m2']))
        self.assertTrue(np.all(residual.remaining_representation_volume_by_cell_class_m3 >= 0))
        # Reconstruct total display ledger, without rewriting frozen/source data.
        np.testing.assert_allclose(frozen_volume + v + residual.remaining_representation_volume_by_cell_class_m3,
                                   physical.solid_budget_by_cell_class_m3, rtol=2e-15, atol=0)
        for name in ('local_retained_deposit_m', 'local_net_deposit_m', 'local_top_active_layer_fraction'):
            np.testing.assert_array_equal(getattr(residual, name), getattr(physical, name))
        common = residual.transported & physical.transported
        self.assertTrue(common.any())
        np.testing.assert_array_equal(residual.extra_embedment_m[common], physical.extra_embedment_m[common])
        self.assertEqual(residual.receipt['fractional_area_roundups'], 0)
        for k, before in snapshots.items():
            np.testing.assert_array_equal(kw[k], before, err_msg=k)

    def test_residuals_above_original_cannot_expand_stock(self):
        kw, _ = dq_fixture()
        first = dq.allocate_transported_grains(**kw)
        kw['remaining_solid_budget_by_cell_class_m3'] = np.ones_like(first.solid_budget_by_cell_class_m3)
        kw['remaining_planar_area_target_by_cell_class_m2'] = np.ones_like(first.target_planar_area_proxy_by_cell_class_m2)
        capped = dq.allocate_transported_grains(**kw)
        np.testing.assert_array_equal(capped.solid_budget_by_cell_class_m3, first.solid_budget_by_cell_class_m3)
        np.testing.assert_array_equal(capped.target_planar_area_proxy_by_cell_class_m2, first.target_planar_area_proxy_by_cell_class_m2)
        self.assertTrue(np.all(capped.exposed_planar_area_proxy_by_cell_class_m2 <= first.target_planar_area_proxy_by_cell_class_m2))

    def test_zero_stock_selects_nothing(self):
        kw, _ = dq_fixture()
        kw['remaining_solid_budget_by_cell_class_m3'] = np.zeros((5, 6, 3))
        ans = dq.allocate_transported_grains(**kw)
        self.assertFalse(ans.transported.any())
        self.assertFalse(ans.extra_embedment_m.any())
        kw.pop('remaining_solid_budget_by_cell_class_m3')
        kw['remaining_planar_area_target_by_cell_class_m2'] = np.zeros((5, 6, 3))
        self.assertFalse(dq.allocate_transported_grains(**kw).transported.any())

    def test_missing_or_partial_manifest_rejects_camera_allocation(self):
        kw, _ = dq_fixture()
        missing = dict(kw)
        missing.pop('complete_stock_cell_counts')
        with self.assertRaisesRegex(ValueError, 'requires complete_stock_cell_counts'):
            dq.allocate_transported_grains(**missing)
        with self.assertRaisesRegex(ValueError, 'Incomplete nearest-stock-cell'):
            dq.allocate_transported_grains(**take(kw, np.arange(len(kw['candidate_ids']) - 1)))
        # Fine-grained camera or LOD subset is never a valid allocation input.
        with self.assertRaisesRegex(ValueError, 'Incomplete nearest-stock-cell'):
            dq.allocate_transported_grains(**take(kw, slice(None, None, 2)))

    def test_render_subset_keyed_embedding_exact(self):
        for mode in ('surviving_deposit_stock', 'net_positive_only'):
            kw, _ = dq_fixture(mode=mode)
            ans = dq.allocate_transported_grains(**kw)
            # Reuse the original bilinear field values, not residual thickness.
            x, dx = dq._axis(kw['x_m'], 'x_m')
            y, dy = dq._axis(kw['y_m'], 'y_m')
            dep = dq._bilinear(kw['retained_deposit_by_class_m'], kw['xy_m'],
                               x, y, dx, dy, np.ones(len(kw['xy_m']), dtype=bool))
            supported = np.isfinite(kw['final_surface_m']) & np.isfinite(kw['local_net_deposit_m'])
            if mode == 'surviving_deposit_stock':
                effective = dq.retained_top_proxy(dep)[1]
                effective = np.where(supported, effective, 0)
            else:
                effective = np.minimum(dep.sum(axis=1), np.maximum(
                    np.where(supported, kw['local_net_deposit_m'], 0), 0))
            subset = np.arange(7, len(kw['candidate_ids']), 3)[::-1]
            render_extra = dq.keyed_extra_embedment_m(candidate_ids=kw['candidate_ids'][subset],
                local_effective_deposit_m=effective[subset], diameter_m=kw['diameter_m'][subset],
                local_z_bounds_m=kw['local_z_bounds_m'][subset], transported=ans.transported[subset],
                config=kw['config'])
            np.testing.assert_array_equal(render_extra, ans.extra_embedment_m[subset])

    def test_keyed_channels_no_rng_and_independent_subset(self):
        kw, _ = dq_fixture()
        with patch.object(np.random, 'default_rng', side_effect=AssertionError('RNG stream forbidden')):
            dq.allocate_transported_grains(**kw)
        draws = [dq.keyed_uniform(kw['candidate_ids'], 73181, channel)
                 for channel in ('jitter', 'race', 'fraction')]
        for i, a in enumerate(draws):
            self.assertTrue(np.all((a >= 0) & (a < 1)))
            for b in draws[i + 1:]:
                self.assertFalse(np.array_equal(a, b))
        subset = np.arange(29, len(kw['candidate_ids']), 17)
        np.testing.assert_array_equal(draws[0][subset], dq.keyed_uniform(kw['candidate_ids'][subset], 73181, 'jitter'))
        self.assertFalse(np.array_equal(draws[0], dq.keyed_uniform(kw['candidate_ids'], 73181 + 2**64, 'jitter')))

    def test_tied_races_use_unsigned_id_order(self):
        kw, ids, _, _ = fixture(n=9)
        for name in POINT_ARRAYS:
            if name in kw:
                kw[name] = np.repeat(kw[name][1:2], 9, axis=0)
        kw['xy_m'][:] = [.1, .1]
        kw['flow_class'][:] = 0
        kw['final_surface_m'][:] = 0
        kw['local_net_deposit_m'][:] = .001
        kw['solid_volume_m3'][:] = 1e-9
        kw['candidate_ids'] = np.array([2**64 - 1, 2**63 + 2, 13, 10, 0, 1, 12, 15, 2**63], dtype='u8')
        counts = np.zeros((5, 6), dtype=int)
        counts[2, 2] = 9
        kw['complete_stock_cell_counts'] = counts
        budget = np.zeros((5, 6, 3))
        budget[2, 2, 0] = 2.5e-9
        kw['remaining_solid_budget_by_cell_class_m3'] = budget
        with patch.object(dq, '_keyed_uniform', side_effect=lambda ids, seed, channel: np.full(len(ids), .5)):
            a = dq.allocate_transported_grains(**kw)
            b = dq.allocate_transported_grains(**take(kw, np.arange(9)[::-1]))
        np.testing.assert_array_equal(kw['candidate_ids'][a.transported], [0, 1])
        np.testing.assert_array_equal(a.transported, b.transported[::-1])

    def test_keyed_channel_version_vectors(self):
        ids = np.array([0, 1, 2**63, 2**64 - 1], dtype='u8')
        expected = {
            'jitter': ['0x1.7767a8cdb0b44p-1', '0x1.020220e074e50p-4',
                       '0x1.10253e064d002p-1', '0x1.655bb5087094cp-3'],
            'race': ['0x1.774c8119e0cddp-1', '0x1.2e3245cf20c4ap-2',
                     '0x1.fa142cfac178ap-2', '0x1.f3b914f3f7ae8p-1'],
            'fraction': ['0x1.22f7a54f263fep-2', '0x1.197bfb559d94ap-1',
                         '0x1.6da01f3b34ec0p-4', '0x1.12fd035e01e70p-3'],
        }
        for channel, values in expected.items():
            self.assertEqual([v.hex() for v in dq.keyed_uniform(ids, 73181, channel)], values)

    def test_invalid_ids_residuals_and_counts(self):
        kw, _ = dq_fixture()
        for values in (kw['candidate_ids'].astype('i8'), kw['candidate_ids'].astype(float),
                       np.zeros(len(kw['candidate_ids']), dtype='u8')):
            bad = dict(kw, candidate_ids=values)
            with self.assertRaises(ValueError):
                dq.allocate_transported_grains(**bad)
        for field in ('remaining_solid_budget_by_cell_class_m3',
                      'remaining_planar_area_target_by_cell_class_m2'):
            for values in (np.full((5, 6, 3), -1e-20), np.full((5, 6, 3), np.nan), np.zeros((5, 6))):
                with self.assertRaises(ValueError):
                    dq.allocate_transported_grains(**dict(kw, **{field: values}))
        for values in (np.zeros((5, 6), dtype=float), np.full((5, 6), -1, dtype=int)):
            with self.assertRaises(ValueError):
                dq.allocate_transported_grains(**dict(kw, complete_stock_cell_counts=values))

    def test_empty_complete_cell_batch(self):
        kw, _ = dq_fixture()
        ans = dq.allocate_transported_grains(**take(kw, np.array([], dtype=int)))
        self.assertEqual(ans.receipt['selected_count'], 0)
        self.assertEqual(ans.receipt['display_stock_accounting']['complete_stock_cells_in_call'], 0)

    def test_original_source_files_unchanged(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), SOURCE_SHA)
        self.assertEqual(hashlib.sha256(HISTORY.read_bytes()).hexdigest(), HISTORY_SHA)


if __name__ == '__main__':
    unittest.main(verbosity=2)
