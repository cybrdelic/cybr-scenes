"""Six tiny synthetic Z inventory regressions, not hydraulic/opacity validation."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
import flow_sediment_model_y as y_model
from flow_sediment_model_z import (FlowConfig, _connected_wet_contact, _neighbors,
                                   _relax_deposits, simulate_shoulder)

PROOF = {}


def tiny_catchment():
    x, y = np.linspace(-.3, .3, 25), np.linspace(-.15, .15, 13)
    xx, yy = np.meshgrid(x, y)
    # Connected ramp drains onto a lower apron, creating a settling transition.
    z = .18 * np.maximum(xx, 0.) + .002 * yy ** 2
    cfg = FlowConfig(rainfall_m=(.014, .022), event_duration_s=120.,
                     boundary_band_m=.05, heterogeneity_strength=0.)
    return x, y, xx, z, cfg


def assert_stock(test, result, atol=1e-15):
    receipt = result.receipt
    initial = np.array(receipt['initial_mobile_bed_layer_by_class_m3'])
    remaining = np.array(receipt['remaining_initial_bed_layer_by_class_m3'])
    deposit = np.array(receipt['retained_transported_deposit_by_class_m3'])
    exported = np.array(receipt['boundary_export_by_class_m3'])
    correction = np.array(receipt['roundoff_inventory_added_by_class_m3'])
    np.testing.assert_allclose(initial + correction, remaining + deposit + exported,
                               rtol=0, atol=atol)
    test.assertTrue(np.all(result.remaining_initial_mobile_class_thickness_m >= 0))
    test.assertTrue(np.all(result.retained_deposit_by_class_m >= 0))
    test.assertTrue(np.all(result.remaining_initial_mobile_class_thickness_m <=
                           result.initial_mobile_class_thickness_m + 1e-15))
    for event in receipt['events']:
        test.assertLess(event['absolute_class_balance_error_m3'], atol)
    test.assertLess(abs(receipt['water_balance_error_m3']), atol)


class FiniteRoadFilmTests(unittest.TestCase):
    def test_01_plain_api_is_bitwise_y_and_connected_contact_preserved(self):
        self.assertEqual(hashlib.sha256(Path(y_model.__file__).read_bytes()).hexdigest(),
                         'fd7e7279492dd6c897454c86259a53b481ded3e78f0d2e56d5f7381a3fb7ae33')
        x, y = np.arange(11) * .025, np.arange(9) * .025
        xx, yy = np.meshgrid(x, y)
        z = .07 * xx + .02 * (yy - .10) ** 2
        cfg = FlowConfig(rainfall_m=(.012, .026), boundary_band_m=.05)
        old = y_model.simulate_shoulder(x, y, z, y_model.FlowConfig(**asdict(cfg)))
        new = simulate_shoulder(x, y, z, cfg)
        for name in old.__dataclass_fields__:
            if name != 'receipt':
                np.testing.assert_array_equal(getattr(new, name), getattr(old, name), err_msg=name)
        height = np.zeros((5, 5))
        height[:, 2] = .010
        cells = np.stack(np.indices((5, 5)), axis=-1).reshape(-1, 2)
        adjacency = np.sum(abs(cells[:, None] - cells[None]), axis=-1) == 1
        args = (height.ravel(), .004, np.full(25, 1 / 25), adjacency, 11)
        new_contact = _connected_wet_contact(*args)
        for new_part, old_part in zip(new_contact, y_model._connected_wet_contact(*args)):
            np.testing.assert_array_equal(new_part, old_part)
        self.assertFalse(new_contact[2].reshape(5, 5)[:, 2:].any())
        assert_stock(self, new)
        PROOF['default_y_equivalence'] = {'shape_yx': list(z.shape), 'events': 2,
            'all_original_result_arrays_bitwise_equal': True, 'dry_crest_blocks_connected_contact': True}

    def test_02_immobile_pavement_cannot_supply_soil(self):
        x, y, xx, z, cfg = tiny_catchment()
        inventory = np.zeros(z.shape + (3,))
        original = inventory.copy()
        r = simulate_shoulder(x, y, z, cfg, initial_mobile_class_thickness_m=inventory)
        np.testing.assert_array_equal(inventory, original)
        self.assertGreater(r.max_shear_pa.max(), cfg.critical_shear_pa[0])
        for field in (r.height_delta_m, r.erosion_by_class_m, r.retained_deposit_by_class_m,
                      r.remaining_initial_mobile_class_thickness_m):
            np.testing.assert_array_equal(field, 0.)
        self.assertEqual(r.receipt['boundary_export_m3'], 0.)
        assert_stock(self, r)
        PROOF['immobile_pavement'] = {'maximum_shear_pa': float(r.max_shear_pa.max()),
            'erosion_m3': r.receipt['cumulative_erosion_m3'],
            'export_m3': r.receipt['boundary_export_m3'], 'height_change_m': float(abs(r.height_delta_m).max())}

    def test_03_matrix_veneer_washes_and_deposits_without_replenishment(self):
        x, y, xx, z, cfg = tiny_catchment()
        inventory = np.zeros(z.shape + (3,))
        inventory[..., 0] = np.where(xx >= .05, .00008, 0.)
        original = inventory.copy()
        r = simulate_shoulder(x, y, z, cfg, initial_mobile_class_thickness_m=inventory)
        np.testing.assert_array_equal(inventory, original)
        np.testing.assert_array_equal(r.remaining_initial_mobile_class_thickness_m[..., 1:], 0.)
        np.testing.assert_array_equal(r.retained_deposit_by_class_m[..., 1:], 0.)
        np.testing.assert_array_equal(r.erosion_by_class_m[..., 1:], 0.)
        self.assertGreater(r.receipt['boundary_export_m3'], 0.)
        self.assertGreater(r.receipt['retained_transported_deposit_m3'], 0.)
        self.assertGreater(r.retained_deposit_by_class_m[xx < 0].sum(), 0.)
        self.assertLess(r.remaining_initial_mobile_class_thickness_m[6, 18, 0], .00008 / 10)
        self.assertTrue(np.all(r.height_delta_m >= -inventory.sum(axis=-1) - 1e-12))
        # Supplied stock stays exact even at the locked perimeter.
        np.testing.assert_array_equal(r.initial_mobile_class_thickness_m, inventory)
        np.testing.assert_array_equal(r.remaining_initial_mobile_class_thickness_m[0], inventory[0])
        assert_stock(self, r)
        PROOF['matrix_veneer'] = {k: r.receipt[k] for k in (
            'initial_mobile_bed_layer_by_class_m3', 'remaining_initial_bed_layer_by_class_m3',
            'retained_transported_deposit_by_class_m3', 'boundary_export_by_class_m3',
            'stock_balance_by_class_m3', 'water_balance_error_m3',
            'minimum_height_delta_m', 'maximum_height_delta_m')}
        PROOF['matrix_veneer']['interior_source_remaining_m'] = float(r.remaining_initial_mobile_class_thickness_m[6, 18, 0])

    def test_04_per_cell_retained_caps_and_mixed_soil_stock(self):
        x, y, xx, z, cfg = tiny_catchment()
        inventory = np.zeros(z.shape + (3,))
        inventory[xx >= .05, 0] = .00008
        inventory[xx < 0] = np.array([.002, .0005, .0002])
        cap = np.where(xx < -.125, 0., .000003)
        original_cap = cap.copy()
        r = simulate_shoulder(x, y, z, cfg, initial_mobile_class_thickness_m=inventory,
                              maximum_deposited_thickness_m=cap)
        np.testing.assert_array_equal(cap, original_cap)
        self.assertTrue(np.all(r.final_deposit_m <= cap + 1e-15))
        np.testing.assert_array_equal(r.final_deposit_m[cap == 0], 0.)
        self.assertGreater(r.final_deposit_m.max(), 0.)
        self.assertGreater(r.receipt['unplaced_deposition_requests_m3'], 0.)
        self.assertGreater(r.receipt['boundary_export_m3'], 0.)
        self.assertTrue(np.all(r.height_delta_m >= -inventory.sum(axis=-1) - 1e-12))
        assert_stock(self, r)
        PROOF['mixed_inventory_capped_storms'] = {k: r.receipt[k] for k in (
            'initial_mobile_bed_layer_by_class_m3', 'remaining_initial_bed_layer_by_class_m3',
            'retained_transported_deposit_by_class_m3', 'boundary_export_by_class_m3',
            'stock_balance_by_class_m3', 'maximum_retained_deposit_cap_excess_m',
            'unplaced_deposition_requests_m3')}
        PROOF['mixed_inventory_capped_storms']['maximum_retained_thickness_m'] = float(r.final_deposit_m.max())
        PROOF['mixed_inventory_capped_storms']['zero_cap_cells_remain_empty'] = True

    def test_05_slumping_respects_per_cell_stock_cap_by_class(self):
        shape, dx, dy = (5, 5), .025, .025
        n, area = 25, dx * dy
        neighbors, distances = _neighbors(shape, dx, dy, np.ones(shape, bool))
        base = np.zeros(n)
        base[12] = .080
        deposited = np.zeros((n, 3))
        deposited[12] = np.array([.002, .001, .001]) * area
        original = deposited.sum(axis=0)
        initial, bed = deposited.copy(), np.zeros_like(deposited)
        erosion, deposition = np.zeros_like(deposited), np.zeros_like(deposited)
        cap = np.full(n, .00003)
        cap[[7, 11]] = 0.
        cap[12] = .004
        moved = _relax_deposits(base, initial, bed, deposited, erosion, deposition,
                                area, np.ones(n), neighbors, distances, FlowConfig(), dx, dy,
                                maximum_deposited_thickness_m=cap)
        self.assertGreater(moved, 0.)
        self.assertTrue(np.all(deposited >= 0.))
        self.assertTrue(np.all(deposited.sum(axis=1) / area <= cap + 1e-15))
        np.testing.assert_array_equal(deposited[cap == 0], 0.)
        np.testing.assert_allclose(deposited.sum(axis=0), original, rtol=0, atol=1e-18)
        np.testing.assert_allclose(erosion.sum(axis=0), deposition.sum(axis=0), rtol=0, atol=1e-18)
        PROOF['capped_slope_redistribution'] = {'shape_yx': list(shape), 'moved_m3': moved,
            'per_class_stock_error_m3': (deposited.sum(axis=0) - original).tolist(),
            'maximum_cap_excess_m': float(max(0., np.max(deposited.sum(axis=1) / area - cap))),
            'zero_cap_receivers_remain_empty': True}

    def test_06_supplied_deep_stock_obeys_y_scour_limit_and_maps_validate(self):
        x, y = np.arange(7) * .025, np.arange(7) * .025
        xx, yy = np.meshgrid(x, y)
        z = .6 * xx
        cfg = FlowConfig(rainfall_m=(.08, .08), event_duration_s=30., max_erosion_m=.00002,
                         boundary_band_m=.025, heterogeneity_strength=0.)
        inventory = np.full(z.shape + (3,), .005)
        r = simulate_shoulder(x, y, z, cfg, initial_mobile_class_thickness_m=inventory)
        self.assertTrue(np.all(r.height_delta_m >= -cfg.max_erosion_m * r.boundary_mobility - 1e-12))
        original_scour = (r.initial_mobile_class_thickness_m -
                          r.remaining_initial_mobile_class_thickness_m).sum(axis=-1)
        self.assertTrue(np.all(original_scour <= cfg.max_erosion_m * r.boundary_mobility + 1e-12))
        assert_stock(self, r)
        for name, bad in (
            ('initial_mobile_class_thickness_m', np.zeros(z.shape)),
            ('initial_mobile_class_thickness_m', np.full(z.shape + (3,), -1.)),
            ('initial_mobile_class_thickness_m', np.full(z.shape + (3,), np.nan)),
            ('maximum_deposited_thickness_m', np.zeros(z.shape + (3,))),
            ('maximum_deposited_thickness_m', np.full(z.shape, -1.)),
            ('maximum_deposited_thickness_m', np.full(z.shape, np.inf)),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                simulate_shoulder(x, y, z, cfg, **{name: bad})
        PROOF['deep_stock_scour_bound'] = {'maximum_allowed_scour_m': cfg.max_erosion_m,
            'minimum_height_delta_m': float(r.height_delta_m.min()),
            'maximum_original_layer_scour_m': float(original_scour.max()), 'invalid_map_cases_rejected': 6}


if __name__ == '__main__':
    import os
    import sys
    import time
    started = time.perf_counter()
    program = unittest.main(exit=False, verbosity=2)
    passed = program.result.wasSuccessful()
    receipt_path = os.environ.get('Z_PROOF_RECEIPT')
    if receipt_path:
        source = Path(__file__).with_name('flow_sediment_model_z.py')
        receipt = {'status': 'PASS' if passed else 'FAIL',
            'scope': 'Six focused tiny synthetic CPU1 tests; no broad convergence, actual-terrain runs, Blender, rendering, or publication',
            'tests_run': program.result.testsRun,
            'failures': len(program.result.failures), 'errors': len(program.result.errors),
            'cpu_affinity': sorted(os.sched_getaffinity(0)), 'runtime_s': time.perf_counter() - started,
            'source_file': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'preserved_y_sha256': hashlib.sha256(source.with_name('flow_sediment_model_y.py').read_bytes()).hexdigest(),
            'caveat': 'NONVALIDATED ART-DIRECTED PHYSICS. Inventory/conservation proof does not validate hydrodynamics, optical opacity, or a particular visual result.',
            'proof': PROOF}
        Path(receipt_path).write_text(json.dumps(receipt, indent=2) + '\n')
    sys.exit(0 if passed else 1)
