"""CB actual-source top-surface reconstruction; no source scene mutation."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'relief_correction'))
from tiled_relief_math import subtract_rectangle,tile_matrix
from relief_math import zipper,smoothstep
from metric_edge_strip_aa import TriangleSampler,load_height,sample_original_height
BOUNDS=(-3.5,-3.,float(np.float32(-.004)),float(np.float32(6.004)))
def clip_actual(co,tri,bounds):
 nv=len(co);v=co[tri,:2];lo=v.min(1);hi=v.max(1);a,b,c,d=bounds
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
  for poly in subtract_rectangle(triangle[:,:2],bounds):
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
 return dict(keep=np.flatnonzero(keep).astype('i4'),co=np.asarray(newco,'f4'),tri=newtri,parents=parents,origin_ids=np.asarray(origin_ids,'i4'),origin_w=np.asarray(origin_w,float))

def source_ca(root,fixture_path=None,ca_payload_path=None):
 p=np.load(fixture_path or root/'audits/metric_extension_ca/actual_road_fixture.npz');q=np.load(ca_payload_path or root/'audits/metric_extension_ca/extension_payload.npz');co=np.r_[p['co'],q['new_co']];tri=np.r_[p['tri'][q['keep_triangle']],q['new_tri'],q['collar_tri']];parents=np.r_[p['triangle_polygon'][q['keep_triangle']],p['triangle_polygon'][q['new_triangle_source']]];mats=np.r_[p['attribute_7'].ravel()[parents],np.zeros(len(q['collar_tri']),'i4')];attrs=[np.r_[p[f'attribute_{i}'],q[f'extra_attribute_{i}']] for i in range(6)];return co,tri,mats,attrs

def build(root,height_path,step=2,fixture_path=None,ca_payload_path=None,outline_path=None):
 assert step in (1,2,4)
 co,tri,mats,attrs=source_ca(root,fixture_path,ca_payload_path);source_fields_sha=[hashlib.sha256(v.tobytes()).hexdigest() for v in attrs];nv=len(co);a,b,c,d=BOUNDS
 print('CB clip actual base',flush=True);clip=clip_actual(co,tri,BOUNDS);cc=np.r_[co,clip['co']];nt=len(cc);source_attrs=[np.r_[v,np.einsum('ni,ni...->n...',clip['origin_w'],v[clip['origin_ids']]).astype(v.dtype)] for v in attrs];del attrs
 base_tri=np.r_[tri[clip['keep']],clip['tri']];base_mats=np.r_[mats[clip['keep']],mats[clip['parents']]]
 # Actual bottom/top cut interfaces, including every inherited split point.
 edges=np.concatenate([base_tri[:,[i,(i+1)%3]] for i in range(3)]);ev=cc[edges,:2];near=np.all((ev[:,:,0]>=a-1e-7)&(ev[:,:,0]<=b+1e-7)&(ev[:,:,1]>=c-1e-7)&(ev[:,:,1]<=d+1e-7),axis=1);edges=edges[near];u,n=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True);cut_ids=np.unique(u[n==1]);ends=[]
 for yy in (c,d):
  ix=cut_ids[abs(cc[cut_ids,1]-yy)<1e-8];ix=ix[np.argsort(cc[ix,0])];assert len(ix)>2;ends.append(ix)
 # Exact retained physical outside rim, including all irregular fracture knots.
 outline=np.load(outline_path or root/'audits/edge_continuity_cb/actual_left_outline.npz');ids=outline['ids'];pts=co[ids];inside=(pts[:,1]>c)&(pts[:,1]<d);left_ids=np.r_[ends[0][0],ids[inside],ends[1][0]];left=cc[left_ids];assert np.all(np.diff(left[:,1])>=0), 'Physical rim turns backward in Y';duplicate=np.diff(left[:,1])==0;assert duplicate.sum()<=1 and np.all(np.abs(np.diff(left[:,0])[duplicate])<1e-12) and np.all(np.abs(np.diff(left[:,2])[duplicate])<1e-7), 'Unqualified vertical rim step'
 height=load_height(height_path)[::step,::step];near_pitch=.25/(len(height)-1);far_pitch=2*near_pitch
 ys=np.r_[np.linspace(0,2,round(2/near_pitch)+1),np.linspace(2,6,round(4/far_pitch)+1)[1:]]
 print('CB build graded metric grid',len(ys),'rows',flush=True)
 verts=[];rowids=[];offset=nt;row_limits=[]
 for k,y in enumerate(ys):
  low=ys[max(0,k-1)] if k else c;high=ys[min(len(ys)-1,k+1)] if k<len(ys)-1 else d
  lo=np.searchsorted(left[:,1],low);hi=np.searchsorted(left[:,1],high,'right');xb=max(float(np.interp(low,left[:,1],left[:,0])),float(np.interp(high,left[:,1],left[:,0])),float(left[lo:hi,0].max(initial=-np.inf)))+.001
  pitch=near_pitch if y<=2 else far_pitch;nx=int(np.ceil((b-.001-xb)/pitch))+1;assert nx>=8
  x=np.linspace(xb,b-.001,nx);j=min(int(np.floor(y/.25)),23);mat=np.asarray(tile_matrix(-3,j*.25),'f4').astype(float);z=mat[2,0]*(x+3)+mat[2,1]*(y-j*.25)+mat[2,3];xy=np.c_[x,np.full(nx,y)];hh=sample_original_height(height,xy)*smoothstep(0,.125,y)*smoothstep(0,.125,6-y);xyz=np.c_[xy,z+hh].astype('f4');verts.append(xyz);rowids.append(np.arange(offset,offset+nx,dtype='i4'));offset+=nx;row_limits.append((xb,nx,pitch))
 fine=np.concatenate(verts);assert len(fine)<1800000,'CB native source vertex bound exceeded'
 strips=[]
 for u,v in zip(rowids[:-1],rowids[1:]):strips.append(zipper(u,v))
 fine_tri=np.concatenate(strips);del strips,verts
 # Native x=-3 boundary, matching the chosen current source-grid LOD exactly.
 yy=np.linspace(0,6,24*(len(height)-1)+1);right=np.empty((len(yy),3),'f4');right[:,:2]=np.c_[np.full(len(yy),-3.),yy]
 for j in range(24):
  select=(yy>=j*.25)&(yy< (j+1)*.25 if j<23 else yy<=6);y=yy[select];mat=np.asarray(tile_matrix(-3,j*.25),'f4').astype(float);right[select,2]=mat[2,1]*(y-j*.25)+mat[2,3]+sample_original_height(height,np.c_[np.full(len(y),-3.),y])*smoothstep(0,.125,y)*smoothstep(0,.125,6-y)
 right_start=offset;right_ids=np.arange(offset,offset+len(right),dtype='i4');offset+=len(right)
 # Cut right-side end segments meet old base outside the native y0..6 band.
 right_extra=cut_ids[abs(cc[cut_ids,0]-b)<1e-8]
 for endpoint,y in ((0,0.),(-1,6.)):
  match=right_extra[abs(cc[right_extra,1]-y)<1e-10]
  if len(match):
   assert len(match)==1 and np.max(abs(cc[match[0]]-right[endpoint]))<5e-7;right_ids[endpoint]=match[0]
 below=right_extra[cc[right_extra,1]<0];above=right_extra[cc[right_extra,1]>6];below=below[np.argsort(cc[below,1])];above=above[np.argsort(cc[above,1])];right_full_ids=np.r_[below,right_ids,above]
 allco=np.r_[cc,fine,right]
 outer=[ends[0],right_full_ids,ends[1],left_ids];inner=[rowids[0],np.array([i[-1] for i in rowids]),rowids[-1],np.array([i[0] for i in rowids])];joins=[]
 for ou,inn,axis in zip(outer,inner,(0,1,0,1)):
  ta=allco[ou,axis].astype(float);tb=allco[inn,axis].astype(float);ta=(ta-ta[0])/(ta[-1]-ta[0]);tb=(tb-tb[0])/(tb[-1]-tb[0]);tt=zipper(ou,inn,ta,tb);v=allco[tt].astype(float);ar=np.cross(v[:,1,:2]-v[:,0,:2],v[:,2,:2]-v[:,0,:2]);area3=np.linalg.norm(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),axis=1);zero=abs(ar)<=1e-15;assert zero.sum()<=1 and np.all(area3>1e-16),('Degenerate new contact collar',axis,float(area3.min()));flip=ar<0
  if np.array_equal(ou,left_ids):flip|=zero
  tt[flip]=tt[flip,::-1];joins.append(tt)
 strip_tri=np.r_[fine_tri,*joins]
 # Sample only new internal points; existing boundary POINT values are retained.
 print('CB sample exact source fields',len(fine),'points',flush=True)
 sample_xy=fine[:,:2].astype(float);v=co[tri,:2];lo=v.min(1);hi=v.max(1);xyarea=np.abs(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]));del v
 attr_out=[np.empty((len(fine)+len(right),v.shape[1]),'f4') for v in source_attrs]
 for slot in range(61):
  low=slot*.1;high=low+.1;sel=np.flatnonzero((sample_xy[:,1]>=low-1e-8)&(sample_xy[:,1]<(high-1e-8) if slot<60 else sample_xy[:,1]<=6.000001))
  if not len(sel):continue
  face=(lo[:,1]<=high+.001)&(hi[:,1]>=low-.001)&(lo[:,0]<=-2.999)&(hi[:,0]>=-3.5)&(xyarea>1e-13)
  source=TriangleSampler(co,tri[face],cell=.006,max_bucket_entries=300000);it,wt=source.weights(sample_xy[sel]);source_ids=source.triangles[it]
  for out,val in zip(attr_out,source_attrs):out[sel]=np.einsum('ni,ni...->n...',wt,val[source_ids]).astype('f4')
 # Right boundary fields only need their original actual base value on x=-3.
 # Read from the continuous base one micrometre to the left if exactly on the
 # existing aperture edge; this is a bounded field limit, never a geometry offset.
 for slot in range(60):
  low=slot*.1;high=low+.1;sel=np.flatnonzero((yy>=low-1e-8)&(yy<(high-1e-8) if slot<59 else yy<=6.000001));face=(lo[:,1]<=high+.001)&(hi[:,1]>=low-.001)&(lo[:,0]<=-2.999)&(hi[:,0]>=-3.05)&(xyarea>1e-13)
  source=TriangleSampler(co,tri[face],cell=.006,max_bucket_entries=300000);it,wt=source.weights(np.c_[np.full(len(sel),-3.000001),yy[sel]]);source_ids=source.triangles[it]
  for out,val in zip(attr_out,source_attrs):out[len(fine)+sel]=np.einsum('ni,ni...->n...',wt,val[source_ids]).astype('f4')
 point_values=[np.r_[val,tail] for val,tail in zip(source_attrs,attr_out)]
 # Unified-ID contact proof across the new strip and exact clipped base.
 actual=np.r_[base_tri,strip_tri];e=np.concatenate([actual[:,[i,(i+1)%3]] for i in range(3)]);v=allco[e,:2];near=np.all((v[:,:,0]>-3.49)&(v[:,:,0]<=-3+1e-7)&(v[:,:,1]>c-1e-7)&(v[:,:,1]<d+1e-7),axis=1);ue,n=np.unique(np.sort(e[near],axis=1),axis=0,return_counts=True);single=ue[n==1];allowed=set(map(tuple,np.sort(np.c_[left_ids[:-1],left_ids[1:]],axis=1)))|set(map(tuple,np.sort(np.c_[right_ids[:-1],right_ids[1:]],axis=1)));bad=[e for e in single if tuple(e) not in allowed];assert not bad and not (n>2).any(),('Unmatched final surface edge',len(bad),int((n>2).sum()))
 def compact(t):
  ids,inv=np.unique(t,return_inverse=True);return ids,inv.reshape(-1,3).astype('i4')
 bi,bt=compact(base_tri);si,st=compact(strip_tri);out=dict(base_co=allco[bi],base_tri=bt,base_material=base_mats,strip_co=allco[si],strip_tri=st)
 for i,vals in enumerate(point_values):out[f'base_attr_{i}']=vals[bi];out[f'strip_attr_{i}']=vals[si]
 report=dict(step=step,native_grid_pitch_m=near_pitch,near_metric_grid_max_m=near_pitch,far_metric_grid_max_m=far_pitch,original_scene_road_co_sha256=hashlib.sha256(co.tobytes()).hexdigest(),original_scene_road_tri_sha256=hashlib.sha256(tri.tobytes()).hexdigest(),physical_rim_vertices_retained=len(left_ids),physical_rim_xyz_exact=True,retained_float32_vertical_rim_steps=int(duplicate.sum()),new_strip_vertices=len(si),new_strip_triangles=len(st),new_base_vertices=len(bi),new_base_triangles=len(bt),non_native_contact_mismatches=0,overused_edges=0,outer_join_width_min_m=.001,far_ends_m=[c,d],road_tile_phase_m=.25,height_scale_m=.004,source_maps_unchanged=True,source_POINT_fields_sha256=source_fields_sha,old_left_tile_fade_removed=True,geometry_offset_for_field_sample_m=0,field_limit_sample_inset_m=.000001)
 return out,report

if __name__=='__main__':
 root=Path(__file__).resolve().parents[1];folder=root/'audits/edge_continuity_cb';height=root.parents[1]/'materials-cloud-20261009/work/normal_fix/native4096/GeometryHeight.npy';out,report=build(root,height,step=2);np.savez_compressed(folder/'edge_payload_step2.npz',**out);report['payload_sha256']=hashlib.sha256((folder/'edge_payload_step2.npz').read_bytes()).hexdigest();(folder/'edge_payload_step2.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
