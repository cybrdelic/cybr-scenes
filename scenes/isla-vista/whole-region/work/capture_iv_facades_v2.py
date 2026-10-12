"""Matched native scene: replace generic facade by source identity only."""
from pathlib import Path
import argparse,hashlib,json,re,shlex,subprocess,sys
from cybr_light import Scene,render
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--spp',type=int,default=32);p.add_argument('--prepare-only',action='store_true');a=p.parse_args();assert a.spp in [16,32,128]
out=R/'evidence/facades-v2-native';out.mkdir(exist_ok=True)
source=R/'evidence/sabado-profile-matched-v2/sabado_profile_600_32.cys'
old_dir=R/'evidence/full-iv-facades';new_dir=R/'evidence/full-iv-facades-v2'
old=json.loads((old_dir/'FACADE_RECEIPT.json').read_text());new=json.loads((new_dir/'FACADE_RECEIPT.json').read_text());verification=json.loads((new_dir/'SERIALIZED_GEOMETRY_VERIFICATION.json').read_text());assert verification['passed']
assert hashlib.sha256((new_dir/'facades.clm').read_bytes()).hexdigest()==verification['target_sha256']
old_by_object={x['object']:x['source'] for x in old['parts']}
lines=[];changed=0;skip_sources=set();inventory=[]
for line in source.read_text().splitlines():
 if not line or line.startswith('#'):continue
 line=re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line)
 q=shlex.split(line)
 if q[0]=='settings':q[3]=str(a.spp);line=' '.join(q)
 if q[0] in {'meshlets','meshlets_excluding'}:
  path=Path(q[1]);excluded=set(map(int,q[3:])) if q[0]=='meshlets_excluding' else set()
  if path==old_dir/'facades.clm':
   skip_sources={old_by_object[x] for x in excluded}
   excluded={x['object'] for x in new['parts'] if x['source'] in skip_sources}
   path=new_dir/'facades.clm';line='meshlets_excluding '+json.dumps(str(path))+' '+str(len(excluded))+' '+' '.join(map(str,sorted(excluded)));changed+=1
  inventory.append({'path':str(path.relative_to(R)),'excluded_objects':len(excluded),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 lines.append(line)
assert changed==1
# All dedicated source properties continue using their original authored meshes.
dedicated_sources=set()
for name in ['full-iv-del-playa-finish-v2','full-iv-sabado-frontages']:
 receipt=json.loads((R/'evidence'/name/'ARCHITECTURE_RECEIPT.json').read_text())
 dedicated_sources.update(b['source_id'] for b in receipt['buildings'])
assert skip_sources==dedicated_sources, (sorted(skip_sources),sorted(dedicated_sources))
new_active_sources={x['source'] for x in new['parts'] if x['source'] not in skip_sources}
assert not new_active_sources & dedicated_sources
scene=Scene();scene.lines=lines;stem=out/f'sabado_facades_v2_600_{a.spp}';scene.save(stem.with_suffix('.cys'))
meta={'purpose':'Matched original Sabado view, reusable generic facade construction v2','source_baseline_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'new_mesh_sha256':verification['target_sha256'],'material_camera_lighting_and_dedicated_meshes_unchanged':True,'dedicated_sources_exactly_excluded':True,'excluded_generic_sources_for_dedicated_components':sorted(skip_sources),'active_mesh_inventory':inventory,'geometry_estimates':'Building-level window proportions, closed frames, inset glass/backing, side curtain panels, and <=42 mm roof-edge trim. Exact current mapped wall footprints, floor counts and roof geometry retained. Frontage estimated from through-streets, not driveways.','limits':'Unknown building forms remain illustrative. Existing road/paving finish and broader planting limitations remain. Roof source restoration beyond this captured baseline is not silently added.'}
(stem.with_name(stem.name+'_SCENE_CONTRACT.json')).write_text(json.dumps(meta,indent=2)+'\n')
subprocess.run([sys.executable,str(R/'work/audit_scene_metric_uv.py'),str(stem.with_suffix('.cys'))],check=True)
if a.prepare_only:raise SystemExit()
report=render(scene,stem,metadata=meta);print(json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
