"""Matched actual coastal component gate and full-area integration."""
from pathlib import Path
import sys,json,re,shlex,hashlib,argparse
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Scene,render
from cybr_light.finishing import atrous,tonemap,save_png
p=argparse.ArgumentParser();p.add_argument('--view',choices=['fixture','overview'],default='fixture');p.add_argument('--baseline',action='store_true');p.add_argument('--prepare-only',action='store_true');p.add_argument('--samples',type=int,default=16);p.add_argument('--water',choices=['refractive','retained-proxy'],default='refractive');args=p.parse_args();assert args.samples>0
component=r/'evidence/full-iv-coastal-life';out=r/('evidence/full-iv-coastal-life-fixture' if args.view=='fixture' else 'evidence/full-iv-coastal-life-overview');out.mkdir(exist_ok=True)
source=r/'evidence/full-iv-current-overview/whole_iv_region_oblique.cys';old=source.read_text().splitlines();validation=json.loads((component/'SERIALIZED_VALIDATION.json').read_text());assert validation['passed'];bottom=json.loads((component/'BOTTOM_RECEIPT.json').read_text());s=Scene();ocean_replaced=False
for line in old:
 q=shlex.split(line)
 if not q or q[0].startswith('#'):continue
 line=re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line)
 if args.view=='fixture' and q[0] in {'camera','settings','film_format','render_options'}:continue
 if q[0] in {'meshlets','meshlets_excluding'}:
  if args.view=='fixture':continue
  if not args.baseline and q[1].endswith('/full-iv-coastal-water/water.clm'):
   assert q[0]=='meshlets';ids=bottom['replace_old_ocean_objects'];line='meshlets_excluding '+json.dumps(str((source.parent/q[1]).resolve()))+' '+str(len(ids))+' '+' '.join(map(str,ids));ocean_replaced=True
 s.lines.append(line)
assert sum(x.startswith('material ') for x in s.lines)==187
retained_water_material=[x for x in s.lines if x.startswith('material ')][85]
for line in (component/'materials.cys').read_text().splitlines():
 if line.startswith('#'):continue
 if args.water=='retained-proxy':
  if line.startswith('material roughglass '):line=retained_water_material
  if line.startswith('spectrum 190 absorption '):continue
 s.lines.append(re.sub(r'"([^"]+)"',lambda m:json.dumps(str((component/m[1]).resolve())),line))
if args.view=='fixture':
 s.settings(700,450,args.samples,8,2,bands=6,seed=20261011,exposure=1.05);s.camera([50,-1400,450],[50,-1110,0],fov=45,orthographic=True,scale=250)
 if args.baseline:s.mesh(r/'evidence/full-iv-coastal-water/water.clm')
elif not args.baseline:assert ocean_replaced
if not args.baseline:
 for mesh in ['ocean_transport.clm','bottom.clm','kelp.clm']:s.mesh(component/mesh)
stem=out/(('baseline' if args.baseline else 'candidate'+('_proxy' if args.water=='retained-proxy' else ''))+(f'_s{args.samples}' if args.view=='fixture' else ''));s.save(stem.with_suffix('.cys'))
meta={'scope':'Dated2016 source-classified kelp geography and measured CoNED bottom, original CYBR procedural fronds and estimated coastal water optical state. '+('Actual offshore component gate.' if args.view=='fixture' else 'Current complete Isla Vista scene, original matched whole-area camera.'),'baseline':args.baseline,'source_current_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'geometry_validation':validation,'bottom_receipt':bottom,'kelp_receipt':json.loads((component/'KELP_RECEIPT.json').read_text()),'denoiser':'Three center-hit albedo, shading-normal, object, depth and variance guided atrous display passes; depth scaled to camera footprint. No material footprint integration.','tone_mapping':'Simple ACES fitted curve and sRGB encoding, exposure1.05; same display pipeline as baseline. Not OCIO AgX. Raw linear spectral-integrated radiance retained.','limits':'2016 kelp state is distinct from2022 aerial reference. Individual fronds, optical properties and subsurface depth are authored. Bathymetry is a dated compiled DEM, not a current survey. Absorption-only dielectric water has no volumetric coastal backscatter, breaking waves, current solver or ecological dynamics. Roughglass direct-light shadow boundary handling can cause variance; visual gate required. Most regional architecture remains simplified.'}
meta['water_variant']=args.water
if args.water=='retained-proxy':
 meta['water_model_superseding_note']='This selected geographic integration retains the prior opaque native Fresnel surface plus low diffuse water-column-return proxy exactly. It does not use the new absorption-only refractive model. Subsurface kelp and submerged bottom remain occluded; only measured bed above authored water and surface canopy contribute. The refractive diagnostic is preserved separately and was rejected as the regional replacement because it lacks coastal backscatter.'
 meta['scope']='Dated2016 source-classified surface kelp and measured exposed coastal bed in the complete current Isla Vista scene; original procedural plants, unchanged prior proxy water response. '+('Actual offshore component gate.' if args.view=='fixture' else 'Original matched whole-area camera.')
 meta['limits']='Opaque surface water-return proxy retained from the baseline; no underwater optical transport is claimed in this selected variant. The separate refractive diagnostic lacks coastal backscatter. Source canopy is from2016, bed is a dated compilation, and individual plants, water state and sediment reflectance are authored. Most regional architecture remains simplified. No coupled dynamics or realtime claim.'
(out/('BASELINE_PREPARATION.json' if args.baseline else 'CANDIDATE_PREPARATION'+('_PROXY' if args.water=='retained-proxy' else '')+'.json')).write_text(json.dumps(meta,indent=2)+'\n')
if args.prepare_only:print(json.dumps({'prepared_scene':str(stem.with_suffix('.cys'))}));sys.exit(0)
report=render(s,stem,metadata=meta);print(json.dumps({'image':str(stem.with_suffix('.png')),'native':{k:report.get(k) for k in ['width','height','spp','primitives','seconds','invalid_path_samples','engine_source_sha256']}}),flush=True)
