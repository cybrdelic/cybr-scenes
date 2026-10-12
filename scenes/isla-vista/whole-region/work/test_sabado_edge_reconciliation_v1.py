"""Tiny cap-ridge regression; no whole-Isla-Vista data or renderer needed."""
from pathlib import Path
import sys
R = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(R / 'geo-deps'), str(R / 'whole-iv-vendor'), str(R / 'work')]
import numpy as np
from reconcile_sabado_profile_edges_v2 import refine_pair, triangle_row
from verify_sabado_profile_v1 import Surface


def test_straight_chord_over_two_facets():
    cap = []
    for left, right, zl, zr in [(0., .5, .2, .3), (.5, 1., .3, .2)]:
        quad = np.array([[left, 0, zl], [right, 0, zr], [right, 1, zr], [left, 1, zl]])
        cap.extend([quad[[0, 1, 2]], quad[[0, 2, 3]]])
    surface = Surface(np.asarray(cap))
    quad = np.array([[0, 0, 0], [1, 0, 0], [1, 0, .2], [0, 0, .2]])
    uv = quad[:, [0, 2]] / 1.25
    tint = np.ones((4, 3))
    pair = np.stack([triangle_row(quad[indices], uv[indices], tint[indices], 11, 4000392)
                     for indices in [[0, 1, 2], [0, 2, 3]]])
    old_gap = float(surface.height(np.array([[.5, 0]]))[0] - .2)
    assert abs(old_gap - .1) < 1e-12, old_gap
    result, receipt = refine_pair(pair, surface)
    assert len(result) == 4 and receipt['output_piece_count'] == 2
    assert np.allclose(receipt['parameter_knots'], [0, .5, 1], atol=1e-12)
    assert receipt['preflight_maximum_cap_gap_m'] < 2e-8
    assert np.all(result[:, 18] == 11) and np.all(result[:, 19] == 4000392)
    assert receipt['maximum_xy_rounding_drift_m'] == 0.
    print('PASS: original 100 mm chord gap becomes <0.00002 mm after the facet split.')


if __name__ == '__main__':
    test_straight_chord_over_two_facets()
