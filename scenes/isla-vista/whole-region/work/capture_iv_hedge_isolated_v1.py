"""Cheap native three-quarter hedge architecture gate; not a street beauty frame."""
from pathlib import Path
import argparse,json,re,sys
import numpy as np
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/'work'),str(R/'whole-iv-vendor'),str(R/'geo-deps')]
from iv_mapped_hedges_v1 import OUT,BASE,FIXTURE,source,digest,verify,NativeParts
from iv_shared_ground import SharedGround
from shapely.geometry import shape
from cybr_light import Scene,render
p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
folder=OUT/a.folder;proof=verify(a.folder);build=json.loads((folder/'BUILD.json').read_text());assert build['material_offset']==0
feature=next(f for f in source() if f['id']==FIXTURE);line=shape(feature['geometry']);m=np.array(line.interpolate(.5,normalized=True).coords[0]);t=np.array(line.coords[-1])-np.array(line.coords[0]);t/=np.linalg.norm(t);n=np.array([t[1],-t[0]])
if n[1]>0:n=-n
ground=SharedGround(BASE/'measured-terrain-state.npz');xy=m+n*3.4+t*2.5;origin=np.r_[xy,ground.height(xy[None])[0]+1.60];target=np.r_[m,ground.height(m[None])[0]+.62]
s=Scene();s.lines=[x for x in (folder/'materials.cys').read_text().splitlines() if x and not x.startswith('#')];s.materials=sum(x.startswith('material ') for x in s.lines)
surface=s.material('diffuse',(.22,.22,.22),1)
parts=NativeParts(folder/'diagnostic_ground.clm',14000000)
tri=ground.vertices[ground.faces];keep=np.any(np.linalg.norm(tri[:,:,:2]-m,axis=2)<18,axis=1);q=tri[keep];parts.mesh('retained_ground_neutral',q.reshape(-1,3),np.arange(len(q)*3).reshape(-1,3),surface,'original retained terrain','Neutral untextured diagnostic reflectance only; no soil material evaluation')
parts.close();s.mesh(folder/'diagnostic_ground.clm');s.mesh(folder/'hedges.clm')
s.settings(400,280,16,8,2,6,20261012,1.05);s.camera(origin,target,(0,0,1),48)
day=json.loads((R/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
observer=R.parent/'work/cybr-light/data/CIE_xyz_1931_2deg.csv';s.emit('observer',json.dumps(str(observer.resolve())));s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str((R/'evidence/coherent-daylight/native_sky.pfm').resolve())),0);s.emit('environment_sun',day['sun_direction'],day['native_solar_irradiance_controls'],day['solar_radius_radians'])
stem=folder/'isolated_three_quarter_400_16';meta={'purpose':'Cheap three-quarter silhouette/branch-support gate of actual source-anchored hedge; not final street integration','source_id':FIXTURE,'source_geometry_unchanged':True,'camera_origin_m':origin.tolist(),'camera_target_m':target.tolist(),'authored_lai':build['source_features'][0]['target_one_sided_lai'],'lai_measured_on_site':False,'shoot_distribution':build['shoot_distribution'],'hedge_mesh_sha256':digest(folder/'hedges.clm'),'source_sha256':digest(Path(__file__)),'limits':'Mapped support and retained terrain, neutral untextured diagnostic ground, authored generic branch architecture and leaf-area scenarios. No artificial opacity, billboards, photo textures, or camera-facing leaves.'}
s.save(stem.with_suffix('.cys'));(folder/'ISOLATED_CAMERA.json').write_text(json.dumps(meta,indent=2)+'\n')
if a.prepare_only:print(json.dumps(meta))
else:
    result=render(s,stem,metadata=meta);print(json.dumps({k:result[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
