"""Run: python -m unittest discover -s src -p test_flow_sediment_model.py -v

Optional full 0.03 m shoulder benchmark:
  FLOW_MODEL_BENCHMARK=1 python -m unittest discover -s src -p test_flow_sediment_model.py -v
Tests use constructed terrain only; integration must sample actual scene triangles.
"""
from dataclasses import replace
import json
import os
import unittest

import numpy as np

from flow_sediment_model import FlowConfig, simulate_shoulder


def terrain(nx=37, ny=73):
    x = np.arange(nx) * 0.03 - 5.8
    y = np.arange(ny) * 0.03 - 0.6
    xx, yy = np.meshgrid(x, y)
    # Grade and measured-terrain-like irregular relief, not output masks.
    z = 0.030 * (xx + 5.8) - 0.010 * yy
    z += 0.003 * np.sin(yy * 6 + xx * 5) + 0.0018 * np.sin(yy * 17 - xx * 9)
    return x, y, z


class ShoulderFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x, cls.y, cls.z = terrain()
        cls.config = FlowConfig()
        cls.r = simulate_shoulder(cls.x, cls.y, cls.z, cls.config)
        cls.area = np.diff(cls.x)[0] * np.diff(cls.y)[0]

    def test_bulk_and_class_volume_conservation(self):
        r = self.r
        eroded = r.erosion_by_class_m.sum(axis=(0, 1)) * self.area
        deposited = r.deposition_by_class_m.sum(axis=(0, 1)) * self.area
        exported = np.asarray(r.receipt['boundary_export_by_class_m3'])
        np.testing.assert_allclose(eroded - deposited, exported, atol=1e-13, rtol=1e-10)
        self.assertAlmostEqual(float(r.height_delta_m.sum()) * self.area,
                               -float(exported.sum()), places=13)
        np.testing.assert_allclose(r.height_delta_m,
                                   r.cumulative_deposition_m - r.cumulative_erosion_m,
                                   atol=2e-16, rtol=1e-10)
        self.assertLess(r.receipt['relative_sediment_balance_error'], 1e-10)
        for event in r.receipt['events']:
            self.assertLess(abs(event['cumulative_sediment_balance_error_m3']), 1e-12)
        # Receipt is an ordinary exportable data object, with no array payload.
        json.dumps(r.receipt)

    def test_water_conservation_and_connected_accumulation(self):
        self.assertLess(abs(self.r.receipt['water_balance_error_m3']), 1e-12)
        self.assertGreater(self.r.receipt['water_boundary_export_m3'], 0)
        local_rain = sum(self.config.rainfall_m) * self.config.runoff_fraction * self.area
        self.assertGreater(self.r.cumulative_water_m3.max(), 50 * local_rain)

    def test_locked_perimeter_and_smooth_conservative_bounds(self):
        r = self.r
        np.testing.assert_array_equal(r.height_delta_m[[0, -1]], 0)
        np.testing.assert_array_equal(r.height_delta_m[:, [0, -1]], 0)
        self.assertTrue(np.all(r.height_delta_m >= -self.config.max_erosion_m * r.boundary_mobility - 1e-12))
        self.assertTrue(np.all(r.height_delta_m <= self.config.max_deposition_m * r.boundary_mobility + 1e-12))
        self.assertTrue(np.all(np.diff(r.boundary_mobility[10, :5]) > 0))
        self.assertGreater(np.abs(r.height_delta_m).max(), .001)
        self.assertGreater(r.final_deposit_m.max(), .001)
        self.assertGreater(r.cumulative_erosion_m.max(), .001)
        self.assertTrue(np.all(r.cumulative_erosion_m <= len(self.config.rainfall_m)
                               * self.config.max_event_erosion_m * r.boundary_mobility + 1e-12))

    def test_class_fields_bounded_and_size_graded_burial(self):
        r = self.r
        for name in ('deposition_fraction', 'surface_fraction', 'exposure_by_class',
                     'burial_by_class', 'lag_exposure', 'compacted_bare', 'flow_strength'):
            field = getattr(r, name)
            self.assertTrue(np.all(np.isfinite(field)), name)
            self.assertTrue(np.all((field >= -1e-12) & (field <= 1 + 1e-12)), name)
        np.testing.assert_allclose(r.surface_fraction.sum(axis=-1), 1., atol=1e-12)
        has_deposit = r.final_deposit_m > 1e-15
        np.testing.assert_allclose(r.deposition_fraction[has_deposit].sum(axis=-1), 1., atol=1e-12)
        # Smaller original grains are buried before larger ones at the same site.
        self.assertTrue(np.all(r.burial_by_class[..., 0] >= r.burial_by_class[..., 1]))
        self.assertTrue(np.all(r.burial_by_class[..., 1] >= r.burial_by_class[..., 2]))
        self.assertTrue(np.all(r.exposure_by_class[..., 0] <= r.exposure_by_class[..., 2]))
        self.assertGreater(np.std(r.deposition_fraction[has_deposit, 0]), .02)
        self.assertGreater(r.lag_exposure.max(), .05)
        self.assertGreater(r.compacted_bare.max(), .05)

    def test_reproducible_and_does_not_mutate_inputs(self):
        original = self.z.copy()
        second = simulate_shoulder(self.x, self.y, self.z, self.config)
        np.testing.assert_array_equal(self.z, original)
        np.testing.assert_array_equal(second.height_delta_m, self.r.height_delta_m)
        np.testing.assert_array_equal(second.deposition_fraction, self.r.deposition_fraction)
        np.testing.assert_array_equal(second.final_receiver, self.r.final_receiver)

    def test_changes_respond_to_supplied_terrain_and_seed(self):
        other_seed = simulate_shoulder(self.x, self.y, self.z, replace(self.config, seed=12))
        other_terrain = simulate_shoulder(self.x, self.y, self.z[:, ::-1], self.config)
        self.assertGreater(np.max(np.abs(other_seed.height_delta_m - self.r.height_delta_m)), 1e-5)
        self.assertGreater(np.max(np.abs(other_terrain.height_delta_m - self.r.height_delta_m)), 1e-4)

    def test_zero_water_zero_displacement(self):
        dry = simulate_shoulder(self.x, self.y, self.z,
                                replace(self.config, rainfall_m=(0., 0.)))
        for name in ('height_delta_m', 'cumulative_water_m3', 'cumulative_erosion_m',
                     'cumulative_deposition_m', 'lag_exposure', 'compacted_bare'):
            np.testing.assert_array_equal(getattr(dry, name), 0)
        self.assertEqual(dry.receipt['boundary_export_m3'], 0)

    def test_drainage_is_acyclic_and_only_exports_at_rim(self):
        rec = self.r.final_receiver.ravel()
        ny, nx = self.z.shape
        finished = np.zeros(rec.size, bool)
        for start in range(rec.size):
            i, visited = start, set()
            while i >= 0 and not finished[i]:
                self.assertNotIn(i, visited)
                visited.add(i)
                j = int(rec[i])
                if j < 0:
                    iy, ix = divmod(i, nx)
                    self.assertTrue(iy in (0, ny - 1) or ix in (0, nx - 1))
                else:
                    iy, ix = divmod(i, nx)
                    jy, jx = divmod(j, nx)
                    self.assertLessEqual(max(abs(iy - jy), abs(ix - jx)), 1)
                i = j
            for i in visited:
                finished[i] = True

    def test_invalid_holes_are_closed_and_do_not_receive_volume(self):
        x, y, z = terrain(21, 25)
        valid = np.ones(z.shape, bool)
        valid[10:13, 9:12] = False
        z[~valid] = np.nan
        r = simulate_shoulder(x, y, z, replace(self.config, rainfall_m=(.02,)), valid)
        np.testing.assert_array_equal(r.height_delta_m[~valid], 0)
        np.testing.assert_array_equal(r.final_receiver[~valid], -2)
        receivers = r.final_receiver[r.final_receiver >= 0]
        self.assertTrue(np.all(valid.ravel()[receivers]))
        self.assertLess(abs(r.receipt['sediment_balance_error_m3']), 1e-12)

    def test_bad_inputs_raise_instead_of_guessing(self):
        bad_x = self.x.copy()
        bad_x[3] += .001
        with self.assertRaises(ValueError):
            simulate_shoulder(bad_x, self.y, self.z)
        with self.assertRaises(ValueError):
            simulate_shoulder(self.x[::-1], self.y, self.z)
        with self.assertRaises(ValueError):
            simulate_shoulder(self.x, self.y, self.z.T)
        with self.assertRaises(ValueError):
            simulate_shoulder(self.x, self.y, self.z, replace(self.config, rainfall_m=(-.01,)))
        with self.assertRaises(ValueError):
            simulate_shoulder(self.x, self.y, self.z, replace(self.config, substrate_fractions=(1., 1., 1.)))
        island = np.zeros(self.z.shape, bool)
        island[10:15, 10:15] = True
        with self.assertRaises(ValueError):
            simulate_shoulder(self.x, self.y, self.z, valid_mask=island)

    @unittest.skipUnless(os.getenv('FLOW_MODEL_BENCHMARK'), 'Set FLOW_MODEL_BENCHMARK=1 for full shoulder')
    def test_full_shoulder_benchmark(self):
        x = np.linspace(-5.8, -3.25, 86)
        y = np.linspace(-.6, 8.2, 295)
        xx, yy = np.meshgrid(x, y)
        z = .024 * (xx + 5.8) - .010 * yy + .003 * np.sin(yy * 6 + xx * 5)
        z += .0018 * np.sin(yy * 17 - xx * 9)
        r = simulate_shoulder(x, y, z)
        print('\nFull shoulder benchmark:', json.dumps({k: r.receipt[k] for k in (
            'runtime_s', 'shape_yx', 'minimum_height_delta_m', 'maximum_height_delta_m',
            'cumulative_erosion_m3', 'cumulative_deposition_m3', 'boundary_export_m3',
            'relative_sediment_balance_error')}))
        self.assertLess(r.receipt['relative_sediment_balance_error'], 1e-10)
        self.assertLess(abs(r.receipt['water_balance_error_m3']), 1e-10)


if __name__ == '__main__':
    unittest.main()
