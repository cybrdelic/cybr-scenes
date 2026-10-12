"""AI CPU1/source-only tests. No Blender, rendering, scene loads, or remote I/O.

Optional direct execution writes only receipts/ai_edge_support_tests.json.
Actual-source numerical qualification is separate from visual acceptance.
"""
import ast
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import unittest

import numpy as np
import runoff_edge_support_ai as ai

ROOT = Path(__file__).resolve().parents[1]
PROOF = {}


def fixture():
    x = np.linspace(-4., -3.25, 16)
    y = np.linspace(-.5, 2.5, 61)
    xx, yy = np.meshgrid(x, y)
    z = .075+.01*yy+.025*(xx+3.2)
    ys = np.linspace(0, 2, 201)
    xe = -3.2+.004*ys
    base = np.c_[xe, ys, .080+.01*ys+.025*(xe+3.2)]
    return dict(x_m=x, y_m=y, foundation_z_m=z,
                sediment_delta_m=np.zeros_like(z),
                retained_deposit_by_class_m=np.zeros(z.shape+(3,)),
                flow_strength=np.full_like(z, .2), base_edge_xyz=base)


def actual_base_edge():
    from metric_edge_strip_aa import TriangleSampler
    with np.load(ROOT/'receipts/aa_actual_road_topology.npz', allow_pickle=False) as f:
        co = f['vertexco']; tri = f['loop_triangles']
    p = co[tri, :2]
    near = ((p[:, :, 0].min(1) < -3.) & (p[:, :, 1].max(1) > -.04)
            & (p[:, :, 1].min(1) < 2.04))
    tri = tri[near]; p = co[tri, :2]
    u = p[:, 1]-p[:, 0]; v = p[:, 2]-p[:, 0]
    tri = tri[np.abs(u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0]) > 1e-13]
    sampler = TriangleSampler(co, tri)
    y = np.linspace(0, 2, 1001)
    xy = np.c_[sampler.left_edge(y), y]
    return np.c_[xy, sampler.sample(co[:, 2], xy)]


