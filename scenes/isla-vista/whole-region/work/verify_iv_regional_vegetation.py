"""Validate serialized aggregate foliage and retained source-tree envelopes."""
from pathlib import Path
import hashlib
import json
import struct
import sys

r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(r / 'geo-deps'))
import numpy as np

out = r / 'evidence/full-iv-regional-vegetation'
report = json.loads((out / 'REGIONAL_VEGETATION_RECEIPT.json').read_text())
rows = {x['source_id']: x for x in report['trees']}
objects = {x['object']: x['source'] for x in report['parts']}
low, high, count = {}, {}, {}
dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
normal_error, minimum_cross = 0., float('inf')
with (out / 'regional_vegetation.clm').open('rb') as f:
    magic, total, packets = struct.unpack('<4sQI', f.read(16))
    assert magic == b'CLM1' and total == report['triangles']
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
        for obj in np.unique(t['object']):
            sid = objects[int(obj)]
            mask = t['object'] == obj
            xyz = q[mask].reshape(-1, 3)
            a, b = xyz.min(0), xyz.max(0)
            low[sid] = np.minimum(low.get(sid, a), a)
            high[sid] = np.maximum(high.get(sid, b), b)
            count[sid] = count.get(sid, 0) + int(mask.sum())
    assert not f.read(1)
assert normal_error < 2e-6 and set(low) == set(rows)
height_error, outward_error = 0., 0.
for sid, row in rows.items():
    a, b = np.asarray(row['original_bounds_m'])
    height_error = max(height_error, abs(float(high[sid][2] - b[2])), abs(float(low[sid][2] - a[2])))
    outward_error = max(outward_error, float(np.max(a - low[sid])), float(np.max(high[sid] - b)))
    assert count[sid] == row['triangles']
assert height_error < .00001 and outward_error < .00015
record = {'passed': True, 'trees_checked': len(rows), 'triangles': total,
    'original_visible_tree_triangles': report['original_visible_tree_triangles'],
    'triangle_reduction_fraction': 1 - total / report['original_visible_tree_triangles'],
    'maximum_visible_height_bound_error_m': height_error,
    'maximum_outward_bound_error_m': outward_error,
    'minimum_triangle_cross_m2': minimum_cross, 'maximum_normal_length_error': normal_error,
    'mesh_sha256': hashlib.sha256((out / 'regional_vegetation.clm').read_bytes()).hexdigest(),
    'qualification': 'Serialized geometry and prior envelope checks only. Aggregate facets are a fixed regional representation, not individual leaves or a transport-equivalent reduction. Source point arrays are retained in both receipts; no geographic scatter is added.'}
(out / 'SERIALIZED_VALIDATION.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
