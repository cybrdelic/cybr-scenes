"""Pure CPU-only AL bank tests. No Blender, renders, or scene writes."""
import ast
from dataclasses import replace
from pathlib import Path
import unittest
import numpy as np
import contact_bank_continuity_al as al
from context_mesh_refine_ab import SourceSampler

ROOT = Path(__file__).resolve().parents[1]


def grid(x, y, z):
    xx, yy = np.meshgrid(x, y)
    co = np.c_[xx.ravel(), yy.ravel(), np.broadcast_to(z(xx, yy), xx.shape).ravel()]
    a = (np.arange(len(y)-1)[:, None]*len(x)+np.arange(len(x)-1)).ravel()
    tri = np.stack((np.c_[a, a+1, a+len(x)+1],
                    np.c_[a, a+len(x)+1, a+len(x)]), axis=1).reshape(-1, 3)
    return co, tri.astype(np.int32)


def fixture():
    x = np.linspace(-4., -3.25, 16); y = np.linspace(1.8, 8.4, 133)
    xx, yy = np.meshgrid(x, y)
    z = .07+.01*yy+.03*(xx+3.2)
    fields = dict(x_m=x, y_m=y, foundation_z_m=z,
        sediment_delta_m=np.zeros_like(z), flow_strength=np.full_like(z, .2),
        retained_deposit_by_class_m=np.zeros(z.shape+(3,)))
    road = grid(np.linspace(-3.2, -2.9, 7), y,
                lambda x, y: .08+.01*y+.02*(x+3.2))
    # Boundary extends 4 cm onto pavement at the inherited +0.2 mm datum.
    ground = grid(np.linspace(-3.9, -3.16, 38), y,
                  lambda x, y: .0802+.01*y+.02*(x+3.2))
    return *ground, *road, fields


