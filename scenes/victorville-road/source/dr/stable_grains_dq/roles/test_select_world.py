"""Small read-only view-consumer audit, no world build or Blender (<=1,200 points)."""
from pathlib import Path
from types import SimpleNamespace
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import math
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
prior_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    import select_world as view
    from context_mesh_refine_ab import SourceSampler
finally:
    sys.dont_write_bytecode = prior_bytecode

import transported_grain_exposure_dq as role
from build_world_roles import set_serial_bits


class Projection:
    def __init__(self, inverse=None, near=.01, f=(230., 190.), offset=(170., 110.)):
        self.inverse = np.eye(4) if inverse is None else inverse
        self.width, self.height, self.near = 340, 220, near
        self.f, self.offset = np.array(f), np.array(offset)

    def project(self, world):
        q = np.asarray(world) @ self.inverse[:3, :3].T + self.inverse[:3, 3]
        depth = -q[:, 2]
        return q[:, :2] / np.maximum(depth, self.near)[:, None] * self.f + self.offset, depth

    def visible(self, world, margin=0):
        uv, depth = self.project(world)
        return ((depth > self.near) & (uv[:, 0] >= -margin) & (uv[:, 0] <= self.width + margin)
                & (uv[:, 1] >= -margin) & (uv[:, 1] <= self.height + margin))


def support_fixture():
    # Use the actual existing placement implementation with a tiny exact plane.
    s = object.__new__(view.Support)
    s.x, s.y = np.arange(5) * .05, np.arange(5) * .05
    s.co = np.array([[-.02, -.02, -1.001], [.22, -.02, -.9962],
                     [.22, .22, -.989], [-.02, .22, -.9938]])
    s.tri = np.array([[0, 1, 2], [0, 2, 3]], dtype='i4')
    s.sampler = SourceSampler(s.co, s.tri, np.arange(2), cell_m=.05)
    s.sediment, s.cap = np.full(4, .0008), np.full(4, .0001)
    s.h = {'sediment_delta_m': np.full((2, 2), .0002)}
    s.pins = {'synthetic_exact_plane': 'tiny-test'}
    s.rows = [dict(flow_class=(0 if i == 64 else 1), volume=1e-8,
                   diameter=.02, footprint=.0001, minimum=-.003,
                   maximum=.0005, offset=(.0000712345 if i == 64 else 0.),
                   bottom=[.0008, -.0006, -.003]) for i in range(65)]
    def local_fields(xy):
        return s.sampler.sample(s.co[:, 2], xy), np.full(len(xy), .001), np.full(len(xy), .0001)
    s.local_fields = local_fields
    return s


def catalog_fixture(n=220):
    rng = np.random.default_rng(810731)
    s = support_fixture()
    ids = np.arange(n, dtype='u8') * np.uint64(31337) + np.uint64(2**63)
    xy = rng.uniform(.002, .198, (n, 2)).astype('f4').astype(float)
    pi = np.where(np.arange(n) % 2, 64, 0).astype('u1')
    yaw = (view.ref._uniform(ids, 'yaw') * math.tau).astype('f4')
    selected = np.arange(n) % 3 == 0
    budget = dict(x=s.x, y=s.y, available=rng.uniform(.00001, .0003, (5, 5, 3)))
    height, cover, cap = s.local_fields(xy)
    extra = view.effective_depth(ids, xy, pi, selected, budget, s, cover)
    pre, z, cover, cap = s.placement(xy, pi, yaw, selected, extra)
    data = dict(id=ids, xy=xy, prototype=pi, yaw=yaw, precap_z=pre, z=z,
                role=selected, cover=cover.astype('f4'), static_cap=cap.astype('f4'))
    return s, budget, data


