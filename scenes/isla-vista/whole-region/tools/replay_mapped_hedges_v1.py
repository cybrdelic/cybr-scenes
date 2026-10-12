"""Bounded optional mapped-hedge fixture; no automatic whole-scene integration."""
from pathlib import Path
import argparse,json,os,subprocess,sys
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','render','baseline']);p.add_argument('--spp',type=int,choices=[16,32,64],default=32);p.add_argument('--lai',type=float,choices=[2.8,4.5],default=4.5);a=p.parse_args()
if a.action=='build':
 commands=[('units',['test_iv_mapped_hedges_v1.py']),('build',['iv_mapped_hedges_v1.py','build','--lai',str(a.lai)]),('verify',['iv_mapped_hedges_v1.py','verify']),('exclusions',['test_iv_mapped_hedge_coverage.py'])]
else:
 commands=[(a.action+'-'+str(a.spp),['capture_iv_mapped_hedges_v1.py','--spp',str(a.spp)]+(['--baseline'] if a.action=='baseline' else []))]
folder=R/'evidence/mapped-hedges-v1/replay';folder.mkdir(parents=True,exist_ok=True)
for name,command in commands:
 receipt=folder/(name+'.guard.json')
 if receipt.exists():raise SystemExit('Existing receipt does not prove cache validity. Preserve outputs and use a fresh replay tree: '+str(receipt))
 cmd=['flock','-w','1800',os.environ.get('CYBR_HEAVY_LOCK',str(R.parent/'cybr-heavy.lock')),'taskset','-c','0,1',sys.executable,str(R/'tools/run_lagoon_stage.py'),'--log',str(folder/(name+'.log')),'--receipt',str(receipt),'--seconds','900','--',sys.executable,str(R/'tools/replay_retained_iv_script.py'),*command]
 print('MAPPED_HEDGE_STAGE',name,flush=True);subprocess.run(cmd,cwd=R,check=True);assert json.loads(receipt.read_text())['passed']
