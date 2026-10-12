"""Whole-region and street views of independently authored native components."""
from pathlib import Path
import sys,json,re,argparse,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Scene,render
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
parser=argparse.ArgumentParser();parser.add_argument('views',nargs='*');parser.add_argument('--variant',choices=['prior','grounded','architectural','regional-grounded','streetscape','coastal-classes','coastal-water','sourced-roofs','near-street'],default='architectural');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
base=r/'evidence/full-iv-roofs';out=r/'evidence'/({'prior':'full-iv-neighborhood-reframed','grounded':'full-iv-grounded','architectural':'full-iv-architectural','regional-grounded':'full-iv-regional-grounded','streetscape':'full-iv-streetscape','coastal-classes':'full-iv-coastal-classes','coastal-water':'full-iv-coastal-water','sourced-roofs':'full-iv-sourced-roofs','near-street':'full-iv-near-street'}[args.variant]);out.mkdir(exist_ok=True)
source=base/('material_state.cys' if (base/'material_state.cys').is_file() else 'whole_iv_street.cys');lines=[]
def material_lines(path):
 return [re.sub(r'"([^"]+)"',lambda m:json.dumps(str((path.parent/m[1]).resolve())),x) for x in path.read_text().splitlines() if x.split(' ',1)[0] in {'material','texture','roughness_texture','nested','metric_bump','coverage'}]
lines=material_lines(source);assert sum(x.startswith('material ') for x in lines)==20
if args.variant!='prior':
 frequency=1.25/.18;material=-1
 for i,line in enumerate(lines):
  if line.startswith('material '):
   material+=1
   if material==1:lines[i]=line.replace('material normalmap ','material bumpmap ',1)
  if line.startswith('texture 0 '):lines[i]=f'texture 0 {json.dumps(str((r/"evidence/full-iv-materials/coastal_soil_color_native.pfm").resolve()))} {frequency} {frequency} 1'
  if line.startswith('roughness_texture 0 '):lines[i]=f'roughness_texture 0 {json.dumps(str((r/"evidence/full-iv-materials/coastal_soil_roughness.pfm").resolve()))} {frequency} {frequency} 1'
  if line.startswith('texture 1 '):lines[i]=f'texture 1 {json.dumps(str((r/"evidence/full-iv-materials/coastal_soil_height_metres.pfm").resolve()))} {frequency} {frequency} 1'
 lines.append('metric_bump 1')
botanical='full-iv-botanical-tiered' if args.variant=='prior' else 'full-iv-botanical-dense'
components=[(r/'evidence/full-iv-house-component','COMPONENT_RECEIPT.json','house.clm'),(r/'evidence'/botanical,'BOTANICAL_RECEIPT.json','botanical.clm'),(r/'evidence/full-iv-pardall','PARDALL_RECEIPT.json','pardall.clm')]
if args.variant!='prior':components.append((r/'evidence'/('full-iv-streetscape-contact' if args.variant=='streetscape' else 'full-iv-contact'),'CONTACT_RECEIPT.json','contact.clm'))
if args.variant in {'architectural','regional-grounded','streetscape','coastal-classes','coastal-water','sourced-roofs','near-street'}:components.append((r/'evidence/full-iv-facades','FACADE_RECEIPT.json','facades.clm'))
if args.variant in {'regional-grounded','streetscape'}:components.append((r/'evidence/full-iv-landcover-contact','LANDCOVER_RECEIPT.json','landcover.clm'))
skip=[];receipts=[]
for folder,receipt_name,mesh in components:
 receipt=json.loads((folder/receipt_name).read_text());receipt_materials=material_lines(folder/'materials.cys');offset=sum(x.startswith('material ') for x in lines)
 if 'material_offset' in receipt:assert offset==receipt['material_offset']
 lines.extend(receipt_materials);skip.extend(receipt['replace_sector_components']);receipts.append({'receipt':str((folder/receipt_name).relative_to(r)),'triangles':receipt['triangles'],'mesh':str((folder/mesh).relative_to(r))})
if args.variant=='streetscape':
 assert sum(x.startswith('material ') for x in lines)==72
 lines.extend(material_lines(r/'evidence/full-iv-street-materials/materials.cys'))
