"""Exact active-geometry storage gate with unchanged native transport."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import shutil
import sys
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/iv-component-runtime')]
from cybr_light import Scene,render
p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
component=r/'evidence/full-iv-active-meshlets';check=json.loads((component/'ACTIVE_MESHLET_BUILD.json').read_text());assert check['passed']
source=r/'evidence/full-iv-canopy-analytic-wood-overview/candidate.cys'
out=r/'evidence/full-iv-active-meshlets-overview';out.mkdir(exist_ok=True)
stem=out/'candidate';scene=stem.with_suffix('.cys')
assert shutil.disk_usage(out).free>(1<<30)+240_000_000
substitutions={(r/x['source']).resolve():x for x in check['meshes']}
s=Scene();found=0
with source.open() as f:
 for line in f:
  if line.startswith('cylinder '):break
  q=shlex.split(line)
  if not q or q[0].startswith('#'):continue
  if q[0]=='meshlets_excluding' and (source.parent/q[1]).resolve() in substitutions:
   row=substitutions[(source.parent/q[1]).resolve()]
   if row['replacement']:s.mesh(r/row['replacement'])
   found+=1;continue
  s.lines.append(re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line.strip()))
assert found==len(substitutions)
s.save(scene)
with scene.open('ab') as target,(r/'evidence/full-iv-canopy-analytic-wood/analytic_wood.cys').open('rb') as wood:
 shutil.copyfileobj(wood,target,8<<20)
class ExistingScene:
 def save(self,path):assert Path(path).resolve()==scene.resolve();return scene
metadata={'scope':'Same whole-Isla-Vista active triangles and analytic wood; excluded packet storage removed from generated input.',
 'geometry_change':False,'material_change':False,'daylight_change':False,'camera_change':False,
 'active_meshlet_build':check,'raw_pixel_parity_pending':True,
 'tone_mapping':'Unchanged three centre-hit guided atrous passes, simple ACES fitted curve and sRGB, exposure1.05.'}
(out/'CANDIDATE_PREPARATION.json').write_text(json.dumps(metadata,indent=2)+'\n')
if a.prepare_only:print(json.dumps({'scene':str(scene)}),flush=True)
else:
 report=render(ExistingScene(),stem,metadata=metadata);print(json.dumps({k:report.get(k) for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
