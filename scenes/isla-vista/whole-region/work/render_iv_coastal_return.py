"""Matched depth-return material gate, followed by original whole-IV view."""
from pathlib import Path
import argparse,sys,json,re,shlex,hashlib
r=Path(__file__).resolve().parent.parent
for path in [r/'geo-deps',r/'work/iv-component-runtime']:sys.path.insert(0,str(path))
from cybr_light import Scene,render
from cybr_light.finishing import atrous,tonemap,save_png
p=argparse.ArgumentParser();p.add_argument('--view',choices=['fixture','overview'],default='fixture');p.add_argument('--baseline',action='store_true');p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
component=r/'evidence/full-iv-coastal-return';receipt=json.loads((component/'SPECTRAL_SHADER_RECEIPT.json').read_text());assert receipt['passed']
source=r/('evidence/full-iv-coastal-life-fixture/candidate_proxy_s16.cys' if args.view=='fixture' else 'evidence/full-iv-coastal-life-overview/candidate_proxy.cys');out=r/('evidence/full-iv-coastal-return-fixture' if args.view=='fixture' else 'evidence/full-iv-coastal-return-overview');out.mkdir(exist_ok=True);s=Scene();replaced=0
for line in source.read_text().splitlines():
 q=shlex.split(line)
 if not q or q[0].startswith('#'):continue
 if args.view=='fixture' and q[0] in {'settings','camera','film_format','render_options'}:continue
 if not args.baseline and q[0]=='meshlets' and q[1].endswith('/ocean_transport.clm'):replaced+=1;continue
 s.lines.append(re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line))
assert sum(x.startswith('material ') for x in s.lines)==191
if not args.baseline:
 assert replaced==1
 for line in (component/'materials_spectral.cys').read_text().splitlines():
  if not line.startswith('#'):s.lines.append(re.sub(r'"([^"]+)"',lambda m:json.dumps(str((component/m[1]).resolve())),line))
 s.mesh(component/'water_return_spectral.clm')
if args.view=='fixture':s.settings(700,450,24,8,2,bands=6,seed=20261011,exposure=1.05);s.camera([300,-970,450],[300,-680,0],orthographic=True,scale=240,fov=45)
stem=out/('baseline' if args.baseline else 'candidate');s.save(stem.with_suffix('.cys'))
metadata={'scope':'Matched actual coastal-depth material comparison.' if args.view=='fixture' else 'Complete current Isla Vista in the original whole-area camera, with source-depth-dependent coastal water return.','baseline':args.baseline,'source_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'water_return_model':receipt,'material_only_change':True,'positions_normals_preserved':True,'uv_depth_attribute':not args.baseline,'spectral_shader_used':not args.baseline,'denoiser':'Three centre-hit albedo, shading-normal, object, depth and variance guided atrous display passes; no new material-footprint integration.','tone_mapping':'Simple ACES fitted curve and sRGB, exposure1.05, unchanged from baseline. Not OCIO AgX.','limits':'Qualified surface-return approximation under native Fresnel, not native volume transport. Homogeneous authored absorption/backscatter and bottom reflectance; measured dated bed depth. No recovered local optical measurement. Nadir model extended as a Lambertian return to an oblique view; no transferred Hydrolight accuracy claim, underwater parallax or refractive object visibility. Dated2016 canopy and current city remain unchanged.'}
(out/('BASELINE_PREPARATION.json' if args.baseline else 'CANDIDATE_PREPARATION.json')).write_text(json.dumps(metadata,indent=2)+'\n')
if args.prepare_only:print(json.dumps({'scene':str(stem.with_suffix('.cys'))}));sys.exit(0)
report=render(s,stem,metadata=metadata);print(json.dumps({k:report.get(k) for k in ['primitives','render_seconds','invalid_path_samples','engine_source_sha256']}),flush=True)
