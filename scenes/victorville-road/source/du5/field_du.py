"""DU original procedural shoulder recipe, authored in metres.
Broad compacted interspaces connect between retained shrub roots. This is a
static landscape construction, not a surveyed site or a transport simulation.
No photos, image maps, camera parameters or view-dependent randomness enter it.
"""
import numpy as np

def smooth(a,b,x):
 t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def hash2(x,y,seed=0):
 # Deterministic lattice values; seed shifts only integer lattice coordinates.
 q=np.sin((x+seed*3.13)*127.1+(y-seed*7.31)*311.7)*43758.5453123
 return q-np.floor(q)

def noise(x,y,seed=0):
 ix=np.floor(x);iy=np.floor(y);u=x-ix;v=y-iy;u=u*u*(3-2*u);v=v*v*(3-2*v)
 return (1-v)*((1-u)*hash2(ix,iy,seed)+u*hash2(ix+1,iy,seed))+v*((1-u)*hash2(ix,iy+1,seed)+u*hash2(ix+1,iy+1,seed))

class Field:
 def __init__(self,roots):
  self.roots=np.asarray(roots,float).reshape(-1,3)
  self.x0=-42.;self.y0=-7.;self.pitch=.08
  self.x=np.arange(self.x0,42.0001,self.pitch);self.y=np.arange(self.y0,130.0001,self.pitch)
  self.shelter=np.zeros((len(self.y),len(self.x)),np.float32)
  self.basal_index=np.full(self.shelter.shape,-1,np.int32);nearest=np.full(self.shelter.shape,np.inf,np.float32)
  for root_id,(x,y,scale) in enumerate(self.roots):
   r=.32+.38*scale
   ix=np.flatnonzero(abs(self.x-x)<r*3.8);iy=np.flatnonzero(abs(self.y-y)<r*4.2)
   if not len(ix) or not len(iy):continue
   xx=self.x[ix][None,:]-x;yy=self.y[iy][:,None]-y
   dist=xx*xx+yy*yy;old=nearest[np.ix_(iy,ix)];take=dist<old
   nearest[np.ix_(iy,ix)]=np.minimum(old,dist);idx=self.basal_index[np.ix_(iy,ix)];idx[take]=root_id;self.basal_index[np.ix_(iy,ix)]=idx
   # Slight asymmetric sheltered accumulation behind a physical shrub base.
   d=((xx-.17*scale)/r)**2+((yy+.10*scale)/(r*1.35))**2
   h=np.exp(-d*1.2)*(1+.10*np.sin(xx*10+yy*5))
   self.shelter[np.ix_(iy,ix)]=np.maximum(self.shelter[np.ix_(iy,ix)],h.astype('f4'))
 def rootfield(self,x,y):
  u=(x-self.x0)/self.pitch;v=(y-self.y0)/self.pitch;i=np.floor(u).astype(int);j=np.floor(v).astype(int)
  inside=(i>=0)&(i<len(self.x)-1)&(j>=0)&(j<len(self.y)-1);i=np.clip(i,0,len(self.x)-2);j=np.clip(j,0,len(self.y)-2);u=np.clip(u-i,0,1);v=np.clip(v-j,0,1)
  s=self.shelter;return inside*((1-v)*((1-u)*s[j,i]+u*s[j,i+1])+v*((1-u)*s[j+1,i]+u*s[j+1,i+1]))
 def evaluate(self,xy):
  x=np.asarray(xy[:,0],float);y=np.asarray(xy[:,1],float)
  root=self.rootfield(x,y)
  wx=x+.72*(noise(x*.19,y*.19,9)-.5);wy=y+.85*(noise(x*.17,y*.17,18)-.5)
  broad=noise(wx*.32,wy*.24,21);meso=noise(wx*.91,wy*.69,12)
  fabric=.42*broad+.58*meso+.20*root
  rough=smooth(.48,.82,fabric)
  opening=1-rough
  # The boundary is softly tapered at the pavement and distant work-domain edge.
  gate=smooth(3.38,3.88,abs(x))*(1-smooth(32.,40.,abs(x)))*smooth(-5.,-2.,y)*(1-smooth(110.,125.,y))
  i=np.clip(np.rint((x-self.x0)/self.pitch).astype(int),0,len(self.x)-1);j=np.clip(np.rint((y-self.y0)/self.pitch).astype(int),0,len(self.y)-1);k=self.basal_index[j,i];base=self.roots[np.maximum(k,0)];dx=x-base[:,0];dy=y-base[:,1];ang=np.arctan2(dy,dx);rr=np.hypot(dx,dy)*(1+.16*np.sin(3*ang+base[:,0])+.11*np.sin(7*ang+base[:,1]));radius=.10+.05*base[:,2];basal=(k>=0)*.012*(1-smooth(.018,radius,rr))
  height=basal+.027*root+.020*(broad-.50)+.009*(meso-.5)-.008*opening
  compact=np.clip(.26+.68*opening-.13*root,0,1)
  # Independent metric centimetre crust variability is substrate structure.
  crust=noise(x*7.3,y*7.3,36)
  return dict(gate=gate,root=root,rough=rough,opening=opening,raw_height=height,compact=compact,crust=crust,basal=basal)
