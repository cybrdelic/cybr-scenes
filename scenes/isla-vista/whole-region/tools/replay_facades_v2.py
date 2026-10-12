"""Bounded optional facade v2 construction and matched native replay."""
from pathlib import Path
import argparse,json,os,subprocess,sys
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','render','close']);p.add_argument('--spp',type=int,choices=[32,128],default=32);a=p.parse_args()
if a.action=='close' and a.spp!=32:raise SystemExit('The reviewed close gate uses32 packets; use its direct script for other diagnostic settings.')
if a.action=='build':
 commands=[('primitive-fixture',['work/test_iv_facade_assemblies.py']),('build',['tools/replay_retained_iv_script.py','build_iv_facade_types_v2.py']),('serialized',['work/verify_iv_facades_v2.py'])]
elif a.action=='close':commands=[('close-'+str(a.spp),['tools/replay_retained_iv_script.py','capture_iv_facade_close_v2.py','--spp',str(a.spp)])]
else:commands=[('render-'+str(a.spp),['tools/replay_retained_iv_script.py','capture_iv_facades_v2.py','--spp',str(a.spp)])]
folder=R/'evidence/facade-v2-replay';folder.mkdir(parents=True,exist_ok=True)
for name,command in commands:
 receipt=folder/(name+'.guard.json')
 if receipt.exists():raise SystemExit('Existing receipt is not cache validity. Preserve outputs and use a fresh replay tree: '+str(receipt))
 cmd=['flock','-w','1800',os.environ.get('CYBR_HEAVY_LOCK',str(R.parent/'cybr-heavy.lock')),'taskset','-c','0,1',sys.executable,str(R/'tools/run_lagoon_stage.py'),'--log',str(folder/(name+'.log')),'--receipt',str(receipt),'--seconds','900','--',sys.executable,*command]
 print('FACADE_V2_STAGE',name,flush=True);subprocess.run(cmd,cwd=R,check=True);assert json.loads(receipt.read_text())['passed']
