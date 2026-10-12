"""Small native street gates of the recovered original whole-IV assemblies.

This is a recovery checkpoint, not a photoreal quality claim. Cameras, OSM
footprints and independently authored frontage details remain distinguishable.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys
from cybr_light import Scene, render

R = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--view', choices=['street', 'pardall', 'del-playa'], default='pardall')
p.add_argument('--variant', choices=['architectural', 'regional-grounded', 'near-street'], default='architectural')
p.add_argument('--width', type=int, default=480)
p.add_argument('--spp', type=int, default=16)
a = p.parse_args()
assert 64 <= a.width <= 2000 and 1 <= a.spp <= 256
OUT = R / 'evidence/whole-iv-recovered-views'
OUT.mkdir(exist_ok=True)
source = Path(__file__)
(OUT / 'CAPTURE_SOURCE_SNAPSHOT.py').write_bytes(source.read_bytes())
subprocess.run([sys.executable, str(R/'tools/replay_retained_iv_script.py'),
                'render_iv_neighborhood.py', a.view, '--variant', a.variant,
                '--prepare-only'], check=True, cwd=R)
folder = {'architectural':'full-iv-architectural',
          'regional-grounded':'full-iv-regional-grounded',
          'near-street':'full-iv-near-street'}[a.variant]
prepared = R/'evidence'/folder/('whole_iv_'+a.view.replace('-', '_')+'.cys')
s = Scene()
s.lines = [line for line in prepared.read_text().splitlines()
           if not line.startswith(('settings ', 'film_format ', 'render_options '))]
s.settings(a.width, round(a.width*.7), a.spp, 8, 2, 6, 20261012, 1.05)
stem = OUT / f'{a.view}_{a.variant}_{a.width}_{a.spp}'
s.save(stem.with_suffix('.cys'))
report = render(s, stem, metadata={
    'purpose':'Native recovery gate of retained full-Isla-Vista residential, street and geographic assemblies',
    'scene_variant':a.variant,
    'scope':'Mapped OSM and UCSB geometry across the acquired geographic region. Geographically placed generic façades are authored estimates, not photographic reconstructions.',
    'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'lighting':'Retained independently card-validated coherent clear daylight. This is an authored light state, not measured weather.',
    'quality_limit':'Recovery checkpoint. No claim of completed whole-IV photoreal improvement.',
    'rendering':'Actual installed CYBR LIGHT scene_compat CPU engine; no image generation.'})
print('RECOVERED_STREET_RENDER', json.dumps({k:report[k] for k in
      ['width','height','primitives','render_seconds','invalid_path_samples']}), flush=True)
