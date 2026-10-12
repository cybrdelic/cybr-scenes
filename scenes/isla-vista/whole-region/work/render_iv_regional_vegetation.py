"""Render an explicit regional vegetation tier in the matched full-IV camera."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import sys

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / 'geo-deps'), str(r / 'work/iv-component-runtime')]
from cybr_light import Scene, render

p = argparse.ArgumentParser()
p.add_argument('--width', type=int, choices=[1000, 2000], default=1000)
p.add_argument('--prepare-only', action='store_true')
args = p.parse_args()
component = r / 'evidence/full-iv-regional-vegetation'
receipt = json.loads((component / 'REGIONAL_VEGETATION_RECEIPT.json').read_text())
validation = json.loads((component / 'SERIALIZED_VALIDATION.json').read_text())
assert validation['passed']
source = r / 'evidence/full-iv-regional-roofs-overview/candidate.cys'
out = r / ('evidence/full-iv-regional-vegetation-overview' + ('-2000' if args.width == 2000 else ''))
out.mkdir(exist_ok=True)
replacement = {str((r / x['path']).resolve()): set(x['active_replaced_objects']) for x in receipt['replace_meshes']}
s = Scene()
found = []
for line in source.read_text().splitlines():
    q = shlex.split(line)
    if not q or q[0].startswith('#'):
        continue
    line = re.sub(r'"([^"]+)"', lambda m: json.dumps(str((source.parent / m[1]).resolve())), line)
    if q[0] == 'settings' and args.width != 1000:
        # Preserve sample packets, spectral bands, seed, exposure and depth.
        q[1], q[2] = str(args.width), str(args.width * 7 // 10)
        line = ' '.join(q)
    if q[0] in {'meshlets', 'meshlets_excluding'}:
        path = str((source.parent / q[1]).resolve())
        if path in replacement:
            found.append(path)
            if Path(path).name in {'botanical.clm', 'vegetation.clm'}:
                continue
            prior = set(map(int, q[3:])) if q[0] == 'meshlets_excluding' else set()
            excluded = sorted(prior | replacement[path])
            line = 'meshlets_excluding ' + json.dumps(path) + ' ' + str(len(excluded)) + ' ' + ' '.join(map(str, excluded))
    s.lines.append(line)
assert len(found) == len(replacement) == 3
s.mesh(component / 'regional_vegetation.clm')
stem = out / 'candidate'
s.save(stem.with_suffix('.cys'))
metadata = {'scope': 'Complete current Isla Vista with an explicit regional aggregate-foliage geometry tier.',
    'source_scene_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'vegetation_validation': validation,
    'geography': 'Same 7,939 retained mapped tree roots and actual visible height envelopes. No new scatter or invented geographic canopy polygons.',
    'geometry_representation': 'Branch-supported foliage group facets and coalesced palm-frond coverage. These are aggregates of unresolved leaves, not metre-scale individual blades. Original detailed near-street meshes are preserved for their separate close-view scene.',
    'material_change': False,
    'fixed_view_tier': True, 'dynamic_lod_or_streaming': False,
    'tone_mapping': 'Unchanged simple ACES fitted curve and sRGB at exposure 1.05, with three centre-hit guided atrous passes.',
    'limits': 'No transport-equivalent simplification, calibrated canopy cover, surveyed crown architecture, ecological dynamics or realtime claim. The 2000-pixel version, if requested, changes only image resolution; it is an offline CPU capture.'}
(out / 'CANDIDATE_PREPARATION.json').write_text(json.dumps(metadata, indent=2) + '\n')
if args.prepare_only:
    print(json.dumps({'scene': str(stem.with_suffix('.cys'))}), flush=True)
else:
    report = render(s, stem, metadata=metadata)
    print(json.dumps({key: report.get(key) for key in ['width', 'height', 'primitives', 'render_seconds', 'invalid_path_samples', 'engine_source_sha256']}), flush=True)
