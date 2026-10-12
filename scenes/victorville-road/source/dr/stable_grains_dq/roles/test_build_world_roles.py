"""Synthetic source-only world-role tests, fewer than 300 points per fixture."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

import build_world_roles as builder
import transported_grain_exposure_dq as dq


class TinyReader:
    def __init__(self, batch, virtual_count):
        self.batch = batch
        self.map = SimpleNamespace(virtual_count=virtual_count)
        self.calls = []

    def band(self, lo, hi):
        self.calls.append((lo, hi))
        mask = (self.batch['xy'][:, 1] >= lo) & (self.batch['xy'][:, 1] < hi)
        # Deliberately noncanonical retrieval ordering.
        idx = np.flatnonzero(mask)[::-1]
        return {key: value[idx] for key, value in self.batch.items()}


class TinySupport:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.values = dict(flow_class=np.array([0, 1, 2]),
                           volume=np.array([1e-8, 2e-8, 4e-8]),
                           diameter=np.array([.0005, .001, .003]),
                           footprint=np.array([.00003, .00005, .0001]),
                           minimum=np.array([-.0005, -.0005, -.001]),
                           maximum=np.array([.0002, .0004, .001]),
                           offset=np.array([.0001732101, .00002349875, 0]))
        self.calls = []

    def arr(self, key):
        return self.values[key]

    def local_fields(self, xy):
        self.calls.append(xy.copy())
        # One deliberately unsupported exact sample; no flat finite replacement.
        height = 37.123456789 + xy[:, 0] * .137 + xy[:, 1] * .093
        height[xy[:, 0] == .123] = np.nan
        cover = .001 + .0001 * xy[:, 1]
        return height, cover, np.full(len(xy), .0003)


def fixture():
    rng = np.random.default_rng(7993)
    x, y = np.arange(4) * .05, -.1 + np.arange(8) * .05
    n = 220
    ix, iy = rng.integers(0, len(x), n), rng.integers(0, len(y), n)
    xy = np.c_[x[ix], y[iy]] + rng.uniform(-.024, .024, (n, 2))
    xy[:, 0] = np.clip(xy[:, 0], x[0], x[-1])
    xy[:, 1] = np.clip(xy[:, 1], y[0], y[-1])
    xy[:12] = np.array([[0, y[0]], [x[-1], y[-1]], [.05, -.025], [.05, .075],
                       [.05, np.nextafter(.075, -np.inf)], [.05, np.nextafter(.075, np.inf)],
                       [.123, .1], [-.01, 0], [.16, 0], [.05, -.11], [.05, .26], [.05, .1]])
    serial = (np.arange(n, dtype='u4') * 2 + 1)
    serial[:10] = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype='u4')
    ids = serial.astype('u8') * np.uint64(1597334677) + np.uint64(2**63)
    pi = rng.integers(0, 3, n, dtype='i4')
    batch = dict(serial=serial, id=ids, xy=xy, prototype=pi,
                 yaw=rng.uniform(0, 6, n).astype('f4'))
    support = TinySupport(x, y)
    reader = TinyReader(batch, n * 2 + 50)
    inside, cy, cx = builder.nearest_stock_cells(xy, x, y, .05, .05)
    counts = np.bincount(cy[inside] * len(x) + cx[inside], minlength=len(x) * len(y)).reshape(len(y), len(x))
    available = np.full((len(y), len(x), 3), .0008)
    cover_grid = np.full((len(y), len(x)), .001)
    cfg = dq.ExposureConfig(availability_mode='surviving_deposit_stock')
    original_budget = available * .05 * .05 * cfg.solid_fraction
    _, effective, top = dq.retained_top_proxy(available)
    original_target = .05 * .05 * cfg.maximum_planar_area_proxy_fraction * (-np.expm1(-effective / cfg.active_layer_m))[..., None] * top
    macro_volume = original_budget * .91
    macro_area = original_target * .68
    # Preserved legacy overshoot gives this cell/class zero additional area.
    macro_area[2, 2, 1] = original_target[2, 2, 1] * 1.1
    budget = dict(x=x, y=y, available=available, cover_grid=cover_grid,
                  original_budget=original_budget, original_target=original_target,
                  macro_spent_volume=macro_volume, macro_spent_area=macro_area,
                  remaining_volume=original_budget - macro_volume,
                  remaining_area=np.maximum(original_target - macro_area, 0), complete_counts=counts)
    return reader, support, budget, cfg, inside


def direct_allocation(reader, support, budget, cfg):
    b = reader.batch
    xy, pi = b['xy'], b['prototype']
    height, cover, _ = support.local_fields(xy)
    offset = support.arr('offset')[pi]
    before = (height.astype('f4').astype(float) - offset).astype('f4')
    return dq.allocate_transported_grains(
        xy_m=xy, flow_class=support.arr('flow_class')[pi], solid_volume_m3=support.arr('volume')[pi],
        diameter_m=support.arr('diameter')[pi], footprint_area_m2=support.arr('footprint')[pi],
        local_z_bounds_m=np.c_[support.arr('minimum'), support.arr('maximum')][pi],
        final_surface_m=before.astype(float) + offset, x_m=budget['x'], y_m=budget['y'],
        retained_deposit_by_class_m=budget['available'], net_deposit_m=budget['cover_grid'],
        local_net_deposit_m=cover, config=cfg, candidate_ids=b['id'],
        remaining_solid_budget_by_cell_class_m3=budget['remaining_volume'],
        remaining_planar_area_target_by_cell_class_m2=budget['remaining_area'],
        complete_stock_cell_counts=budget['complete_counts'])


class WorldRoleTests(unittest.TestCase):
    def test_or_at_multiple_indices_in_same_byte(self):
        bits = np.zeros(4, dtype='u1')
        serial = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 10, 15, 16, 31], dtype='u4')
        builder.set_serial_bits(bits, serial)
        np.testing.assert_array_equal(bits, [255, 133, 1, 128])
        self.assertTrue(builder.serial_bits_at(bits, serial).all())
        self.assertFalse(builder.serial_bits_at(bits, np.array([9, 11, 17, 30], dtype='u4')).any())

    def test_complete_bands_match_whole_allocation_and_static_outside(self):
        reader, support, budget, cfg, inside = fixture()
        direct = direct_allocation(reader, support, budget, cfg)
        self.assertTrue(direct.transported.any())
        snapshots = {k: v.copy() for k, v in budget.items()}
        for rows in (1, 2, 4, 8):
            result = builder.build_roles(reader, support, budget, rows_per_band=rows, config=cfg)
            np.testing.assert_array_equal(builder.serial_bits_at(result.role1, reader.batch['serial']), direct.transported)
            np.testing.assert_array_equal(result.selected_volume, direct.selected_solid_volume_by_cell_class_m3)
            np.testing.assert_array_equal(result.selected_area, direct.exposed_planar_area_proxy_by_cell_class_m2)
            np.testing.assert_array_equal(result.selected_count, direct.selected_count_by_cell_class)
            np.testing.assert_array_equal(result.processed_counts, budget['complete_counts'])
            self.assertTrue(result.processed_rows.all())
            self.assertFalse(builder.serial_bits_at(result.role1, reader.batch['serial'][~inside]).any())
            self.assertEqual(result.receipt['maximum_volume_cap_exceedance_m3'], 0)
            self.assertEqual(result.receipt['maximum_area_cap_exceedance_m2'], 0)
        for k, before in snapshots.items():
            np.testing.assert_array_equal(budget[k], before)

    def test_support_gate_uses_exact_legacy_float32_origin_equation(self):
        reader, support, budget, cfg, _ = fixture()
        captured = []
        original = builder.allocate_transported_grains
        def inspect(**kwargs):
            captured.append(kwargs)
            return original(**kwargs)
        with patch.object(builder, 'allocate_transported_grains', side_effect=inspect):
            result = builder.build_roles(reader, support, budget, config=cfg)
        self.assertGreater(len(captured), 0)
        saw_nan = False
        for kw in captured:
            lookup = {int(i): int(p) for i, p in zip(reader.batch['id'], reader.batch['prototype'])}
            pi = np.array([lookup[int(i)] for i in kw['candidate_ids']])
            height, _, _ = support.local_fields(kw['xy_m'])
            offset = support.arr('offset')[pi]
            expected = (height.astype('f4').astype(float) - offset).astype('f4').astype(float) + offset
            np.testing.assert_array_equal(kw['final_surface_m'], expected)
            self.assertIs(kw['retained_deposit_by_class_m'], budget['available'])
            saw_nan |= np.isnan(expected).any()
        self.assertTrue(saw_nan)
        unsupported = reader.batch['xy'][:, 0] == .123
        self.assertFalse(builder.serial_bits_at(result.role1, reader.batch['serial'][unsupported]).any())

    def test_missing_entire_cell_is_rejected(self):
        reader, support, budget, cfg, _ = fixture()
        xy = reader.batch['xy']
        _, iy, ix = builder.nearest_stock_cells(xy, budget['x'], budget['y'], .05, .05)
        chosen = (iy == 3) & (ix == 2)
        self.assertTrue(chosen.any())
        reader.batch = {k: v[~chosen] for k, v in reader.batch.items()}
        with self.assertRaisesRegex(ValueError, 'Missing/extra complete-cell'):
            builder.build_roles(reader, support, budget, config=cfg)

    def test_duplicate_virtual_serial_is_rejected(self):
        reader, support, budget, cfg, _ = fixture()
        # Distinct IDs and locations do not permit spending one virtual serial twice.
        reader.batch['serial'][1] = reader.batch['serial'][0]
        with self.assertRaisesRegex(ValueError, 'Duplicate full virtual serial'):
            builder.build_roles(reader, support, budget, rows_per_band=1, config=cfg)

    def test_candidate_limit_fails_without_partial_result(self):
        reader, support, budget, cfg, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'exceeding bounded limit'):
            builder.build_roles(reader, support, budget, max_batch_candidates=1, config=cfg)

    def test_stale_macro_residual_is_rejected(self):
        reader, support, budget, cfg, _ = fixture()
        budget['remaining_volume'] = budget['original_budget'].copy()
        with self.assertRaisesRegex(ValueError, 'fixed macro debit'):
            builder.build_roles(reader, support, budget, config=cfg)

    def test_empty_cells_processed_and_no_unsupported_writes(self):
        reader, support, budget, cfg, _ = fixture()
        reader.batch = {k: v[:0] for k, v in reader.batch.items()}
        budget['complete_counts'][:] = 0
        result = builder.build_roles(reader, support, budget, config=cfg)
        self.assertFalse(result.role1.any())
        self.assertTrue(result.processed_rows.all())
        self.assertEqual(result.receipt['selected_count'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
