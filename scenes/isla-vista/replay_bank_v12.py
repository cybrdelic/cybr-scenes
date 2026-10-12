"""Replay the additive bank checkpoint on the verified bounded lagoon base."""
from pathlib import Path
import argparse,json,runpy,sys
from replay import runtime_contract
from public_inputs import resolve
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('action',choices=['build','check','capture']);p.add_argument('--width',type=int,default=600);p.add_argument('--spp',type=int,default=32);a=p.parse_args()
resolve(ROOT,False);print('LIGHT_DEPENDENCY',json.dumps(runtime_contract()),flush=True)
sys.path.insert(0,str(ROOT/'work'))
script={'build':'enrich_lagoon_ground_v12.py','check':'check_lagoon_v12_contracts.py','capture':'capture_lagoon_v12.py'}[a.action]
sys.argv=[str(ROOT/'work'/script)]
if a.action=='capture':sys.argv+=['--view','lagoon-overlook','--width',str(a.width),'--spp',str(a.spp)]
runpy.run_path(sys.argv[0],run_name='__main__')
