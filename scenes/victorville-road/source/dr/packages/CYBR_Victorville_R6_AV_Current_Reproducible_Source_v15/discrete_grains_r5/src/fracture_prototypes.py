"""Deterministic fractured convex solids with narrow irregular edge truncation.
Normalized shapes only; the scene assigns all physical particle sizes.
"""
import numpy as np,json
from scipy.spatial import ConvexHull, HalfspaceIntersection
from pathlib import Path
rng=np.random.default_rng(1849);out=[]
for k in range(96):
 # Many intersecting oblique planes, including several competing top planes.
 N=int(rng.integers(5,9));theta=np.arange(N)*2*np.pi/N+rng.uniform(-.2,.2,N)
 planes=[]
 for a in theta:planes.append([np.cos(a),np.sin(a),rng.uniform(-.55,.55),-rng.uniform(.58,.94)])
 for j in range(int(rng.integers(3,6))):
  a=rng.uniform(0,2*np.pi);mag=rng.uniform(.3,1.15);planes.append([np.cos(a)*mag,np.sin(a)*mag,1,-rng.uniform(.46,.83)])
 for j in range(2):planes.append([rng.uniform(-.5,.5),rng.uniform(-.5,.5),-1,-rng.uniform(.45,.75)])
 planes=np.asarray(planes);planes/=np.linalg.norm(planes[:,:3],axis=1)[:,None]
 points=HalfspaceIntersection(planes,np.zeros(3)).intersections;h=ConvexHull(points);raw_points=points.copy();raw_faces=h.simplices.copy()
 # Clip true dihedral edges using short bevel planes, never smooth face normals.
 extra=[];seen=set()
 for fi,tri in enumerate(h.simplices):
  for ni in h.neighbors[fi]:
   key=tuple(sorted((int(fi),int(ni))))
   if key in seen:continue
   seen.add(key);a=h.equations[fi,:3];b=h.equations[ni,:3]
   if np.dot(a,b)>.998:continue
   edge=set(h.simplices[fi]).intersection(h.simplices[ni])
   if len(edge)!=2:continue
   q=points[list(edge)].mean(0);normal=a+b;normal/=np.linalg.norm(normal);width=rng.uniform(.008,.022)
   extra.append([*normal,-np.dot(normal,q)+width])
 if extra:
  pp=np.vstack([planes,np.asarray(extra)]);points=HalfspaceIntersection(pp,np.zeros(3)).intersections;h=ConvexHull(points)
 # Scale to unit maximum XY diameter, bottom0/top1 before scene dimensions.
 points[:,:2]-=(points[:,:2].max(0)+points[:,:2].min(0))/2
 points[:,:2]/=np.ptp(points[:,:2],axis=0).max();points[:,2]=(points[:,2]-points[:,2].min())/np.ptp(points[:,2])
 faces=h.simplices.copy()
 # ConvexHull simplices have no winding guarantee; enforce outward orientation.
 center=points.mean(0)
 for i,face in enumerate(faces):
  p=points[face];normal=np.cross(p[1]-p[0],p[2]-p[0])
  if np.dot(normal,p.mean(0)-center)<0:faces[i,[1,2]]=faces[i,[2,1]]
 raw_points[:,:2]-=(raw_points[:,:2].max(0)+raw_points[:,:2].min(0))/2
 raw_points[:,:2]/=np.ptp(raw_points[:,:2],axis=0).max();raw_points[:,2]=(raw_points[:,2]-raw_points[:,2].min())/np.ptp(raw_points[:,2]);center=raw_points.mean(0)
 for i,face in enumerate(raw_faces):
  p=raw_points[face];normal=np.cross(p[1]-p[0],p[2]-p[0])
  if np.dot(normal,p.mean(0)-center)<0:raw_faces[i,[1,2]]=raw_faces[i,[2,1]]
 out.append(dict(vertices=points.round(9).tolist(),faces=faces.tolist(),fine_vertices=raw_points.round(9).tolist(),fine_faces=raw_faces.tolist()))
r=Path(__file__).resolve().parents[1];(r/'prototypes/fracture_solids.json').write_text(json.dumps(out,separators=(',',':')));print('PROTOTYPES',len(out),'average vertices',np.mean([len(x['vertices']) for x in out]))
