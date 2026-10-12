"""Small procedural geometry writer; all dimensions are metres."""
import numpy as np
from cybrlight.scene_compat import Meshlets

class Parts:
 def __init__(self,path,object_start):
  self.writer=Meshlets(path);self.object=object_start;self.parts=[]
 def mesh(self,name,v,f,material,source,estimate,uv=None,tint=1,uv_period=None,drop_zero_projected_area=False,normals=None):
  v=np.asarray(v,float);f=np.asarray(f,int)
  if not len(f):return
  t=v[f];cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);length=np.linalg.norm(cross,axis=1);keep=length>1e-9;t=t[keep];f=f[keep];cross=cross[keep]/length[keep,None]
  a=np.zeros((len(t),36),'<f4');a[:,:9]=t.reshape(-1,9);a[:,9:18]=np.repeat(cross[:,None,:],3,axis=1).reshape(-1,9);a[:,18]=material;a[:,19]=self.object
  if normals is not None:
   nn=np.asarray(normals,float);assert nn.shape==v.shape and np.isfinite(nn).all();nn=nn/np.linalg.norm(nn,axis=1,keepdims=True);a[:,9:18]=nn[f].reshape(-1,9)
  tex=(v[f,:2]/1.25 if uv is None else np.asarray(uv)[f])
  if uv_period is not None:
   if uv is None:tex=a[:,:9].reshape(-1,3,3).astype(float)[:,:,:2]/1.25
   tex=tex-np.floor(tex[:,:1,:]/uv_period)*uv_period
  a[:,20:26]=tex.reshape(-1,6);a[:,26:35]=tint
  if drop_zero_projected_area:
   xy=a[:,:9].reshape(-1,3,3).astype(float)[:,:,:2];e=xy[:,1]-xy[:,0];g=xy[:,2]-xy[:,0];valid=abs(e[:,0]*g[:,1]-e[:,1]*g[:,0])>1e-14;a=a[valid]
  self.writer.add(a);self.parts.append({'object':self.object,'name':name,'source':source,'estimated':estimate,'triangles':len(a)});self.object+=1
 def box(self,name,size,center,material,source,estimate,frame=None):
  s=np.asarray(size)/2;c=np.asarray(center);v=np.array([[x,y,z] for z in [-1,1] for y in [-1,1] for x in [-1,1]])*s+c
  if frame is not None:v=frame(v)
  f=[[0,2,3],[0,3,1],[4,5,7],[4,7,6],[0,1,5],[0,5,4],[2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]]
  self.mesh(name,v,f,material,source,estimate)
 def tube(self,name,a,b,ra,rb,material,source,estimate,segments=7):
  a=np.asarray(a);b=np.asarray(b);axis=b-a;axis/=np.linalg.norm(axis);ref=np.array([0,0,1]) if abs(axis[2])<.95 else np.array([1,0,0]);u=np.cross(axis,ref);u/=np.linalg.norm(u);v=np.cross(axis,u);angles=np.arange(segments)*2*np.pi/segments;ring=np.cos(angles)[:,None]*u+np.sin(angles)[:,None]*v
  vv=np.vstack([a+ra*ring,b+rb*ring]);ff=[]
  for j in range(segments):k=(j+1)%segments;ff.extend([[j,k,segments+k],[j,segments+k,segments+j]])
  self.mesh(name,vv,ff,material,source,estimate)
 def close(self):
  self.writer.__exit__(None,None,None);return {'triangles':self.writer.triangles,'meshlets':self.writer.meshlets,'parts':self.parts}

def leaf_mesh(centers,axes,lengths,widths,folded=True,rolls=None):
 centers=np.asarray(centers);axes=np.asarray(axes);axes/=np.linalg.norm(axes,axis=1,keepdims=True)
 up=np.tile([0.,0.,1.],(len(axes),1));parallel=abs(axes[:,2])>.97;up[parallel]=[1,0,0]
 sides=np.cross(axes,up);sides/=np.linalg.norm(sides,axis=1,keepdims=True)
 normal=np.cross(sides,axes)
 if rolls is not None:
  rolls=np.asarray(rolls);sides=sides*np.cos(rolls)[:,None]+normal*np.sin(rolls)[:,None];normal=np.cross(sides,axes)
 lengths=np.asarray(lengths);widths=np.asarray(widths)
 # Folded diamonds preserve a genuine leaf silhouette and a shallow midrib.
 vv=np.stack([centers-axes*lengths[:,None]*.5,centers-sides*widths[:,None]*.5,centers+axes*lengths[:,None]*.5,centers+sides*widths[:,None]*.5,centers+normal*widths[:,None]*.10],axis=1)
 if folded:
  ff=(np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])[None]+np.arange(len(axes))[:,None,None]*5).reshape(-1,3)
 else:
  vv=vv[:,:4];ff=(np.array([[0,1,2],[0,2,3]])[None]+np.arange(len(axes))[:,None,None]*4).reshape(-1,3)
 return vv.reshape(-1,3),ff
