"""Current integrated city, with distinct source-based cameras and components.

Large analytic-wood text is joined in a temporary native input for each render.
Exact retained controls, body hash and full-input hash reproduce that input;
no duplicate 104 MB scene bodies are retained for every camera.
"""
from pathlib import Path
import argparse,hashlib,json,math,re,shlex,shutil,struct,subprocess,sys,tempfile
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/iv-component-runtime'),str(r/'work/cybr-iv-full/src'),str(r/'whole-iv-vendor')]
import numpy as np
import shapely
from shapely.geometry import shape,Point
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
from cybr_light import Scene,render
from cybr_light.runtime import publish
p=argparse.ArgumentParser();p.add_argument('view',choices=['sabado','lagoon-overlook','lagoon-edge','coastal','del-playa-tight','pardall','sabado-detail']);p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
print('IV_VIEWSET_PHASE admitted',a.view,flush=True)
out=r/f'evidence/full-iv-viewset-{a.view}';out.mkdir(exist_ok=True)
(out/'RENDER_SOURCE_SNAPSHOT.py').write_bytes(Path(__file__).read_bytes())
assert shutil.disk_usage(out).free>(1<<30)+260_000_000
source=r/'evidence/full-iv-active-meshlets-overview/candidate.cys'
dp=r/'evidence/full-iv-del-playa-finish-v2';sab=r/'evidence/full-iv-sabado-frontages';lag=r/'evidence/full-iv-lagoon-context'
sab_receipt=json.loads((sab/'ARCHITECTURE_RECEIPT.json').read_text());lag_receipt=json.loads((lag/'LAGOON_CONTEXT_RECEIPT.json').read_text())
assert sab_receipt['validation']['finite_geometry'] and sab_receipt['validation']['serialized_geometry']['valid_material_references'] and sab_receipt['validation']['serialized_geometry']['nondegenerate_geometry']
replace_sources={b['source_id'] for b in sab_receipt['buildings']+lag_receipt['buildings']}
def load(relative):return json.loads((r/relative).read_text())
facade=load('evidence/full-iv-facades/FACADE_RECEIPT.json');roof=load('evidence/full-iv-regional-roofs/REGIONAL_ROOF_RECEIPT.json');oldroof=load('evidence/full-iv-sourced-roofs/SOURCED_ROOFS_RECEIPT.json')
layout=load('evidence/full-iv-roofs/glb-part-layout.json');prefixes=tuple(x.replace(':','_')+'_' for x in replace_sources)
base_skip={p['component'] for group in layout.values() for p in group['parts'] if p['part'].startswith(prefixes) and p['part'].endswith(('_roof','_walls'))}
skips={'full-iv-roofs__sector.clm':base_skip,'facades.clm':{p['object'] for p in facade['parts'] if p['source'] in replace_sources},'regional_roofs.clm':{p['object'] for p in roof['parts'] if p['source'] in replace_sources},'roofs.clm':{p['object'] for p in oldroof['parts'] if p['source'] in replace_sources}}
street_detail = a.view=='sabado-detail'
metric_paths = street_detail or a.view in {'lagoon-edge','coastal','del-playa-tight'}
street_canopy_skip=set();street_tree_receipt=None
if street_detail:
 street_trees=r/'evidence/full-iv-sabado-street-trees'
 street_tree_receipt=json.loads((street_trees/'VEGETATION_RECEIPT.json').read_text())
 assert json.loads((street_trees/'VEGETATION_VALIDATION.json').read_text())['passed']
 selected={x['source_id'] for x in street_tree_receipt['source_features']}
 regional=load('evidence/full-iv-regional-vegetation/REGIONAL_VEGETATION_RECEIPT.json')
 canopy=load('evidence/full-iv-canopy-supported-crowns/CANOPY_SUPPORTED_CROWNS_RECEIPT.json')
 skips['full-iv-regional-vegetation__regional_vegetation.clm']={x['object'] for x in regional['parts'] if x['source'] in selected}
 street_canopy_skip={x['object'] for x in canopy['parts'] if x['source'] in selected}
 skips['exact_foliage.clm']=street_canopy_skip;skips['retained_wood.clm']=street_canopy_skip

def absolute(line,parent):return re.sub(r'"([^"]+)"',lambda m:json.dumps(str((parent/m[1]).resolve())),line)
def lines(path):return [absolute(x,path.parent) for x in path.read_text().splitlines() if x and not x.startswith('#')]
replacement={};index=171
for line in lines(dp/'materials.cys'):
 if line.startswith('material '):index+=1;replacement[index]=[]
 replacement[index].append(line)
