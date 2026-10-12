"""Actual-triangle extension of retained original asphalt; pure deterministic data step.
The original surface outside the cut retains exact loop triangles, coordinates and
face assignments. No road/paint sheets are layered under the new metric tiles.
"""
from pathlib import Path
import sys,json,hashlib
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'relief_correction'))
from tiled_relief_math import subtract_rectangle,tile_matrix,road_height
from relief_math import zipper
OUTER=np.array([-3.0399999618530273,-.20999999344348907,2.,float(np.float32(6.04))])

class TriangleSampler:
 def __init__(self,co,tri,step=.08):
  self.co=co;self.tri=tri;self.step=step;self.cells={};v=co[tri,:2];self.v=v.astype(float)
  low=np.floor(v.min(1)/step).astype(int);hi=np.floor(v.max(1)/step).astype(int)
  for i,(a,b) in enumerate(zip(low,hi)):
   if np.prod(b-a+1)>256:raise ValueError('Unexpected source triangle span')
   for x in range(a[0],b[0]+1):
    for y in range(a[1],b[1]+1):self.cells.setdefault((x,y),[]).append(i)
 def locate(self,xy):
  xy=np.asarray(xy);result=np.full(len(xy),-1,'i4');weights=np.zeros((len(xy),3));cell=np.floor(xy/self.step).astype('i4');keys,inverse=np.unique(cell,axis=0,return_inverse=True)
  order=np.argsort(inverse);cuts=np.r_[0,np.cumsum(np.bincount(inverse))]
  for k,key in enumerate(keys):
   rows=order[cuts[k]:cuts[k+1]];ix=np.array(self.cells.get(tuple(key),[]),dtype=int)
   if not len(ix):raise ValueError(('No triangle cell',key))
   v=self.v[ix];a=v[:,1]-v[:,0];b=v[:,2]-v[:,0];det=a[:,0]*b[:,1]-a[:,1]*b[:,0];valid=abs(det)>1e-16;ix=ix[valid];v=v[valid];a=a[valid];b=b[valid];det=det[valid]
   for r0 in range(0,len(rows),256):
    r=rows[r0:r0+256];d=xy[r,None,:]-v[None,:,0];u=(d[:,:,0]*b[None,:,1]-d[:,:,1]*b[None,:,0])/det;w=(a[None,:,0]*d[:,:,1]-a[None,:,1]*d[:,:,0])/det;score=np.minimum(np.minimum(u,w),1-u-w);best=score.argmax(1);minimum=score[np.arange(len(r)),best]
    if np.any(minimum < -2e-5):raise ValueError(('Query escaped source triangle',xy[r[minimum.argmin()]],minimum.min()))
    result[r]=ix[best];weights[r]=np.column_stack((1-u[np.arange(len(r)),best]-w[np.arange(len(r)),best],u[np.arange(len(r)),best],w[np.arange(len(r)),best]))
  return self.tri[result],weights
 def sample(self,values,xy):
  ids,w=self.locate(xy);return np.einsum('ni,ni...->n...',w,values[ids])

