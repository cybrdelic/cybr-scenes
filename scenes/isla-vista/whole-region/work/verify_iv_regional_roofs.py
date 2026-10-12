"""Check the serialized construction, source support and retained envelope."""
from pathlib import Path
import hashlib
import json
import struct
import sys

r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(r / 'geo-deps'))
import numpy as np

out = r / 'evidence/full-iv-regional-roofs'
receipt = json.loads((out / 'REGIONAL_ROOF_RECEIPT.json').read_text())
audit = json.loads((out / 'RETAINED_ROOF_AUDIT.json').read_text())
source = np.load(out / 'retained_roof_faces.npz')
q, ids = source['vertices'], source['material_object']
parts = {x['object']: x for x in receipt['parts']}
old = {x['source_id']: x for x in audit['buildings_detail']}
dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
area = {}
bounds = {}
minimum_cross = float('inf')
normal_error = 0.
with (out / 'regional_roofs.clm').open('rb') as f:
    magic, total, packets = struct.unpack('<4sQI', f.read(16))
    assert magic == b'CLM1' and total == receipt['triangles']
    for _ in range(packets):
        nv, nt = struct.unpack('<HH', f.read(4))
        v = np.frombuffer(f.read(nv * 44), '<f4').reshape(nv, 11)
        t = np.frombuffer(f.read(nt * 11), dtype)
        assert np.isfinite(v).all() and t['indices'].max() < nv
        assert t['material'].min() >= 192 and t['material'].max() < 192 + receipt['material_count']
        normal_error = max(normal_error, float(abs(np.linalg.norm(v[:, 3:6], axis=1) - 1).max()))
        tri = v[t['indices'], :3].astype(float)
        cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        length = np.linalg.norm(cross, axis=1)
        minimum_cross = min(minimum_cross, float(length.min()))
        assert length.min() > 1e-10
        for obj in np.unique(t['object']):
            mask = t['object'] == obj
            sid = parts[int(obj)]['source']
            area[sid] = area.get(sid, 0.) + float(abs(cross[mask, 2]).sum() * .5)
            xyz = tri[mask].reshape(-1, 3)
            low, high = xyz.min(0), xyz.max(0)
            if sid in bounds:
                low, high = np.minimum(low, bounds[sid][0]), np.maximum(high, bounds[sid][1])
            bounds[sid] = low, high
    assert not f.read(1)
assert normal_error < 2e-6
max_area_error = 0.
max_height_increase = 0.
max_footprint_bound_change = 0.
for sid, row in old.items():
    original = q[np.isin(ids[:, 1], row['objects']), :, :3].astype(float)
    a = np.cross(original[:, 1] - original[:, 0], original[:, 2] - original[:, 0])
    original_area = float(abs(a[:, 2]).sum() * .5)
    error = abs(area[sid] - original_area)
    max_area_error = max(max_area_error, error)
    assert error < max(.012, original_area * .00001), (sid, original_area, area[sid])
    lo, hi = bounds[sid]
    previous_lo, previous_hi = map(np.asarray, row['bounds_m'])
    max_height_increase = max(max_height_increase, float(hi[2] - previous_hi[2]))
    max_footprint_bound_change = max(max_footprint_bound_change,
        float(abs(lo[:2] - previous_lo[:2]).max()), float(abs(hi[:2] - previous_hi[:2]).max()))
assert max_height_increase < .00001 and max_footprint_bound_change < .00015
record = {'passed': True, 'serialized_triangles': total,
    'buildings_checked': len(old), 'minimum_serialized_triangle_cross_m2': minimum_cross,
    'maximum_unit_normal_error': normal_error,
    'maximum_projected_area_error_m2': max_area_error,
    'maximum_height_increase_m': max_height_increase,
    'maximum_footprint_bound_change_m': max_footprint_bound_change,
    'mesh_sha256': hashlib.sha256((out / 'regional_roofs.clm').read_bytes()).hexdigest(),
    'qualification': 'Serialized numerical envelope and projected-area check. This does not validate authored construction as surveyed building detail.'}
(out / 'SERIALIZED_VALIDATION.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
