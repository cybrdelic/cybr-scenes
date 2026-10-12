"""Read compact statuses in fixed world-space stock bands, never camera quotas."""
from pathlib import Path
import json,sys,hashlib,math
import numpy as np
O=Path(__file__).resolve().parent;sys.path.insert(0,str(O/'core'))
import compact_catalog as c
import stable_catalog as ref
class Reader:
 def __init__(self):
  r=json.loads((O/'FULL_ROAD_PACKING_STATUS.json').read_text());self.report=r;kw=dict(r['spec']);kw['thinning_by_band']={int(k):v for k,v in kw['thinning_by_band'].items()};self.spec=ref.CatalogSpec(**kw);self.map=c.build_serial_map(self.spec,[ref.Prototype(**q)for q in r['prototypes']]);assert c._array_sha256(self.map.prefix,'<u8')==r['storage']['prefix_sha256'];self.status=np.load(O/'FULL_ROAD_PACKING_STATUS.npz')['status2'];assert hashlib.sha256(self.status.tobytes()).hexdigest()==r['storage']['status_sha256'];self.proto=np.array([p.prototype_id for p in self.map.prototypes],'i4')
 def status_at(self,serial):return(self.status[serial//4]>>(2*(serial%4)))&3
 def band(self,ylo,yhi):
  cells=self.map.cells;step=self.spec.cell_size;cell_y=cells[:,1]*step;ok=(cell_y+step>ylo-.000001)&(cell_y<yhi+.000001);groups=np.flatnonzero(ok[self.map.group_cell]);parts=[]
  # Groups do not exceed ~1,020 physical sand candidates at the pinned .18m
  # cell scale. Avoid full-world ID or point arrays.
  for g in groups:
   seq=np.arange(self.map.prefix[g],self.map.prefix[g+1],dtype='u4');seq=seq[self.status_at(seq)==1]
   if len(seq):parts.append(seq)
  serial=np.concatenate(parts)if parts else np.empty(0,'u4');ids,xy,slots,cell,ordinal=c._decode(self.map,serial,step);rawxy=xy;xy=xy.astype('f4').astype('f8');mask=(xy[:,1]>=ylo)&(xy[:,1]<yhi);serial,ids,xy,slots=serial[mask],ids[mask],xy[mask],slots[mask];pi=self.proto[slots];yaw=(ref._uniform(ids,'yaw')*math.tau).astype('f4')
  # Every new body must lie outside the already frozen full-density macro.
  q=rawxy[mask];old=(q[:,0]>=-5.2)&(q[:,0]<-4.55)&(q[:,1]>=5.1)&(q[:,1]<5.85);assert not old.any(),'Full extension duplicated the frozen macro domain'
  return {'serial':serial,'id':ids,'xy':xy,'prototype':pi,'yaw':yaw}