assert sorted(replacement)==list(range(172,185))
if metric_paths:
 # Mapped path objects still used the old atlas slots10/11. Reuse exact
 # established CYBR brushed-concrete fields and their metric frequency.
 current=-1;concrete={185:[],186:[]}
 with source.open() as stream:
  for line in stream:
   if line.startswith('cylinder '):break
   q=shlex.split(line)
   if not q:continue
   if q[0]=='material':current+=1
   if current not in concrete:continue
   if q[0] not in {'material','texture','roughness_texture','nested','metric_bump','coverage','anisotropy'}:continue
   if q[0]!='material':
    q[1]=str({185:10,186:11}.get(int(q[1]),int(q[1])))
    if q[0]=='nested':q[2]=str({185:10,186:11}.get(int(q[2]),int(q[2])))
    if q[0] in {'texture','roughness_texture'}:q[2]=json.dumps(str((source.parent/q[2]).resolve()))
    line=' '.join(q)
   concrete[current].append(line.strip())
 replacement[10]=concrete[185];replacement[11]=concrete[186]
 assert len(concrete[185])==3 and len(concrete[186])==4

# Retain all original inland-water packets except the lagoon being corrected.
remaining=lag/'other_inland_water.clm';water_source=r/'evidence/full-iv-active-meshlets/full-iv-coastal-water__water.clm'
if not remaining.exists():
 lagoon=shape(lag_receipt['full_lagoon_polygon']);dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);removed=kept=packets=0
 with tempfile.NamedTemporaryFile(prefix='iv-inland-',suffix='.clm',delete=False) as dst:
  temp=Path(dst.name);dst.write(b'\0'*16)
  with water_source.open('rb') as src:
   magic,total,n=struct.unpack('<4sQI',src.read(16));assert magic==b'CLM1'
   for _ in range(n):
    nv,nt=struct.unpack('<HH',src.read(4));vb=src.read(nv*44);tb=src.read(nt*11);v=np.frombuffer(vb,'<f4').reshape(nv,11);t=np.frombuffer(tb,dtype);centroids=v[t['indices'],:2].mean(axis=1)
    # All lagoon-area triangles, including the retained OSM/GIS union edge,
    # lie in this disjoint bounding region. Devereux and ocean do not.
    remove=(centroids[:,0]>950)&(centroids[:,0]<1620)&(centroids[:,1]>-810)&(centroids[:,1]<-185);k=int((~remove).sum());removed+=int(remove.sum())
    if k:dst.write(struct.pack('<HH',nv,k)+vb+t[~remove].tobytes());kept+=k;packets+=1
  dst.seek(0);dst.write(struct.pack('<4sQI',b'CLM1',kept,packets))
 publish(temp,remaining)
 (lag/'INLAND_REPLACEMENT_RECEIPT.json').write_text(json.dumps({'source_sha256':hashlib.sha256(water_source.read_bytes()).hexdigest(),'removed_lagoon_triangles':removed,'retained_other_inland_triangles':kept,'retained_attributes_byte_exact':True,'boundary_note':'Prior inland water used the union of clipped OSM and UCSB polygons. This view replaces the lagoon region with the complete UCSB polygon; thin source-disagreement margins remain a geographic uncertainty.'},indent=2)+'\n')
s=Scene();geometry=[];index=-1;directives={'texture','roughness_texture','nested','metric_bump','coverage','anisotropy'}
with source.open() as src:
 for line in src:
  if line.startswith('cylinder '):break
  q=shlex.split(line)
  if not q or q[0].startswith('#'):continue
  if q[0]=='material':
   index+=1
   if index in replacement:s.lines.extend(replacement[index]);continue
  elif q[0] in directives and int(q[1]) in replacement:continue
  if q[0] in ['settings','film_format','render_options','camera']:continue
  if q[0] in ['meshlets','meshlets_excluding']:
   path=(source.parent/q[1]).resolve();skip=set(map(int,q[3:])) if q[0]=='meshlets_excluding' else set();skip|=skips.get(path.name,set())
   if path.parent.name=='full-iv-del-playa-architecture':path=dp/'architecture.clm'
   if path==water_source:path=remaining;skip=set()
   geometry.append(('meshlets_excluding '+json.dumps(str(path))+' '+str(len(skip))+' '+' '.join(map(str,sorted(skip)))) if skip else 'meshlets '+json.dumps(str(path)))
  else:s.lines.append(absolute(line.strip(),source.parent))
assert index==281
s.lines.extend(lines(dp/'cloth_materials.cys'));assert sum(x.startswith('material ') for x in s.lines)==286
s.lines.extend(lines(sab/'materials.cys'));assert sum(x.startswith('material ') for x in s.lines)==302
padding=Scene();padding.materials=302
for _ in range(18):padding.material('diffuse')
s.lines.extend(padding.lines)
lagoon_materials=lines(lag/'materials.cys')
if a.view=='lagoon-edge':
 q=lagoon_materials[0].split();assert q[:2]==['material','plastic'];q[5]='0.08';lagoon_materials[0]=' '.join(q)
