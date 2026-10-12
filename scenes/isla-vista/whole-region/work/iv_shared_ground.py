"""Retained CYBR TERRAIN display geometry and exact triangle-height contract."""
from pathlib import Path
import json,numpy as np
from scipy.ndimage import gaussian_filter
from cybr_terrain.geometry import grid_faces
class SharedGround:
 def __init__(self,state_path):
  state=np.load(state_path);self.meta=json.loads(str(state['metadata']));config=self.meta['config'];self.n=config['grid'];self.extent=config['extent'];self.dx=self.extent/(self.n-1)
  assert np.max(state['water'])==0 and np.max(state['loose'])==0 and len(self.meta['layers'])==1
  z=state['foundation']+state['thickness'].sum(0);rng=np.random.default_rng(config['seed']+19);fields=[]
  for sigma in [.75,2.2,6]:
   a=gaussian_filter(rng.normal(size=(self.n,self.n)),sigma);a/=max(a.std(),1e-9);fields.append(a)
  rough,medium,coarse=fields;amplitude=min(max(self.meta['layers'][0]['grain_scale']*.30,.008),self.dx*.20)
  self.z=z+(.54*rough+.30*medium+.16*coarse-.14*np.maximum(rough,0)**2)*amplitude
  axis=np.linspace(-self.extent/2,self.extent/2,self.n);x,y=np.meshgrid(axis,axis);self.xy=np.c_[x.ravel(),y.ravel()];self.faces=grid_faces(self.n);self.vertices=np.c_[self.xy,self.z.ravel()]
  assert np.max(abs(self.height(self.xy[::17])-self.vertices[::17,2]))<1e-7
 def height(self,p):
  p=np.asarray(p);q=np.clip((p+self.extent/2)/self.dx,0,self.n-1-1e-9);ix=np.floor(q[:,0]).astype(int);iy=np.floor(q[:,1]).astype(int);x=q[:,0]-ix;y=q[:,1]-iy;z=self.z;a=z[iy,ix];b=z[iy,ix+1];c=z[iy+1,ix+1];d=z[iy+1,ix]
  return np.where(y<=x,(1-x)*a+(x-y)*b+y*c,(1-y)*a+x*c+(y-x)*d)
