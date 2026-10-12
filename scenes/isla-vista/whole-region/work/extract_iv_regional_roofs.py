"""Recover only active serialized roof faces; preserve their source identities."""
from pathlib import Path
import hashlib
import json
import shlex
import struct
import sys

r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(r / 'geo-deps'))
import numpy as np

out = r / 'evidence/full-iv-regional-roofs'
out.mkdir(exist_ok=True)
source = r / 'evidence/full-iv-coastal-return-overview/candidate.cys'
features = json.loads((r / 'evidence/full-iv-roofs/normalized.geojson').read_text())['features']
buildings = {f['id']: f for f in features if f['properties']['category'] == 'building'}
stems = {source_id.replace(':', '_') + '_': source_id for source_id in buildings}
layout = json.loads((r / 'evidence/full-iv-roofs/glb-part-layout.json').read_text())
objects = {}
for batch in layout.values():
    for part in batch['parts']:
        name = part['part']
        if not (name.endswith('_roof') or '_roof_tagged_' in name):
            continue
        matches = [source_id for stem, source_id in stems.items() if name.startswith(stem)]
        assert len(matches) == 1, (name, matches)
        objects[part['component']] = {'source_id': matches[0], 'part': name, 'mesh': 'sector.clm'}
previous = json.loads((r / 'evidence/full-iv-sourced-roofs/SOURCED_ROOFS_RECEIPT.json').read_text())
for part in previous['parts']:
    if '_retained_roof_' in part['name'] or '_restored_roof_' in part['name']:
        objects[part['object']] = {'source_id': part['source'], 'part': part['name'], 'mesh': 'roofs.clm'}
entries = []
for line in source.read_text().splitlines():
    q = shlex.split(line)
    if q and q[0] in {'meshlets', 'meshlets_excluding'}:
        path = (source.parent / q[1]).resolve()
        if path in {r / 'evidence/full-iv-roofs/sector.clm', r / 'evidence/full-iv-sourced-roofs/roofs.clm'}:
            excluded = set(map(int, q[3:])) if q[0] == 'meshlets_excluding' else set()
            assert q[0] == 'meshlets' or len(excluded) == int(q[2])
            entries.append((path, excluded))
assert len(entries) == 2
dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
triangles, records, sources = [], [], []
for path, excluded in entries:
    selection = {obj for obj, item in objects.items() if item['mesh'] == path.name} - excluded
    selected = np.array(sorted(selection), dtype=np.uint32)
    with path.open('rb') as stream:
        magic, total, packets = struct.unpack('<4sQI', stream.read(16))
        assert magic == b'CLM1'
        for _ in range(packets):
            nv, nt = struct.unpack('<HH', stream.read(4))
            v = np.frombuffer(stream.read(nv * 44), '<f4').reshape(nv, 11)
            t = np.frombuffer(stream.read(nt * 11), dtype)
            take = np.isin(t['object'], selected)
            if not take.any():
                continue
            triangles.append(v[t['indices'][take]].copy())
            records.append(np.c_[t['material'][take], t['object'][take]].copy())
        assert not stream.read(1)
    sources.append({'path': str(path.relative_to(r)), 'excluded_objects': sorted(excluded),
                    'selected_roof_objects': sorted(selection)})
q = np.concatenate(triangles)
ids = np.concatenate(records)
assert np.isfinite(q).all()
np.savez_compressed(out / 'retained_roof_faces.npz', vertices=q, material_object=ids)
active = set(map(int, np.unique(ids[:, 1])))
object_rows = {str(obj): item for obj, item in objects.items() if obj in active}
by_source = {}
for obj, item in object_rows.items():
    by_source.setdefault(item['source_id'], []).append(int(obj))
rows = []
for source_id, object_ids in by_source.items():
    face = q[np.isin(ids[:, 1], object_ids)]
    props = buildings[source_id]['properties']['source_properties']
    xyz = face[:, :, :3]
    cross = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
    area = np.linalg.norm(cross, axis=1)
    keep = area > 1e-9
    normals = np.abs(cross[keep] / area[keep, None])
    rows.append({'source_id': source_id, 'objects': object_ids,
                 'triangles': len(face), 'bounds_m': [xyz.reshape(-1, 3).min(0).tolist(), xyz.reshape(-1, 3).max(0).tolist()],
                 'area_m2': float(area.sum() / 2),
                 'max_slope_normal_xy': float(np.linalg.norm(normals[:, :2], axis=1).max()),
                 'source_properties': props})
record = {'passed': True, 'source_scene_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'triangles': len(q), 'roof_objects': len(active), 'buildings': len(rows),
          'serialized_position_normal_sha256': hashlib.sha256(q[:, :, :6].tobytes()).hexdigest(),
          'source_meshes': sources, 'objects': object_rows, 'buildings_detail': rows,
          'scope': 'Only active general regional roof faces. Dedicated source-reference house, Pardall and Del Playa architecture components are preserved separately and are not replaced.'}
(out / 'RETAINED_ROOF_AUDIT.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ['passed', 'triangles', 'roof_objects', 'buildings']}), flush=True)