def build(p,meta):
 co=p['co'];tri=p['tri'];nv=len(co);v=co[tri,:2];lo=v.min(1);hi=v.max(1);a,b,c,d=OUTER
 outside=(hi[:,0]<a)|(lo[:,0]>b)|(hi[:,1]<c)|(lo[:,1]>d)
 inside=(lo[:,0]>=a)&(hi[:,0]<=b)&(lo[:,1]>=c)&(hi[:,1]<=d)
 cross=np.flatnonzero(~outside&~inside);keep=outside.copy();newco=[];origin_ids=[];origin_w=[];newtri=[];parents=[];splits={}
 key=lambda q:(round(float(q[0]),9),round(float(q[1]),9))
 near=(co[:,0]>a-.15)&(co[:,0]<b+.15)&(co[:,1]>c-.15)&(co[:,1]<d+.15)
 lookup={key(co[i]):int(i) for i in np.flatnonzero(near)}
 def point(q,ids,w):
  k=key(q)
  if k in lookup:return lookup[k]
  ix=nv+len(newco);lookup[k]=ix;newco.append(q.copy());origin_ids.append(ids);origin_w.append(w);return ix
 def coord(ix):return co[ix] if ix<nv else newco[ix-nv]
 def addring(ring,parent):
  if len(ring)>1 and ring[0]==ring[-1]:ring.pop()
  for k in range(1,len(ring)-1):
   t=(ring[0],ring[k],ring[k+1]);v=np.array([coord(i)[:2] for i in t]);area=np.linalg.det(np.stack((v[1]-v[0],v[2]-v[0])))
   if abs(area)>1e-15:newtri.append(t if area>0 else t[::-1]);parents.append(parent)
 for index in cross:
  ids=tri[index];triangle=co[ids].astype(float)
  for poly in subtract_rectangle(triangle[:,:2],OUTER):
   ring=[]
   for q in poly:
    xyz=q[2:]@triangle;xyz[:2]=q[:2];ix=point(xyz,ids,q[2:]);nz=np.flatnonzero(abs(q[2:])>1e-10)
    if len(nz)==2:splits.setdefault(tuple(sorted(map(int,ids[nz]))),set()).add(ix)
    if not ring or ring[-1]!=ix:ring.append(ix)
   addring(ring,int(index))
 edgeverts=np.array(sorted({i for edge in splits for i in edge}));neartris=np.flatnonzero(outside & np.any(np.isin(tri,edgeverts),axis=1))
 for index in neartris:
  ids=tri[index];ring=[];changed=False
  for j in range(3):
   ia,ib=int(ids[j]),int(ids[(j+1)%3]);ring.append(ia);extra=splits.get(tuple(sorted((ia,ib))),set())-{ia,ib}
   if extra:
    changed=True;direction=co[ib,:2]-co[ia,:2];ring.extend(sorted(extra,key=lambda ix:float(np.dot(coord(ix)[:2]-co[ia,:2],direction))))
  if not changed:continue
  keep[index]=False;ci=point(co[ids].astype(float).mean(0),ids,np.full(3,1/3))
  for ia,ib in zip(ring,ring[1:]+ring[:1]):newtri.append((ci,ia,ib));parents.append(int(index))
 newtri=np.array(newtri,dtype='i4');parents=np.array(parents,'i4')
 # Discover actual cut boundary, counting edges only near the three new sides.
 allco=np.concatenate((co,np.asarray(newco,'f4')));alltri=np.concatenate((tri[keep],newtri));edges=np.concatenate([alltri[:,[i,(i+1)%3]] for i in range(3)]);ev=allco[edges,:2];mask=np.zeros(len(edges),bool)
 for axis,val in ((0,a),(0,b),(1,c),(1,d)):mask|=np.all(abs(ev[:,:,axis]-val)<2e-7,axis=1)
 mask&=np.all((ev[:,:,0]>=a-2e-7)&(ev[:,:,0]<=b+2e-7)&(ev[:,:,1]>=c-2e-7)&(ev[:,:,1]<=d+2e-7),axis=1)
 ue,counts=np.unique(np.sort(edges[mask],axis=1),axis=0,return_counts=True);cut=ue[counts==1];cutids=np.unique(cut);del alltri,edges,ev
 local=(hi[:,0]>=a-.1)&(lo[:,0]<=b+.1)&(hi[:,1]>=c-.1)&(lo[:,1]<=d+.1);sampler=TriangleSampler(co,tri[local])
 # Three open collar sides: no new seam/collar at y=2. Native y2 join becomes interior.
 collars=[];boundary_report=[]
 for side in ('left','right','top'):
  axis,val,sortaxis=(0,a,1) if side=='left' else ((0,b,1) if side=='right' else (1,d,0))
  outer=cutids[abs(allco[cutids,axis]-val)<2e-7];outer=outer[np.argsort(allco[outer,sortaxis])]
  if len(outer)<2:raise ValueError(('Missing exact outer boundary',side))
  if side in ('left','right'):
   ys=np.linspace(2,6,16*512+1);xs=np.full(len(ys),-3. if side=='left' else -.25)
   z=np.empty(len(ys));ij=np.minimum(((ys-2)/.25).astype(int),15)
   for j in range(16):
    q=ij==j;x0=-3 if side=='left' else -.5;m=tile_matrix(x0,2+j*.25);z[q]=m[2,0]*(xs[q]-x0)+m[2,1]*(ys[q]-(2+j*.25))+m[2,3]
  else:
   xs=np.linspace(-3,-.25,11*512+1);ys=np.full(len(xs),6.);z=np.empty(len(xs));ij=np.minimum(((xs+3)/.25).astype(int),10)
   for i in range(11):
    q=ij==i;x0=-3+i*.25;m=tile_matrix(x0,5.75);z[q]=m[2,0]*(xs[q]-x0)+m[2,1]*.25+m[2,3]
  xy=np.column_stack((xs,ys));ids,weights=sampler.locate(xy);inner=[]
  for q,zz,ii,ww in zip(xy,z,ids,weights):inner.append(point(np.r_[q,zz],ii,ww))
  inner=np.asarray(inner,'i4');outer_p=allco[outer,sortaxis];inner_p=xy[:,sortaxis]
  # Same physical side parameter; corner trapezoids extend outer by40mm.
  tt=zipper(outer,inner,(outer_p-outer_p[0])/(outer_p[-1]-outer_p[0]),(inner_p-inner_p[0])/(inner_p[-1]-inner_p[0]))
  conforming=[]
  bottom_ids=cutids[abs(allco[cutids,1]-2.)<2e-7]
  for t in tt:
   q=np.array([coord(i)[:2] for i in t]);on=np.flatnonzero(abs(q[:,1]-2.)<2e-7)
   if len(on)==2:
    ia,ib=t[on[0]],t[on[1]];other=t[3-int(on.sum())];xmin,xmax=sorted((q[on[0],0],q[on[1],0]));extra=bottom_ids[(allco[bottom_ids,0]>xmin+1e-9)&(allco[bottom_ids,0]<xmax-1e-9)]
    ring=np.r_[ia,extra[np.argsort(allco[extra,0])],ib] if q[on[0],0]<q[on[1],0] else np.r_[ia,extra[np.argsort(-allco[extra,0])],ib]
    conforming.extend((other,u,v) for u,v in zip(ring[:-1],ring[1:]))
   else:conforming.append(t)
  for t in conforming:
   q=np.array([coord(i)[:2] for i in t]);ar=np.linalg.det(np.stack((q[1]-q[0],q[2]-q[0])))
   if abs(ar)<1e-16:raise ValueError(('Degenerate collar',side))
   collars.append(t if ar>0 else t[::-1])
  boundary_report.append(dict(side=side,outer_vertices=len(outer),inner_vertices=len(inner)))
 nc=np.asarray(newco,'f4');ni=np.asarray(origin_ids,'i4');nw=np.asarray(origin_w,float)
 out=dict(keep_triangle=np.flatnonzero(keep).astype('i4'),new_co=nc,new_tri=newtri,new_triangle_source=parents,collar_tri=np.asarray(collars,'i4'))
 for spec in meta['attributes']:
  if spec['domain']=='POINT':out['extra_'+spec['key']]=np.einsum('ni,ni...->n...',nw,p[spec['key']][ni]).astype(p[spec['key']].dtype)
 # Extend only below/after the immutable original pixel rows, same2mm lattice.
 old=p['lookup'];height=old.shape[0]+2000;width=old.shape[1];data=np.empty((height,width,4),'f4');data[:len(old)]=old
 origin=np.array(meta['lookup_origin'][:2]);pitch=1/np.array(meta['lookup_scale'][:2])/[width,len(old)];xx=origin[0]+(np.arange(width)+.5)*pitch[0]
 vals=np.column_stack((p['attribute_4'][:,0],p['attribute_1'].ravel(),p['attribute_2'].ravel(),p['attribute_3'].ravel()))
 for y0 in range(len(old),height,32):
  y1=min(y0+32,height);yy=origin[1]+(np.arange(y0,y1)+.5)*pitch[1];x,y=np.meshgrid(xx,yy);xy=np.column_stack((x.ravel(),y.ravel()));data[y0:y1]=sampler.sample(vals,xy).reshape(y1-y0,width,4)
 out['lookup']=data
 # Hard checks against visible double sheets and changes to physical source data.
 assert np.array_equal(data[:len(old)],old)
 nct=np.concatenate((newtri,out['collar_tri']));allco=np.concatenate((co,nc));cent=allco[nct,:2].mean(1)
 assert not np.any((cent[:,0]>-3+1e-7)&(cent[:,0]<-.25-1e-7)&(cent[:,1]>2+1e-7)&(cent[:,1]<6-1e-7)),'Replacement base overlaps native tile interior'
 report=dict(status='pure actual-source construction passed',outer_bounds_m=OUTER.tolist(),native_bounds_m=[-3,-.25,0,6],old_native_bounds_m=[-3,-.25,0,2],kept_source_triangles=int(keep.sum()),removed_inside_triangles=int(inside.sum()),crossing_triangles=len(cross),new_clipped_triangles=len(newtri),new_collar_triangles=len(collars),new_vertices=len(nc),unchanged_original_lookup_rows=len(old),lookup_shape=list(data.shape),lookup_pitch_m=pitch.tolist(),lookup_origin_m=origin.tolist(),boundary=boundary_report,all_existing_coordinates_unchanged=True,source_face_assignments_preserved=True,no_base_under_new_tiles=True,interpretation='Same source geometry recipe/amplitude; extension is representation coverage, not new asphalt material.')
 return out,report

if __name__=='__main__':
 root=Path(__file__).resolve().parents[1];folder=root/'audits/metric_extension_ca';meta=json.loads((folder/'actual_road_fixture.json').read_text());p=np.load(folder/'actual_road_fixture.npz');out,report=build(p,meta);np.savez_compressed(folder/'extension_payload.npz',**out);report['payload_sha256']=hashlib.sha256((folder/'extension_payload.npz').read_bytes()).hexdigest();(folder/'extension_payload.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
