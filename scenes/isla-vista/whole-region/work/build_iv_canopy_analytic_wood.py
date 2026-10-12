"""Use existing native cylinders for subpixel crown wood; preserve foliage bytes.

The already validated CLM1 is the geometry source. Ordered tube topology is
checked before fitting each uncapped cylinder. Trunks and any tube that would
leave the prior complete crown bounds remain exact triangles. A constant radius
matches original polygonal lateral area; it approximates taper and facets.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / 'geo-deps'), str(r / 'work/iv-component-runtime')]
import numpy as np
from cybr_light import Meshlets
from cybr_light.runtime import publish

source = r / 'evidence/full-iv-canopy-supported-crowns'
out = r / 'evidence/full-iv-canopy-analytic-wood'
out.mkdir(exist_ok=True)
assert shutil.disk_usage(out).free > (1 << 30) + 450_000_000
receipt = json.loads((source / 'CANOPY_SUPPORTED_CROWNS_RECEIPT.json').read_text())
validation = json.loads((source / 'SERIALIZED_VALIDATION.json').read_text())
assert validation['passed']
records = {x['source_id']: x for x in receipt['trees']}
objects = {x['object']: x for x in receipt['parts']}
dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
selected = source / 'canopy_supported_crowns.clm'
source_hash = hashlib.sha256()
with selected.open('rb') as f:
    for b in iter(lambda: f.read(8 << 20), b''): source_hash.update(b)
assert source_hash.hexdigest() == validation['mesh_sha256']
foliage_hash = hashlib.sha256()
retained = Meshlets(out / 'retained_wood.clm')
foliage_path = out / 'exact_foliage.clm'
wood_path = out / 'analytic_wood.cys'
assert not foliage_path.exists() and not wood_path.exists()
foliage_triangles = foliage_packets = cylinders = original_wood = 0
maximum_bbox_expansion = maximum_ring_center_connection_error = 0.
maximum_radial_radius_difference = maximum_surface_area_relative_error = 0.
per_tree = []


def retain(tris, obj):
    if not len(tris): return
    a = np.zeros((len(tris), 36), '<f4')
    a[:, :9] = tris[:, :, :3].reshape(-1, 9)
    a[:, 9:18] = tris[:, :, 3:6].reshape(-1, 9)
    a[:, 18], a[:, 19] = 39, obj
    a[:, 20:26] = tris[:, :, 6:8].reshape(-1, 6)
    a[:, 26:35] = tris[:, :, 8:11].reshape(-1, 9)
    retained.add(a)


def convert_tree(tris, obj, writer):
    global cylinders, original_wood, maximum_bbox_expansion
    global maximum_radial_radius_difference, maximum_surface_area_relative_error
    row = records[objects[obj]['source']]
    groups = row['foliage_group_centres']
    assert len(tris) == 12 + groups * 8 + groups * 2 * 6
    original_wood += len(tris)
    retain(tris[:12], obj)  # Original resolved tapered trunk remains exact.
    low, high = np.asarray(row['candidate_bounds_m'], float)
    lows, highs = tris[:, :, :3].min((0, 1)), tris[:, :, :3].max((0, 1))
    converted = kept = 0
    for start, count, sides in [(12, groups, 4), (12 + groups * 8, groups * 2, 3)]:
        t = tris[start:start + count * sides * 2].reshape(count, sides * 2, 3, 11)
        xyz = t[..., :3].astype(float)
        aa, bb = xyz[:, ::2, 0], xyz[:, 1::2, 2]
        expected = np.stack([np.stack([aa, np.roll(aa, -1, axis=1), np.roll(bb, -1, axis=1)], axis=2),
                             np.stack([aa, np.roll(bb, -1, axis=1), bb], axis=2)], axis=2).reshape(count, sides * 2, 3, 3)
        assert np.array_equal(xyz, expected), 'Serialized tube topology changed'
        a, b = aa.mean(1), bb.mean(1)
        lengths = np.linalg.norm(b - a, axis=1)
        axis = (b - a) / lengths[:, None]
        original_area = np.linalg.norm(np.cross(xyz[:, :, 1] - xyz[:, :, 0], xyz[:, :, 2] - xyz[:, :, 0]), axis=2).sum(1) * .5
        radius = original_area / (2 * np.pi * lengths)
        extent = radius[:, None] * np.sqrt(np.maximum(0., 1 - axis * axis))
        ca, cb = np.minimum(a, b) - extent, np.maximum(a, b) + extent
        old_a, old_b = xyz.min((1, 2)), xyz.max((1, 2))
        expansion = np.maximum(old_a - ca, cb - old_b).max(1)
        # These are a view-specific subpixel tier. The source has 2.286 m
        # vertical pixel footprints at the matched whole-area camera.
        ok = (lengths > 1e-6) & (radius * 2 <= .08) & (expansion <= .025)
        ok &= (ca >= low[None] - 1e-7).all(1) & (cb <= high[None] + 1e-7).all(1)
        retain(t[~ok].reshape(-1, 3, 11), obj)
        kept += int((~ok).sum())
        for i in np.flatnonzero(ok):
            numbers = [*a[i], *b[i], radius[i]]
            writer.write('cylinder 39 ' + str(obj) + ' ' + ' '.join(format(float(v), '.17g') for v in numbers) + ' 0 0 0\n')
        n = int(ok.sum()); cylinders += n; converted += n
        if n:
            maximum_bbox_expansion = max(maximum_bbox_expansion, float(expansion[ok].max()))
            old_radii = np.concatenate([np.linalg.norm(aa - a[:, None], axis=2), np.linalg.norm(bb - b[:, None], axis=2)], axis=1)
            maximum_radial_radius_difference = max(maximum_radial_radius_difference, float(abs(old_radii[ok] - radius[ok, None]).max()))
            area_error = abs(2 * np.pi * radius[ok] * lengths[ok] - original_area[ok]) / original_area[ok]
            maximum_surface_area_relative_error = max(maximum_surface_area_relative_error, float(area_error.max()))
    per_tree.append({'source_id': row['source_id'], 'wood_object': obj, 'source_xy_m': row['source_xy_m'],
                     'source_height_tag_m': row['source_height_tag_m'], 'cylinders': converted,
                     'retained_branch_tubes': kept, 'retained_trunk_triangles': 12,
                     'previous_bounds_m': row['candidate_bounds_m']})


with tempfile.TemporaryDirectory(prefix='iv-analytic-wood-') as td:
    temp_leaf, temp_wood = Path(td) / 'foliage.clm', Path(td) / 'wood.cys'
    with selected.open('rb') as f, temp_leaf.open('w+b') as leaves, temp_wood.open('w') as wood:
        magic, total, packets = struct.unpack('<4sQI', f.read(16))
        assert magic == b'CLM1' and total == receipt['triangles']
        leaves.write(struct.pack('<4sQI', b'CLM1', 0, 0))
        current_obj, buffers = None, []
        for _ in range(packets):
            header = f.read(4); nv, nt = struct.unpack('<HH', header)
            vb, tb = f.read(nv * 44), f.read(nt * 11)
            v = np.frombuffer(vb, '<f4').reshape(nv, 11)
            t = np.frombuffer(tb, dtype)
            ids, mats = np.unique(t['object']), np.unique(t['material'])
            assert len(ids) == len(mats) == 1
            obj, material = int(ids[0]), int(mats[0])
            if material == 42:
                payload = header + vb + tb
                leaves.write(payload); foliage_hash.update(payload)
                foliage_triangles += nt; foliage_packets += 1
            else:
                assert material == 39
                if obj != current_obj and buffers:
                    convert_tree(np.concatenate(buffers), current_obj, wood); buffers = []
                current_obj = obj
                buffers.append(v[t['indices']])
        if buffers: convert_tree(np.concatenate(buffers), current_obj, wood)
        assert not f.read(1)
        leaves.seek(0); leaves.write(struct.pack('<4sQI', b'CLM1', foliage_triangles, foliage_packets))
    retained.__exit__(None, None, None)
    publish(temp_leaf, foliage_path); publish(temp_wood, wood_path)

summary = {'passed_construction_checks': True, 'source_mesh_sha256': source_hash.hexdigest(),
    'foliage_packets_byte_identical': True, 'foliage_packet_sha256': foliage_hash.hexdigest(),
    'foliage_triangles': foliage_triangles, 'foliage_packets': foliage_packets,
    'original_wood_triangles': original_wood, 'retained_wood_triangles': retained.triangles,
    'analytic_cylinders': cylinders, 'candidate_component_primitives': foliage_triangles + retained.triangles + cylinders,
    'maximum_wood_bbox_expansion_m': maximum_bbox_expansion,
    'maximum_source_ring_vertex_radius_difference_m': maximum_radial_radius_difference,
    'maximum_lateral_area_relative_error': maximum_surface_area_relative_error,
    'tree_count': len(per_tree), 'trees': per_tree,
    'taper_approximation': 'Uncapped constant-radius cylinders match each replaced polygonal tube lateral area. Taper, faceted cross-section, and the small anisotropic vertical stretch are approximated. Original trunks and tubes that would violate retained full-crown bounds stay exact triangles.',
    'scope': 'Same geographically supported whole-area foliage, material, camera and source roots. An explicit regional representation only; no automatic LOD or near-street parity claim.',
    'validation_pending': True}
(out / 'ANALYTIC_WOOD_RECEIPT.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k:v for k,v in summary.items() if k != 'trees'}), flush=True)
