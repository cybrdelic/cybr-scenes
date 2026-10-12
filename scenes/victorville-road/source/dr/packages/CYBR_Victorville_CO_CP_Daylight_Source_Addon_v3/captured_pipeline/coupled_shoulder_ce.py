"""CE authored graded foundation plus conservative historical surface sorting.
SI metres. This is an original static scene model, not calibrated hydraulics.
The broad road earthwork and finite mobile sediment have separate ledgers.
"""
import numpy as np
from scipy.spatial import cKDTree
from scipy.interpolate import CubicSpline,PchipInterpolator
from road_margin_composition_ap import REACHES
from visible_shoulder_flow_ad import sample_field

BOUNDS=(-7.,-3.36,-.9,18.)
def smooth(a,b,v):
 q=np.clip((np.asarray(v)-a)/(b-a),0,1);return q*q*(3-2*q)
def region(p):
 x,y=p.T
 return smooth(-7.,-6.5,x)*(1-smooth(-3.64,-3.36,x))*smooth(-.9,-.6,y)*(1-smooth(16.,18.,y))
def history(p):
 """Nearest analytic spline reach; unequal widths, asymmetric finite banks."""
 p=np.asarray(p,float);core=np.zeros(len(p));receive=core.copy();owner=np.zeros(len(p),int);best=core.copy();cuts=core.copy()
 for ri,r0 in enumerate(tuple(REACHES[:4])+(((-3.39,-.55,.10),(-4.15,-.12,.20),(-4.65,.55,.35),(-5.10,4.10,.53)),)):
  r=np.asarray(r0,float);s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(r[:,:2],axis=0),axis=1))];cs=CubicSpline(s,r[:,:2],bc_type='natural');ar=np.linspace(0,s[-1],int(s[-1]/.018)+2);c=cs(ar);tan=cs(ar,1);tan/=np.linalg.norm(tan,axis=1)[:,None];idx=cKDTree(c).query(p,workers=1)[1]
  diff=p-c[idx];along=np.sum(diff*tan[idx],axis=1);sc=np.clip(ar[idx]+along,0,s[-1]);cc=cs(sc);tt=cs(sc,1);tt/=np.linalg.norm(tt,axis=1)[:,None];dd=p-cc;signed=dd[:,0]*(-tt[:,1])+dd[:,1]*tt[:,0];endpoint=np.maximum(-ar[idx]-along,0)+np.maximum(ar[idx]+along-s[-1],0)
  t=sc/s[-1];width=np.maximum(.18,PchipInterpolator(s,r[:,2])(sc)*1.12);half=width*np.where(signed>0,1.10,.72);u=np.hypot(signed,endpoint)/half
  # Piecewise near-planar bank with small rounded toe/crest, not a Gaussian trench.
  section=np.clip((1-u)/.84,0,1);section=np.where(u>.86,section*smooth(.0,.14,1-u),section);section*=smooth(0,.12,t)
  strength=section*(1-.50*smooth(.72,1,t));depth=(.010+.027*smooth(.05,.65,t))*strength
  update=depth>cuts;owner[update]=(0,0,1,1,0)[ri];cuts=np.maximum(cuts,depth);core=np.maximum(core,strength)
  # Broad receiving patches continue the same reach; no raised ring along banks.
  rv=section*smooth(.40,.85,t)*(1-smooth(.90,1.15,t))
  take=rv>receive;owner[take]=(0,0,1,1,0)[ri];receive=np.maximum(receive,rv)
 return cuts,core,receive,owner

def area_weights(co,tri):
 p=co[tri,:2];area=np.abs((p[:,1,0]-p[:,0,0])*(p[:,2,1]-p[:,0,1])-(p[:,1,1]-p[:,0,1])*(p[:,2,0]-p[:,0,0]))*.5
 a=np.zeros(len(co));np.add.at(a,tri.ravel(),np.repeat(area/3,3));return a,area

