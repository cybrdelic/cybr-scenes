from pathlib import Path
import json,hashlib,shutil,argparse
p=argparse.ArgumentParser();p.add_argument('--da',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();base=a.da.resolve();out=a.out.resolve();here=Path(__file__).resolve().parent;assert not out.exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();m=json.loads((base/'runtime/pipeline/manifest.json').read_text());pin=hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest();assert pin in ['b45bd6c125d0e8e7e932f593f3ad6910cabb7e73099b93d1c075eed764da1d53','22a034e68f52bdbde901e83833b2ecad6bac8a7b2947b2115f917899cebe57c9'];bank=base/'runtime/pipeline/pipeline_snapshots'/pin
if not bank.is_dir():bank=base/'runtime/pipeline'
for n,h in m.items():assert sha(bank/n)==h
shutil.copytree(base/'runtime',out/'runtime',ignore=shutil.ignore_patterns('pipeline_snapshots','__pycache__'))
for n in m:
 shutil.copyfile(bank/n,out/'runtime/pipeline'/n)
 if n.endswith('.py'):shutil.copyfile(bank/n,out/'runtime/src'/n)
s=(out/'runtime/pipeline/render_landform_candidate.py').read_text();anchor="  if job.get('source_relative_burial_da'):";assert s.count(anchor)==1;s=s.replace(anchor,"  if job.get('geometry_soil_normals_db'):\n   extra_sources['geometry_soil_normals_db.py']=pathlib.Path(__file__).resolve().parent.parent/'src/geometry_soil_normals_db.py'\n   extra_sources['receiver_probe.py']=pathlib.Path(__file__).resolve().parent.parent/'src/receiver_probe.py'\n\n"+anchor)
anchor=' cull_adaptation=camera_cull_dense_offscreen(job,s)';assert s.count(anchor)==1;s=s.replace(anchor," if job.get('geometry_soil_normals_db'):\n  from geometry_soil_normals_db import apply as geometry_soil_normals_db\n  report=geometry_soil_normals_db(s,job['geometry_soil_normals_db'],pathlib.Path(job['output']).parent);adaptations.append({'geometry_soil_normals_db':report})\n  from receiver_probe import probe as receiver_probe_db\n  if job['visible_fine_grains_cz'].get('close_center'):receiver_probe_db(s,pathlib.Path(job['output']).parent)\n"+anchor)
for n in ('render.py','render_landform_candidate.py'):
 for sub in ('pipeline','src'):(out/'runtime'/sub/n).write_text(s)
 m[n]=sha(out/'runtime/pipeline'/n)
for n,path in [('geometry_soil_normals_db.py',here/'geometry_soil_normals_db.py'),('receiver_probe.py',here/'receiver_probe.py')]:
 for sub in ('pipeline','src'):shutil.copyfile(path,out/'runtime'/sub/n)
 m[n]=sha(path)
(out/'runtime/pipeline/manifest.json').write_text(json.dumps(m,indent=2)+'\n');j=json.loads((base/'job.json').read_text());j['output']=str(out/'INTERNAL_PANEL.png');j['geometry_soil_normals_db']={'revision':1};j['view_scope']='DB matched actual broad-soil normal repair, using current real terrain topology. Geometry, grain material/size/position, source microfields, camera and lighting unchanged.';(out/'job.json').write_text(json.dumps(j,indent=2)+'\n');print(out)
