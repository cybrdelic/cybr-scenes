import json,hashlib,subprocess,os,shutil,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1];variant=sys.argv[sys.argv.index('--variant')+1].lower() if '--variant' in sys.argv else 'e';assert variant in('e','i','k','l','o');p=r/('preview/road_r6_'+variant+'.blend');env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2');digest=hashlib.sha256(p.read_bytes()).hexdigest()
views=[(variant+'_preview',1200,800,32,None,None,None)] if '--preview' in sys.argv else [('01_Foreground_and_Full_Road',2048,1365,64,None,None,None),('02_Shoulder_Road_Context',2048,1365,64,(-5.6,-2.6,.85),(-.4,19,.0),30),('03_Road_Construction_Detail',1800,1200,64,(-3.62,.20,.26),(-3.2,1.05,.07),40)]
if '--detail-only' in sys.argv:views=views[-1:]
if '--hero-only' in sys.argv:views=views[:1]
if '--context-only' in sys.argv:views=views[1:2]
ready=[]
for name,w,h,sp,loc,targ,lens in views:
 o=r/'captures'/((variant+'_' if variant!='e' else '')+name);o.mkdir(exist_ok=True);j=dict(source=str(p),source_sha256=digest,engine='CYCLES',width=w,height=h,samples=sp,capture_mode='guided',save_guides=True,light_tree=False,color_depth=16,dither_intensity=0,use_adaptive_sampling=False,rss_cap_mib=6144,time_limit_seconds=1800,sync_limit_seconds=180,output=str(o/'INTERNAL_PANEL.png'))
 if loc:j.update(camera_location=loc,camera_target=targ,lens=lens)
 (o/'job.json').write_text(json.dumps(j,indent=2))
 subprocess.run([sys.executable,str(r/'pipeline/bounded_clean_run.py'),str(o/'job.json'),str(r/((variant+'_' if variant!='e' else '')+name+'.log')),str(o/'resource_receipt.json'),'6144'],env=env,check=True)
 resources=json.loads((o/'resource_receipt.json').read_text());assert resources['exit_code']==0 and resources['resource_contract_passed'],resources
 out=r/'deliverables'/('CYBR_Victorville_R6'+(variant.upper() if variant!='e' else '')+'_'+name+'.png');shutil.copy2(o/'CLEAN_OIDN_PANEL.png',out);ready.append(dict(path=str(out),bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest()));(r/'receipts'/(('preview_'+variant+'_ready.json') if '--preview' in sys.argv else ('views_'+variant+'_ready.json'))).write_text(json.dumps(ready,indent=2));print('VIEW_READY',out,flush=True)