s.lines.extend(lagoon_materials);assert sum(x.startswith('material ') for x in s.lines)==331
if a.view=='pardall':
 pardall=r/'evidence/full-iv-pardall-metric-finish';check=json.loads((pardall/'METRIC_FINISH_RECEIPT.json').read_text());assert check['passed'];s.lines.extend(lines(pardall/'materials.cys'));assert sum(x.startswith('material ') for x in s.lines)==333
 geometry=[line.replace(str((r/'evidence/full-iv-pardall/pardall.clm').resolve()),str((pardall/'pardall.clm').resolve())) for line in geometry]
s.lines.extend(geometry);s.mesh(sab/'architecture.clm');s.mesh(lag/'lagoon_context.clm')
if street_detail:s.mesh(street_trees/'vegetation.clm')
if a.view=='lagoon-edge':
 habitat=r/'evidence/full-iv-lagoon-habitat-extension';assert json.loads((habitat/'HABITAT_EXTENSION_VALIDATION.json').read_text())['passed'];s.mesh(habitat/'habitat_extension.clm');s.emit('metric_bump',1)
frame=Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame;dem=DEM(r/'data/full-iv-20261011/dem.tif',frame)
if a.view=='sabado':
 camera=sab_receipt['camera_recommendation'];origin=np.array([519.2692708155955,-291.7469537849538,float(dem.sample(519.2692708155955,-291.7469537849538))+1.7]);target=np.array([566.,-307.,float(dem.sample(566.,-307.))+4.4]);horizontal=68.;vfov=math.degrees(2*math.atan(math.tan(math.radians(horizontal/2))/(1000/700)));basis='Verified mapped north-sidewalk vertex OSM5695821277; authored oblique view along Sabado Tarde toward the source-identified Laguna/Seaside group.'
elif a.view=='sabado-detail':
 origin=np.array([519.2692708155955,-291.7469537849538,float(dem.sample(519.2692708155955,-291.7469537849538))+1.7]);target=np.array([548.,-306.,float(dem.sample(548.,-306.))+4.8]);vfov=38.;basis='Same verified mapped north-sidewalk camera root as the first Sabado frame, with a tighter authored frontage composition. Whole nearby mapped trees use the established detailed botanical tier.'
elif a.view=='lagoon-overlook':
 origin=np.array([1110.,-950.,320.]);target=np.array([1260.,-465.,4.]);vfov=55.;basis='Authored elevated oblique camera showing the complete mapped lagoon and its bounded eastern context; not a street-height or surveyed camera.'
elif a.view=='lagoon-edge':
 from iv_shared_ground import SharedGround
 ground=SharedGround(r/'evidence/full-iv-roofs/measured-terrain-state.npz');xy=np.array([994.0337269633443,-378.97308339473835]);origin=np.r_[xy,ground.height(xy[None])[0]+.142+1.7];target=np.array([1090.,-390.,3.25]);vfov=40.;basis='Eye1.7m above the retained authored path top at a verified point on OSM196222525, source surface=compacted. Looking across the western lagoon channel within complete modeled coverage; camera and path width are authored, water level is the dataset hydroflattened value.'
elif a.view=='pardall':
 origin=np.array([470.,4.,float(dem.sample(470.,4.))+1.7]);target=np.array([483.,18.,float(dem.sample(483.,18.))+3.5]);vfov=38.;basis='Authored close oblique camera toward the officially referenced Pardall Center, grounded to retained terrain near mapped street frontage.'
elif a.view=='coastal':
 origin=np.array([410.,-454.,float(dem.sample(410.,-454.))+1.7]);target=np.array([565.,-495.,2.5]);vfov=46.;basis='Authored low coastal/beach-height view using the current dated geographic water/bathymetry scene.'
else:
 origin=np.array([318.,-395.,float(dem.sample(318.,-395.))+1.7]);target=np.array([318.,-365.,float(dem.sample(318.,-365.))+2.8]);vfov=44.;basis='Tighter frontage view near the mapped Del Playa centerline; eye height above terrain1.7m, framing authored.'
