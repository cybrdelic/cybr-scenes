"""Capture connected bank state with the actual separate installed LIGHT engine."""
from pathlib import Path
import argparse,json,re,sys
import cybrlight.scene_compat as compatibility
from cybrlight.scene_compat import runtime,finishing
sys.modules['cybr_light']=compatibility;sys.modules['cybr_light.runtime']=runtime;sys.modules['cybr_light.finishing']=finishing
from rebuild_lagoon_v11b import *
BASE=OUT;EXTRA=R/'evidence/lagoon-restoration-v12'
p=argparse.ArgumentParser();p.add_argument('--width',type=int,default=960);p.add_argument('--spp',type=int,default=32);p.add_argument('--view',choices=['basin','lagoon-context','lagoon-west','lagoon-east-bank','lagoon-upper-bank','lagoon-overlook'],default='lagoon-west');a=p.parse_args()
views={'lagoon-overlook':(CAMERA,TARGET,65.),'lagoon-upper-bank':(np.array([1400.,-455.,11.95]),np.array([1310.,-490.,4.]),58.),'lagoon-east-bank':(np.array([1460.,-490.,10.43]),np.array([1330.,-459.,6.4]),57.),'basin':(CAMERA,TARGET,49.),'lagoon-context':(np.array([1400.,-498.,11.]),np.array([1328.,-454.,6.8]),55.),'lagoon-west':(np.array([1400.,-498.,5.75]),np.array([1240.,-412.,4.15]),58.)};origin,target,fov=views[a.view]
light=json.loads((BASE/'LIGHT.json').read_text());s=Scene();s.lines=(BASE/'materials.cys').read_text().splitlines();s.lines=[re.sub(r'"([^\"]+)"',lambda m:json.dumps(str((BASE/m[1]).resolve())),line) for line in s.lines]
s.settings(a.width,round(a.width*.7),a.spp,8,2,6,20261012,1.05);s.camera(origin,target,(0,0,1),fov)
s.emit('observer',json.dumps(str(R/'work/cybr-light/data/CIE_xyz_1931_2deg.csv')));s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str(BASE/'coastal_diffuse_sky.pfm')),0);s.emit('environment_sun',DAY['sun_direction'],light['native_sun'],DAY['solar_radius_radians'])
for name in ['ground','architecture','plants']:s.mesh((EXTRA if name=='ground' else BASE)/(name+'.clm'))
s.mesh(EXTRA/'understory.clm');stem=EXTRA/f'{a.view}_{a.width}_{a.spp}';s.save(stem.with_suffix('.cys'))
import subprocess
subprocess.run([sys.executable,str(R/'work/audit_scene_metric_uv.py'),str(stem.with_suffix('.cys'))],check=True)
report=render(s,stem,metadata={'scope':'Complete mapped lagoon and surrounding geographic context with coherent bank understory and contact litter.','rendering':'Actual native CYBR LIGHT CPU. No image generation, photograph textures or scene geography replacement.','display':'Retained centre-hit guided atrous, ACES fitted and sRGB at exposure1.05.','authoring_estimates':['Understory patch occupancy, abundance and season','Organic contact reflectance modulation, not moisture simulation','Leaf/litter morphology','Basin dimensions/level and architecture details retained authored estimates'],'camera':{'name':a.view,'origin_m':origin.tolist(),'target_m':target.tolist(),'vertical_fov_degrees':fov,'qualification':'Virtual authored terrestrial-bank camera, not a recovered photograph pose.'}})
print('V12_RENDER',json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
