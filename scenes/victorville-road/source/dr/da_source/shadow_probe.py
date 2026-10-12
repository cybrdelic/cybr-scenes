"""Read-only bounded centre-sun ray through the retained close crop's dark patch."""
from pathlib import Path
import json,time,gc
import numpy as np

def probe(scene,out):
 import bpy
 start=time.monotonic();origin=np.array([-4.904404279370176,6.032379635137808,.09742442957284234]);origin[2]+=2e-6;direction=np.array([-.7595045499001313,.5318108111446443,.374606593415912]);hits=[];tested=0;triangles=0;matrices=[]
 def box_hit(ob,m):
  inv=np.linalg.inv(m);o=inv[:3,:3]@origin+inv[:3,3];d=inv[:3,:3]@direction;bb=np.array(ob.bound_box);lo=bb.min(0);hi=bb.max(0);near=0.;far=5.
  for k in range(3):
   if abs(d[k])<1e-12:
    if o[k]<lo[k]or o[k]>hi[k]:return None
   else:
    a,b=(lo[k]-o[k])/d[k],(hi[k]-o[k])/d[k];near=max(near,min(a,b));far=min(far,max(a,b))
  return (o,d)if far>=near else None
 def test(ob,m,label):
  nonlocal tested,triangles
  if ob.type!='MESH' or ob.hide_render or not getattr(ob,'visible_shadow',True):return
  hit=box_hit(ob,m)
  if hit is None:return
  me=ob.data
  if len(me.vertices)>150000:return
  tested+=1;me.calc_loop_triangles();n=len(me.loop_triangles);triangles+=n
  if triangles>1000000:raise ValueError('Shadow probe triangle budget exceeded')
  co=np.empty((len(me.vertices),3),'f4');me.vertices.foreach_get('co',co.ravel());idx=np.empty((n,3),'i4');me.loop_triangles.foreach_get('vertices',idx.ravel());v=co[idx].astype(float);o,d=hit;e1=v[:,1]-v[:,0];e2=v[:,2]-v[:,0];p=np.cross(np.broadcast_to(d,e2.shape),e2);det=np.einsum('ij,ij->i',e1,p);valid=abs(det)>1e-14;inv=np.zeros(n);inv[valid]=1/det[valid];ss=o-v[:,0];u=np.einsum('ij,ij->i',ss,p)*inv;q=np.cross(ss,e1);vv=q@d*inv;t=np.einsum('ij,ij->i',e2,q)*inv;valid&=(u>=-1e-8)&(vv>=-1e-8)&(u+vv<=1+1e-8)&(t>1e-5)&(t<5)
  if valid.any():hits.append(dict(object=label,mesh=me.name,distance_m=float(t[valid].min()),triangle_count=n))
 for ob in scene.objects:
  if any(m.type=='NODES'for m in ob.modifiers):continue
  if ob.name.startswith('Graded shoulder')or ob.name.startswith('Original asphalt native tile'):continue
  test(ob,np.asarray(ob.matrix_world,float),ob.name)
 # Only potentially large existing instance banks. Fine grains cannot create
 # this centimetre-wide soft shadow; terrain and full realized BVHs are skipped.
 dep=bpy.context.evaluated_depsgraph_get();seen_instances=0
 for it in dep.object_instances:
  if not it.is_instance or not it.parent:continue
  name=it.parent.original.name
  if name not in ['AP graded margin / exact metric lag instances','CG finite 18–60 mm historical gravel pockets']:continue
  seen_instances+=1;test(it.object,np.asarray(it.matrix_world,float),name+' / '+it.object.original.name)
 rec=dict(method='Exact Moller–Trumbore intersections on bounded candidate source/evaluated meshes after world-AABB filtering. Solar-centre ray only; no scene geometry/material changes.',origin_world_m=origin.tolist(),toward_sun=direction.tolist(),hits=sorted(hits,key=lambda h:h['distance_m']),tested_meshes=tested,tested_triangles=triangles,examined_coarse_instances=seen_instances,skipped='Terrain, high-vertex static bodies, curves and fine instancers; translucent material optical throughput not evaluated.',elapsed_seconds=time.monotonic()-start)
 (Path(out)/'DARK_PATCH_SHADOW_PROBE.json').write_text(json.dumps(rec,indent=2)+'\n');print('SHADOW_PROBE',json.dumps(rec),flush=True);gc.collect();return rec
