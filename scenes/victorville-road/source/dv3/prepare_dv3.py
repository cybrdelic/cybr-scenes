"""Prepare the opt-in plant-only correction over admitted DU5, never edit it."""
from pathlib import Path
import argparse,subprocess,sys,json,hashlib,shutil
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--du5-root',type=Path,default=R.parent/'du5');p.add_argument('--dr-root',type=Path,default=R.parent/'dr');p.add_argument('--material-root',required=True,type=Path);p.add_argument('--output-root',required=True,type=Path);p.add_argument('--view',choices=['crop','normal'],default='crop');a=p.parse_args()
D=a.du5_root.resolve();M=a.material_root.resolve();O=a.output_root.resolve();assert not O.exists();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins=json.loads((R/'MATERIAL_DEPENDENCY.json').read_text())
for row in pins['files']:assert sha(M/row['path'])==row['sha256'],row['path']
subprocess.run([sys.executable,str(D/'prepare_du5.py'),'--dr-root',str(a.dr_root.resolve()),'--material-root',str(M),'--output-root',str(O),'--view','normal'],check=True)
modules=['apply_woody_scene.py','woody_form.py','wood_surface.py'];cfg={'kind':3,'revision':3}
for name in modules:shutil.copy2(R/name,O/'runtime/src'/name)
for key,row in zip(['bark_source','bark_profile'],pins['files']):
 target=O/'runtime/src'/Path(row['path']).name;shutil.copy2(M/row['path'],target);cfg[key]=str(target);cfg[key+'_sha256']=sha(target)
for name in ['render.py','render_landform_candidate.py']:
 file=O/'runtime/pipeline'/name;s=file.read_text();key='  pipeline=pipeline_snapshot(extra_sources)';assert s.count(key)==1
 names=tuple(modules+[Path(r['path']).name for r in pins['files']]);s=s.replace(key,"  if job.get('dv_woody_form'):\n   for name in "+repr(names)+":extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name\n"+key);file.write_text(s)
file=O/'runtime/src/geometry_soil_normals_db.py';s=file.read_text();key=" candidate=geometry(scene,cfg['du'],out)";assert s.count(key)==1;s=s.replace(key,key+"\n from apply_woody_scene import apply as apply_dv\n plant=apply_dv(scene,cfg['dv'],out)");s=s.replace("'DU_candidate':candidate}","'DU_candidate':candidate,'DV_plant_candidate':plant}");file.write_text(s)
file=O/'job.json';job=json.loads(file.read_text());job['geometry_soil_normals_db']['dv']=cfg;job['dv_woody_form']=cfg
if a.view=='crop':job['render_border']=[450/2000,1300/2000,34/1334,814/1334]
job['view_scope']='DV3 plant-only correction over admitted DU5. Native 850x780 crop or separately qualified normal view. Same soil, clasts, grain banks, existing transforms, camera, lights and mountains.';file.write_text(json.dumps(job,indent=2)+'\n')
(O/'DV_PREPARATION.json').write_text(json.dumps({'source_files':{n:sha(R/n)for n in modules},'material_dependencies':pins,'native_full_size':[2000,1334],'crop_pixels_top_left':[450,520,1300,1300]if a.view=='crop'else None,'clast_candidates_included':False,'accepted_DR_and_DU5_edited':False,'view':a.view},indent=2)+'\n');print(file)