class ViewAuditTests(unittest.TestCase):
    def test_interval_never_rejects_exact_visible_lod_candidate(self):
        rng = np.random.default_rng(419)
        n = 1200
        xy = rng.uniform(-2, 2, (n, 2))
        zlo = rng.uniform(-3, -.02, n)
        zhi = zlo + rng.uniform(0, 2.5, n)
        ids = np.arange(n, dtype='u8') * np.uint64(9769)
        diameter, height = rng.uniform(.0002, .015, n), rng.uniform(0, .004, n)
        for angle, near in ((0., .01), (.65, .01), (-1.05, .0001), (1.3, .03)):
            c, s = math.cos(angle), math.sin(angle)
            inverse = np.eye(4)
            inverse[:3, :3] = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
            inverse[:3, 3] = [.04, -.08, -.05]
            proj = Projection(inverse, near=near)
            broad = view.interval_candidates(xy, zlo, zhi, proj, diameter, height, ids)
            for t in (0., .13, .5, .89, 1.):
                world = np.c_[xy, zlo + t * (zhi - zlo)]
                _, depth = proj.project(world)
                px = (diameter + height / math.tan(math.radians(22))) * proj.f[0] / np.maximum(depth, .001)
                exact = proj.visible(world) & (view.ref._uniform(ids, 'lod') < view.ref.lod_fraction(px))
                self.assertFalse(np.any(exact & ~broad), f'false cull at angle={angle}, t={t}')

    def test_effective_depth_exact_for_same_axis_sampling_and_subset(self):
        rng = np.random.default_rng(7301)
        s = support_fixture()
        x, y = np.arange(-6.975, -6.475, .05), np.arange(-.875, -.375, .05)
        n = 1000
        xy = rng.uniform([x[0], y[0]], [x[-1], y[-1]], (n, 2))
        ids, pi = np.arange(n, dtype='u8'), np.zeros(n, dtype='i4')
        selected = rng.random(n) < .5
        cover = np.full(n, .001)
        cover[::37] = np.nan
        budget = dict(x=x, y=y, available=rng.uniform(.00001, .0003, (len(y), len(x), 3)))
        xx, dx = role._axis(x, 'x')
        yy, dy = role._axis(y, 'y')
        dep = role._bilinear(budget['available'], xy, xx, yy, dx, dy, np.ones(n, dtype=bool))
        effective = np.where(np.isfinite(cover), role.retained_top_proxy(dep)[1], 0)
        expected = role.keyed_extra_embedment_m(candidate_ids=ids, local_effective_deposit_m=effective,
            diameter_m=s.arr('diameter')[pi], local_z_bounds_m=np.c_[s.arr('minimum'), s.arr('maximum')][pi],
            transported=selected, config=role.ExposureConfig(availability_mode='surviving_deposit_stock'))
        actual = view.effective_depth(ids, xy, pi, selected, budget, s, cover)
        np.testing.assert_array_equal(actual, expected)
        subset = np.arange(11, n, 7)[::-1]
        np.testing.assert_array_equal(view.effective_depth(ids[subset], xy[subset], pi[subset],
            selected[subset], budget, s, cover[subset]), expected[subset])

    def test_exact_contact_placement_is_subset_invariant(self):
        s, budget, all_data = catalog_fixture()
        subset = np.arange(5, len(all_data['id']), 3)[::-1]
        d = {k: v[subset] for k, v in all_data.items()}
        height, cover, cap = s.local_fields(d['xy'])
        extra = view.effective_depth(d['id'], d['xy'], d['prototype'], d['role'], budget, s, cover)
        actual = s.placement(d['xy'], d['prototype'], d['yaw'], d['role'], extra)
        for values, key in zip(actual, ('precap_z', 'z', 'cover', 'static_cap')):
            np.testing.assert_array_equal(values.astype(d[key].dtype), d[key])

    def test_cell_height_bounds_enclose_tiny_exact_contact_surface(self):
        s, budget, data = catalog_fixture()
        with tempfile.TemporaryDirectory(dir=HERE) as path:
            path = Path(path)
            (path / 'ACTUAL_CATALOG.json').write_text(json.dumps({'provenance': {'prototypes': [{'radius': .002}]}}))
            cells = np.array([[0, 0], [1, 0], [0, 1], [1, 1]])
            with patch.object(view, 'O', path):
                bounds = view.cell_height_bounds(s, cells, .1)
            ci = np.floor(data['xy'][:, 1] / .1).astype(int) * 2 + np.floor(data['xy'][:, 0] / .1).astype(int)
            self.assertTrue(np.all(data['z'] >= bounds[ci, 0]))
            self.assertTrue(np.all(data['z'] <= bounds[ci, 1]))

    def run_synthetic_select(self, projection, order=None, macro_count=35):
        s, budget, data = catalog_fixture()
        n = len(data['id'])
        order = np.arange(n) if order is None else order
        macro_idx, new_idx = order[:macro_count], order[macro_count:]
        new = {k: v[new_idx] for k, v in data.items()}
        reader = SimpleNamespace(
            map=SimpleNamespace(virtual_count=len(new_idx), cells=np.array([[0, 0]]),
                                prefix=np.array([0, len(new_idx)], dtype='u8'), group_cell=np.array([0])),
            spec=SimpleNamespace(cell_size=.2), proto=np.array([0, 64]),
            report={'status_file_sha256': 'synthetic-status'},
            status_at=lambda serial: np.ones(len(serial), dtype='u1'))
        def decode(serial_map, serial, step):
            return (new['id'][serial], new['xy'][serial], (new['prototype'][serial] == 64).astype('u2'),
                    np.zeros((len(serial), 2), dtype='i4'), serial.astype('u8'))
        with tempfile.TemporaryDirectory(dir=HERE) as dirname:
            path = Path(dirname)
            (path / 'roles').mkdir()
            np.savez_compressed(path / 'WORLD_ROLE_BUDGET.npz', **budget)
            np.savez_compressed(path / 'ACTUAL_CATALOG.npz', **{k: v[macro_idx] for k, v in data.items()})
            bits = np.zeros((len(new_idx) + 7) // 8, dtype='u1')
            set_serial_bits(bits, np.flatnonzero(new['role']).astype('u4'))
            roles_path = path / 'roles/WORLD_ROLES.npz'
            np.savez_compressed(roles_path, role1=bits)
            def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
            receipt = dict(roles_ready=True, schema='dq-full-virtual-serial-role1-v1',
                           config=asdict(role.ExposureConfig(availability_mode='surviving_deposit_stock')),
                           keyed_role_version='dq-stock-role-v1', output_npz_sha256=sha(roles_path),
                           role_sha256=hashlib.sha256(bits.tobytes()).hexdigest(), field_pins=s.pins,
                           input_sha256={name: sha(path/name) for name in ('WORLD_ROLE_BUDGET.npz', 'ACTUAL_CATALOG.npz')})
            roles_path.with_suffix('.json').write_text(json.dumps(receipt))
            with ExitStack() as stack:
                stack.enter_context(patch.object(view, 'O', path))
                stack.enter_context(patch.object(view, 'Reader', return_value=reader))
                stack.enter_context(patch.object(view, 'Support', return_value=s))
                stack.enter_context(patch.object(view, 'cell_height_bounds', return_value=np.array([[-1.03, -.96]])))
                stack.enter_context(patch.object(view.c, '_decode', side_effect=decode))
                stack.enter_context(patch.object(role, 'allocate_transported_grains', side_effect=AssertionError('view must not allocate')))
                selected, report = view.select_world(projection, {'grit_budget': 7, 'sand_budget': 9})
        return selected, report, data

    def test_fixed_rank_membership_is_canonical_across_partition_order(self):
        first, report, all_data = self.run_synthetic_select(Projection())
        second, _, _ = self.run_synthetic_select(Projection(), np.arange(220)[::-1], macro_count=91)
        for key in first:
            np.testing.assert_array_equal(first[key], second[key], err_msg=key)
        rank = view.ref._mix64(all_data['id'] ^ np.uint64(0xCBBB9D5DC1059ED8))
        wanted = []
        for sand, count in ((False, 7), (True, 9)):
            ii = np.flatnonzero((all_data['prototype'] >= 64) == sand)
            wanted.extend(ii[np.lexsort((all_data['id'][ii], rank[ii]))[:count]])
        np.testing.assert_array_equal(first['id'], np.sort(all_data['id'][wanted]))
        self.assertEqual(report['selected'], 16)

    def test_empty_view_returns_typed_empty_subset(self):
        inverse = np.eye(4)
        inverse[0, 3] = 100
        selected, report, all_data = self.run_synthetic_select(Projection(inverse))
        self.assertEqual(report['selected'], 0)
        for key, value in selected.items():
            self.assertEqual(value.shape, all_data[key][:0].shape)
            self.assertEqual(value.dtype, all_data[key].dtype)


if __name__ == '__main__':
    unittest.main(verbosity=2)
