"""Single-thread, scene-free tests for the supplemental representation selector.

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m unittest -v test_transported_grain_exposure.py
"""
from dataclasses import replace
import json
import unittest

import numpy as np

from transported_grain_exposure import ExposureConfig, allocate_transported_grains


def patch(*, depth=.004, count=6000, fractions=(.70, .24, .06), seed=41):
    rng = np.random.default_rng(seed)
    x = np.arange(9) * .025
    y = np.arange(7) * .025
    xy = rng.uniform([x[0], y[0]], [x[-1], y[-1]], (count, 2))
    classes = np.where(rng.random(count) < .5, 1, 2)
    diameter = np.where(classes == 1, .001, .003) * rng.uniform(.75, 1.25, count)
    height = diameter * .60
    return dict(xy_m=xy, flow_class=classes,
                solid_volume_m3=diameter ** 2 * height * .34,
                diameter_m=diameter, footprint_area_m2=diameter ** 2 * .68,
                local_z_bounds_m=np.column_stack((-.55 * height, .45 * height)),
                final_surface_m=np.full(count, 10. + depth),
                x_m=x, y_m=y,
                retained_deposit_by_class_m=np.broadcast_to(
                    depth * np.asarray(fractions), (len(y), len(x), 3)).copy(),
                net_deposit_m=np.full((len(y), len(x)), depth),
                local_net_deposit_m=np.full(count, depth))


