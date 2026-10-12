"""Tiny pure-NumPy AN triangle tests; never reads a scene or actual field."""
import unittest

import numpy as np

from sample_final_surface_an import (
    PartialSurfaceSampler, nested_axes, select_topmost, include_section_support,
    coverage_diagnostics, nearest_triangle_witness,
)


def bent_quad():
    # A-C is the actual diagonal. Its piecewise plane differs from bilinear.
    co = np.array([[0., 0., 0.], [.02, 0., 0.],
                   [.02, .02, .008], [0., .02, 0.]])
    return co, np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)


class ExactSurfaceTests(unittest.TestCase):
    def test_actual_nonplanar_triangles_not_bilinear(self):
        co, tri = bent_quad()
        query = np.array([[[.015, .005], [.005, .015]],
                          [[.01, .01], [.02, .02]]])
        actual = PartialSurfaceSampler(co, tri).height(query)
        expected = np.array([[.002, .002], [.004, .008]])
        np.testing.assert_allclose(actual, expected, rtol=0., atol=2e-18)
        bilinear = .008 * query[..., 0] * query[..., 1] / .02**2
        self.assertGreater(np.max(np.abs(actual - bilinear)), .001)
        self.assertEqual(actual.shape, query.shape[:-1])

    def test_topmost_triangle_wins_even_with_less_interior_hit(self):
        # The higher triangle contains the query only near its edge. Choosing
        # the most-interior triangle instead of the highest would return zero.
        co = np.array([[0., 0., 0.], [.04, 0., 0.], [0., .04, 0.],
                       [.009, .009, .006], [.03, .009, .006],
                       [.009, .03, .006]])
        tri = np.arange(6, dtype=np.int32).reshape(2, 3)
        query = np.array([[.01, .01], [.002, .002]])
        for ordered in (tri, tri[::-1], tri[:, ::-1]):
            np.testing.assert_allclose(
                PartialSurfaceSampler(co, ordered).height(query), [.006, 0.],
                rtol=0., atol=1e-18)

    def test_uncovered_triangle_bbox_and_outside_points_remain_nan(self):
        co, tri = bent_quad()
        sampler = PartialSurfaceSampler(co, tri[:1])
        q = np.array([[.005, .015], [-.01, .005], [3., 4.]])
        self.assertTrue(np.isnan(sampler.height(q)).all())
        self.assertTrue(np.isfinite(sampler.height([[.015, .005]])).all())
        self.assertEqual(sampler.height(np.empty((0, 2))).shape, (0,))

    def test_exact_vertices_shared_edges_and_query_chunking(self):
        co, tri = bent_quad()
        axis = np.linspace(0., .02, 9)
        xx, yy = np.meshgrid(axis, axis)
        q = np.stack((xx, yy), axis=-1)
        reference = PartialSurfaceSampler(co, tri).height(q)
        bounded = PartialSurfaceSampler(co, tri, max_query_products=3).height(q)
        np.testing.assert_array_equal(bounded, reference)
        np.testing.assert_allclose(reference, .008 * np.minimum(xx, yy) / .02,
                                   rtol=0., atol=2e-18)
        np.testing.assert_array_equal(
            PartialSurfaceSampler(co, tri).height(co[:, :2]), co[:, 2])

    def test_exact_left_edge_union_horizontal_and_sloped_edges(self):
        co = np.array([[0., 0., 0.], [.02, .02, 0.], [.04, 0., 0.],
                       [.06, 0., .1], [.08, .02, .1], [.10, 0., .1]])
        tri = np.arange(6, dtype=np.int32).reshape(2, 3)
        y = np.array([[0., .005, .01, .02], [-.001, .021, .015, 0.]])
        edge = PartialSurfaceSampler(co, tri).left_edge(y)
        np.testing.assert_allclose(edge[0], [0., .005, .01, .02], atol=1e-18)
        self.assertTrue(np.isnan(edge[1, :2]).all())
        np.testing.assert_allclose(edge[1, 2:], [.015, 0.], atol=1e-18)
        self.assertEqual(edge.shape, y.shape)

    def test_degenerate_triangles_omitted_without_mutating_sources(self):
        co, tri = bent_quad()
        tri = np.concatenate((tri, [[0, 0, 1]])).astype(np.int32)
        before_co, before_tri = co.copy(), tri.copy()
        q = np.array([[.003, .007], [.01, .01]])
        q_before = q.copy()
        sampler = PartialSurfaceSampler(co, tri)
        sampler.height(q)
        sampler.left_edge(q[:, 1])
        self.assertEqual(sampler.omitted_degenerate_triangles, 1)
        np.testing.assert_array_equal(co, before_co)
        np.testing.assert_array_equal(tri, before_tri)
        np.testing.assert_array_equal(q, q_before)

    def test_invalid_inputs_and_allocation_caps_fail(self):
        co, tri = bent_quad()
        cases = [dict(max_triangles=1), dict(max_bin_entries=1),
                 dict(cell_m=0.), dict(max_query_products=0)]
        for kw in cases:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                PartialSurfaceSampler(co, tri, **kw)
        for ids in (tri.astype(float), [[0, 1, 4]], [[0, 0, 1]]):
            with self.subTest(triangles=ids), self.assertRaises(ValueError):
                PartialSurfaceSampler(co, ids)
        bad = co.copy()
        bad[0, 0] = np.nan
        with self.assertRaises(ValueError):
            PartialSurfaceSampler(bad, tri)
        with self.assertRaises(ValueError):
            PartialSurfaceSampler(co, tri).height([[np.nan, 0.]])


