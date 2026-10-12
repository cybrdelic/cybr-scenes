"""Recover authored Sabado/Del Playa detail without waiting for coastal caches.

Same retained source assemblies and material IDs as the full-region viewset.
This gate does not stand in for the later complete canopy/coastal assembly.
"""
from pathlib import Path
import argparse, hashlib, json, math, re, shlex, subprocess, sys
import numpy as np
from cybr_light import Scene, render
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/'work/cybr-iv-full/src'),str(R/'whole-iv-vendor')]
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
p=argparse.ArgumentParser();p.add_argument('view',choices=['sabado','del-playa']);p.add_argument('--width',type=int,default=600);p.add_argument('--spp',type=int,default=32);p.add_argument('--street-trees',action='store_true');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
assert 64<=a.width<=2000 and 1<=a.spp<=256
OUT=R/'evidence/whole-iv-recovered-views';OUT.mkdir(exist_ok=True)
(OUT/'FRONTAGE_CAPTURE_SOURCE_SNAPSHOT.py').write_bytes(Path(__file__).read_bytes())
subprocess.run([sys.executable,str(R/'tools/replay_retained_iv_script.py'),'render_iv_neighborhood.py','pardall','--variant','architectural','--prepare-only'],check=True,cwd=R)
base=R/'evidence/full-iv-architectural/whole_iv_pardall.cys'
dp=R/'evidence/full-iv-del-playa-finish-v2';sab=R/'evidence/full-iv-sabado-frontages';walk=R/'evidence/full-iv-del-playa-walks'
def load(p):return json.loads(p.read_text())
def lines(p):return [re.sub(r'"([^\"]+)"',lambda m:json.dumps(str((p.parent/m[1]).resolve())),line) for line in p.read_text().splitlines() if line and not line.startswith('#')]
dp_r=load(dp/'ARCHITECTURE_RECEIPT.json');sab_r=load(sab/'ARCHITECTURE_RECEIPT.json')
skip_base=set(dp_r['replace_sector_components'])|set(sab_r['replace_sector_components'])
skip_facade=set(dp_r['exclude_prior_facade_objects'])|set(sab_r['exclude_prior_facade_objects'])
skip_botany=set();tree_folder=None;tree_r=None
if a.street_trees:
 tree_folder=R/'evidence'/('full-iv-sabado-street-trees' if a.view=='sabado' else 'full-iv-near-street-vegetation')
 tree_r=load(tree_folder/'VEGETATION_RECEIPT.json');skip_base.update(tree_r['replace_sector_components']);skip_botany.update(tree_r['exclude_prior_botanical_objects'])
s=Scene();geometry=[]
for line in lines(base):
 q=shlex.split(line)
 if q[0] in {'settings','film_format','render_options','camera'}:continue
 if q[0] in {'meshlets','meshlets_excluding'}:
  path=Path(q[1]);excluded=set(map(int,q[3:])) if q[0]=='meshlets_excluding' else set()
  if path.name=='sector.clm':excluded.update(skip_base)
  elif path.name=='facades.clm':excluded.update(skip_facade)
  elif path.name=='botanical.clm':excluded.update(skip_botany)
  elif path.name=='contact.clm':
   repaired=R/'evidence/full-iv-path-uv-rebased'
   assert load(repaired/'UV_REBASE_RECEIPT.json')['all_non_uv_fields_exact']
   path=repaired/'contact.clm'
  geometry.append('meshlets_excluding '+json.dumps(str(path))+' '+str(len(excluded))+' '+' '.join(map(str,sorted(excluded))) if excluded else 'meshlets '+json.dumps(str(path)))
 else:s.lines.append(line)
assert sum(x.startswith('material ') for x in s.lines)==72
def pad_to(n):
 s.materials=sum(x.startswith('material ') for x in s.lines)
 assert s.materials<=n
 while s.materials<n:s.material('diffuse')
pad_to(172);s.lines.extend(lines(dp/'materials.cys'))
assert sum(x.startswith('material ') for x in s.lines)==185
s.lines.extend(lines(walk/'materials.cys'));pad_to(282)
s.lines.extend(lines(dp/'cloth_materials.cys'));s.lines.extend(lines(sab/'materials.cys'))
assert sum(x.startswith('material ') for x in s.lines)==302
# Use the same established metric concrete finish on the retained path slots.
blocks={};current=-1
for line in s.lines:
 if line.startswith('material '):current+=1
 if current in {185,186} and line.split()[0] in {'material','texture','roughness_texture','nested','metric_bump'}:
  q=shlex.split(line)
  if q[0]!='material':q[1]=str({185:10,186:11}.get(int(q[1]),int(q[1])))
  if q[0]=='nested':q[2]=str({185:10,186:11}.get(int(q[2]),int(q[2])))
  if q[0] in {'texture','roughness_texture'}:q[2]=json.dumps(q[2])
  blocks.setdefault(current,[]).append(' '.join(q))
assert len(blocks[185])==3 and len(blocks[186])==4
new=[];current=-1
for line in s.lines:
 if line.startswith('material '):
  current+=1
  if current in {10,11}:new.extend(blocks[{10:185,11:186}[current]]);continue
 elif current in {10,11} and line.split()[0] in {'texture','roughness_texture','nested','metric_bump'}:continue
 new.append(line)
s.lines=new
dem=DEM(R/'data/full-iv-20261011/dem.tif',Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame)
if a.view=='sabado':
 xy=np.array([519.2692708155955,-291.7469537849538]);origin=np.r_[xy,dem.sample(*xy)+1.7];target=np.array([566.,-307.,dem.sample(566.,-307.)+4.4]);fov=math.degrees(2*math.atan(math.tan(math.radians(34))/(1000/700)))
 camera_basis='Retained OSM5695821277 north-sidewalk root; authored view along Sabado Tarde toward individually referenced frontages.'
else:
 origin=np.array([318.,-395.,dem.sample(318.,-395.)+1.7]);target=np.array([318.,-365.,dem.sample(318.,-365.)+2.8]);fov=44.
 camera_basis='Retained bounded Del Playa frontage view at authored eye height above the source terrain.'
s.settings(a.width,round(a.width*.7),a.spp,8,2,6,20261012,1.05);s.camera(origin,target,(0,0,1),fov)
s.lines.extend(geometry)
for f in [dp/'architecture.clm',sab/'architecture.clm',walk/'walks.clm']:s.mesh(f)
if tree_folder:s.mesh(tree_folder/'vegetation.clm')
stem=OUT/f'{a.view}_frontages_{a.width}_{a.spp}';s.save(stem.with_suffix('.cys'))
subprocess.run([sys.executable,str(R/'work/audit_scene_metric_uv.py'),str(stem.with_suffix('.cys'))],check=True)
if a.prepare_only:raise SystemExit(0)
report=render(s,stem,metadata={'purpose':'Recovered original street/frontage assemblies, not a new photoreal improvement claim','view':a.view,'camera_basis':camera_basis,'camera_origin_m':origin.tolist(),'camera_target_m':target.tolist(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'replaced_building_source_ids':[b['source_id'] for b in dp_r['buildings']+sab_r['buildings']],'material_count':302,'street_tree_tier':bool(tree_folder),'remaining_limits':'Regional canopy support and coastal scene restoration are still in progress. Architecture dimensions, unseen elevations, roughness and reflectance remain authored estimates. Photographs are references only, not textures.','rendering':'Actual installed original CYBR LIGHT native CPU engine, with original GEO and MATERIAL source.'})
print('RECOVERED_FRONTAGE_RENDER',json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
