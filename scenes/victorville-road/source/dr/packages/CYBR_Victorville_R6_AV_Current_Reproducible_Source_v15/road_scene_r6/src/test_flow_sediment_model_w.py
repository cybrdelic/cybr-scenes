"""Focused W tests. No Blender or render; small single-thread numerical patches.
Run with OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover
-s src -p test_flow_sediment_model_w.py -v. This tests discretization/accounting,
not field validation. All test heights are simple planar reference surfaces.
"""
import json
import unittest
from pathlib import Path
from dataclasses import replace

import numpy as np

from flow_sediment_model_w import (FlowConfig, _footprints, _neighbors, _repair_roundoff_inventory,
                                   _relax_deposits, simulate_shoulder)


def plane(spacing=.025):
    x = np.arange(round(.6 / spacing) + 1) * spacing
    y = np.arange(round(.9 / spacing) + 1) * spacing
    xx, yy = np.meshgrid(x, y)
    return x, y, .03 * xx - .008 * yy


class WFootprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = FlowConfig(rainfall_m=(.026, .035), heterogeneity_strength=0,
                             upstream_width_m=.6)
        cls.x, cls.y, cls.z = plane()
        cls.r = simulate_shoulder(cls.x, cls.y, cls.z, cls.cfg)

    def test_conservation_bounds_and_frozen_rim(self):
        r = self.r
        area = (self.x[1] - self.x[0]) * (self.y[1] - self.y[0])
        np.testing.assert_allclose((r.erosion_by_class_m - r.deposition_by_class_m).sum(axis=(0, 1)) * area,
                                   r.receipt['boundary_export_by_class_m3'], atol=1e-13)
        np.testing.assert_allclose(r.height_delta_m,
                                   r.cumulative_deposition_m - r.cumulative_erosion_m, atol=1e-14)
        self.assertLess(abs(r.receipt['net_bed_plus_export_error_m3']), 1e-12)
        self.assertLess(abs(r.receipt['water_balance_error_m3']), 1e-12)
        self.assertTrue(np.all(r.height_delta_m >= -self.cfg.max_erosion_m * r.boundary_mobility - 1e-12))
        self.assertTrue(np.all(r.height_delta_m <= self.cfg.max_deposition_m * r.boundary_mobility + 1e-12))
        np.testing.assert_array_equal(r.height_delta_m[[0, -1]], 0)
        np.testing.assert_array_equal(r.height_delta_m[:, [0, -1]], 0)
        self.assertGreater(r.receipt['cumulative_slope_redistribution_m3'], 0.)
        json.dumps(r.receipt)

    def test_translation_invariance_and_quarter_turn_sensitivity(self):
        moved = simulate_shoulder(self.x - 5.8, self.y + 1.3, self.z + 82., self.cfg)
        np.testing.assert_allclose(moved.height_delta_m, self.r.height_delta_m, atol=1e-11)
        rotated = simulate_shoulder(self.y, self.x, np.rot90(self.z),
                                     replace(self.cfg, upstream_edge='y_min'))
        relative = np.mean(abs(rotated.height_delta_m - np.rot90(self.r.height_delta_m)))
        relative /= np.mean(abs(self.r.height_delta_m))
        self.assertLess(relative, .005)
        print('\nW quarter-turn relative height L1:', relative)

    def test_physical_footprint_width_survives_grid_refinement(self):
        moments = []
        for dx in (.025, .0125):
            x, y, z = plane(dx)
            indices, weights = _footprints(z.shape, dx, dx, np.ones(z.shape, bool), .10)
            cy, cx = np.array(z.shape) // 2
            node = cy * len(x) + cx
            yy, xx = np.divmod(indices[node], len(x))
            moment = np.sum(weights[node] * (((xx - cx) * dx) ** 2 + ((yy - cy) * dx) ** 2))
            moments.append(moment)
            self.assertAlmostEqual(float(weights[node].sum()), 1.)
            self.assertGreater(np.count_nonzero(weights[node]), 8)
        # Cell-integrated disk radius .05 m has radial second moment .00125 m².
        self.assertLess(abs(moments[1] - .00125), .00008)
        self.assertLess(abs(moments[1] - moments[0]) / moments[1], .12)

    def test_small_patch_finer_grid_convergence(self):
        results = []
        for spacing in (.05, .025, .0125):
            if spacing == .025:
                results.append(self.r)
            else:
                results.append(simulate_shoulder(*plane(spacing), self.cfg))
        errors = [np.mean(abs(a.height_delta_m - b.height_delta_m[::2, ::2]))
                  for a, b in zip(results, results[1:])]
        volumes = [r.receipt['cumulative_erosion_m3'] for r in results]
        self.assertLess(errors[1], errors[0])
        self.assertLess(errors[1], .0005)
        self.assertLess((max(volumes) - min(volumes)) / np.mean(volumes), .02)
        print('\nW grid refinement height L1 errors (m):', errors,
              '; eroded bulk volumes (m³):', volumes)

    def test_actual_terrain_regression_remains_finite_bounded_and_conservative(self):
        path = Path(__file__).parent / 'fixtures/shoulder_w_actual_regression.json'
        data = json.loads(path.read_text())
        r = simulate_shoulder(np.array(data['x_m']), np.array(data['y_m']),
                              np.array(data['source_z_m']))
        for name in ('height_delta_m', 'cumulative_water_m3', 'cumulative_erosion_m',
                     'cumulative_deposition_m', 'retained_deposit_by_class_m',
                     'surface_fraction', 'lag_exposure', 'compacted_bare'):
            self.assertTrue(np.all(np.isfinite(getattr(r, name))), name)
        self.assertTrue(np.all(r.retained_deposit_by_class_m >= 0))
        self.assertTrue(np.all(r.cumulative_erosion_m >= 0))
        self.assertTrue(np.all(r.cumulative_deposition_m >= 0))
        self.assertTrue(np.all(r.height_delta_m >= -.018 * r.boundary_mobility - 1e-12))
        self.assertTrue(np.all(r.height_delta_m <= .024 * r.boundary_mobility + 1e-12))
        for key in ('sediment_balance_error_m3', 'net_bed_plus_export_error_m3',
                    'water_balance_error_m3'):
            self.assertLess(abs(r.receipt[key]), 1e-12, key)
        for event in r.receipt['events']:
            self.assertLess(event['absolute_class_balance_error_m3'], 1e-12)
        self.assertLess(r.receipt['roundoff_inventory_added_m3'], 1e-15)
        print('\nW actual31x25 regression:', {k: r.receipt[k] for k in (
            'minimum_height_delta_m', 'maximum_height_delta_m', 'boundary_export_m3',
            'net_bed_plus_export_error_m3', 'roundoff_inventory_added_m3')})

    def test_roundoff_guard_repairs_only_tiny_deficits_with_a_ledger(self):
        ledger = {'added_by_class_m3': np.zeros(3), 'corrected_entries': 0}
        a = np.array([[.001, -8.27e-25, 0.]])
        _repair_roundoff_inventory(a, ledger, 'test', 1e-20)
        self.assertEqual(a[0, 1], 0.)
        self.assertEqual(ledger['corrected_entries'], 1)
        self.assertEqual(ledger['added_by_class_m3'][1], 8.27e-25)
        for bad in (-1e-7, np.nan, -np.inf):
            with self.assertRaises(FloatingPointError):
                _repair_roundoff_inventory(np.array([[.001, bad, 0.]]), ledger, 'test', 1e-20)

    def test_slope_transport_moves_only_mobile_deposit_conservatively(self):
        shape = (17, 17)
        dx = .025
        valid = np.ones(shape, bool)
        n, area = valid.size, dx ** 2
        neighbors, distance = _neighbors(shape, dx, dx, valid)
        cfg = self.cfg
        zero = np.zeros((n, 3))
        deposited = zero.copy()
        center = (shape[0] // 2) * shape[1] + shape[1] // 2
        deposited[center] = .012 * area * np.array(cfg.substrate_fractions)
        before = deposited.sum(axis=0)
        erosion, deposition = zero.copy(), zero.copy()
        moved = _relax_deposits(np.zeros(n), zero, zero.copy(), deposited,
                                erosion, deposition, area, np.ones(n),
                                neighbors, distance, cfg, dx, dx)
        np.testing.assert_allclose(deposited.sum(axis=0), before, atol=1e-18)
        np.testing.assert_allclose(erosion.sum(axis=0), deposition.sum(axis=0), atol=1e-18)
        self.assertGreater(moved, 0.)
        self.assertLess(deposited[center].sum(), before.sum())
        self.assertTrue(np.all(deposited >= -1e-18))
        # Without mobile sediment even a steep original surface is untouched.
        empty = zero.copy()
        no_move = _relax_deposits(np.arange(n) * .05, zero, zero.copy(), empty,
                                  zero.copy(), zero.copy(), area, np.ones(n),
                                  neighbors, distance, cfg, dx, dx)
        self.assertEqual(no_move, 0.)
        np.testing.assert_array_equal(empty, 0.)


if __name__ == '__main__':
    unittest.main()