def evaluate(co,tri,hist):
 p=co[:,:2].astype(float);z=co[:,2].astype(float);gate=region(p);area,ta=area_weights(co,tri);cut,core,recv,owner=history(p)
 # Smooth survey-like longitudinal datums are fitted to THIS existing surface.
 # They are construction controls, not a filtered new sediment result.
 ys=np.arange(-.8,18.001,.4);tree=cKDTree(p)
 inner=[];outer=[]
 for y in ys:
  ii=tree.query([-3.36,y],k=24)[1];oo=tree.query([-6.7,y],k=24)[1];inner.append(np.median(z[ii]));outer.append(np.median(z[oo]))
 # A low-order longitudinal grade retains road rise while removing old rut bands.
 fi=np.polyfit(ys,np.asarray(inner),3);fo=np.polyfit(ys,np.asarray(outer),3)
 u=np.clip((-3.36-p[:,0])/3.34,0,1);plane=np.polyval(fi,p[:,1])*(1-u)+np.polyval(fo,p[:,1])*u
 work=(1-smooth(1.8,3.25,-3.36-p[:,0]))*.78
 foundation=((plane-z)*work-cut)*gate
 assert np.max(np.abs(foundation))<.15
 # Carry retained AH stock onto the authored foundation. Outside its domain,
 # declare an 18mm regional parent layer, not purported recovered event stock.
 hx,hy=hist['x_m'],hist['y_m'];inside=(p[:,0]>=hx[0])&(p[:,0]<=hx[-1])&(p[:,1]>=hy[0])&(p[:,1]<=hy[-1])
 stock=np.tile(np.array([.72,.23,.05])*.018,(len(p),1))
 ah=hist['remaining_initial_mobile_class_thickness_m']+hist['retained_deposit_by_class_m']
 stock[inside]=sample_field(ah,p[inside],hx,hy)
 # Transport is an explicit reach-constrained capacity redistribution. It is
 # conservative, but has no claim to solve water momentum or rainfall history.
 desired=.0035*core*(1-.9*recv)*gate
 weight=stock*np.array([1.,.24,.035]);mix=np.divide(weight,weight.sum(1)[:,None],out=np.zeros_like(weight),where=weight.sum(1)[:,None]>0)
 removed=np.minimum(stock,desired[:,None]*mix);deposited=np.zeros_like(removed);receiving_weight=(recv**1.3)*gate
 for g in (0,1):
  domain=owner==g
  # Class mass remains within the connected reach group; finite 8mm receiver cap.
  eligible=domain&(receiving_weight>0)&(area>0)
  volume=(removed[domain]*area[domain,None]).sum(0);capacity=(area[eligible]*.008).sum()
  if volume.sum()>capacity:
   removed[domain]*=capacity/max(volume.sum(),1e-30);volume=(removed[domain]*area[domain,None]).sum(0)
  left=volume.copy();cap=np.where(eligible,.008,0.)
  for _ in range(30):
   w=receiving_weight*(cap>1e-12);den=(w*area).sum()
   if den<=0 or left.sum()<1e-14:break
   inc=w[:,None]*left[None]/den;scale=np.minimum(1,np.divide(cap,inc.sum(1),out=np.ones(len(p)),where=inc.sum(1)>0));inc*=scale[:,None];deposited+=inc;left-=(inc*area[:,None]).sum(0);cap-=inc.sum(1)
  assert np.max(np.abs(left))<1e-10,left
 sediment=(deposited-removed).sum(1);delta=foundation+sediment
 assert np.allclose(delta[gate==0],0,atol=1e-10)
 before=(stock*area[:,None]).sum(0);after=((stock-removed+deposited)*area[:,None]).sum(0)
 assert (stock-removed).min()>-1e-12 and np.max(np.abs(after-before))<1e-10
 report=dict(bounds_m=list(BOUNDS),authored_foundation_volume_m3=float((foundation*area).sum()),authored_foundation_delta_range_m=[float(foundation.min()),float(foundation.max())],sediment_delta_range_m=[float(sediment.min()),float(sediment.max())],delta_range_m=[float(delta.min()),float(delta.max())],initial_class_bulk_m3=before.tolist(),final_class_bulk_m3=after.tolist(),class_residual_m3=(after-before).tolist(),transferred_class_bulk_m3=(removed*area[:,None]).sum(0).tolist(),receiving_area_above_1mm_m2=float(area[deposited.sum(1)>.001].sum()),scoured_area_above_1mm_m2=float(area[removed.sum(1)>.001].sum()),changed_area_m2=float(area[abs(delta)>.001].sum()),inner_datum_coefficients=fi.tolist(),outer_datum_coefficients=fo.tolist(),source_triangles=len(tri),source_vertices=len(co),maximum_authored_swale_depth_m=float(cut.max()),model='Authored road grading and shared AP reach hierarchy; finite class-preserving capacity redistribution within each connected reach group',physical_limits='Bulk-volume conservation on actual triangle-lumped horizontal areas, not density-resolved sediment mass or validated hydraulics. Existing AH stock is carried onto new earthwork; old storm trajectory is not claimed valid on this new surface. Outside AH is declared18mm parent stock. No new rain simulation.',contact='Exactly zero at x >= -3.36; existing pavement support union ends inside this boundary. New contact audit required before promotion.')
 return dict(delta=delta.astype('f4'),foundation=foundation.astype('f4'),sediment=sediment.astype('f4'),removed=removed.astype('f4'),deposited=deposited.astype('f4'),gate=gate.astype('f4'),core=core.astype('f4'),receiving=recv.astype('f4'),area=area.astype('f4'),stock=stock.astype('f4')),report
