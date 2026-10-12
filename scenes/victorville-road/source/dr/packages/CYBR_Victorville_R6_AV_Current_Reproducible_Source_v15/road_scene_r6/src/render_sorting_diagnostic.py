import json,hashlib,subprocess,os,sys,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1]
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--variants',nargs='+',choices=['e','i','k','l','m','n','o'],default=['l']);args=ap.parse_args()
for variant in args.variants:
 p=r/('preview/road_r6_'+variant+'.blend');o=r/'captures'/('sorting_'+variant);o.mkdir(exist_ok=True);job={'source':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'engine':'CYCLES','width':1000,'height':667,'samples':24,'capture_mode':'guided','save_guides':True,'light_tree':False,'color_depth':16,'dither_intensity':0,'use_adaptive_sampling':False,'rss_cap_mib':6144,'time_limit_seconds':1800,'sync_limit_seconds':180,'output':str(o/'INTERNAL_PANEL.png')};(o/'job.json').write_text(json.dumps(job,indent=2))
 subprocess.run([sys.executable,str(r/'pipeline/bounded_clean_run.py'),str(o/'job.json'),str(r/('sorting_'+variant+'.log')),str(o/'resource_receipt.json'),'6144'],check=True)
 receipt=json.loads((o/'resource_receipt.json').read_text());assert receipt['exit_code']==0 and receipt['resource_contract_passed'];shutil.copy2(o/'CLEAN_OIDN_PANEL.png',r/'preview'/('sorting_'+variant+'.png'));print('SORTING_VIEW_READY',variant,flush=True)
