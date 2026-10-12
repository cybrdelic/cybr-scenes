"""Tiny stage/connectivity regressions, including the portable real-terrain patch.
No Blender or full-grid run. This is numerical evidence, not hydraulic validation.
"""
import json
from pathlib import Path
import unittest

import numpy as np

from flow_sediment_model_y import (FlowConfig, _connected_wet_contact,
                                   _flow_routes, _neighbors, simulate_shoulder)


class ConnectedWetStageTests(unittest.TestCase):
    @staticmethod
    def contact_grid():
        yy, xx = np.indices((5, 5))
        cells = np.stack((yy.ravel(), xx.ravel()), axis=1)
        adjacency = np.sum(abs(cells[:, None] - cells[None]), axis=-1) == 1
        heights = np.zeros((5, 5))
        heights[:, 2] = .010  # A dry crest separates two low, nearby pockets.
        return heights, np.full(25, 1 / 25), adjacency, 2 * 5 + 1

    def test_dry_crest_blocks_low_receiver_inside_footprint(self):
        height, weights, adjacency, center = self.contact_grid()
        contact, head, reached = _connected_wet_contact(height.ravel(), .004, weights,
                                                        adjacency, center)
        self.assertTrue(np.all(reached.reshape(5, 5)[:, :2]))
        self.assertFalse(np.any(reached.reshape(5, 5)[:, 2:]))
        self.assertTrue(np.all(head.reshape(5, 5)[:, 3:] > 0))
        self.assertLess(contact.sum(), weights.sum())  # No concentrating renormalization.
        # Open a submerged connecting face, and the low far pocket becomes wet.
        height[2, 2] = .002
        _, _, opened = _connected_wet_contact(height.ravel(), .004, weights,
                                               adjacency, center)
        self.assertTrue(np.all(opened.reshape(5, 5)[:, 3:]))
        # Filling that same connection to water stage closes it immediately.
        height[2, 2] = .004
        _, _, reclosed = _connected_wet_contact(height.ravel(), .004, weights,
                                                 adjacency, center)
        self.assertFalse(np.any(reclosed.reshape(5, 5)[:, 3:]))

    def test_head_capacity_leaves_rejected_volume_in_each_class_load(self):
        height, weights, adjacency, center = self.contact_grid()
        stage, area = .004, .025 ** 2
        contact, head, _ = _connected_wet_contact(height.ravel(), stage, weights,
                                                  adjacency, center)
        load = np.array([.001, .0002, .00007])
        add = contact[:, None] * load[None]
        add *= np.minimum(1., area * head / np.maximum(add.sum(axis=1), 1e-30))[:, None]
        remaining = load - add.sum(axis=0)
        np.testing.assert_allclose(add.sum(axis=0) + remaining, load, atol=1e-18)
        self.assertTrue(np.all(remaining > 0))
        receiving = add.sum(axis=1) > 0
        self.assertTrue(np.all(height.ravel()[receiving] + add.sum(axis=1)[receiving] / area <= stage + 1e-12))
        self.assertTrue(np.all(add.reshape(5, 5, 3)[:, 2:] == 0))

    def test_near_equal_flat_routing_never_strands_packets(self):
        shape = (7, 9)
        valid = np.ones(shape, bool)
        # Near-equal caps must have the same definition of a flat and sort key.
        heights = np.arange(valid.size) % 3 * 2e-13
        neighbors, distances = _neighbors(shape, .025, .025, valid)
        weights, _, _, order, _ = _flow_routes(heights, valid, neighbors, distances, 1.35)
        packets = np.zeros((valid.size, 3))
        packets[3 * shape[1] + 4] = [.001, .0002, .00005]
        original = packets.sum(axis=0)
        exported = np.zeros(3)
        for i in order:
            moving = weights[i] > 0
            if np.any(moving):
                packets[neighbors[i, moving]] += weights[i, moving, None] * packets[i]
            else:
                exported += packets[i]
            packets[i] = 0
        np.testing.assert_array_equal(packets, 0)
        np.testing.assert_allclose(exported, original, atol=1e-18)

    def test_actual_terrain_keeps_guards_and_class_conservation(self):
        path = Path(__file__).parent / 'fixtures/shoulder_w_actual_regression.json'
        fixture = json.loads(path.read_text())
        r = simulate_shoulder(np.array(fixture['x_m']), np.array(fixture['y_m']),
                              np.array(fixture['source_z_m']))
        for name in ('height_delta_m', 'retained_deposit_by_class_m', 'surface_fraction',
                     'cumulative_erosion_m', 'cumulative_deposition_m', 'lag_exposure'):
            self.assertTrue(np.all(np.isfinite(getattr(r, name))), name)
        self.assertTrue(np.all(r.retained_deposit_by_class_m >= 0))
        self.assertTrue(np.all(r.height_delta_m >= -.018 * r.boundary_mobility - 1e-12))
        self.assertTrue(np.all(r.height_delta_m <= .024 * r.boundary_mobility + 1e-12))
        for key in ('sediment_balance_error_m3', 'net_bed_plus_export_error_m3',
                    'water_balance_error_m3'):
            self.assertLess(abs(r.receipt[key]), 1e-12)
        for event in r.receipt['events']:
            self.assertLess(event['absolute_class_balance_error_m3'], 1e-12)
        self.assertGreater(r.receipt['stage_blocked_receiver_contacts'], 0)
        self.assertGreater(r.receipt['unplaced_deposition_requests_m3'], 0)
        self.assertLess(r.height_delta_m.max(), .0045)
        self.assertEqual(r.receipt['roundoff_inventory_added_m3'], 0.)
        print('\nY real31x25 fixture:', {k: r.receipt[k] for k in (
            'runtime_s', 'minimum_height_delta_m', 'maximum_height_delta_m',
            'cumulative_erosion_m3', 'cumulative_deposition_m3', 'boundary_export_m3',
            'net_bed_plus_export_error_m3', 'water_balance_error_m3')})


if __name__ == '__main__':
    unittest.main()
