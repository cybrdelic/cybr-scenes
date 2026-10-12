"""Read-only exact camera receiver and actual stored corner-normal diagnosis."""
from pathlib import Path
import json,math
import numpy as np

def probe(scene,out):
 import bpy
 from mathutils import Vector
 d=bpy.context.evaluated_depsgraph_get();c=scene.camera;P=c.calc_matrix_camera(d,x=900,y=675,scale_x=1,scale_y=1);inv=(P@c.matrix_world.inverted()).inverted();o=c.matrix_world.translation.copy();sun=Vector((-.7595045499001313,.5318108111446443,.374606593415912));rows=[]
 for x,y in [(480,240),(450,230),(500,245),(530,240),(480,280)]:
  a=inv@Vector((2*(x+.5)/900-1,1-2*(y+.5)/675,-1,1));q=Vector((a.x/a.w,a.y/a.w,a.z/a.w));v=(q-o).normalized();hit,loc,norm,face,ob,m=scene.ray_cast(d,o,v,distance=5.)
  r=dict(pixel_900=[x,y],hit=hit)
  if hit:
   r.update(object=ob.name,face=face,location=list(loc),geometric_normal=list(norm),geometric_solar_cosine=float(norm.dot(sun)))
   ev=ob.evaluated_get(d);me=ev.data
   if ev.type=='MESH' and 0<=face<len(me.polygons):
    f=me.polygons[face];nmat=m.to_3x3().inverted().transposed();corners=[(nmat@me.corner_normals[i].vector).normalized() for i in f.loop_indices];r['stored_corner_normals']=[list(n)for n in corners];r['corner_solar_cosines']=[float(n.dot(sun))for n in corners];r['material']=me.materials[f.material_index].name if f.material_index<len(me.materials)else None
   h2,l2,n2,f2,ob2,m2=scene.ray_cast(d,loc+sun*1e-5,sun,distance=5.);r['solar_ray_hit']=dict(object=ob2.name,location=list(l2),distance_m=float((l2-loc).length))if h2 else None
  rows.append(r)
 rec=dict(method='Blender evaluated scene ray_cast for actual primary receiver, then stored actual corner normals and solar ray. Instance visibility is subject to Blender scene-ray API semantics; prior exact coarse-instance ray is retained.',camera=list(o),rows=rows)
 Path(out,'DARK_PATCH_RECEIVER_PROBE.json').write_text(json.dumps(rec,indent=2)+'\n');print('RECEIVER_PROBE',json.dumps(rec),flush=True);return rec
