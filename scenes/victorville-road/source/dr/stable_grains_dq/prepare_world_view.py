"""Numerical-only pure view selection, separated from Blender render memory."""
from pathlib import Path
import sys,json,hashlib,argparse,time
import numpy as np
O=Path(__file__).resolve().parent;sys.path.insert(0,str(O));from select_world import select_world
p=argparse.ArgumentParser();p.add_argument('--view',choices=['normal_2000','macro_1800'],required=True);a=p.parse_args()
class Projection:
 def __init__(self,q):
  self.__dict__.update(q)
  for k in ['inverse','f','offset']:setattr(self,k,np.asarray(getattr(self,k),float))
 def project(self,world):
  q=np.asarray(world)@self.inverse[:3,:3].T+self.inverse[:3,3];depth=-q[:,2];return q[:,:2]/np.maximum(depth,self.near)[:,None]*self.f+self.offset,depth
 def visible(self,world,margin=0):
  uv,d=self.project(world);return(d>self.near)&(uv[:,0]>=-margin)&(uv[:,0]<=self.width+margin)&(uv[:,1]>=-margin)&(uv[:,1]<=self.height+margin)
q=json.loads((O/'VIEW_PROJECTIONS.json').read_text())[a.view];proj=Projection(q);data,rep=select_world(proj,{'sand_budget':85000,'grit_budget':135000});out=O/('VIEW_'+a.view+'.npz');np.savez_compressed(out,**data);rep['catalog_sha256']=hashlib.sha256(out.read_bytes()).hexdigest();rep['projection']=q;rep['projection_source_sha256']=hashlib.sha256((O/'VIEW_PROJECTIONS.json').read_bytes()).hexdigest();rep['prototype_metadata']=json.loads((O/'ACTUAL_CATALOG.json').read_text())['prototype_metadata'];rep['scope_bounds_m']=[-7,-3.52,4.7,11.5];rep['limits'].append('The world is fixed to a bounded foreground support domain; this does not claim unresolved particles across the distant landscape.');out.with_suffix('.json').write_text(json.dumps(rep,indent=2)+'\n');print(json.dumps(rep),flush=True)