class EdgeSupportTests(unittest.TestCase):
    def test_01_planar_source_stays_planar_and_has_no_sectors(self):
        p = ai.build_edge_support(**fixture())
        got = p.sample(np.linspace(0, 2, 8001))
        np.testing.assert_allclose(got['exposure_m'], .005, atol=1e-16, rtol=0)
        np.testing.assert_array_equal(got['structural_loss_m'], 0.)
        np.testing.assert_array_equal(got['sector_id'], 0)
        self.assertFalse(p.report['authored_exposure_sectors'])
        self.assertFalse(p.report['periodic_or_random_displacement'])

    def test_02_deterministic_and_input_immutable(self):
        f = fixture(); before = {k: v.copy() for k, v in f.items()}
        a = ai.build_edge_support(**f); b = ai.build_edge_support(**f)
        np.testing.assert_array_equal(a.bank_top_z_m, b.bank_top_z_m)
        for key in before:
            np.testing.assert_array_equal(f[key], before[key])
        with self.assertRaises(ValueError):
            a.exposure_m[0] = 0

    def test_03_erosion_uses_actual_source_offset_at_unchanged_scale(self):
        f = fixture(); source = np.maximum(1-np.abs(f['y_m']-.65)/.40, 0.)
        f['sediment_delta_m'][:] = -.002*source[:, None]
        p = ai.build_edge_support(**f)
        expected = .005+.002*np.interp(p.y_m, f['y_m'], source)
        np.testing.assert_allclose(p.exposure_m, expected, atol=1e-16, rtol=0)
        self.assertAlmostEqual(float(p.sample(.65)['exposure_m']), .007)

    def test_04_retained_deposition_is_counted_exactly_once(self):
        f = fixture()
        f['sediment_delta_m'][:] = .001
        f['retained_deposit_by_class_m'][..., 1] = .001
        p = ai.build_edge_support(**f)
        np.testing.assert_allclose(p.exposure_m, .004, atol=1e-16, rtol=0)
        np.testing.assert_allclose(p.anchor_retained_deposit_m, .001, atol=1e-18, rtol=0)
        self.assertFalse(p.report['modeled_edge_deposition'])
        self.assertFalse(p.report['conserves_or_introduces_sediment_mass'])

    def test_05_reworked_retained_stock_is_not_added_to_net_height(self):
        f = fixture(); f['retained_deposit_by_class_m'][..., 0] = .003
        p = ai.build_edge_support(**f)
        np.testing.assert_allclose(p.exposure_m, .005, atol=1e-16, rtol=0)

    def test_06_flow_diagnostic_cannot_invent_excavation(self):
        f = fixture(); a = ai.build_edge_support(**f)
        f['flow_strength'][:] = 1.
        b = ai.build_edge_support(**f)
        np.testing.assert_array_equal(a.exposure_m, b.exposure_m)
        self.assertEqual(float(b.anchor_flow_strength.max()), 1.)

    def test_07_road_knots_and_source_breakpoints_are_preserved(self):
        f = fixture(); p = ai.build_edge_support(**f)
        for value in f['base_edge_xyz'][:, 1]:
            self.assertIn(value, p.y_m)
        for value in f['y_m'][(f['y_m'] >= 0) & (f['y_m'] <= 2)]:
            self.assertLess(float(np.min(np.abs(value-p.y_m))), 1e-12)
        self.assertGreater(float(np.diff(p.y_m).min()), .0099)
        np.testing.assert_allclose(p.sample(p.y_m)['bank_top_z_m'], p.bank_top_z_m, atol=0, rtol=0)

    def test_08_bank_clearance_and_existing_depth_cap_are_explicit(self):
        f = fixture(); f['base_edge_xyz'][:, 2] += .04
        p = ai.build_edge_support(**f)
        np.testing.assert_array_equal(p.exposure_m, .032)
        self.assertEqual(p.report['depth_constrained_knots'], len(p.y_m))
        self.assertGreater(p.report['maximum_bank_constraint_adjustment_m'], .01)
        f = fixture(); f['base_edge_xyz'][:, 2] -= .01
        p = ai.build_edge_support(**f)
        np.testing.assert_array_equal(p.exposure_m, .0008)
        self.assertEqual(p.report['clearance_constrained_knots'], len(p.y_m))

    def test_09_missing_source_coverage_never_clamps_silently(self):
        f = fixture(); f['x_m'] += .35
        with self.assertRaisesRegex(ValueError, 'coverage'):
            ai.build_edge_support(**f)
        f = fixture()
        f['base_edge_xyz'][:, 1] += 3.
        with self.assertRaisesRegex(ValueError, 'Y extent'):
            ai.build_edge_support(**f)
        p = ai.build_edge_support(**fixture())
        for q in (-1e-12, 2.0000001, np.nan):
            with self.assertRaisesRegex(ValueError, 'outside'):
                p.sample(q)

    def test_10_rejects_bad_fields_and_false_deposition(self):
        for key, value in [('foundation_z_m', np.nan), ('sediment_delta_m', .001),
                           ('retained_deposit_by_class_m', -.001), ('flow_strength', 1.01)]:
            f = fixture(); f[key].flat[0] = value
            with self.assertRaises(ValueError):
                ai.build_edge_support(**f)
        f = fixture(); f['sediment_delta_m'].flat[0] = -.019
        with self.assertRaisesRegex(ValueError, 'metric bound'):
            ai.build_edge_support(**f)
        f = fixture(); f['x_m'][1] += .001
        with self.assertRaisesRegex(ValueError, 'uniformly'):
            ai.build_edge_support(**f)

    def test_11_rejects_excess_grade_distance_and_contact_contamination(self):
        f = fixture(); f['foundation_z_m'] *= 10.
        with self.assertRaisesRegex(ValueError, 'too steep'):
            ai.build_edge_support(**f)
        f = fixture(); f['base_edge_xyz'][:, 0] += 1.
        with self.assertRaisesRegex(ValueError, 'bounded'):
            ai.build_edge_support(**f)
        for s in (replace(ai.EdgeSupportSpec(), max_exposure_m=.033),
                  replace(ai.EdgeSupportSpec(), inner_anchor_x_m=-3.42),
                  replace(ai.EdgeSupportSpec(), max_grid_samples=8),
                  replace(ai.EdgeSupportSpec(), max_continuation_m=.8)):
            with self.assertRaises(ValueError):
                ai.build_edge_support(**fixture(), spec=s)

    def test_12_vertical_datum_invariance_and_shorter_crop_consistency(self):
        f = fixture(); a = ai.build_edge_support(**f)
        g = {k: v.copy() for k, v in f.items()}
        g['foundation_z_m'] += 20.; g['base_edge_xyz'][:, 2] += 20.
        b = ai.build_edge_support(**g)
        np.testing.assert_allclose(a.exposure_m, b.exposure_m, atol=2e-14, rtol=0)
        f['base_edge_xyz'] = f['base_edge_xyz'][40:151]
        c = ai.build_edge_support(**f)
        np.testing.assert_allclose(c.exposure_m, a.sample(c.y_m)['exposure_m'], atol=4e-17, rtol=0)

    def test_13_existing_ac_top_and_contact_seams_remain_exact(self):
        import pavement_contact_ac as ac
        p = ai.build_edge_support(**fixture()); base = p.base_edge_xyz
        top = base.copy()
        top[:, 0] += .005*(1+np.sin(top[:, 1]*181))
        top[:, 2] += .0004*np.cos(top[:, 1]*203)
        spec = ac.ContactSpec(sectors=(), support_profile=p)
        section = ac.build_section(top, spec, base_edge_xyz=base)
        np.testing.assert_array_equal(section.wall_vertices[section.top_vertex_ids], top)
        np.testing.assert_allclose(section.wall_vertices[section.contact_vertex_ids],
                                   section.ground_contact, atol=1e-14, rtol=0)
        np.testing.assert_allclose(section.ground_contact[:, 2], p.bank_top_z_m, atol=3e-17, rtol=0)
        self.assertTrue(np.all(np.diff(section.layer_depth, axis=1) > 0))
        self.assertFalse(section.report['crown_lateral_microgeometry_extruded_through_course'])
        PROOF['ac_seam'] = dict(section.report,
            runtime_profile_seam='Actual explicit optional ContactSpec.support_profile; no module patching')

    def test_14_actual_ah_fields_and_road_have_shallow_bounded_support(self):
        path = ROOT/'captures/ah_d_integrated_bank_context_preview/AH_FIELDS.npz'
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with np.load(path, allow_pickle=False) as f:
            args = {k: f[k] for k in ('x_m', 'y_m', 'foundation_z_m', 'sediment_delta_m',
                                      'retained_deposit_by_class_m', 'flow_strength')}
        p = ai.build_edge_support(**args, base_edge_xyz=actual_base_edge())
        self.assertLess(float(p.exposure_m.max()), .014)
        self.assertGreater(float(p.exposure_m.min()), .0008)
        self.assertEqual(p.report['depth_constrained_knots'], 0)
        self.assertEqual(p.report['clearance_constrained_knots'], 0)
        self.assertGreater(p.report['distance_beyond_AH_grid_range_m'][0], 0)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        PROOF['actual_AH'] = dict(p.report, source_field_sha256=before,
            source_road_topology_sha256=hashlib.sha256(
                (ROOT/'receipts/aa_actual_road_topology.npz').read_bytes()).hexdigest(),
            fields_and_road_source_unchanged=True, visual_acceptance=False)

    def test_15_pure_helper_has_no_scene_or_file_side_effects(self):
        self.assertNotIn('bpy', sys.modules)
        tree = ast.parse((ROOT/'src/runoff_edge_support_ai.py').read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        self.assertEqual(set(imports), {'__future__', 'dataclasses', 'numpy'})
        names = [n.func.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertFalse(set(names) & {'render', 'save_as_mainfile', 'open_mainfile', 'save',
                                     'savez', 'savez_compressed', 'write_text', 'Popen', 'run'})


if __name__ == '__main__':
    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EdgeSupportTests))
    report = dict(passed=result.wasSuccessful(), tests_run=result.testsRun,
        failures=len(result.failures), errors=len(result.errors),
        elapsed_seconds=time.monotonic()-start,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        thread_environment={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS')},
        blender_executed=False, rendered=False, proof=PROOF)
    (ROOT/'receipts/ai_edge_support_tests.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'proof'}, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
