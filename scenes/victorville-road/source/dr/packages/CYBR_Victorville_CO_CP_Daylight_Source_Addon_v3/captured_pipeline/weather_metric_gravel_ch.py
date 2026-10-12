"""CH subordinate weathering of the finite CG gravel bank.
Subtractive edge planes retain each body's parent envelope, location and scale.
No smooth vertex normals, no rounded dome substitution, no repacking.
"""
import numpy as np
from scipy.spatial import ConvexHull,HalfspaceIntersection,cKDTree
from finite_historical_gravel_cg import bank as source_bank

def bank(path):
 records=source_bank(path);rng=np.random.default_rng(2610101919)
 for i,r in enumerate(records):
  original=r['v'].astype(float);center=original.mean(0);p=original-center;hull=ConvexHull(p);planes=hull.equations.copy();diam=r['diameter'];height=r['height'];bevel=diam*rng.uniform(.010,.037);added=[];seen=set()
  # Real intersections cut narrow pieces from convex fracture edges. Varying
  # setback by edge avoids an identical machined fillet around every fragment.
  for fi,face in enumerate(hull.simplices):
   for ni in hull.neighbors[fi]:
    key=tuple(sorted((fi,int(ni))))
    if key in seen:continue
    seen.add(key);n1=hull.equations[fi,:3];n2=hull.equations[ni,:3]
    if n1@n2>.988:continue
    edge=list(set(face).intersection(hull.simplices[ni]));q=p[edge].mean(0)
    if q[2]+center[2]<height*.16:continue # retain original buried support
    n=n1+n2;n/=np.linalg.norm(n);cut=bevel*rng.uniform(.32,1.0);support=n@q-cut
    support=max(support,float((p[original[:,2]<height*.16]@n).max())+1e-10)
    if support>height*.08:added.append([*n,-support])
  if added:planes=np.vstack([planes,added])
  pts=HalfspaceIntersection(planes,np.zeros(3)).intersections;hh=ConvexHull(pts)
  # A second, much narrower corner truncation leaves multi-planar weathering,
  # while broad fracture faces remain hard and geometrically explicit.
  more=[];seen=set()
  for fi,face in enumerate(hh.simplices):
   for ni in hh.neighbors[fi]:
    key=tuple(sorted((fi,int(ni))))
    if key in seen:continue
    seen.add(key);n1=hh.equations[fi,:3];n2=hh.equations[ni,:3]
    if n1@n2>.98:continue
    edge=list(set(face).intersection(hh.simplices[ni]));q=pts[edge].mean(0)
    if q[2]+center[2]<height*.23:continue
    n=n1+n2;n/=np.linalg.norm(n);support=n@q-bevel*rng.uniform(.07,.17)
    support=max(support,float((p[original[:,2]<height*.16]@n).max())+1e-10)
    if support>height*.08:more.append([*n,-support])
  if more:pts=HalfspaceIntersection(np.vstack([planes,more]),np.zeros(3)).intersections
  hh=ConvexHull(pts);f=hh.simplices.copy()
  for j,face in enumerate(f):
   if np.cross(pts[face[1]]-pts[face[0]],pts[face[2]]-pts[face[0]])@pts[face].mean(0)<0:f[j,[1,2]]=f[j,[2,1]]
  v=pts+center
  # Preserve the parent mineral/coating field by interpolation, not recoloring.
  dist,near=cKDTree(original).query(v,k=4);w=1/np.maximum(dist,1e-8);w/=w.sum(1)[:,None];col=(r['color'][near]*w[:,:,None]).sum(1);rough=(r['rough'][near]*w).sum(1)
  assert abs(v[:,2].min())<1e-8,'Weathering must retain original buried support'
  volume=float(hh.volume);assert volume<=r['volume']*(1+1e-6) and volume>r['volume']*.45
  edges=np.sort(np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]])),axis=1);assert np.all(np.unique(edges,axis=0,return_counts=True)[1]==2)
  r.update(parent_volume=r['volume'],parent_radius=r['radius'],v=v.astype('f4'),f=f.astype('i4'),color=col.astype('f4'),rough=rough.astype('f4'),volume=volume,radius=float(np.linalg.norm(v[:,:2],axis=1).max()),weathering_width_m=bevel,area=float(ConvexHull(v[:,:2]).volume))
 return records
