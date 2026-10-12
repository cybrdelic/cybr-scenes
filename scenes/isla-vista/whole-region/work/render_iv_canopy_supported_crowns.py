"""Matched whole-area capture of geographically supported crown construction."""
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
p.add_argument('--prepare-only', action='store_true')
a = p.parse_args()
component = r / 'evidence/full-iv-canopy-supported-crowns'
receipt = json.loads((component / 'CANOPY_SUPPORTED_CROWNS_RECEIPT.json').read_text())
validation = json.loads((component / 'SERIALIZED_VALIDATION.json').read_text())
assert validation['passed']
source = r / 'evidence/full-iv-regional-vegetation-overview/candidate.cys'
out = r / 'evidence/full-iv-canopy-supported-crowns-overview'
out.mkdir(exist_ok=True)
target_mesh = (r / 'evidence/full-iv-regional-vegetation/regional_vegetation.clm').resolve()
excluded = receipt['replaced_regional_objects']
s, found = Scene(), 0
for line in source.read_text().splitlines():
    q = shlex.split(line)
    if not q or q[0].startswith('#'):
        continue
    line = re.sub(r'"([^"]+)"', lambda m: json.dumps(str((source.parent / m[1]).resolve())), line)
    if q[0] in {'meshlets', 'meshlets_excluding'} and (source.parent / q[1]).resolve() == target_mesh:
        prior = set(map(int, q[3:])) if q[0] == 'meshlets_excluding' else set()
        ids = sorted(prior | set(excluded))
        line = 'meshlets_excluding ' + json.dumps(str(target_mesh)) + ' ' + str(len(ids)) + ' ' + ' '.join(map(str, ids))
        found += 1
    s.lines.append(line)
assert found == 1
s.mesh(component / 'canopy_supported_crowns.clm')
stem = out / 'candidate'
s.save(stem.with_suffix('.cys'))
metadata = {'scope': 'Complete current Isla Vista, same whole-area camera, with eligible existing broadleaf crowns constrained by dated classified canopy support.',
    'source_scene_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'validation': validation,
    'new_mapped_roots': 0, 'material_change': False, 'daylight_change': False,
    'source_canopy_year': 2022, 'tree_correspondence_and_crown_architecture_are_authored': True,
    'limits': 'Classification does not identify exact trees or heights. Unassociated classified canopy is left unfilled. Existing palms, conifers and unassociated trees remain in their prior regional form. Geographic source points and visible height envelopes are retained.',
    'tone_mapping': 'Unchanged three centre-hit guided atrous passes, simple ACES fitted curve and sRGB, exposure 1.05.'}
(out / 'CANDIDATE_PREPARATION.json').write_text(json.dumps(metadata, indent=2) + '\n')
if a.prepare_only:
    print(json.dumps({'scene': str(stem.with_suffix('.cys'))}), flush=True)
else:
    report = render(s, stem, metadata=metadata)
    print(json.dumps({key: report.get(key) for key in ['width', 'height', 'primitives', 'render_seconds', 'invalid_path_samples']}), flush=True)