class BankContinuityTests(unittest.TestCase):
    def test_gate_exact_zero_and_smooth_bounded_onset(self):
        y = np.array([1., 1.999999, 2., 2.05, 2.1, 2.15, 2.2, 7.9, 8.05, 8.2, 9.])
        g = al.bank_gate(np.c_[np.full(len(y), -3.2), y])
        np.testing.assert_array_equal(g[:3], 0.)
        np.testing.assert_array_equal(g[-2:], 0.)
        self.assertTrue(np.all(np.diff(g[2:7]) > 0))
        self.assertAlmostEqual(g[4], .5)
        self.assertAlmostEqual(g[8], .5)
        np.testing.assert_array_equal(al.bank_gate([[-3.76, 4.], [-3.75, 4.], [-3.0, 4.]]), 0.)

    def test_plan_immutable_xy_and_existing_topology(self):
        args = fixture(); saved = [a.copy() for a in args[:4]]
        fsave = {k: v.copy() for k, v in args[4].items()}
        p = al.plan_bank(*args)
        self.assertGreater(p.report['changed_vertices'], 100)
        np.testing.assert_array_equal(p.before[:, :2], p.after[:, :2])
        for a, b in zip(args[:4], saved):
            np.testing.assert_array_equal(a, b)
        for k in fsave:
            np.testing.assert_array_equal(args[4][k], fsave[k])
        self.assertFalse(p.report['sediment_mass_conservation_claim'])
        self.assertEqual(p.report['new_ground_sheets'], 0)

    def test_triangles_cannot_leak_into_ac_or_outside_domain(self):
        co, tri, *rest = fixture(); p = al.plan_bank(co, tri, *rest)
        a, b, c, d = p.spec.bounds; q = co[tri, :2]
        outside = ((q[:, :, 0] < a) | (q[:, :, 0] > b) |
                   (q[:, :, 1] < c) | (q[:, :, 1] > d)).any(axis=1)
        np.testing.assert_array_equal(p.delta_m[tri[outside]], 0.)
        np.testing.assert_array_equal(p.after[co[:, 1] <= 2.], co[co[:, 1] <= 2.])

    def test_under_pavement_row_buried_on_full_strength_span(self):
        args = fixture(); p = al.plan_bank(*args)
        q = p.after; core = (q[:, 0] >= -3.2) & (q[:, 1] >= 2.3) & (q[:, 1] <= 7.8)
        top = .08+.01*q[core, 1]+.02*(q[core, 0]+3.2)
        self.assertGreater(core.sum(), 100)
        self.assertTrue(np.all(top-q[core, 2] >= .009999999))
        self.assertLessEqual(np.max(np.abs(p.delta_m)), .03)

    def test_exact_triangle_grain_shift_not_nearest_or_loose_burial(self):
        args = fixture(); p = al.plan_bank(*args)
        q = np.array([[-3.52, 3.33], [-3.42, 4.01], [-3.19, 5.25]])
        final = SourceSampler(p.after, p.local_triangles, np.arange(len(p.local_triangles)))
        want = final.height(q)-p.sampler.height(q)
        np.testing.assert_allclose(p.height_shift(q), want, atol=5e-17, rtol=0)
        self.assertTrue(np.isnan(p.height_shift([[-3., 3.]]))[0])

    def test_retained_deposition_not_double_added(self):
        args = fixture(); p1 = al.plan_bank(*args)
        args[-1]['retained_deposit_by_class_m'][..., 1] = .003
        p2 = al.plan_bank(*args)
        np.testing.assert_array_equal(p1.after, p2.after)
        args[-1]['sediment_delta_m'][:] = .001
        p3 = al.plan_bank(*args)
        row = (p1.before[:, 0] == -3.2) & (p1.before[:, 1] > 2.3) & (p1.before[:, 1] < 7.8)
        np.testing.assert_allclose(p3.after[row, 2]-p2.after[row, 2], .001, atol=1e-16)

    def test_source_drives_nonperiodic_bank_and_float32_storage(self):
        args = list(fixture()); args[0] = args[0].astype('f4')
        args[-1]['sediment_delta_m'][:, :] = -.004*np.maximum(1-abs(args[-1]['y_m'][:, None]-4.)/.8, 0.)
        p = al.plan_bank(*args)
        self.assertEqual(p.after.dtype, np.float32)
        np.testing.assert_array_equal(p.delta_m, p.after[:, 2].astype(float)-p.before[:, 2])
        self.assertFalse(p.report['periodic_or_random_edge_pattern'])

    def test_limits_fail_closed(self):
        for s in (replace(al.BankSpec(), max_movement_m=.031),
                  replace(al.BankSpec(), onset_m=.05), replace(al.BankSpec(), y_min_m=1.9),
                  replace(al.BankSpec(), max_local_triangles=400000)):
            with self.assertRaises(ValueError):
                s.validate()
        args = fixture(); args[-1]['foundation_z_m'][:] = np.nan
        with self.assertRaises(ValueError):
            al.plan_bank(*args)

    def test_adapter_preserves_normals_before_geometry_update(self):
        tree = ast.parse((ROOT/'src/contact_bank_continuity_al.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'apply')
        text = ast.get_source_segment((ROOT/'src/contact_bank_continuity_al.py').read_text(), fn)
        self.assertLess(text.index("normals = _read(mesh.corner_normals"), text.index("mesh.vertices.foreach_set"))
        self.assertIn('update_normals', text)
        for prohibited in ('open_mainfile', 'save_as_mainfile', 'bpy.ops.render'):
            self.assertNotIn(prohibited, text)

    def test_preserved_detail_normals_rotate_by_actual_plane_change(self):
        from types import SimpleNamespace
        from terrain_normal_transfer_ah import update_normals
        class Loops:
            def __len__(self):
                return 3
            def foreach_get(self, name, output):
                self.assert_name = name
                output[:] = [0, 1, 2]
        class Mesh:
            loops = Loops()
            def normals_split_custom_set(self, values):
                self.normals = np.asarray(values).copy()
        mesh = Mesh()
        before = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        after = before.copy(); after[:, 2] = .05*after[:, 0]
        preserved = np.tile([0., .6, .8], (3, 1))
        report = update_normals(mesh, SimpleNamespace(triangles=np.array([[0, 1, 2]])),
                                before, after, after[:, 2]-before[:, 2], preserved)
        n = np.sqrt(1+.05**2)
        np.testing.assert_allclose(mesh.normals, np.tile([-.04/n, .6, .8/n], (3, 1)), atol=1e-15)
        np.testing.assert_array_equal(preserved, np.tile([0., .6, .8], (3, 1)))
        self.assertEqual(report['changed_corner_normals'], 3)

    def test_clearance_audit_detects_triangle_interiors(self):
        args = fixture(); p = al.plan_bank(*args)
        self.assertGreater(p.report['clearance']['sampled_full_strength_under_pavement_points'], 100)
        self.assertEqual(p.report['clearance']['sampled_penetrations'], 0)
        _, sampler = al.actual_road_profile(args[2], args[3])
        bad = p.after.copy(); bad[:, 2] += .020
        report = al.audit_triangle_clearance(bad, p.local_triangles, sampler, p.profile)
        self.assertGreater(report['sampled_penetrations'], 100)

    def test_actual_cached_road_and_ah_bank_qualify(self):
        roadpath = ROOT/'receipts/aa_actual_road_topology.npz'
        fields_path = ROOT/'captures/ak_substrate_units_context_preview/AH_FIELDS.npz'
        source_path = ROOT/'audits/far_edge_causal_20261010/exact_z_edge_coordinates.npz'
        if not all(p.exists() for p in (roadpath, fields_path, source_path)):
            self.skipTest('Actual read-only caches not present')
        with np.load(roadpath, allow_pickle=False) as f:
            edge, sampler = al.actual_road_profile(f['vertexco'], f['loop_triangles'])
        with np.load(fields_path, allow_pickle=False) as f:
            profile = al.support_from_fields(dict(f), edge)
        with np.load(source_path, allow_pickle=False) as f:
            co = f['ground_co']; co = co[(co[:, 1] >= 2.) & (co[:, 1] <= 8.2)]
        delta, report = al.bank_vertex_delta(co, profile, sampler)
        self.assertEqual(report['movement_cap_clipped_vertices'], 0)
        self.assertLess(np.max(abs(delta)), .03)
        self.assertGreater(np.count_nonzero(delta), 6000)
        self.assertLess(np.max(abs(profile.foundation_grade)), .081)
        ex = np.interp(co[:, 1], profile.y_m, profile.base_edge_xyz[:, 0])
        core = ((co[:, 0] >= ex) & (co[:, 1] >= 2.2) & (co[:, 1] <= 7.9))
        road_z = sampler.sample(sampler.co[:, 2], co[core, :2])
        clearance = road_z-(co[core, 2]+delta[core])
        self.assertTrue(np.all(clearance >= .0008-1e-12))
        print('AL_ACTUAL_CACHE_PROOF', dict(vertices=len(co), core_buried_vertices=int(core.sum()),
            final_clearance_min_m=float(clearance.min()), **report))


if __name__ == '__main__':
    unittest.main(verbosity=2)
