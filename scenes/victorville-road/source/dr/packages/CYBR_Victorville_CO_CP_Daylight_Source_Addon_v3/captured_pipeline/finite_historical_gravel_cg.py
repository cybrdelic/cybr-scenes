"""CG original finite 18–60 mm historical gravel tier.
An independent authored substrate class, NOT converted AH 1.66–5.9 mm chips.
Bulk inventory = buried reserve + explicit body solids / assumed packing fraction.
Geometry and historical stock share one reach field; this is not calibrated transport.
"""
from pathlib import Path
import json,math,hashlib
import numpy as np
from scipy.spatial import ConvexHull
from coupled_shoulder_ce import history,region,smooth
PALETTE=np.array([[.56,.53,.45],[.39,.315,.225],[.265,.205,.135],[.145,.163,.154],[.49,.385,.26],[.165,.108,.062],[.34,.34,.31]])
BOUNDS=(-6.4,-3.50,-.58,10.8)
CELL=.25
SOLID_FRACTION=.62

def bank(path):
 source=json.loads(Path(path).read_text());assert len(source)==96
 rng=np.random.default_rng(2610101911);out=[]
 for k in range(192):
  rec=source[k%96];v=np.array(rec['vertices'],float);f=np.array(rec['faces'],np.int32)
  d=float(np.exp(rng.uniform(np.log(.018 if k<128 else .032),np.log(.037 if k<128 else .060))))
  aspect=rng.uniform(.28,.48) if k%6==0 else rng.uniform(.56,1.0)
  v[:,0]*=d;v[:,1]*=d*aspect;v[:,2]*=d*rng.uniform(.19,.47)
  v[:,:2]+=(v[:,2]-v[:,2].max()*.5)[:,None]*rng.normal(0,.12,2)
  # Exact final horizontal diameter bounded by class, rather than nominal scale.
  hull=ConvexHull(v[:,:2]);hv=v[hull.vertices,:2];diam=np.sqrt(((hv[:,None]-hv[None,:])**2).sum(2).max());v*=d/diam
  v[:,2]-=v[:,2].min();h=v[:,2].max();mineral=int(rng.choice(7,p=[.23,.23,.19,.08,.11,.07,.09]));base=PALETTE[mineral]*rng.uniform(.85,1.13)
  coat=np.clip(rng.uniform(.025,.14)+(1-v[:,2]/h)*.32,0,.65);color=np.ones((len(v),4));color[:,:3]=base[None]*(1-coat[:,None])+np.array([.29,.231,.16])*coat[:,None]
  rough=np.minimum(.92,(.48 if mineral in(0,4) else .67)+rng.uniform(-.07,.07)+coat*.2)
  edges=np.sort(np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]])),axis=1);assert np.all(np.unique(edges,axis=0,return_counts=True)[1]==2),'Non-watertight gravel prototype'
  vv=v[f];volume=abs(np.sum(vv[:,0]*np.cross(vv[:,1],vv[:,2]))/6)
  assert volume>0 and .0179<=d<=.0601
  out.append(dict(v=v.astype('f4'),f=f,color=color.astype('f4'),rough=rough.astype('f4'),diameter=d,height=h,radius=float(np.linalg.norm(v[:,:2],axis=1).max()),volume=float(volume),mineral=mineral,area=float(ConvexHull(v[:,:2]).volume)))
 return out

def cells(transition=False):
 bounds=(BOUNDS[0],-3.35,BOUNDS[2],BOUNDS[3]) if transition else BOUNDS
 xmin,xmax,ymin,ymax=bounds;x=np.r_[np.arange(xmin,xmax,CELL),xmax];y=np.r_[np.arange(ymin,ymax,CELL),ymax];xx,yy=np.meshgrid((x[:-1]+x[1:])/2,(y[:-1]+y[1:])/2);xy=np.c_[xx.ravel(),yy.ravel()];area=(np.diff(y)[:,None]*np.diff(x)[None,:]).ravel();_,core,receive,_=history(xy)
 # A thin historical mixed gravel mantle: worked matrix remains extensive;
 # winnowing exposes more of this finite class, receiving pockets bury it.
 outer=smooth(.45,1.9,-3.2-xy[:,0]);patch=np.clip(.18+.72*core+.40*outer-.72*receive,0,1)
 thickness=.003+.020*patch
 # Allocation is continuous in history. Cell ledger boundaries never displace terrain.
 target_fraction=np.clip(.12+.62*core+.20*outer-.64*receive,.04,.80)
 return dict(x=x,y=y,xy=xy,area=area,core=core,receiving=receive,bulk_thickness=thickness,initial_solid=area*thickness*SOLID_FRACTION,target_fraction=target_fraction)

def cell_ids(xy,c):
 xx=np.searchsorted(c['x'],xy[:,0],side='right')-1;yy=np.searchsorted(c['y'],xy[:,1],side='right')-1;ok=(xx>=0)&(xx<len(c['x'])-1)&(yy>=0)&(yy<len(c['y'])-1)
 return yy*(len(c['x'])-1)+xx,ok

def proposed_points(n=200000,transition=False):
 bounds=(BOUNDS[0],-3.35,BOUNDS[2],BOUNDS[3]) if transition else BOUNDS
 rng=np.random.default_rng(2610101912);xy=np.c_[rng.uniform(bounds[0],bounds[1],n),rng.uniform(bounds[2],bounds[3],n)];_,core,receive,_=history(xy);outer=smooth(.45,1.9,-3.2-xy[:,0]);prob=np.clip(.045+.77*core+.20*outer-.80*receive,.015,.9)
 # Continuous fade at bounds prevents a new rectangular scatter cutoff.
 fade=smooth(bounds[0],bounds[0]+.40,xy[:,0])*(1-smooth(bounds[1]-(.055 if transition else .20),bounds[1],xy[:,0]))*smooth(bounds[2],bounds[2]+.12,xy[:,1])*(1-smooth(bounds[3]-.9,bounds[3],xy[:,1]));prob+=.055*(1-smooth(.12,.58,-3.2-xy[:,0])) if transition else 0;q=rng.random(n)<prob*fade
 xy=xy[q];core=core[q];receive=receive[q];larger=rng.random(len(xy))<(.18+.30*core)*(1-.7*receive);idx=rng.integers(0,128,len(xy));idx[larger]=rng.integers(128,192,larger.sum());yaw=rng.uniform(0,math.tau,len(xy));return xy,idx,yaw,receive