s.settings(1000,700,32,8,2,6,20261011,1.05);s.camera(origin,target,(0,0,1),vfov)
# Every material is defined before geometry, and primitive order is stable.
geom=[x for x in s.lines if x.startswith(('meshlets ','meshlets_excluding '))];s.lines=[x for x in s.lines if not x.startswith(('meshlets ','meshlets_excluding '))]+geom
stem=out/'candidate';s.save(stem.with_suffix('.cys'));wood=r/'evidence/full-iv-canopy-analytic-wood/analytic_wood.cys'
meta={'scope':'Current whole-IV geographic scene plus full sourced lagoon context and individually reference-authored Sabado/DelPlaya buildings.', 'view':a.view,'camera_origin_local_m':origin.tolist(),'camera_target_local_m':target.tolist(),'vertical_fov_degrees':vfov,'camera_basis':basis,'replaced_building_source_ids':sorted(replace_sources),'material_slots302_to319':'Explicit unused reservation so lagoon fixed320..330 and Sabado286..301 bindings remain stable.','denoiser':'Three centre-hit textured-albedo/shading-normal/object/variance guided atrous display passes; no footprint-integrated guide in these views.','tone_mapping':'Unchanged three centre-hit guided atrous display passes, simple ACES fitted curve and sRGB, exposure1.05.','geometry_and_material_limits':'Footprints/floor counts and GIS roots are source anchors. Unobserved architecture, botanical structure and optical conditions are authored estimates. Lagoon hydroflattened dataset level is not observed current water. Regional foliage remains an overview tier outside separately established close geometry.'}
if a.view=='lagoon-edge':
 meta['lagoon_specific_optics']={'IOR':1.333,'unresolved_surface_roughness':.08,'previous_overlook_roughness':.16,'diffuse_return':'Unchanged estimated homogeneous brackish return, not native volume transport.','ripple_field':'Unchanged2.5m metric tile,1.5/.7/.3mm components plus retained resolved long ripples.','state':'Authored smoother calm-surface microfacet state; not an observed wind/water condition.'};meta['lagoon_habitat_extension']='Five recovered complete source polygons extend the existing class response across the old x1300m tile edge; individual shrubs remain authored.'
if metric_paths:meta['mapped_path_finish']='Old generic atlas slots10/11 rebound to exact current original CYBR brushed-concrete fields185/186, .32m physical tile on1.25m charts. Existing path geometry is retained.'
if street_detail:
 meta['near_tree_source_ids']=sorted(selected);meta['near_tree_excluded_analytic_object_ids']=sorted(street_canopy_skip);meta['near_tree_policy']='Replace entire source trees, including all aggregate foliage and analytic wood objects. No crown fragments are clipped.';meta['mapped_path_finish']='Old generic atlas slots10/11 rebound to exact current original CYBR brushed-concrete fields185/186, .32m physical tile on1.25m charts. Existing path geometry is retained.'
(out/'VIEW_PREPARATION.json').write_text(json.dumps(meta,indent=2)+'\n')
if a.prepare_only:print(json.dumps(meta),flush=True);sys.exit(0)
with tempfile.TemporaryDirectory(prefix='iv-varied-native-') as temporary:
 native_scene=Path(temporary)/'scene.cys'
 controls=('\n'.join(absolute(x,out) for x in stem.with_suffix('.cys').read_text().splitlines())+'\n').encode()
 (out/'SCENE_CONTROLS_ABSOLUTE.cys').write_bytes(controls)
 digest=hashlib.sha256();digest.update(controls)
 with native_scene.open('wb') as dst,wood.open('rb') as src:
  dst.write(controls)
  if street_canopy_skip:
   removed_cylinders=0
   for line in src:
    if line.startswith(b'cylinder ') and int(line.split()[2]) in street_canopy_skip:removed_cylinders+=1;continue
    dst.write(line);digest.update(line)
  else:
   for chunk in iter(lambda:src.read(8<<20),b''):dst.write(chunk);digest.update(chunk)
 receipt={'native_input_sha256':digest.hexdigest(),'controls_sha256':hashlib.sha256(controls).hexdigest(),'analytic_body_sha256':hashlib.file_digest(wood.open('rb'),'sha256').hexdigest(),'analytic_body':'evidence/full-iv-canopy-analytic-wood/analytic_wood.cys','rebuild':'Concatenate SCENE_CONTROLS_ABSOLUTE.cys and the exact retained analytic body. Saved candidate.cys contains controls/mesh references for finishing, without the analytic tail; use this receipt for complete rendering.','temporary_body_cleanup':'Automatic only after this native phase; exact controls/body and all radiance/guide outputs retained.'}
 if street_canopy_skip:
  receipt['excluded_analytic_object_ids']=sorted(street_canopy_skip);receipt['removed_cylinders']=removed_cylinders;receipt['rebuild']='Concatenate retained absolute controls with source analytic body, omitting only cylinder lines whose third field is an excluded_analytic_object_id. All retained line bytes and order stay exact.'
 (out/'NATIVE_INPUT_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
 class SavedScene:
  def save(self,path):assert Path(path).resolve()==stem.with_suffix('.cys').resolve();return native_scene
 print('IV_VIEWSET_PHASE native tracing',a.view,flush=True)
 report=render(SavedScene(),stem,metadata=meta)
 print(json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
