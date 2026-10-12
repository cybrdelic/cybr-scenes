"""Bound one owned build/render tree; hold the common flock around this runner."""
import argparse,json,os,signal,subprocess,time,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--log',required=True);p.add_argument('--receipt',required=True);p.add_argument('--seconds',type=float,default=900);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();cmd=a.command[1:] if a.command[:1]==['--'] else a.command
assert cmd and 0<a.seconds<=1800
root=Path(__file__).resolve().parents[1];reserve=1024**3;cap=4480.;assert shutil.disk_usage(root).free>=reserve
start=time.monotonic();peak=0.;reason=None;min_free=shutil.disk_usage(root).free
with open(a.log,'w') as log:
 child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 def sample():
  rows={}
  for path in Path('/proc').iterdir():
   if not path.name.isdecimal():continue
   try:
    status=path.joinpath('status').read_text().splitlines();ppid=next((int(x.split()[1]) for x in status if x.startswith('PPid:')),0);rss=next((float(x.split()[1])/1024 for x in status if x.startswith('VmRSS:')),0.)
    rows[int(path.name)]=(ppid,rss)
   except (FileNotFoundError,ProcessLookupError):continue
  owned={child.pid}
  while True:
   new=owned|{pid for pid,(ppid,rss) in rows.items() if ppid in owned}
   if new==owned:break
   owned=new
  return owned,sum(rows.get(pid,(0,0.))[1] for pid in owned)
 def stop(owned):
  groups=set()
  for pid in owned:
   try:
    group=os.getpgid(pid)
    if group in owned and group!=os.getpgrp():groups.add(group)
   except ProcessLookupError:pass
  for sig in (signal.SIGTERM,signal.SIGKILL):
   for group in sorted(groups,reverse=True):
    try:os.killpg(group,sig)
    except ProcessLookupError:pass
   if sig==signal.SIGTERM:
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:pass
  child.wait()
 try:
  while child.poll() is None:
   owned,rss=sample();peak=max(peak,rss);min_free=min(min_free,shutil.disk_usage(root).free)
   if peak>cap:reason='Sampled aggregate RSS cap exceeded'
   elif time.monotonic()-start>a.seconds:reason='Stage deadline exceeded'
   elif min_free<reserve:reason='Disk reserve breached'
   if reason:stop(owned);break
   time.sleep(.25)
 except BaseException:
  stop(sample()[0]);raise
 code=child.wait()
receipt={'command':cmd,'exit_code':code,'stop_reason':reason,'elapsed_seconds':round(time.monotonic()-start,2),'peak_sampled_aggregate_rss_mib':round(peak,2),'cap_mib':cap,'min_free_disk_gib':round(min_free/1024**3,3),'disk_reserve_gib':1,'sample_seconds':.25,'passed':code==0 and reason is None,'scope':'Owned process tree; sampled user-space RSS guard, not kernel hard cap'}
Path(a.receipt).write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True);raise SystemExit(code if code else (125 if reason else 0))
