from resource_contract import resource_violations
import sys,json,pathlib,subprocess,hashlib,time,shutil
from cache_validation import validate_cache
from queue_paths import execution_paths
from capture_modes import capture_mode,final_image,is_workbench_raw
ROOT=pathlib.Path(__file__).resolve().parent
records=[]
for jp in sys.argv[1:]:
 jobpath=pathlib.Path(jp);j=json.loads(jobpath.read_text());out=pathlib.Path(j['output']);clean=final_image(j);mode=capture_mode(j);receipt=clean.with_suffix('.png.json');execution=execution_paths(jobpath,ROOT/'handoff-receipts')
 cached=False
 if receipt.exists() and clean.exists():
  cache_check=validate_cache(j,receipt,ROOT);cached=cache_check['valid']
  if not cached:print('CACHE_INVALID '+json.dumps(cache_check['reasons']),flush=True)
 if cached:
  performance=json.loads(execution['performance'].read_text());violations=resource_violations(performance,j.get('rss_cap_mib',2560))
  if violations:raise RuntimeError('Cached files retained but resource contract failed; explicit new run required: '+str(violations))
 if not cached:
  disk_free=shutil.disk_usage(ROOT).free;reserve=max(130*1024**2,j.get('width',960)*j.get('height',960)*115)
  if disk_free<reserve:raise RuntimeError('Insufficient scratch space before render: '+str(disk_free)+' bytes free; '+str(reserve)+' bytes required; no render launched')
  log=execution['log'];perf=execution['performance']
  subprocess.run([sys.executable,str(ROOT/'bounded_clean_run.py'),str(jobpath),str(log),str(perf),str(j.get('rss_cap_mib',2560))],check=True)
  result=json.loads(perf.read_text())
  if result['exit_code']!=0 or not receipt.exists():raise RuntimeError('Render failed: '+str(result))
 r=json.loads(receipt.read_text());gd=out.parent/(out.stem+'_guides');removed=[]
 if len(r.get('guide_paths',[]))==3 and all(pathlib.Path(p).is_file() for p in r['guide_paths']) and ((gd/'denoised_linear.exr').is_file() if mode=='guided' else clean.is_file()):
  for f in gd.glob('*.pfm'):
   removed.append({'path':str(f),'bytes':f.stat().st_size});f.unlink()
 execution['cleanup'].write_text(json.dumps({'retained':'all raw EXR guides, any denoised EXR, raw and final PNG','removed_regenerable_pfm':removed},indent=2))
 records.append({'job':str(jobpath),'image_path':str(clean),({'guided':'clean_image','unfiltered':'unfiltered_image','component-recombined':'component_image'}[mode]):str(clean),'capture_mode':mode,'source_sha256':r['source_sha256'],'render_seconds':r['render_seconds'],'cached':cached,'visual_QA':'pending'})
 (ROOT/'handoff-receipts'/'latest_queue_results.json').write_text(json.dumps(records,indent=2));print('PANEL_READY '+str(clean),flush=True)
