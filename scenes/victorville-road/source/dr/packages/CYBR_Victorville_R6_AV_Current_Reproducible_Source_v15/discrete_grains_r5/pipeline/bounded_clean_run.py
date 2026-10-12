from resource_contract import resource_violations
import subprocess,os,signal,time,json,pathlib,sys,resource
job,log,receipt=sys.argv[1:4];cap=int(sys.argv[4]) if len(sys.argv)>4 else 5120;cfg=json.load(open(job));limit=cfg.get('time_limit_seconds',900);sync_limit=cfg.get('sync_limit_seconds',180);start=time.monotonic();peak=0;why=None;first_sample=None
root=pathlib.Path(__file__).resolve().parent
with open(log,'w') as out:
 p=subprocess.Popen([str(root/'clean_render.sh'),job],stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
 def rss_tree(pid):
  result=subprocess.run(['ps','-eo','pid=,ppid=,rss='],capture_output=True,text=True)
  rows=[tuple(map(int,line.split())) for line in result.stdout.splitlines() if len(line.split())==3]
  ids={pid}
  for _ in range(12):
   expanded=ids|{q for q,parent,rss in rows if parent in ids}
   if expanded==ids:break
   ids=expanded
  return sum(rss for q,parent,rss in rows if q in ids)
 while p.poll() is None:
  elapsed=time.monotonic()-start;rss=rss_tree(p.pid)/1024;peak=max(peak,rss)
  if first_sample is None:
   try:
    if 'Sample 1/' in pathlib.Path(log).read_text():first_sample=elapsed
   except OSError:pass
  if rss>cap:why='RSS cap crossed'
  elif elapsed>limit:why='Total timeout'
  elif cfg.get('engine')=='CYCLES' and elapsed>sync_limit and first_sample is None:why='No first sample before sync timeout'
  if why:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   break
  time.sleep(.2)
 code=p.wait()
r={'job':job,'log':log,'exit_code':code,'stop_reason':why,'peak_process_tree_RSS_MiB':peak,'RSS_sample_interval_seconds':.2,'RSS_cap_MiB':cap,'elapsed_seconds':time.monotonic()-start,'first_sample_observed_seconds':first_sample,'sample_watchdog_enabled':cfg.get('engine')=='CYCLES','scope':'Owned descendants via ps parent graph; sampled RSS plus kernel child high-water mark','kernel_max_child_RSS_MiB':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024}
violations=resource_violations(r,cap);r['actual_process_exit_code']=code;r['resource_contract_passed']=not violations;r['resource_contract_violations']=violations
if violations and code==0:
 r['exit_code']=125;r['stop_reason']='Recorded resource peak exceeded or failed cap contract after process completion; artifacts retained'
pathlib.Path(receipt).write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
