"""Exact retained triangle support and unchanged class-stock context, SI units."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
O=Path(__file__).resolve().parent;R=O.parent;sys.path.insert(0,str(R/'low_ground_dp_native/runtime/src'))
from context_mesh_refine_ab import SourceSampler,intersecting_triangles
from visible_shoulder_flow_ad import sample_field
from history_budget_dg import reconcile,retained_cover

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Support:
 def __init__(self,build_budget=False):
  j=json.loads((R/'low_ground_dp_native/job.json').read_text());cfg=j['historical_grain_roles_dg'];scfg=j['static_fine_layer_dl'];self.rows=json.loads((O/'ACTUAL_CATALOG.json').read_text())['prototype_metadata'];self.pins={}
  for k in ['payload','historical_fields','sand_bank','datums']:
   self.pins[k]=sha(cfg[k]);assert self.pins[k]==cfg[k+'_sha256']
  self.pins['static_cap']=sha(scfg['field']);assert self.pins['static_cap']==scfg['field_sha256']
  with np.load(cfg['payload'])as f:p={k:f[k]for k in f.files}
  with np.load(cfg['historical_fields'])as f:self.h={k:f[k]for k in f.files}
  with np.load(scfg['field'])as f:cap={k:f[k]for k in ['co','tri','cap_m']}
  self.co=p['source_coordinates'].copy();self.co[:,2]+=p['delta'];self.tri=p['tri'];assert np.array_equal(self.co,cap['co'])and np.array_equal(self.tri,cap['tri']);self.cap=cap['cap_m'];self.sediment=p['sediment'];self.x=np.arange(-6.975,-3.36,.05);self.y=np.arange(-.875,18.,.05)
  if build_budget:
   self.sampler=SourceSampler(self.co,self.tri,np.arange(len(self.tri)),max_triangles=500000,max_bin_entries=4000000);xx,yy=np.meshgrid(self.x,self.y);grid=np.c_[xx.ravel(),yy.ravel()];rem=self.sample(p['removed'],grid);dep=self.sample(p['deposited'],grid);prior=self.historical(self.h['retained_deposit_by_class_m'],grid);self.available=reconcile(prior,rem,dep)['available'].reshape(len(self.y),len(self.x),3);net=self.sample(self.sediment,grid);self.cover_grid=retained_cover(self.historical(self.h['sediment_delta_m'],grid),net).reshape(len(self.y),len(self.x))
  local=intersecting_triangles(self.co,self.tri,(-7.02,-3.50,4.68,11.52));self.sampler=SourceSampler(self.co,self.tri,local,cell_m=.04,max_triangles=500000,max_bin_entries=4000000)
 def arr(self,k):return np.array([q[k]for q in self.rows])
 def sample(self,values,xy):
  xy=np.asarray(xy,float);ans=np.empty((len(xy),)+np.asarray(values).shape[1:]);order=np.lexsort((xy[:,1],np.floor(xy[:,0]/.045)))
  for s in range(0,len(order),2048):
   ii=order[s:s+2048];ans[ii]=self.sampler.sample(values,xy[ii])
  return ans
 def historical(self,values,xy):
  h=self.h;out=np.zeros((len(xy),)+np.asarray(values).shape[2:]);inside=(xy[:,0]>=h['x_m'][0])&(xy[:,0]<=h['x_m'][-1])&(xy[:,1]>=h['y_m'][0])&(xy[:,1]<=h['y_m'][-1]);out[inside]=sample_field(values,xy[inside],h['x_m'],h['y_m']);return out
 def local_fields(self,xy):
  v=self.sample(np.c_[self.co[:,2],self.sediment,self.cap],xy);cover=retained_cover(self.historical(self.h['sediment_delta_m'],xy),v[:,1]);return v[:,0],cover,v[:,2]
 def placement(self,xy,pi,yaw,role,extra):
  height,cover,cap=self.local_fields(xy);before=(height.astype('f4').astype(float)-self.arr('offset')[pi]).astype('f4');z=(before.astype(float)-cover).astype('f4');z[role]=(before[role].astype(float)-extra[role]).astype('f4');b=self.arr('bottom')[pi];c=np.cos(yaw.astype(float));s=np.sin(yaw.astype(float));bxy=xy+np.c_[b[:,0]*c-b[:,1]*s,b[:,0]*s+b[:,1]*c];terrain=self.sample(self.co[:,2],bxy);z=np.minimum(z.astype(float),terrain-b[:,2]-.000020).astype('f4');pre=z.copy();static=(pi<64)&~role;z[static]-=cap[static].astype('f4');assert np.max(z.astype(float)+b[:,2]-terrain,initial=-1)<=.000021;return pre,z,cover,cap
