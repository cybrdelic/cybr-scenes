"""Resolve retained mapped trees and the actual visible geometry envelope."""
from pathlib import Path
import hashlib
import json
import shlex
import struct
import sys

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / 'geo-deps'), str(r / 'work/cybr-iv-full/src'), str(r / 'whole-iv-vendor')]
import numpy as np
from cybr_ucsb.geometry import stable_seed
from cybr_ucsb.ingest import metres

out = r / 'evidence/full-iv-regional-vegetation'
out.mkdir(exist_ok=True)
base = r / 'evidence/full-iv-roofs'
features = json.loads((base / 'normalized.geojson').read_text())['features']
layout = json.loads((base / 'glb-part-layout.json').read_text())
parts = {p['part']: p['component'] for batch in layout.values() for p in batch['parts']}
botanical = json.loads((r / 'evidence/full-iv-botanical-dense/BOTANICAL_RECEIPT.json').read_text())
near = json.loads((r / 'evidence/full-iv-near-street-vegetation/VEGETATION_RECEIPT.json').read_text())
previous = {x['source_id']: x for x in botanical['features']}
previous.update({x['source_id']: x for x in near['source_features']})
palms = {'Syagrus', 'Phoenix', 'Washingtonia', 'Howea', 'Butia', 'Chamaerops', 'Archontophoenix'}
records = []
objects = {}
for feature in features:
    if feature['geometry']['type'] != 'Point' or feature['properties']['category'] not in {'tree', 'vegetation'}:
        continue
    stem = feature['id'].replace(':', '_')
    old = [parts[name] for name in [stem + '_trunk', stem + '_crown', stem + '_fronds'] if name in parts]
    if not old:
        continue
    source = feature['id']
    properties = feature['properties']['source_properties']
    genus = str(properties.get('genus', '')).strip()
    family = str(properties.get('taxon:family', '')).strip()
    supplied = metres(properties.get('height'))
    rng = np.random.default_rng(stable_seed(source))
    prior_height = supplied or (11 if genus in palms else 14 if genus in {'Pinus', 'Eucalyptus', 'Corymbia'} else 7.5) * rng.uniform(.8, 1.15)
    height = previous.get(source, {}).get('height_m', prior_height)
    index = len(records)
    records.append({'source_id': source, 'source_xy_m': feature['geometry']['coordinates'],
        'source_genus': genus, 'source_family': family, 'source_height_tag_m': supplied,
        'retained_height_parameter_m': height,
        'height_parameter_source': 'prior detailed botanical geometry' if source in previous else 'prior geographic massing formula',
        'form': 'fan palm' if genus in {'Washingtonia', 'Chamaerops'} else 'pinnate palm' if genus in palms or family in {'Arecaceae', 'Arecacea'} else 'conifer' if genus in {'Pinus', 'Cedrus', 'Cupressus', 'Sequoia', 'Podocarpus'} else 'broadleaf',
        'form_is_estimated': True, 'baseline_sector_objects': old})
    for obj in old:
        objects[('sector.clm', obj)] = index
source_indices = {x['source_id']: i for i, x in enumerate(records)}
for name, receipt in [('botanical.clm', botanical), ('vegetation.clm', near)]:
    for part in receipt['parts']:
        assert part['source'] in source_indices
        objects[(name, part['object'])] = source_indices[part['source']]
scene = r / 'evidence/full-iv-regional-roofs-overview/candidate.cys'
low = np.full((len(records), 3), np.inf)
high = np.full((len(records), 3), -np.inf)
triangle_counts = np.zeros(len(records), dtype=np.int64)
mesh_records = []
dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
for line in scene.read_text().splitlines():
    words = shlex.split(line)
    if not words or words[0] not in {'meshlets', 'meshlets_excluding'}:
        continue
    path = (scene.parent / words[1]).resolve()
    if path.name not in {'sector.clm', 'botanical.clm', 'vegetation.clm'}:
        continue
    excluded = set(map(int, words[3:])) if words[0] == 'meshlets_excluding' else set()
    selected = {obj: index for (name, obj), index in objects.items() if name == path.name and obj not in excluded}
    max_id = max(selected) + 1
    index_map = np.full(max_id, -1, dtype=np.int32)
    for obj, index in selected.items():
        index_map[obj] = index
    with path.open('rb') as f:
        magic, total, packets = struct.unpack('<4sQI', f.read(16))
        assert magic == b'CLM1'
        for _ in range(packets):
            nv, nt = struct.unpack('<HH', f.read(4))
            vertices = np.frombuffer(f.read(nv * 44), '<f4').reshape(nv, 11)
            triangles = np.frombuffer(f.read(nt * 11), dtype)
            candidates = triangles[triangles['object'] < max_id]
            for obj in np.unique(candidates['object']):
                index = index_map[obj]
                if index < 0:
                    continue
                matching = candidates[candidates['object'] == obj]
                xyz = vertices[matching['indices'], :3].reshape(-1, 3)
                low[index] = np.minimum(low[index], xyz.min(0))
                high[index] = np.maximum(high[index], xyz.max(0))
                triangle_counts[index] += len(matching)
        assert not f.read(1)
    mesh_records.append({'path': str(path.relative_to(r)), 'name': path.name,
        'active_replaced_objects': sorted(selected), 'originally_excluded_objects': sorted(excluded)})
assert len(mesh_records) == 3
assert np.isfinite(low).all() and np.isfinite(high).all() and np.all(triangle_counts > 0)
for i, row in enumerate(records):
    row.update(original_bounds_m=[low[i].tolist(), high[i].tolist()],
        original_visible_height_m=float(high[i, 2] - low[i, 2]), original_visible_triangles=int(triangle_counts[i]))
report = {'passed': True, 'trees': len(records), 'visible_tree_triangles': int(triangle_counts.sum()),
    'sources': records, 'meshes': mesh_records,
    'source_scene_sha256': hashlib.sha256(scene.read_bytes()).hexdigest(),
    'normalized_source_sha256': hashlib.sha256((base / 'normalized.geojson').read_bytes()).hexdigest(),
    'scope': 'Existing retained source points only. No new scatter or inferred species. Actual current tree geometry envelopes are measured for the regional representation; detailed source meshes are preserved.'}
(out / 'SOURCE_TREE_AUDIT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ['passed', 'trees', 'visible_tree_triangles']}), flush=True)