class TransportedExposureTests(unittest.TestCase):
    def test_reproducible_without_mutating_inputs_and_ledger_closes(self):
        inputs = patch()
        saved = {name: a.copy() for name, a in inputs.items()}
        a = allocate_transported_grains(**inputs)
        b = allocate_transported_grains(**inputs)
        np.testing.assert_array_equal(a.transported, b.transported)
        np.testing.assert_array_equal(a.extra_embedment_m, b.extra_embedment_m)
        self.assertEqual(a.receipt, b.receipt)
        json.dumps(a.receipt, allow_nan=False)
        for name, value in saved.items():
            np.testing.assert_array_equal(inputs[name], value, err_msg=name)
        self.assertGreater(a.transported.sum(), 0)
        self.assertLess(a.transported.sum(), len(a.transported))
        self.assertTrue(np.all(a.remaining_representation_volume_by_cell_class_m3 >= 0))
        np.testing.assert_allclose(a.selected_solid_volume_by_cell_class_m3
                                   + a.remaining_representation_volume_by_cell_class_m3,
                                   a.solid_budget_by_cell_class_m3, rtol=1e-15, atol=0)
        ledger = np.zeros_like(a.solid_budget_by_cell_class_m3)
        yy, xx = a.candidate_cell_yx[a.transported].T
        np.add.at(ledger, (yy, xx, inputs['flow_class'][a.transported]),
                  inputs['solid_volume_m3'][a.transported])
        np.testing.assert_allclose(ledger, a.selected_solid_volume_by_cell_class_m3,
                                   rtol=1e-14, atol=1e-22)
        self.assertTrue(np.all(ledger <= a.solid_budget_by_cell_class_m3 * (1 + 1e-14)))
        self.assertEqual(a.receipt['audit']['negative_remaining_inventory_entries'], 0)
        self.assertEqual(a.receipt['audit']['solid_budget_exceedance_m3'], 0)
        np.testing.assert_array_equal(a.extra_embedment_m[~a.transported], 0)
        # Original source embedment is preserved, plus downward-only extra burial.
        self.assertTrue(np.all(a.extra_embedment_m >= 0))
        self.assertTrue(np.all(a.extra_embedment_m[a.transported]
                               < inputs['local_z_bounds_m'][a.transported, 1]))

    def test_zero_and_net_eroded_zones_have_no_transport(self):
        for depth, net in ((0., 0.), (.004, -.001), (.004, 0.)):
            inputs = patch(depth=depth)
            inputs['net_deposit_m'][:] = net
            inputs['local_net_deposit_m'][:] = net
            r = allocate_transported_grains(**inputs)
            self.assertEqual(r.transported.sum(), 0)
            np.testing.assert_array_equal(r.extra_embedment_m, 0)
            np.testing.assert_array_equal(r.selected_solid_volume_by_cell_class_m3, 0)
            json.dumps(r.receipt, allow_nan=False)

    def test_only_supported_positive_local_deposit_is_promoted(self):
        inputs = patch()
        # Grid deposition alone must not override actual final triangle support.
        inputs['xy_m'][:500, 0] = -1
        inputs['final_surface_m'][500:1000] = np.nan
        inputs['local_net_deposit_m'][1000:1500] = -.001
        inputs['local_net_deposit_m'][1500:2000] = 0
        inputs['local_net_deposit_m'][2000:2500] = np.nan
        # A fully submerged/above-datum prototype cannot meet the placement rule.
        inputs['local_z_bounds_m'][2500:2750] = (-.002, -.001)
        inputs['local_z_bounds_m'][2750:3000] = (.001, .002)
        r = allocate_transported_grains(**inputs)
        self.assertFalse(r.transported[:3000].any())
        self.assertTrue(r.transported[3000:].any())
        self.assertTrue(np.all(r.candidate_cell_yx[:500] == -1))
        for key in ('promoted_outside_grid', 'promoted_unsupported_surface',
                    'promoted_without_positive_net_deposit', 'promoted_without_retained_own_class'):
            self.assertEqual(r.receipt['audit'][key], 0)

    def test_no_cross_class_budget_borrowing(self):
        inputs = patch(fractions=(.70, .30, 0.))
        r = allocate_transported_grains(**inputs)
        self.assertFalse(r.transported[inputs['flow_class'] == 2].any())
        self.assertTrue(r.transported[inputs['flow_class'] == 1].any())
        np.testing.assert_array_equal(r.selected_solid_volume_by_cell_class_m3[..., [0, 2]], 0)

    def test_large_bodies_cannot_spend_neighbor_or_other_class_volume(self):
        inputs = patch(count=200)
        inputs['solid_volume_m3'][:] = .001  # Larger than every local solid stock.
        r = allocate_transported_grains(**inputs)
        self.assertEqual(r.transported.sum(), 0)
        self.assertGreater(r.receipt['volume_rejected_attempts'], 0)
        np.testing.assert_array_equal(r.remaining_representation_volume_by_cell_class_m3,
                                      r.solid_budget_by_cell_class_m3)

    def test_thickness_and_settling_change_exposure_selectively(self):
        shallow_inputs = patch(depth=.0004)
        deep_inputs = patch(depth=.006)
        shallow = allocate_transported_grains(**shallow_inputs)
        deep = allocate_transported_grains(**deep_inputs)
        self.assertGreater(deep.exposed_planar_area_proxy_by_cell_class_m2.sum(),
                           shallow.exposed_planar_area_proxy_by_cell_class_m2.sum())
        common = shallow.transported & deep.transported
        self.assertTrue(common.any())
        self.assertTrue(np.all(deep.extra_embedment_m[common] < shallow.extra_embedment_m[common]))
        inputs = patch(depth=.006, count=12000)
        low = allocate_transported_grains(**inputs, config=replace(
            ExposureConfig(), top_availability_by_class=(1., .80, .10)))
        high = allocate_transported_grains(**inputs, config=replace(
            ExposureConfig(), top_availability_by_class=(1., .80, .95)))
        chips = inputs['flow_class'] == 2
        self.assertLess(low.transported[chips].sum(), high.transported[chips].sum())
        self.assertGreater(low.transported[chips].sum(), 0)
        self.assertLess(high.transported[chips].sum(), chips.sum())

    def test_fractional_area_target_overshoot_is_at_most_one_body_proxy(self):
        inputs = patch(count=18000)
        r = allocate_transported_grains(**inputs)
        footprint_cap = np.zeros_like(r.solid_budget_by_cell_class_m3)
        yy, xx = r.candidate_cell_yx.T
        np.maximum.at(footprint_cap, (yy, xx, inputs['flow_class']), inputs['footprint_area_m2'])
        overshoot = np.maximum(r.exposed_planar_area_proxy_by_cell_class_m2
                               - r.target_planar_area_proxy_by_cell_class_m2, 0)
        self.assertTrue(np.all(overshoot <= footprint_cap + 1e-20))
        self.assertGreater(r.receipt['fractional_area_roundups'], 0)
        self.assertGreater(r.receipt['fractional_area_rounddowns'], 0)
        self.assertTrue(np.all(r.selected_solid_volume_by_cell_class_m3
                               <= r.solid_budget_by_cell_class_m3))

    def test_bilinear_local_field_and_input_order_seed_contract(self):
        inputs = patch(count=3000)
        inputs.pop('local_net_deposit_m')
        inputs['net_deposit_m'] *= np.linspace(0, 1, len(inputs['x_m']))[None, :]
        a = allocate_transported_grains(**inputs)
        expected = .004 * inputs['xy_m'][:, 0] / inputs['x_m'][-1]
        np.testing.assert_allclose(a.local_net_deposit_m, expected, atol=1e-15)
        b = allocate_transported_grains(**inputs, config=replace(ExposureConfig(), seed=73182))
        self.assertFalse(np.array_equal(a.transported, b.transported))
        np.testing.assert_allclose(a.local_top_active_layer_fraction.sum(axis=1), 1)

    def test_empty_finite_candidate_pool_reports_unrepresented_volume(self):
        inputs = patch(count=0)
        r = allocate_transported_grains(**inputs)
        self.assertEqual(r.transported.shape, (0,))
        self.assertEqual(r.candidate_cell_yx.shape, (0, 2))
        self.assertGreater(r.remaining_representation_volume_by_cell_class_m3.sum(), 0)
        self.assertGreater(r.receipt['target_cells_with_insufficient_candidate_area'], 0)
        json.dumps(r.receipt, allow_nan=False)

    def test_invalid_inventories_geometry_and_grid_are_rejected(self):
        for key, index, value in (
            ('retained_deposit_by_class_m', (0, 0, 0), -1e-30),
            ('retained_deposit_by_class_m', (0, 0, 0), np.nan),
            ('solid_volume_m3', 0, 0),
            ('diameter_m', 0, -1),
            ('footprint_area_m2', 0, np.nan),
            ('flow_class', 0, 0),
            ('flow_class', 0, 3),
            ('final_surface_m', 0, np.inf),
            ('net_deposit_m', (0, 0), np.nan),
            ('x_m', 1, .027),
        ):
            inputs = patch(count=20)
            inputs[key][index] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                allocate_transported_grains(**inputs)
        with self.assertRaises(ValueError):
            allocate_transported_grains(**patch(count=20), config=replace(ExposureConfig(), solid_fraction=1.1))


if __name__ == '__main__':
    unittest.main()