class OwnershipAndAxesTests(unittest.TestCase):
    def test_strict_topmost_ownership_road_ties_and_missing_one_surface(self):
        ground = np.array([[.004, .006, np.nan], [.01, .002, .002]])
        road = np.array([[.005, .005, .003], [np.nan, .002, .002-1e-12]])
        kinds = np.array([[1, 2, 2], [1, 2, 1]], np.uint8)
        saved = [a.copy() for a in (ground, road, kinds)]
        z, pavement, owner = select_topmost(ground, road, kinds)
        np.testing.assert_array_equal(z, [[.005, .006, .003], [.01, .002, .002]])
        np.testing.assert_array_equal(pavement, [[True, False, True], [False, True, False]])
        np.testing.assert_array_equal(owner, [[1, 0, 2], [0, 2, 0]])
        self.assertEqual(owner.dtype, np.uint8)
        for original, before in zip((ground, road, kinds), saved):
            np.testing.assert_array_equal(original, before)

    def test_missing_all_surfaces_and_infinite_or_invalid_owners_fail(self):
        cases = [([np.nan], [np.nan], None), ([0.], [np.inf], None),
                 ([0., 1.], [1.], None), ([0.], [1.], [0]),
                 ([0.], [1.], [5]), ([0.], [1.], [1, 2])]
        for ground, road, kinds in cases:
            with self.subTest(ground=ground, road=road, kinds=kinds):
                with self.assertRaises(ValueError):
                    select_topmost(ground, road, kinds)

    def test_nested_axes_coincide_bitwise_and_keep_world_origin(self):
        bounds = (-3.8, -3.7, -.3, -.25)
        x, y = nested_axes(bounds, .00625)
        self.assertEqual((len(y), len(x)), (9, 17))
        self.assertEqual(x[0], bounds[0])
        self.assertEqual(y[0], bounds[2])
        for stride in (2,):
            coarse_x, coarse_y = nested_axes(bounds, .00625 * stride)
            np.testing.assert_array_equal(x[::stride], coarse_x)
            np.testing.assert_array_equal(y[::stride], coarse_y)
        # A second tiny domain permits all three production resolution strides.
        bounds = (-3.8, -3.7, -.3, -.2)
        x, y = nested_axes(bounds, .00625)
        x4, y4 = nested_axes(bounds, .025)
        np.testing.assert_array_equal(x[::4], x4)
        np.testing.assert_array_equal(y[::4], y4)
        np.testing.assert_allclose(np.diff(x), .00625, rtol=0., atol=5e-16)

    def test_nested_axes_reject_nonintegral_or_non_nested_bounds(self):
        cases = [((0., .025, 0., .025), 0.),
                 ((0., .025, 0., .025), np.inf),
                 ((0., .026, 0., .025), .00625),
                 ((0., .0375, 0., .025), .00625),
                 ((0., 0., 0., .025), .00625),
                 ((0., .025, 0., np.nan), .00625)]
        for bounds, spacing in cases:
            with self.subTest(bounds=bounds, spacing=spacing):
                with self.assertRaises(ValueError):
                    nested_axes(bounds, spacing)


