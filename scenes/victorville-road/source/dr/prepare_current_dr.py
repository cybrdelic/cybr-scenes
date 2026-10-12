"""Restore the saved DR pipeline through its exact additive source contracts.
Source/configuration preparation only. No rendering or invented replay evidence.
Run after the admitted AV scene and exact CA/CB payloads exist.
"""
from pathlib import Path
import argparse, copy, hashlib, json, shutil, subprocess, sys

R=Path(__file__).resolve().parent;P=R/'packages'
ap=argparse.ArgumentParser();ap.add_argument('--artifacts-root',type=Path,default=R)
args=ap.parse_args();A=args.artifacts_root.resolve()
DR=P/'CYBR_Victorville_DR_Compact_Foreground_Source_Addon/CYBR_Victorville_DR_Compact_Foreground_Source_Addon'
DH=P/'CYBR_Victorville_Ground_Current_Source_v8/CYBR_Victorville_Ground_Current_Source_v8'
CQ=P/'CYBR_Victorville_CQ_CR_Coherent_Surface_Source_v1'
AV=P/'CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15'
capture=A/'packages'/AV.name/'road_scene_r6/captures/av_recovery_oct12'
cache=capture/'av_outward/ASSEMBLED_SCENE_AV.blend'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(script,*args):
 subprocess.run([sys.executable,'-B',str(script),*map(str,args)],check=True)
def save(p,obj):p.write_text(json.dumps(obj,indent=2)+'\n')
assert cache.is_file()
if not (R/'co_prepared').exists():
 run(R/'helpers/prepare_co_replay.py','--unpacked',P,'--av-cache',cache,
  '--z-admission',capture/'source_admission.json','--ca-payload',A/'generated_ca/extension_payload.npz',
  '--cb-payload',A/'generated_cb/edge_payload_step2.npz','--output-dir',R/'co_prepared')
else:
 prior=json.loads((R/'co_prepared/job.json').read_text())
 assert Path(prior['source']).resolve()==cache.resolve() and prior['source_sha256']==sha(cache)
 assert (R/'co_prepared/CO_REPLAY_STAGING.json').is_file()
run(R/'helpers/prepare_cm_candidate.py','--co-staged-dir',R/'co_prepared','--output-dir',R/'cm_prepared')

# Reassemble the saved CQ source bank from the newly prepared exact CM bank.
# The archive contains the exact CQ renderer and adapter. No CM image is faked.
base=R/'cm_prepared';out=R/'cq_prepared';assert not out.exists()
cm=json.loads((base/'runtime/pipeline/manifest.json').read_text())
pin=hashlib.sha256(json.dumps(cm,sort_keys=True).encode()).hexdigest()
assert pin=='6ea55e74a5253398f3bc78fd10d0068f818e48b3eeccefbf3cd62bb1f7f48057'
bank=base/'runtime/pipeline/pipeline_snapshots'/pin
shutil.copytree(base/'runtime',out/'runtime',ignore=shutil.ignore_patterns('pipeline_snapshots','__pycache__'))
for name,h in cm.items():
 assert sha(bank/name)==h
 shutil.copy2(bank/name,out/'runtime/pipeline'/name)
 if name.endswith('.py'):shutil.copy2(bank/name,out/'runtime/src'/name)
manifest=json.loads((CQ/'captured_pipeline_reference/manifest.json').read_text())
for sub in ['pipeline','src']:
 for name in ['render.py','render_landform_candidate.py']:
  shutil.copy2(CQ/'captured_pipeline_reference/render_landform_candidate.py',out/'runtime'/sub/name)
 shutil.copy2(CQ/'cq_source/correct_historical_gravel_domain_cq.py',out/'runtime'/sub/'correct_historical_gravel_domain_cq.py')
