"""Four source-roof assembly controls and the unchanged whole-area camera."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import struct
import sys

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / x) for x in ['geo-deps', 'work/iv-component-runtime', 'work/cybr-iv-full/src', 'whole-iv-vendor']]
import numpy as np
import shapely
from cybr_light import Scene, render
from iv_mesh_parts import Parts

p = argparse.ArgumentParser()
p.add_argument('--view', choices=['fixture', 'overview'], default='fixture')
p.add_argument('--baseline', action='store_true')
p.add_argument('--prepare-only', action='store_true')
args = p.parse_args()
component = r / 'evidence/full-iv-regional-roofs'
receipt = json.loads((component / 'REGIONAL_ROOF_RECEIPT.json').read_text())
validation = json.loads((component / 'SERIALIZED_VALIDATION.json').read_text())
assert validation['passed']
source = r / 'evidence/full-iv-coastal-return-overview/candidate.cys'
out = r / ('evidence/full-iv-regional-roofs-' + args.view)
out.mkdir(exist_ok=True)
s = Scene()
for line in source.read_text().splitlines():
    q = shlex.split(line)
    if not q or q[0].startswith('#'):
        continue
    if args.view == 'fixture' and (q[0] in {'camera', 'settings', 'film_format', 'render_options'} or q[0].startswith('meshlets')):
        continue
    line = re.sub(r'"([^"]+)"', lambda m: json.dumps(str((source.parent / m[1]).resolve())), line)
    if not args.baseline and q[0] in {'meshlets', 'meshlets_excluding'}:
        name = Path(q[1]).name
        if name in receipt['replace_by_mesh'] and Path(q[1]).parent.name in {'full-iv-roofs', 'full-iv-sourced-roofs'}:
            prior = set(map(int, q[3:])) if q[0] == 'meshlets_excluding' else set()
            excluded = sorted(prior | set(receipt['replace_by_mesh'][name]))
            line = 'meshlets_excluding ' + json.dumps(str((source.parent / q[1]).resolve())) + ' ' + str(len(excluded)) + ' ' + ' '.join(map(str, excluded))
    s.lines.append(line)
assert sum(x.startswith('material ') for x in s.lines) == 192
for line in (component / 'materials.cys').read_text().splitlines():
    if not line.startswith('#'):
        s.lines.append(re.sub(r'"([^"]+)"', lambda m: json.dumps(str((component / m[1]).resolve())), line))
s.materials = 192 + receipt['material_count']
selection = []
if args.view == 'overview':
    if not args.baseline:
        s.mesh(component / 'regional_roofs.clm')
else:
    audit = json.loads((component / 'RETAINED_ROOF_AUDIT.json').read_text())
    rows = {x['source_id']: x for x in audit['buildings_detail']}
    chosen = []
    for family in ['cementitious', 'fired_tile', 'bonded_mineral', 'light_membrane']:
        candidates = [x for x in receipt['buildings'] if x['authored_finish'] == family and 2 < rows[x['source_id']]['area_m2'] < 500]
        assert candidates, family
        selected = min(candidates, key=lambda x: abs(rows[x['source_id']]['area_m2'] - 140))
        chosen.append(selected)
    data = np.load(component / 'retained_roof_faces.npz')
    original, original_ids = data['vertices'], data['material_object']
    transforms = {}
    cursor = 0.
    foundation = Parts(out / 'fixture_foundation.clm', 15800000)
    wall_mat = s.material('diffuse', (.25, .25, .25))
    floor_mat = s.material('diffuse', (.16, .16, .16))
    for index, row in enumerate(chosen):
        sid = row['source_id']
        low, high = np.asarray(rows[sid]['bounds_m'])
        width = high[0] - low[0]
        shift = np.array([cursor - low[0], -(low[1] + high[1]) * .5, 2. - low[2]])
        transforms[sid] = shift
        face = original[np.isin(original_ids[:, 1], row['old_roof_objects']), :, :3].astype(float)
        poly = shapely.union_all(shapely.polygons(face[:, :, :2]))
        for polygon in ([poly] if poly.geom_type == 'Polygon' else poly.geoms):
            for boundary in [polygon.exterior, *polygon.interiors]:
                xy = np.asarray(boundary.coords)[:, :2] + shift[:2]
                for j, (a, b) in enumerate(zip(xy[:-1], xy[1:])):
                    v = np.array([[*a, 0], [*b, 0], [*b, 2], [*a, 2]])
                    foundation.mesh(f'neutral_fixture_wall_{index}_{j}', v, [[0, 1, 2], [0, 2, 3]], wall_mat, sid,
                        'Neutral two-metre fixture wall; specimen arrangement is not geographic scene placement.')
        selection.append({'source_id': sid, 'finish': row['authored_finish'], 'source_material': row['source_roof_material'],
            'translation_m': shift.tolist(), 'retained_roof_bounds_m': [low.tolist(), high.tolist()]})
        cursor += width + 7
    foundation.box('neutral_fixture_ground', [cursor + 30, 100, .1], [cursor * .5, 0, -.055], floor_mat, 'fixture', 'Neutral comparison support.')
    foundation.close()
    s.mesh(out / 'fixture_foundation.clm')
    mesh = Parts(out / ('baseline_roofs.clm' if args.baseline else 'candidate_roofs.clm'), 15850000)
    if args.baseline:
        for row in chosen:
            mask = np.isin(original_ids[:, 1], row['old_roof_objects'])
            values = original[mask]
            mats = original_ids[mask, 0]
            for material in np.unique(mats):
                q = values[mats == material]
                vertices = q[:, :, :3].reshape(-1, 3).astype(float) + transforms[row['source_id']]
                faces = np.arange(len(vertices)).reshape(-1, 3)
                mesh.mesh(row['source_id'], vertices, faces, int(material), row['source_id'], 'Translated retained roof fixture.',
                    uv=q[:, :, 6:8].reshape(-1, 2), normals=q[:, :, 3:6].reshape(-1, 3), tint=q[:, :, 8:11].reshape(-1, 9))
    else:
        part_source = {x['object']: x['source'] for x in receipt['parts']}
        wanted = np.array([obj for obj, sid in part_source.items() if sid in transforms], dtype=np.uint32)
        dtype = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])
        with (component / 'regional_roofs.clm').open('rb') as f:
            magic, total, packets = struct.unpack('<4sQI', f.read(16))
            for _ in range(packets):
                nv, nt = struct.unpack('<HH', f.read(4))
                v = np.frombuffer(f.read(nv * 44), '<f4').reshape(nv, 11)
                t = np.frombuffer(f.read(nt * 11), dtype)
                for obj in np.intersect1d(np.unique(t['object']), wanted):
                    selected = t[t['object'] == obj]
                    sid = part_source[int(obj)]
                    for mat in np.unique(selected['material']):
                        values = v[selected['indices'][selected['material'] == mat]]
                        vv = values[:, :, :3].reshape(-1, 3).astype(float) + transforms[sid]
                        ff = np.arange(len(vv)).reshape(-1, 3)
                        mesh.mesh(sid, vv, ff, int(mat), sid, 'Translated candidate roof fixture.',
                            uv=values[:, :, 6:8].reshape(-1, 2), normals=values[:, :, 3:6].reshape(-1, 3))
            assert not f.read(1)
    mesh.close()
    s.mesh(mesh.writer.path if hasattr(mesh.writer, 'path') else out / ('baseline_roofs.clm' if args.baseline else 'candidate_roofs.clm'))
    s.settings(1000, 600, 32, 8, 2, bands=6, seed=20261011, exposure=1.05)
    s.camera([cursor * .5, -cursor * .43, cursor * .58], [cursor * .5, 0, 0],
        orthographic=True, scale=cursor * .7, fov=45)
stem = out / ('baseline' if args.baseline else 'candidate')
s.save(stem.with_suffix('.cys'))
metadata = {'scope': 'Four translated actual roof-assembly specimens.' if args.view == 'fixture' else 'Current complete Isla Vista, original matched overview camera.',
    'baseline': args.baseline, 'roof_validation': validation, 'specimens': selection,
    'source_scene_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'authored_construction': 'Inset low-slope roof decks, coping and inner flashing. Pitched form retained in this pass. Exact footprints and maximum heights are checked; inferred finishes and weathering remain authored.',
    'material_sampling': receipt['context_sampling'],
    'tone_mapping': 'Unchanged simple ACES fitted curve and sRGB, exposure 1.05; three centre-hit guided atrous passes.',
    'limits': 'Regional construction is an explicit estimate where source tags are missing. No exact facade/roof reconstruction or photorealism claim. Fixture translates four roofs to compare construction; it is not a geographic scene view. Surface-return ocean and dated source assumptions remain unchanged.'}
(out / (stem.name.upper() + '_PREPARATION.json')).write_text(json.dumps(metadata, indent=2) + '\n')
if args.prepare_only:
    print(json.dumps({'scene': str(stem.with_suffix('.cys'))}), flush=True)
else:
    report = render(s, stem, metadata=metadata)
    print(json.dumps({key: report.get(key) for key in ['primitives', 'render_seconds', 'invalid_path_samples', 'engine_source_sha256']}), flush=True)
