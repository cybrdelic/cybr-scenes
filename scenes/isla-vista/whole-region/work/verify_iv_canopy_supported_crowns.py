"""Validate retained heights, source roots and serialized classified support."""
from pathlib import Path
import hashlib
import json
import struct
import sys

r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(r / 'geo-deps'))
import numpy as np
import rasterio
from pyproj import Transformer

out = r / 'evidence/full-iv-canopy-supported-crowns'
receipt = json.loads((out / 'CANOPY_SUPPORTED_CROWNS_RECEIPT.json').read_text())
rows = {x['source_id']: x for x in receipt['trees']}
objects = {x['object']: x['source'] for x in receipt['parts']}
source_rows = {x['source_id']: x for x in json.loads((r / 'evidence/full-iv-regional-vegetation/SOURCE_TREE_AUDIT.json').read_text())['sources']}
for sid, row in rows.items():
    assert row['source_xy_m'] == source_rows[sid]['source_xy_m']
    assert row['source_height_tag_m'] == source_rows[sid]['source_height_tag_m']
origin = np.array([237001.80699345336, 3811663.448398269])
transform = Transformer.from_crs(32611, 3310, always_xy=True)
with rasterio.open(r / 'data/urban-canopy-2022/iv_canopy_2022_native_060m.tif') as ds:
    mask = ds.read(1) == 1
    inv = ~ds.transform
low, high, count = {}, {}, {}
minimum_cross, normal_error = float('inf'), 0.
foliage_samples, unsupported_samples = 0, 0
dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
with (out / 'canopy_supported_crowns.clm').open('rb') as f:
    magic, total, packets = struct.unpack('<4sQI', f.read(16))
    assert magic == b'CLM1' and total == receipt['triangles']
    for _ in range(packets):
        nv, nt = struct.unpack('<HH', f.read(4))
        v = np.frombuffer(f.read(nv * 44), '<f4').reshape(nv, 11)
        t = np.frombuffer(f.read(nt * 11), dtype)
        assert np.isfinite(v).all() and t['indices'].max() < nv
        assert set(t['material']).issubset({39, 42})
        normal_error = max(normal_error, float(abs(np.linalg.norm(v[:, 3:6], axis=1) - 1).max()))
        q = v[t['indices'], :3].astype(float)
        cross = np.linalg.norm(np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]), axis=1)
        minimum_cross = min(minimum_cross, float(cross.min()))
        assert cross.min() > 1e-10
        leaves = q[t['material'] == 42]
        if len(leaves):
            # Vertices, edge midpoints and centroid sample the serialized
            # triangles. The construction's conservative EDT radius supplies
            # the additional continuous support bound.
            p = np.concatenate([leaves.reshape(-1, 3), leaves.mean(1),
                ((leaves + np.roll(leaves, 1, axis=1)) * .5).reshape(-1, 3)])[:, :2]
            x, y = transform.transform(*(p + origin).T)
            col = np.floor(inv.a * x + inv.c).astype(int)
            row = np.floor(inv.e * y + inv.f).astype(int)
            inside = (row >= 0) & (row < mask.shape[0]) & (col >= 0) & (col < mask.shape[1])
            supported = np.zeros(len(p), dtype=bool)
            supported[inside] = mask[row[inside], col[inside]]
            foliage_samples += len(p)
            unsupported_samples += int((~supported).sum())
        for obj in np.unique(t['object']):
            sid = objects[int(obj)]
            selected = t['object'] == obj
            xyz = q[selected].reshape(-1, 3)
            a, b = xyz.min(0), xyz.max(0)
            low[sid] = np.minimum(low.get(sid, a), a)
            high[sid] = np.maximum(high.get(sid, b), b)
            count[sid] = count.get(sid, 0) + int(selected.sum())
    assert not f.read(1)
height_error = 0.
for sid, row in rows.items():
    a, b = np.asarray(row['previous_bounds_m'])
    height_error = max(height_error, abs(float(low[sid][2] - a[2])), abs(float(high[sid][2] - b[2])))
    assert count[sid] == row['triangles']
passed = height_error < .00001 and normal_error < 2e-6 and unsupported_samples == 0
q = {'passed': passed, 'trees': len(rows), 'triangles': total, 'source_roots_and_height_tags_exactly_retained': True,
    'maximum_visible_height_bound_error_m': height_error, 'minimum_triangle_cross_m2': minimum_cross,
    'maximum_normal_length_error': normal_error, 'serialized_foliage_support_samples': foliage_samples,
    'unsupported_foliage_samples': unsupported_samples,
    'mesh_sha256': hashlib.sha256((out / 'canopy_supported_crowns.clm').read_bytes()).hexdigest(),
    'qualification': 'Numerical and geographic-support checks. Dated classification and authored nearest-root association do not establish exact tree identity, surveyed crown shape, height accuracy, species or leaf-area density.'}
(out / 'SERIALIZED_VALIDATION.json').write_text(json.dumps(q, indent=2) + '\n')
print(json.dumps(q, indent=2), flush=True)
assert passed