class SectionSupportTests(unittest.TestCase):
    def test_actual_section_fills_interval_and_retains_substrate_ownership(self):
        # Actual inclined course spans a crown-to-bank XY interval; top-road
        # and ground objects have a genuine support gap there by themselves.
        co=np.array([[0.,0.,.004],[.01,0.,0.],[.01,.02,0.],[0.,.02,.004]])
        tri=np.array([[0,1,2],[0,2,3]])
        xy=np.array([[[.005,.01],[.02,.01],[.006,.01],[.008,.01]]])
        za=PartialSurfaceSampler(co,tri).height(xy)
        zg=np.array([[np.nan,np.nan,.005,np.nan]])
        zr=np.array([[np.nan,np.nan,np.nan,np.nan]])
        zs=np.array([[np.nan,np.nan,np.nan,.006]])
        kinds=np.ones(zg.shape,np.uint8)
        before=coverage_diagnostics(xy,zg,zr)
        soil,road,so,k=include_section_support(zg,zr,kinds,za,zs)
        after=coverage_diagnostics(xy,soil,road)
        self.assertEqual(before['missing_xy_count'],3)
        self.assertEqual(after['missing_xy_count'],1)
        self.assertEqual(after['missing_xy_bounds_m'],[.02,.02,.01,.01])
        # True unsupported sample stays missing; no false bridge is installed.
        with self.assertRaises(ValueError):select_topmost(soil,road,k,so)
        z,p,owner=select_topmost(soil[:,[0,2,3]],road[:,[0,2,3]],k[:,[0,2,3]],so[:,[0,2,3]])
        np.testing.assert_array_equal(owner,[[3,0,4]])
        np.testing.assert_array_equal(p,[[True,False,False]])
        np.testing.assert_allclose(z,[[.002,.005,.006]],rtol=0,atol=1e-18)
        self.assertTrue(np.isnan(zg[0,0]))

    def test_section_ties_keep_original_owner_and_invalid_soil_owner_rejected(self):
        zg=np.array([.002]);zr=np.array([.004]);kind=np.array([2],np.uint8)
        soil,road,so,k=include_section_support(zg,zr,kind,[.004],[.002])
        np.testing.assert_array_equal(k,[2]);np.testing.assert_array_equal(so,[0])
        self.assertEqual(select_topmost(soil,road,k,so)[2][0],2)
        with self.assertRaises(ValueError):select_topmost(soil,road,k,[3])

    def test_nearest_witness_diagnoses_geometry_without_filling(self):
        co,tri=bent_quad();sampler=PartialSurfaceSampler(co,tri)
        points=np.array([[.03,.01],[.015,.005]])
        result=nearest_triangle_witness(sampler,points)
        self.assertAlmostEqual(result[0]['distance_m'],.01)
        self.assertFalse(result[0]['exact_interior_hit'])
        self.assertTrue(result[1]['exact_interior_hit'])
        self.assertEqual(result[1]['distance_m'],0.)
        self.assertTrue(np.isnan(sampler.height(points[:1])).all())
        with self.assertRaises(ValueError):nearest_triangle_witness(sampler,np.zeros((17,2)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
