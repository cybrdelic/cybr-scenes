"""Pure, bounded numerical checks. Does not load Blender or write scene files."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np

SCRIPT = Path(__file__).with_name('prepare_physical_lenses.py')
spec = importlib.util.spec_from_file_location('physical_lenses', SCRIPT)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class MockRNA(SimpleNamespace):
    def __str__(self):
        return f'<bpy_struct, {self.bl_rna.identifier} at {id(self):#x}>'


class FingerprintTests(unittest.TestCase):
    @staticmethod
    def ramp():
        return MockRNA(bl_rna=SimpleNamespace(identifier='ColorRamp', base=None),
                       color_mode='RGB', interpolation='LINEAR', hue_interpolation='NEAR',
                       elements=[SimpleNamespace(position=0., color=[.2, .3, .4, 1.]),
                                 SimpleNamespace(position=1., color=[.7, .8, .9, 1.])])

    @staticmethod
    def tree(value):
        node = SimpleNamespace(name='Ramp', bl_idname='ShaderNodeValToRGB', color_ramp=value,
                               inputs=[], outputs=[], bl_rna=SimpleNamespace(properties=[
                                   SimpleNamespace(identifier='color_ramp', type='POINTER')]))
        return SimpleNamespace(nodes=[node], links=[])

    def test_color_ramp_hash_is_content_based_not_pointer_based(self):
        a, b = self.ramp(), self.ramp()
        self.assertIsNot(a, b)
        self.assertNotEqual(str(a), str(b))
        self.assertEqual(u.graph_signature(self.tree(a)), u.graph_signature(self.tree(b)))
        for change in ('position', 'color', 'interpolation', 'hue_interpolation', 'color_mode'):
            b = self.ramp()
            if change == 'position':
                b.elements[0].position = .1
            elif change == 'color':
                b.elements[0].color[2] = .5
            else:
                setattr(b, change, 'CHANGED')
            self.assertNotEqual(u.graph_signature(self.tree(a)), u.graph_signature(self.tree(b)), change)

    def test_curve_mapping_values_and_handles_are_protected(self):
        def curve():
            return SimpleNamespace(bl_rna=SimpleNamespace(identifier='CurveMapping', base=None),
                                   black_level=[0., 0., 0.], white_level=[1., 1., 1.],
                                   clip_min_x=0., clip_min_y=0., clip_max_x=1., clip_max_y=1.,
                                   use_clip=True, extend='EXTRAPOLATED', tone='STANDARD',
                                   curves=[SimpleNamespace(points=[
                                       SimpleNamespace(location=[0., 0.], handle_type='AUTO')])])
        original = u.stable_value(curve())
        self.assertEqual(original, u.stable_value(curve()))
        for change in ('location', 'handle_type', 'tone', 'extend', 'white_level', 'clip_max_x', 'use_clip'):
            value = curve()
            if change == 'location':
                value.curves[0].points[0].location[1] = .1
            elif change == 'handle_type':
                value.curves[0].points[0].handle_type = 'VECTOR'
            elif change == 'white_level':
                value.white_level[0] = .9
            else:
                setattr(value, change, False if change == 'use_clip' else 2. if change == 'clip_max_x' else 'CHANGED')
            self.assertNotEqual(original, u.stable_value(value), change)

    def test_id_reference_uses_rna_ancestry_and_stable_name(self):
        value = SimpleNamespace(name='Approved source', bl_rna=SimpleNamespace(
            identifier='Material', base=SimpleNamespace(identifier='ID', base=None)))
        self.assertEqual(u.stable_value(value), ('ID', 'Approved source'))

    def test_image_user_frame_and_image_selection_are_protected(self):
        fields = dict(frame_current=1, frame_duration=1, frame_offset=0, frame_start=1,
                      multilayer_layer=0, multilayer_pass=0, multilayer_view=0, tile=1001,
                      use_auto_refresh=False, use_cyclic=False)
        def image_user():
            return MockRNA(bl_rna=SimpleNamespace(identifier='ImageUser', base=None), **fields)
        original = u.graph_signature(self.tree(image_user()))
        self.assertEqual(original, u.graph_signature(self.tree(image_user())))
        for name, value in fields.items():
            changed = image_user()
            setattr(changed, name, not value if isinstance(value, bool) else value+1)
            self.assertNotEqual(original, u.graph_signature(self.tree(changed)), name)

    def test_texture_and_color_mapping_include_vectors_enums_and_nested_ramp(self):
        def mapping(kind, properties):
            return SimpleNamespace(bl_rna=SimpleNamespace(identifier=kind, base=None, properties=[
                SimpleNamespace(identifier=name, type=ptype) for name, ptype, _ in properties]),
                **{name: value for name, _, value in properties})
        texture = mapping('TexMapping', [('translation', 'FLOAT', [0., 0., 0.]),
                                         ('vector_type', 'ENUM', 'POINT'), ('use_min', 'BOOLEAN', False)])
        original = u.stable_value(texture)
        self.assertEqual(original['translation'], [0., 0., 0.])
        texture.translation[1] = .01
        self.assertNotEqual(original, u.stable_value(texture))
        color = mapping('ColorMapping', [('blend_color', 'FLOAT', [.5, .5, .5]),
                                        ('blend_type', 'ENUM', 'MIX'), ('brightness', 'FLOAT', 1.),
                                        ('color_ramp', 'POINTER', self.ramp())])
        original = u.graph_signature(self.tree(color))
        color.color_ramp.elements[1].color[0] = .6
        self.assertNotEqual(original, u.graph_signature(self.tree(color)))
        unknown = mapping('TexMapping', [('unknown', 'POINTER', object())])
        with self.assertRaisesRegex(ValueError, 'Unsupported fingerprint property: TexMapping.unknown/POINTER'):
            u.stable_value(unknown)

    def test_unknown_rna_pointer_is_not_named_or_stringified_or_skipped(self):
        value = SimpleNamespace(name='Not an ID', bl_rna=SimpleNamespace(identifier='UnknownMapping', base=None))
        with self.assertRaisesRegex(ValueError, 'Unsupported non-ID RNA pointer.*UnknownMapping'):
            u.graph_signature(self.tree(value))
        with self.assertRaisesRegex(ValueError, 'Unsupported fingerprint value'):
            u.stable_value(object())

    def test_socket_vector_values_remain_json_safe(self):
        self.assertEqual(u.stable_value((1., (.2, .3), None)), [1., [.2, .3], None])


class PhysicalLensesTests(unittest.TestCase):
    def test_exact_compact_support_and_bare_gaps(self):
        x, y = np.meshgrid(np.linspace(-4.9, -3.4, 250), np.linspace(.3, 4.3, 420))
        xyz = np.stack((x, y, np.zeros_like(x)), -1)
        dz, deps, cuts, lag = u.displacement(xyz)
        outside = ~u.in_bounds(xyz[..., :2])
        self.assertTrue(np.all(dz[outside] == 0))
        self.assertTrue(np.all(lag[outside] == 0))
        domain = u.in_bounds(xyz[..., :2])
        self.assertGreater(np.mean(dz[domain] == 0), .55)
        gap = (y > 2.22) & (y < 2.37)
        self.assertTrue(np.all(np.maximum.reduce(deps)[gap] == 0))
        self.assertGreater(np.count_nonzero(dz[gap] < 0), 0)
        self.assertEqual(len(deps), 2)
        self.assertEqual(len(cuts), 2)
        self.assertLessEqual(dz.max(), .008)
        self.assertGreaterEqual(dz.min(), -.010)
        self.assertLess(dz.min(), -.008)
        for field in deps:
            self.assertGreater(np.count_nonzero(field == 1), 80)
            support = field > 0
            width, length = np.ptp(x[support]), np.ptp(y[support])
            self.assertGreater(width, .5)
            self.assertLess(width, 1.2)
            self.assertGreater(length, .5)
            self.assertLess(length, 1.2)

    def test_plane_plateau_is_resolved_with_bounded_thickness(self):
        x, y = np.meshgrid(np.arange(-4.7, -3.7, .023), np.arange(.6, 4., .025))
        z = .008*y-.029*(np.abs(x)-3.2)+.035+.0003*np.sin(11*x+8*y)
        xyz = np.stack((x, y, z), -1).reshape(-1, 3)
        planes = u.fit_plateaus(xyz)
        dz, deps, _, _ = u.displacement(xyz, planes)
        for field, plane, lens in zip(deps, planes, u.LENSES):
            core = field == 1
            top = xyz[core, :2]@plane[:2]+plane[2]+lens[5]
            np.testing.assert_allclose(xyz[core, 2]+dz[core], top, atol=2e-15)
            self.assertTrue(np.all(dz[core] >= .004))
            self.assertTrue(np.all(dz[core] <= .008))

    def test_old_grains_settle_and_bury_without_shape_deformation(self):
        delta = np.array([-.009, -.003, 0., .004, .008])
        shift = u.loose_shift(delta)
        np.testing.assert_allclose(shift, [-.009, -.003, 0, .0006, .0012])
        body = np.array([[0, 0, -.001], [.005, 0, .001], [0, .004, .003]])
        shifted = body+np.array([0, 0, shift[-1]])
        np.testing.assert_allclose(shifted[:, None]-shifted[None], body[:, None]-body[None], atol=1e-15)
        self.assertAlmostEqual(delta[-1]-shift[-1], .0068)

    def test_contact_uses_triangle_and_diagonal_not_bilinear_or_formula(self):
        vertices = [[0, 0, 0], [1, 0, 0], [1, 1, .1], [0, 1, 0]]
        diagonal_ac = u.TrianglePatch(vertices, [[0, 1, 2], [0, 2, 3]], cell=1.)
        diagonal_bd = u.TrianglePatch(vertices, [[0, 1, 3], [1, 2, 3]], cell=1.)
        points = np.array([[.25, .75], [.75, .25], [.5, .5], [0, 0], [1, 1]])
        np.testing.assert_allclose(diagonal_ac.height(points), [.025, .025, .05, 0, .1], atol=1e-14)
        np.testing.assert_allclose(diagonal_bd.height(points), [0, 0, 0, 0, .1], atol=1e-14)
        self.assertGreater(abs(diagonal_ac.height([.5, .5])-diagonal_bd.height([.5, .5])), .049)
        with self.assertRaises(ValueError):
            diagonal_ac.height([1.01, .5])

    def test_zero_footprint_triangles_do_not_invent_or_remove_surface(self):
        vertices = [[0, 0, 0], [1, 0, 1], [1, 1, 2], [0, 1, 1], [0, 1, 1]]
        patch = u.TrianglePatch(vertices, [[0, 1, 2], [0, 2, 3], [0, 3, 4]], cell=1.)
        self.assertEqual(patch.discarded_zero_footprint_triangles, 1)
        np.testing.assert_allclose(patch.height([[.25, .4], [.7, .9]]), [.65, 1.6])
        with self.assertRaises(ValueError):
            patch.height([[1.1, .5]])

    def test_triangle_patch_matches_explicit_plane_at_many_points(self):
        x, y = np.meshgrid(np.arange(0, .301, .025), np.arange(0, .451, .03))
        z = -.08*x+.015*y+.25
        vertices = np.stack([x, y, z], -1).reshape(-1, 3)
        nx = x.shape[1]
        q = (np.arange(x.shape[0]-1)[:, None]*nx+np.arange(nx-1)[None]).ravel()
        faces = np.r_[np.stack([q, q+1, q+nx+1], -1), np.stack([q, q+nx+1, q+nx], -1)]
        patch = u.TrianglePatch(vertices, faces)
        rng = np.random.default_rng(1701)
        p = rng.uniform([0, 0], [.30, .45], (3500, 2))
        np.testing.assert_allclose(patch.height(p), -.08*p[:, 0]+.015*p[:, 1]+.25, atol=2e-15)

    def test_new_rigid_grit_crosses_actual_surface(self):
        patch = u.TrianglePatch([[0, 0, 0], [.05, 0, .002], [0, .05, -.001]], [[0, 1, 2]])
        v = np.array([[.011, .011, 0], [.015, .011, .001], [.011, .015, .002]])
        surface = patch.height(v[:, :2])
        thickness = np.ptp(v[:, 2]); burial = .45
        v[:, 2] += np.max(surface-v[:, 2])-burial*thickness
        contact = v[:, 2]-patch.height(v[:, :2])
        self.assertAlmostEqual(contact.min(), -burial*thickness)
        self.assertGreater(contact.max(), .0001)

    def test_disk_nonoverlap_across_hash_bins_and_large_source_clasts(self):
        disks = u.DiskIndex(cell=.025)
        disks.add([-.010, .025], .006)
        self.assertFalse(disks.clear([-.002, .025], .003))
        self.assertTrue(disks.clear([.002, .025], .003))
        disks.add([.2, .2], .05)
        self.assertFalse(disks.clear([.248, .2], .002))
        self.assertTrue(disks.clear([.253, .2], .002))

    def test_lag_is_sparse_bounded_and_candidates_are_not_a_blanket(self):
        rng = np.random.default_rng(u.SEED)
        p = rng.uniform([-4.7, .6], [-3.7, 4.], (28000, 2))
        deps, _, lag = u.profile_fields(p[:, 0], p[:, 1])
        self.assertLess(np.mean(lag > .08), .10)
        keep = (lag > .08) & (rng.random(len(lag)) < .40*lag**1.45*(1-.8*np.maximum.reduce(deps)))
        self.assertGreater(keep.sum(), 200)
        self.assertLess(keep.sum(), 600)
        self.assertTrue(np.all(lag[keep] > .08))


if __name__ == '__main__':
    unittest.main()
