"""Tagged roofs and source-linked street material in the full IV geography."""
from pathlib import Path
import json,sys,re,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor']:sys.path.insert(0,str(p))
from cybr_ucsb.rendering import prepare
from cybr_light import Scene,render
from cybr_light.runtime import read_pfm
from cybr_terrain.materials import write_pfm
from cybr_ucsb.ingest import DEM
from cybr_ucsb.coordinates import Sector
out=r/'evidence/full-iv-roofs';assets=prepare(out);mat=r/'evidence/full-iv-materials';mat.mkdir(exist_ok=True)
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.asarray(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inv=np.linalg.inv(M)
# Authored kinematic surface, not measured sea state or coupled water solver.
y,x=np.mgrid[0:512,0:512]/512
water_height=.070*np.sin(2*np.pi*(2*x+y))+.032*np.sin(2*np.pi*(7*x-4*y))+.010*np.sin(2*np.pi*(15*x+11*y))
write_pfm(mat/'water_height_metres.pfm',np.repeat(water_height[:,:,None],3,axis=2).astype('f4'))
write_pfm(mat/'water_roughness.pfm',np.full((2,2,3),.045,dtype='f4'))
raw=[x for x in (out/'materials.cys').read_text().splitlines() if x and not x.startswith('#')]
lines=[];material_lines={};material_index=0;metric_ids=[];fits=[]
for line in raw:
 if line.startswith('material '):material_lines[material_index]=len(lines);material_index+=1
 match=re.search(r'"([^"]+)"',line)
 if match:
  path=(out/match[1]).resolve();name=path.name;parts=line.split();mid=int(parts[1])
  if name.startswith('asphalt_'):
   suffix='color_native' if name.endswith('_color.pfm') else 'height_metres' if name.endswith('_normal.pfm') else 'roughness';path=mat/f'asphalt_{suffix}.pfm';line=parts[0]+' '+str(mid)+' '+json.dumps(str(path.resolve()))+' 5 5 1'
   if suffix=='height_metres':metric_ids.append(mid)
  elif name.startswith('water-surface-proxy_'):
   if name.endswith('_normal.pfm'):path=mat/'water_height_metres.pfm';line='texture '+str(mid)+' '+json.dumps(str(path.resolve()))+' .078125 .078125 1';metric_ids.append(mid)
   elif name.endswith('_roughness.pfm'):path=mat/'water_roughness.pfm';line='roughness_texture '+str(mid)+' '+json.dumps(str(path.resolve()))+' 1 1 1'
   else:
    controls=(np.array([.003,.016,.027])*white)@inv.T;path=mat/'water_color_native.pfm';write_pfm(path,np.broadcast_to(controls,(2,2,3)).astype('f4'));line='texture '+str(mid)+' '+json.dumps(str(path.resolve()))+' 1 1 1'
    fields=lines[material_lines[mid]].split();fields[6]='1.333';lines[material_lines[mid]]=' '.join(fields)
  elif name.endswith('_color.pfm'):
   rgb=read_pfm(path);controls=(rgb*white)@inv.T
   if controls.min() < -1e-6:raise ValueError('Negative reflectance control')
   target=path.with_name(path.stem+'_native.pfm');write_pfm(target,np.maximum(0,controls));line=line[:match.start()]+json.dumps(str(target))+line[match.end():]
  else:line=line[:match.start()]+json.dumps(str(path))+line[match.end():]
 lines.append(line)
for mid in metric_ids:
 i=material_lines[mid];lines[i]=lines[i].replace('material normalmap','material bumpmap');lines.append('metric_bump '+str(mid))
if '--prepare-only' in sys.argv:
 prepared=Scene();prepared.lines=lines.copy();prepared.save(out/'material_state.cys');print('PREPARED full-IV native material state',flush=True);sys.exit(0)
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame)
for view in sys.argv[1:] or ['overview']:
 s=Scene();s.lines=lines.copy();s.settings(1000,700,48 if view!='overview' else 32,8,2,6,20261011,1.05)
 if view=='overview':s.camera((-450,-1640,1600),(0,0,7),(0,0,1),54)
 elif view=='street':
  from shapely.geometry import shape
  f=next(f for f in json.loads((out/'normalized.geojson').read_text())['features'] if f['id']=='osm:way:828562491');line=shape(f['geometry']);a=np.array(line.interpolate(18).coords[0]);b=np.array(line.interpolate(92).coords[0]);s.camera((*a,dem.sample(*a)+1.7),(*b,dem.sample(*b)+1.45),(0,0,1),64)
 elif view=='ground':
  a=np.array([451.,0.]);b=a+np.array([1.1,.25]);s.camera((*a,dem.sample(*a)+.62),(*b,dem.sample(*b)+.08),(0,0,1),56)
 elif view=='north-up':s.camera((0,0,2600),(0,0,0),(0,1,0),45,orthographic=True,scale=1950)
 else:raise ValueError(view)
 s.emit('observer',json.dumps(str((r/'work/cybr-light/data/CIE_xyz_1931_2deg.csv').resolve())))
 s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str((r/'evidence/coherent-daylight/native_sky.pfm').resolve())),0);s.emit('environment_sun',day['sun_direction'],day['native_solar_irradiance_controls'],day['solar_radius_radians']);s.mesh(out/'sector.clm')
 report=render(s,out/('whole_iv_'+view),metadata={'generator':'CYBR all-Isla-Vista tagged roof and street-material candidate','coordinate_contract':sector.metadata(),'source_triangles':assets['triangles'],'tagged_roof_count':json.loads((out/'TAGGED_ROOFS.json').read_text())['count'],'asphalt_source':'Current Materials master retained dense reference construction, native1024 prototype at0.25m. Not current selected fracture appearance parity.','water':'Estimated surface-only Fresnel/diffuse proxy at IOR1.333 with three kinematic metric wave bands across16m. No measured bathymetry, volume scattering or coupled simulation asserted.','scope':'Geographic neighborhood with sourced roof tags. Missing facade, crown and height details remain explicit; street view reveals remaining limits.'})
 print('COMPLETED',view,json.dumps(report),flush=True)
