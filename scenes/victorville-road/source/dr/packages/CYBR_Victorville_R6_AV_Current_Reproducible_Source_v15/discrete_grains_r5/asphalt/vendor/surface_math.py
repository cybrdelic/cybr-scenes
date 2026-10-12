"""Periodic physical structure utilities shared by the material generators."""
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, map_coordinates, zoom
from scipy.interpolate import CubicSpline
TAU=np.float32(2*np.pi)
def clamp(a,lo=0,hi=1):return np.clip(a,lo,hi)
def smooth(a,lo,hi):
 t=clamp((a-lo)/(hi-lo));return t*t*(3-2*t)

def field(n,cells,seed,octaves=1):
 """Periodic process variation, cubic interpolated at finite feature scales."""
 rng=np.random.default_rng(seed);out=np.zeros((n,n),np.float32);norm=0
 shape=(cells,cells) if isinstance(cells,int) else cells
 for i in range(octaves):
  sy,sx=[int(v*2**i) for v in shape]
  grid=rng.uniform(-1,1,(sy,sx)).astype(np.float32)
  a=zoom(grid,(n/sy,n/sx),order=3,mode='grid-wrap',grid_mode=True)
  weight=0.5**i;out+=a*weight;norm+=weight
 return out/np.float32(norm)

def color(base,mod):return np.stack([v+mod for v in base],axis=-1).astype(np.float32)
def blend(rgb,tint,mask):
 for c,v in enumerate(tint):rgb[...,c]=rgb[...,c]*(1-mask)+v*mask
 return rgb

def specks(n,seed,count,rx_range,ry_range,power=.75):
 """Ragged compact inclusions/cavities with varied, finite-support outlines."""
 rng=np.random.default_rng(seed);out=np.zeros((n,n),np.float32)
 for _ in range(count):
  cx,cy=rng.uniform(0,n,2);rx,ry=rng.uniform(*rx_range)*n,rng.uniform(*ry_range)*n
  ix=np.arange(int(cx-rx*1.3-1),int(cx+rx*1.3+2));iy=np.arange(int(cy-ry*1.3-1),int(cy+ry*1.3+2))
  u=(ix[None,:]-cx)/max(rx,.6);v=(iy[:,None]-cy)/max(ry,.6)
  angle=np.arctan2(v,u);phase=rng.uniform(0,TAU)
  r=(u*u+v*v)*(1+.17*np.sin(3*angle+phase)+.09*np.sin(7*angle-phase))
  patch=clamp(1-r).astype(np.float32)**power*rng.uniform(.55,1)
  target=np.ix_(iy%n,ix%n);out[target]=np.maximum(out[target],patch)
 return out

def paths(n,seed,count,width=(.0003,.001),length=(.02,.15),angle=np.pi/2,jitter=.2,bend=.08):
 """Finite scratches, checks or fibers; curved paths wrapped around the tile."""
 rng=np.random.default_rng(seed);im=Image.new('L',(n,n));draw=ImageDraw.Draw(im)
 for _ in range(count):
  center=rng.uniform(0,n,2);theta=angle+rng.uniform(-jitter,jitter);size=rng.uniform(*length)*n
  t=np.linspace(-.5,.5,7);control=rng.uniform(-1,1,7)*size*bend;control[0]*=.3;control[-1]*=.3
  fine=np.linspace(-.5,.5,64);off=CubicSpline(t,control)(fine)
  xx=center[0]+np.cos(theta)*fine*size-np.sin(theta)*off
  yy=center[1]+np.sin(theta)*fine*size+np.cos(theta)*off
  line_width=max(1,round(rng.uniform(*width)*n));tone=int(rng.uniform(120,255))
  for oy in (-n,0,n):
   for ox in (-n,0,n):draw.line(list(zip(xx+ox,yy+oy)),fill=tone,width=line_width)
 return gaussian_filter(np.asarray(im,dtype=np.float32)/255,.42,mode='wrap')

def warp_map(a,u,v):
 n=a.shape[0];u,v=np.broadcast_arrays(u,v)
 return map_coordinates(a,np.stack([(v%1)*n-.5,(u%1)*n-.5]),order=1,mode='grid-wrap',prefilter=False)

def voronoi(n,cells,seed,u=None,v=None):
 """Distance gap, seed distance and cell variation on an irregular tiling."""
 rng=np.random.default_rng(seed);jx=rng.uniform(-.46,.46,(cells,cells)).astype(np.float32);jy=rng.uniform(-.46,.46,(cells,cells)).astype(np.float32)
 values=rng.uniform(-1,1,(cells,cells)).astype(np.float32)
 if u is None:u=(np.arange(n,dtype=np.float32)[None,:]+.5)/n
 if v is None:v=(np.arange(n,dtype=np.float32)[:,None]+.5)/n
 xx=np.broadcast_to(u*cells,(n,n));yy=np.broadcast_to(v*cells,(n,n));ix=np.floor(xx).astype(np.int16);iy=np.floor(yy).astype(np.int16)
 first=np.full((n,n),100,np.float32);second=first.copy();best=np.zeros((n,n),np.float32)
 for dy in (-1,0,1):
  for dx in (-1,0,1):
   cx=(ix+dx)%cells;cy=(iy+dy)%cells
   ds=(xx-(ix+dx+.5+jx[cy,cx]))**2+(yy-(iy+dy+.5+jy[cy,cx]))**2
   low=ds<first;second=np.where(low,first,np.minimum(second,ds));best=np.where(low,values[cy,cx],best);first=np.minimum(first,ds)
 return np.sqrt(second)-np.sqrt(first),np.sqrt(first),best

