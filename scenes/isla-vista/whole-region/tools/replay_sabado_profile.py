"""Bounded authored Sabado profile replay after the whole-region baseline."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action',choices=['build','render']);p.add_argument('--spp',type=int,choices=[32,128],default=32)
a=p.parse_args()
if a.action=='build':
 commands=[('profile',['tools/replay_retained_iv_script.py','reprofile_sabado_sidewalk_v1.py']),
           ('conform',['tools/replay_retained_iv_script.py','reconcile_sabado_profile_edges_v2.py']),
           ('serialized-check',['work/verify_sabado_reconciled_v1.py','--target','evidence/sabado-profile-closed-v2/contact.clm']),
           ('adjacent-check',['work/check_sabado_adjacent_edges_v1.py','--target','evidence/sabado-profile-closed-v2/contact.clm'])]
else:
 commands=[('render-'+str(a.spp),['tools/replay_retained_iv_script.py','capture_sabado_profile_v2.py','--mesh','evidence/sabado-profile-closed-v2/contact.clm','--verification','evidence/sabado-profile-closed-v2/SERIALIZED_SURFACE_VERIFICATION.json','--spp',str(a.spp)])]
folder=R/'evidence/sabado-profile-replay';folder.mkdir(parents=True,exist_ok=True)
for name,command in commands:
 receipt=folder/(name+'.guard.json')
 if receipt.exists():
  raise SystemExit('Existing receipt is not a cache-validity proof. Preserve prior generated outputs and use a fresh replay tree: '+str(receipt))
 cmd=['flock','-w','1800',os.environ.get('CYBR_HEAVY_LOCK',str(R.parent/'cybr-heavy.lock')),
      'taskset','-c','0,1',sys.executable,str(R/'tools/run_lagoon_stage.py'),
      '--log',str(folder/(name+'.log')),'--receipt',str(receipt),'--seconds','900','--',sys.executable,*command]
 print('SABADO_PROFILE_STAGE',name,flush=True)
 subprocess.run(cmd,cwd=R,check=True)
 assert json.loads(receipt.read_text())['passed']