if args.variant in {'coastal-classes','coastal-water','sourced-roofs','near-street'}:
 assert sum(x.startswith('material ') for x in lines)==72
 reserved=Scene();reserved.material('diffuse');reserved.material('diffuse');lines.extend([x for x in reserved.lines if x.startswith('material ')])
 folder=r/'evidence/full-iv-coastal-classes';receipt_name='COASTAL_CLASSES_RECEIPT.json';mesh='coastal.clm';receipt=json.loads((folder/receipt_name).read_text());assert sum(x.startswith('material ') for x in lines)==receipt['material_offset'];lines.extend(material_lines(folder/'materials.cys'));skip.extend(receipt['replace_sector_components']);receipts.append({'receipt':str((folder/receipt_name).relative_to(r)),'triangles':receipt['triangles'],'mesh':str((folder/mesh).relative_to(r))});components.append((folder,receipt_name,mesh))
if args.variant in {'coastal-water','sourced-roofs','near-street'}:
 folder=r/'evidence/full-iv-coastal-water';receipt_name='WATER_RECEIPT.json';mesh='water.clm';receipt=json.loads((folder/receipt_name).read_text());assert sum(x.startswith('material ') for x in lines)==receipt['material_offset'];lines.extend(material_lines(folder/'materials.cys'));skip.extend(receipt['replace_sector_components']);receipts.append({'receipt':str((folder/receipt_name).relative_to(r)),'triangles':receipt['triangles'],'mesh':str((folder/mesh).relative_to(r))});components.append((folder,receipt_name,mesh))
if args.variant in {'sourced-roofs','near-street'}:
 folder=r/'evidence/full-iv-sourced-roofs';receipt_name='SOURCED_ROOFS_RECEIPT.json';mesh='roofs.clm';receipt=json.loads((folder/receipt_name).read_text());assert sum(x.startswith('material ') for x in lines)==receipt['material_offset'];lines.extend(material_lines(folder/'materials.cys'));skip.extend(receipt['replace_sector_components']);receipts.append({'receipt':str((folder/receipt_name).relative_to(r)),'triangles':receipt['triangles'],'mesh':str((folder/mesh).relative_to(r))});components.append((folder,receipt_name,mesh))
near_receipt=None
if args.variant=='near-street':
 folder=r/'evidence/full-iv-near-street-vegetation';receipt_name='VEGETATION_RECEIPT.json';mesh='vegetation.clm';near_receipt=json.loads((folder/receipt_name).read_text());assert sum(x.startswith('material ') for x in lines)==near_receipt['material_offset'];skip.extend(near_receipt['replace_sector_components']);components.append((folder,receipt_name,mesh));receipts.append({'receipt':str((folder/receipt_name).relative_to(r)),'triangles':near_receipt['triangles'],'mesh':str((folder/mesh).relative_to(r)),'excluded_prior_botanical_objects':len(near_receipt['exclude_prior_botanical_objects'])})
