"""Prepare DG in the established full source pipeline; cache is optional.
This creates only source/config files, never geometry or images.
"""
from pathlib import Path
import argparse,hashlib,json,shutil
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--close-centre',nargs=2,type=float);p.add_argument('--native-close-proof',action='store_true');a=p.parse_args();b=a.baseline.resolve();runtime=a.runtime.resolve();out=a.out.resolve();own=Path(__file__).resolve().parent;assert not out.exists()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
j=json.loads((b/'job.json').read_text());assert not j.get('coupled_fine_burial_df') and not j.get('historical_grain_roles_dg');out.mkdir();shutil.copytree(runtime,out/'runtime',ignore=shutil.ignore_patterns('__pycache__'))
names=['historical_grain_roles_dg.py','history_budget_dg.py','transported_grain_exposure_dg.py']
for name in names:shutil.copy2(own/name,out/'runtime/src'/name)
r=out/'runtime/pipeline/render_landform_candidate.py';s=r.read_text();anchor="  if job.get('geometry_soil_normals_db'):\n";assert s.count(anchor)==1
extra="  if job.get('historical_grain_roles_dg'):\n"+''.join("   extra_sources[%r]=pathlib.Path(__file__).resolve().parent.parent/'src'/%r\n"%(n,n)for n in names);s=s.replace(anchor,extra+anchor)
needle=" if job.get('geometry_soil_normals_db'):\n  from geometry_soil_normals_db import apply as geometry_soil_normals_db\n";assert s.count(needle)==1;s=s.replace(needle," if job.get('historical_grain_roles_dg'):\n  from historical_grain_roles_dg import apply as historical_grain_roles_dg\n  report=historical_grain_roles_dg(s,job['historical_grain_roles_dg'],pathlib.Path(job['output']).parent);adaptations.append({'historical_grain_roles_dg':report})\n"+needle);compile(s,str(r),'exec');r.write_text(s)
ce=j['coupled_shoulder_ce'];ci=j['fixed_gravel_support_ci'];cz=j['visible_fine_grains_cz'];da=j['source_relative_burial_da'];cfg={'revision':1,'payload':ce['payload'],'payload_sha256':ce['payload_sha256'],'historical_fields':ci['historical_fields'],'historical_fields_sha256':ci['historical_fields_sha256'],'sand_bank':cz['sand_bank'],'sand_bank_sha256':cz['sand_bank_sha256'],'datums':da['datums'],'datums_sha256':da['datums_sha256']}
for key in ('payload','historical_fields','sand_bank','datums'):assert sha(cfg[key])==cfg[key+'_sha256']
j.update(output=str(out/'INTERNAL_PANEL.png'),historical_grain_roles_dg=cfg,view_scope='DG current-view historical stock and grain roles. Metric source bank and finite ledgers unchanged. Nonvalidated representation coupling, not a site reconstruction or tracked-particle simulation.')
if a.close_centre:
 x,y=a.close_centre;j.update(width=900,height=675,samples=32);j['visible_fine_grains_cz'].update(width=900,height=675,close_center=[x,y],bounds=[x-.3,x+.35,y-.4,y+.35])
if a.native_close_proof:
 assert not a.close_centre, 'Native proof has its pinned close centre'
 j.update(width=900,height=675,samples=32,preview_hide_fully_offscreen_terrain=True,render_border=[2/9,7/9,137/675,537/675])
 j.pop('shadow_probe_da',None)
 j['visible_fine_grains_cz'].update(width=900,height=675,close_center=[-4.9,5.5],bounds=[-5.2,-4.55,5.1,5.85])
(out/'job.json').write_text(json.dumps(j,indent=2)+'\n');(out/'PREPARATION.json').write_text(json.dumps({'baseline_job_sha256':sha(b/'job.json'),'candidate_job_sha256':sha(out/'job.json'),'adapter_sha256':sha(out/'runtime/src/historical_grain_roles_dg.py'),'cache_required':False,'source_prepared_only':True,'fresh_full_parent_replay_verified':False},indent=2)+'\n');print(out)
