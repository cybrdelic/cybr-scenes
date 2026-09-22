import numpy as np,json
from pathlib import Path
R=6360000.;Rt=6460000.
sun=np.array([-.8,.4,.28]);sun/=np.linalg.norm(sun)
def exit(p,d):
 b=np.sum(p*d,axis=-1);c=np.sum(p*p,axis=-1)-Rt**2
 return -b+np.sqrt(b*b-c)
def depth(p,n,power):
 p=np.asarray(p);end=exit(p,sun)
 edges=(np.arange(n+1)/n)**power
 t=(edges[1:]+edges[:-1])*.5;ds=np.diff(edges)
 pos=p[...,None,:]+end[...,None,None]*t[:,None]*sun
 h=np.maximum(np.linalg.norm(pos,axis=-1)-R,0)
 return np.sum(np.exp(-h/8000)*end[...,None]*ds,axis=-1),np.sum(np.exp(-h/1200)*end[...,None]*ds,axis=-1)
p=np.array([0,0,R+1.])
ref=depth(p,2048,2)
results={}
for n,power in [(12,1),(32,2),(48,2),(64,2)]:
 rr,mm=depth(p,n,power)
 results[f'{n}_power_{power}']={'rayleigh':float(rr),'aerosol':float(mm),'rayleigh_relative_error':float(abs(rr-ref[0])/ref[0]),'aerosol_relative_error':float(abs(mm-ref[1])/ref[1])}
# Single-scattering radiance in arbitrary units at three viewing elevations.
w=380+(np.arange(16)+.5)*25;br=13.5e-6*(550/w)**4.08;bm=2.8e-6*(550/w)**1.3

def sky(el,n,power,ns,ps):
 theta=np.deg2rad(el);d=np.array([0,np.cos(theta),np.sin(theta)])
 end=exit(p,d);ed=(np.arange(n+1)/n)**power;ds=np.diff(ed)*end;t=(ed[1:]+ed[:-1])*.5*end
 pos=p[None,:]+t[:,None]*d
 h=np.maximum(np.linalg.norm(pos,axis=-1)-R,0);dr=np.exp(-h/8000);dm=np.exp(-h/1200)
 vr=np.cumsum(dr*ds)-.5*dr*ds;vm=np.cumsum(dm*ds)-.5*dm*ds
 sr,sm=depth(pos,ns,ps);c=np.dot(d,sun);pr=3*(1+c*c)/(16*np.pi);g=.76
 pm=(1-g*g)/(4*np.pi*(1+g*g-2*g*c)**1.5)
 tr=np.exp(-(vr+sr)[:,None]*br-(vm+sm)[:,None]*bm)
 return np.sum(tr*(br[None,:]*dr[:,None]*pr+.93*bm[None,:]*dm[:,None]*pm)*ds[:,None],axis=0)
res=[]
for el in [2.,8.,20.,50.,90.]:
 reference=sky(el,640,2,128,2)
 old=sky(el,32,1,12,1)
 new=sky(el,64,2,32,2)
 res.append({'view_elevation_deg':el,'legacy_max_band_relative_error':float(np.max(abs(old-reference)/reference)),'refined_max_band_relative_error':float(np.max(abs(new-reference)/reference)), 'legacy_mean_ratio':float(np.mean(old/reference)), 'refined_mean_ratio':float(np.mean(new/reference))})
r={'scope':'Quadrature convergence for the same reduced single-scattering sky, not measured atmosphere validation','sun_elevation_deg':float(np.rad2deg(np.arcsin(sun[2]))),'solar_path':results,'sky':res}
# JSON is emitted to stdout; callers choose the destination.
print(json.dumps(r,indent=2))
