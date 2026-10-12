"""A source-anchored hedge gate in fresh base geography, never final integration."""
from pathlib import Path
import argparse, json, re, sys
import numpy as np
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/'work'),str(R/'geo-deps'),str(R/'whole-iv-vendor')]
from iv_mapped_hedges_v1 import BASE, OUT, FIXTURE, source, digest, verify
from iv_shared_ground import SharedGround
from shapely.geometry import shape,Point
from shapely.ops import nearest_points
from cybr_light import Scene,render

p=argparse.ArgumentParser();p.add_argument('--spp',type=int,default=32);p.add_argument('--baseline',action='store_true');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
assert a.spp in [16,32,64]
verify()
features=source();byid={x['id']:x for x in features};g=shape(byid[FIXTURE]['geometry']);mid=g.interpolate(.5,normalized=True);m=np.array(mid.coords[0])
roads=[x for x in features if x['properties']['category']=='road' and x['properties']['source_properties'].get('name')]
road=min(roads,key=lambda x:shape(x['geometry']).distance(mid));rg=shape(road['geometry']);nearest=np.array(nearest_points(mid,rg)[1].coords[0]);n=nearest-m;n/=np.linalg.norm(n);t=np.array([-n[1],n[0]])
xy=m+n*4.6+t*.8
assert not any(shape(x['geometry']).covers(Point(xy)) for x in features if x['properties']['category']=='building')
ground=SharedGround(BASE/'measured-terrain-state.npz');origin=np.r_[xy,ground.height(xy[None])[0]+1.65];target=np.r_[m,ground.height(m[None])[0]+.72]

def lines(path):
    return [re.sub(r'"([^"]+)"',lambda x:json.dumps(str((path.parent/x[1]).resolve())),line) for line in path.read_text().splitlines() if line and not line.startswith('#')]

s=Scene();s.lines=lines(BASE/'material_state.cys');offset=sum(x.startswith('material ') for x in s.lines)
build=json.loads((OUT/'fixture/BUILD.json').read_text());assert offset==build['material_offset'],(offset,build['material_offset'])
s.lines+=lines(OUT/'fixture/materials.cys')
s.settings(700,490,a.spp,8,2,6,20261012,1.05);s.camera(origin,target,(0,0,1),53)
day=json.loads((R/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
# The licensed CIE table is a separate repository input, not included in the
# isolated installed runtime snapshot. Do not follow its historical data link.
observer=R.parent/'work/cybr-light/data/CIE_xyz_1931_2deg.csv'
assert observer.is_file()
s.emit('observer',json.dumps(str(observer.resolve())))
s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str((R/'evidence/coherent-daylight/native_sky.pfm').resolve())),0);s.emit('environment_sun',day['sun_direction'],day['native_solar_irradiance_controls'],day['solar_radius_radians'])
s.mesh(BASE/'sector.clm')
if not a.baseline:s.mesh(OUT/'fixture/hedges.clm')
stem=OUT/'fixture'/('pasado_baseline_700_'+str(a.spp) if a.baseline else 'pasado_hedge_700_'+str(a.spp))
meta={'purpose':'Small actual mapped Pasado Road hedge construction gate; fresh base context only, not current complete scene integration','source_id':FIXTURE,'source_url':'https://www.openstreetmap.org/way/'+FIXTURE.rsplit(':',1)[1],'nearest_named_road':road['id'],'road_name':road['properties']['source_properties']['name'],'source_hedge_geometry':byid[FIXTURE]['geometry'],'camera_origin_m':origin.tolist(),'camera_target_m':target.tolist(),'authored_camera':'1.65 m eye, 4.6 m toward mapped road and 0.8 m along it, 53-degree FOV','camera_outside_mapped_buildings':True,'geometry_variant':'base without hedge' if a.baseline else 'source-supported optional hedge','ground_geometry':'Unchanged freshly regenerated retained stage-1 ground','one_sided_lai':build['source_features'][0]['actual_one_sided_lai'],'baseline_mesh_sha256':digest(BASE/'sector.clm'),'hedge_mesh_sha256':digest(OUT/'fixture/hedges.clm'),'source_sha256':digest(Path(__file__)),'limits':'Hedge height/line width, generic species form, stem/shoot topology, leaf dimensions, LAI and optics are authored estimates. Surrounding architecture is base mapped massing. Merged facade/sidewalk and dedicated assemblies are unchanged; this isolated gate does not replay or replace their integrated scene. Native LIGHT, no image generation or photo textures.'}
s.save(stem.with_suffix('.cys'));(stem.with_name(stem.name+'_CAMERA.json')).write_text(json.dumps(meta,indent=2)+'\n')
if a.prepare_only:print(json.dumps(meta),flush=True)
else:
    result=render(s,stem,metadata=meta)
    print(json.dumps({k:result[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
