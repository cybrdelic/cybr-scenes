"""Guard one recovery build stage; caller holds common flock for its lifetime."""
import json,os,pathlib,resource,signal,subprocess,sys,time
log,receipt,seconds=sys.argv[1:4];command=sys.argv[4:];cap=4480.;seconds=float(seconds)
assert command and 0<seconds<=1800
start=time.monotonic();peak=0.;reason=None;terminated_groups=[]
with open(log,'x') as stream:
 p=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
 while p.poll() is None:
  rows=[tuple(map(int,line.split())) for line in subprocess.run(['ps','-eo','pid=,ppid=,rss='],capture_output=True,text=True,check=True).stdout.splitlines()]
  ids={p.pid}
  for _ in range(32):
   more=ids|{q for q,par,rss in rows if par in ids}
   if more==ids:break
   ids=more
  peak=max(peak,sum(rss for q,par,rss in rows if q in ids)/1024)
  if peak>cap:reason='Aggregate RSS cap exceeded'
  elif time.monotonic()-start>seconds:reason='Stage timeout'
  if reason:
   # Inner admission/render guards deliberately create their own sessions.
   # Kill every owned descendant process group, not just the outer leader.
   groups=set()
   for pid in ids:
    try:
     group=os.getpgid(pid)
     if group in ids and group!=os.getpgrp():groups.add(group)
    except ProcessLookupError:pass
   terminated_groups=sorted(groups)
   for group in reversed(terminated_groups):
    try:os.killpg(group,signal.SIGTERM)
    except ProcessLookupError:pass
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    alive=[]
    for group in groups:
     try:os.killpg(group,0);alive.append(group)
     except ProcessLookupError:pass
    if not alive:break
    time.sleep(.1)
   for group in groups:
    try:os.killpg(group,signal.SIGKILL)
    except ProcessLookupError:pass
   p.wait()
   break
  time.sleep(.2)
 code=p.wait()
k=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024
r={'command':command,'exit_code':code,'stop_reason':reason,'elapsed_seconds':time.monotonic()-start,'sampled_process_tree_peak_MiB':peak,'kernel_max_child_RSS_MiB':k,'cap_MiB':cap,'termination_scope':'Every owned descendant process group, including inner detached guard sessions','terminated_groups':terminated_groups,'passed':code==0 and not reason and max(peak,k)<=cap}
pathlib.Path(receipt).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);sys.exit(0 if r['passed'] else(code or 125))
