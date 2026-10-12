"""Stage a visually reviewed DH body gate after an exact DG source pipeline."""
from pathlib import Path
import argparse,hashlib,json,shutil
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--visual-gate',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();b=a.baseline.resolve();out=a.out.resolve();own=Path(__file__).resolve().parent;assert not out.exists()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
j=json.loads((b/'job.json').read_text());assert j.get('historical_grain_roles_dg')and not j.get('coarse_geometry_dh')
manifest=a.manifest.resolve();data=json.loads(manifest.read_text());assert data['revision']==1
gate=json.loads(a.visual_gate.read_text());assert gate['status']=='SUITABLE_FOR_MATCHED_SCENE_TEST'and gate['manifest_sha256']==sha(manifest),'Unreviewed or rejected specimen must not be integrated'
out.mkdir();shutil.copytree(b/'runtime',out/'runtime',ignore=shutil.ignore_patterns('__pycache__','pipeline_snapshots'));i=out/'inputs/coarse';i.mkdir(parents=True);shutil.copy2(manifest,i/manifest.name)
for e in data['entries']:
 source=(manifest.parent/e['npz']).resolve();assert source.is_relative_to(manifest.parent)and sha(source)==e['npz_sha256'];target=i/e['npz'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
files={'apply_weathered_fields.py':a.adapter.resolve(),'check_terrain_contact.py':own/'check_terrain_contact.py','apply_weathered_contact_dh.py':own/'apply_weathered_contact_dh.py'}
for name,source in files.items():shutil.copy2(source,out/'runtime/src'/name)
r=out/'runtime/pipeline/render_landform_candidate.py';s=r.read_text();anchor="  if job.get('geometry_soil_normals_db'):\n";assert s.count(anchor)==1
replacement="  if job.get('coarse_geometry_dh'):\n"+''.join("   extra_sources['"+n+"']=pathlib.Path(__file__).resolve().parent.parent/'src/"+n+"'\n"for n in files)
s=s.replace(anchor,replacement+anchor)
needle=" if job.get('geometry_soil_normals_db'):\n  from geometry_soil_normals_db import apply as geometry_soil_normals_db\n";assert s.count(needle)==1;s=s.replace(needle," if job.get('coarse_geometry_dh'):\n  from apply_weathered_contact_dh import apply as coarse_geometry_dh\n  report=coarse_geometry_dh(s,job['coarse_geometry_dh'],pathlib.Path(job['output']).parent);adaptations.append({'coarse_geometry_dh':report})\n"+needle);compile(s,str(r),'exec');r.write_text(s)
h=j['historical_grain_roles_dg'];j.update(output=str(out/'INTERNAL_PANEL.png'),coarse_geometry_dh={'revision':1,'coarse':{'revision':1,'manifest':str(i/manifest.name),'manifest_sha256':sha(i/manifest.name)},'contact':{'revision':1,'payload':h['payload'],'payload_sha256':h['payload_sha256'],'settle_downward':True,'embedding_m':.000020}},view_scope='DH two-prototype original procedural coarse-body gate after exact DG. Within original metric envelope, with authored shape redistribution and separately accounted representation volumes. Exact current material fields, IDs, XY, yaw and daylight retained. Downward-only true-terrain contact correction if required; no physical weathering-time or transport-event claim.')
(out/'job.json').write_text(json.dumps(j,indent=2)+'\n');(out/'PREPARATION.json').write_text(json.dumps({'baseline_job_sha256':sha(b/'job.json'),'candidate_job_sha256':sha(out/'job.json'),'adapter_files_sha256':{n:sha(out/'runtime/src'/n)for n in files},'manifest_sha256':sha(i/manifest.name),'source_prepared_only':True},indent=2)+'\n');print(out)
