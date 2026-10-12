"""Matched regional analytic-wood capture using the unchanged native renderer."""
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
component=r/'evidence/full-iv-canopy-analytic-wood'
check=json.loads((component/'SERIALIZED_VALIDATION.json').read_text());assert check['passed']
source=r/'evidence/full-iv-canopy-supported-crowns-overview/candidate.cys'
out=r/'evidence/full-iv-canopy-analytic-wood-overview';out.mkdir(exist_ok=True)
stem=out/'candidate';scene=stem.with_suffix('.cys')
assert shutil.disk_usage(out).free>(1<<30)+240_000_000
s=Scene();found=0;materials=[]
for line in source.read_text().splitlines():
 q=shlex.split(line)
 if not q or q[0].startswith('#'):continue
 if q[0]=='material':materials.append(line)
 if q[0] in ['texture','roughness_texture','shader','nested','metric_bump','bump_scale','uv_checker','checker']:
  assert q[1]!='39','Analytic wood UV/tint contract needs separate transport adaptation'
 if q[0]=='meshlets' and (source.parent/q[1]).resolve()==(r/'evidence/full-iv-canopy-supported-crowns/canopy_supported_crowns.clm').resolve():
  found+=1;continue
 s.lines.append(re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line))
assert found==1 and shlex.split(materials[39])[1]=='plastic'
s.mesh(component/'exact_foliage.clm');s.mesh(component/'retained_wood.clm');s.save(scene)
with scene.open('ab') as target,(component/'analytic_wood.cys').open('rb') as source_stream:
 shutil.copyfileobj(source_stream,target,8<<20)

class ExistingScene:
 def save(self,path):
  assert Path(path).resolve()==scene.resolve();return scene

metadata={'scope':'Whole Isla Vista with unchanged geographically supported foliage and area-matched analytic thin wood.',
 'foliage_byte_identical':True,'validation':check,'wood_material':materials[39],
 'approximation':'Subpixel woody tubes become uncapped constant-radius cylinders; taper and faceted normals are approximated. Original trunks and height-bound exceptions retain exact triangles.',
 'material_change':False,'daylight_change':False,'camera_change':False,
 'tone_mapping':'Unchanged three centre-hit guided atrous passes, simple ACES fitted curve and sRGB, exposure1.05.'}
(out/'CANDIDATE_PREPARATION.json').write_text(json.dumps(metadata,indent=2)+'\n')
if a.prepare_only:print(json.dumps({'scene':str(scene)}),flush=True)
else:
 report=render(ExistingScene(),stem,metadata=metadata)
 print(json.dumps({k:report.get(k) for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