assert len(skip)==len(set(skip))
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame)
for view in args.views or ['region-oblique']:
 print('BEGIN neighborhood view',view,flush=True)
 s=Scene();s.lines=lines.copy();s.settings(1000,700,24 if view=='region-oblique' else 32,8,2,6,20261011,1.05);camera_check={}
 if view=='region-oblique':
  origin=np.array([20.,-1370,1500]);target=np.array([20.,-70,0]);up=np.array([0.,0,1]);scale=1600.;s.camera(origin,target,up,45,orthographic=True,scale=scale)
  from shapely.geometry import shape
  boundary=json.loads((r/'evidence/whole-iv-coverage/isla_vista_cdp.geojson').read_text());poly=shape(boundary['features'][0]['geometry']) if 'features' in boundary else shape(boundary['geometry'] if 'geometry' in boundary else boundary)
  rings=[]
  for p in (poly.geoms if hasattr(poly,'geoms') else [poly]):rings.extend(list(p.exterior.coords))
  ll=np.asarray(rings);x,y=sector.frame.local(ll[:,0],ll[:,1]);xyz=np.c_[x,y,dem.sample(x,y)]
  f=(target-origin)/np.linalg.norm(target-origin);right=np.cross(f,up);right/=np.linalg.norm(right);top=np.cross(right,f);delta=xyz-origin
  ndc=np.c_[delta@right/(scale*.5*1000/700),delta@top/(scale*.5)];assert np.max(abs(ndc))<1
  # The full image footprint at the reference zero-height plane stays inside
  # the acquired tile; the framing keeps the complete CDP visible.
  corners=[]
  for xx in [-1,1]:
   for yy in [-1,1]:
    o=origin+right*xx*scale*.5*1000/700+top*yy*scale*.5;corners.append((o+f*(-o[2]/f[2])).tolist())
  assert np.max(abs(np.array(corners)[:,:2]))<1300
  camera_check={'all_cdp_boundary_vertices_in_frame':True,'maximum_abs_ndc':float(np.max(abs(ndc))),'image_ground_footprint_local_m':corners,'whole_frame_within_source_tile_at_reference_plane':True}
 elif view=='street':
  native_camera=next(x for x in (base/'whole_iv_street.cys').read_text().splitlines() if x.startswith('camera '));s.lines.append(native_camera)
 elif view=='pardall':
  from shapely.geometry import shape
  f=next(f for f in json.loads((base/'normalized.geojson').read_text())['features'] if f['id']=='osm:way:828562491');a=np.array(shape(f['geometry']).interpolate(50).coords[0]);s.camera((*a,dem.sample(*a)+1.7),(483,18,float(dem.sample(483,18))+3.15),(0,0,1),64)
 elif view=='del-playa':
  from shapely.geometry import shape
  feature=next(f for f in json.loads((base/'normalized.geojson').read_text())['features'] if f['id']=='osm:way:50978848');line=shape(feature['geometry']);a=np.array(line.interpolate(350).coords[0]);b=np.array(line.interpolate(400).coords[0]);s.camera((*a,dem.sample(*a)+1.7),(*b,dem.sample(*b)+1.55),(0,0,1),62)
  camera_check={'camera_source_road':feature['id'],'source_road_name':'Del Playa Drive','eye_height_above_DEM_m':1.7,'look_direction':'Along source centerline toward increasing arclength; height and framing are authored.'}
 elif view=='ground':
  a=np.array([451.,0.]);b=a+np.array([1.1,.25]);s.camera((*a,dem.sample(*a)+.62),(*b,dem.sample(*b)+.08),(0,0,1),56)
 else:raise ValueError(view)
 s.emit('observer',json.dumps(str((r/'work/cybr-light/data/CIE_xyz_1931_2deg.csv').resolve())));s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str((r/'evidence/coherent-daylight/native_sky.pfm').resolve())),0);s.emit('environment_sun',day['sun_direction'],day['native_solar_irradiance_controls'],day['solar_radius_radians'])
 s.emit('meshlets_excluding',json.dumps(str((base/'sector.clm').resolve())),len(skip),*skip)
 for folder,_,mesh in components:
  if near_receipt is not None and folder.name=='full-iv-botanical-dense':
   excluded=near_receipt['exclude_prior_botanical_objects'];s.emit('meshlets_excluding',json.dumps(str((folder/mesh).resolve())),len(excluded),*excluded)
  else:s.mesh(folder/mesh)
 if args.prepare_only:
  s.save(out/('whole_iv_'+view.replace('-','_')+'.cys'));print('PREPARED',view,'excluded',len(skip),'component_triangles',sum(x['triangles'] for x in receipts),'camera_check',camera_check,flush=True);continue
 report=render(s,out/('whole_iv_'+view.replace('-','_')),metadata={'generator':'CYBR full Isla Vista geographic scene with reference-authored components','variant':args.variant,'coordinate_contract':sector.metadata(),'coverage':json.loads((r/'evidence/whole-iv-coverage/COVERAGE.json').read_text()),'camera_coverage_check':camera_check,'components':receipts,'replaced_base_objects':len(skip),'scope':'Entire Census Isla Vista CDP plus context in the acquired geographic tile. Pardall Center and retained 6503 are individually reference-authored. When the architectural variant is selected, mapped buildings receive illustrative typed openings, facade finishes and unseen backing; these are not observations of each building. Retained footprints and supplied floor counts remain source anchors. Paving contact, curb heights and local transition profiles are authored construction estimates. Retained tree positions/taxonomy are sourced, dimensions estimated. Additional habitat-class shrub and grass positions, canopy dimensions, reflectance and seasonal state are explicitly authored within mapped polygons. Fixed spatial detail tiers, no dynamic streaming, real-time benchmark, measured reflectance or survey-grade facade claim.'})
 print('COMPLETED',view,json.dumps(report),flush=True)