for name,h in manifest.items():assert sha(out/'runtime/pipeline'/name)==h,name
assert hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()=='067ceffd2795b5c059b8341dd179bdd11ddb53cfbaf669298c50ff4d97999168'
save(out/'runtime/pipeline/manifest.json',manifest)
j=json.loads((base/'job.json').read_text());j['correct_historical_gravel_domain_cq']=copy.deepcopy(j['existing_gravel_cf']);j['output']=str(out/'INTERNAL_PANEL.png');save(out/'job.json',j)
save(out/'SOURCE_REPLAY.json',{'exact_saved_CQ_pipeline_reconstructed':True,'fresh_CM_or_CQ_image_claimed':False})
run(DH/'cz/prepare_addon.py','--cq',out,'--out',R/'cz_prepared','--mode','wide')
run(DH/'da/prepare.py','--cz',R/'cz_prepared','--out',R/'da_prepared','--width',2000,'--height',1334,'--shadow-probe')
run(DH/'db/prepare.py','--da',R/'da_prepared','--out',R/'db_prepared')
run(DH/'de_source/prepare.py','--baseline',R/'db_prepared','--out',R/'de_prepared')
run(DH/'dg_history_source/prepare_full.py','--baseline',R/'de_prepared','--runtime',R/'db_prepared/runtime','--out',R/'dg_prepared')
run(DH/'dh_coarse_source/prepare_full.py','--baseline',R/'dg_prepared','--adapter',DH/'dh_specimens/apply_weathered_fields.py',
 '--manifest',DH/'dh_specimens/CANDIDATE_MANIFEST.json','--visual-gate',DH/'dh_coarse_source/FINAL_SPECIMEN_REVIEW.json','--out',R/'dh_prepared')
run(P/'CYBR_Victorville_DL_Static_Fines_Source_Addon/DL_Static_Fines/prepare_scene.py','--baseline',R/'dh_prepared','--out',R/'dl_prepared')
run(P/'CYBR_Victorville_DM_Static_Domain_Source_Addon/DM_Static_Domain/prepare_scene.py','--baseline',R/'dl_prepared','--out',R/'dm_prepared')

# Restore exact saved DR configuration with only path/cache/output relocation.
out=R/'dr_recovered_whole';assert not out.exists();shutil.copytree(R/'dm_prepared/runtime',out/'runtime',ignore=shutil.ignore_patterns('__pycache__','pipeline_snapshots'))
oldroot='/CYBR_ROOT'
original=json.loads((DR/'prepared_job.json').read_text())
def relocate(v):
 if isinstance(v,dict):return {relocate(k):relocate(x)for k,x in v.items()}
 if isinstance(v,list):return [relocate(x)for x in v]
 if isinstance(v,str)and v.startswith(oldroot):return str(R)+v[len(oldroot):]
 return v
j=relocate(original);j['source']=str(cache);j['source_sha256']=sha(cache);j['output']=str(out/'INTERNAL_PANEL.png')
j['metric_pavement_extension_ca']['payload']=str(A/'generated_ca/extension_payload.npz')
j['continuous_edge_top_cb']['payload']=str(A/'generated_cb/edge_payload_step2.npz')
hook=R/'stable_grains_dq/after_da_hook.py'
bridge='from pathlib import Path\nimport importlib.util,hashlib\ndef apply(scene,cfg,out):\n p=Path('+repr(str(hook))+')\n assert hashlib.sha256(p.read_bytes()).hexdigest()=='+repr(sha(hook))+'\n s=importlib.util.spec_from_file_location("dq_pinned_whole_hook",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m.apply(scene,cfg,out)\n'
(out/'runtime/src/geometry_soil_normals_db.py').write_text(bridge)
pin_count=0
def verify(v):
 global pin_count
 if isinstance(v,dict):
  for k,x in v.items():
   if k=='source_pins':
    for p,h in x.items():assert sha(p)==h,p;pin_count+=1
   else:verify(x)
 elif isinstance(v,list):
  for x in v:verify(x)
verify(j)
missing=[]
def paths(v,key=''):
 if isinstance(v,dict):
  for k,x in v.items():paths(x,k)
 elif isinstance(v,list):
  for x in v:paths(x,key)
 elif isinstance(v,str)and v.startswith('/')and key!='output' and not Path(v).exists():missing.append(v)
paths(j);assert not missing,missing
save(out/'job.json',j)
save(out/'RECOVERY_PREPARATION.json',{'source_pins_checked':pin_count,'all_input_paths_resolved':True,
 'saved_DR_job_sha256':sha(DR/'prepared_job.json'),'new_job_sha256':sha(out/'job.json'),
 'new_AV_cache_sha256':sha(cache),'changes':'Path relocation and rebuilt semantically admitted AV serialization only.',
 'fresh_DR_actual_image_verified':False,'lost_I_result_recovered':False})
print(out)
