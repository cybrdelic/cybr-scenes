"""Rebuild only broad soil shading normals from the actual current mesh.
Intrinsic R5D/AZ material normal fields and all disconnected particles remain unchanged.
"""
from pathlib import Path
import hashlib,json,time,gc
import numpy as np

def _values(seq,field,width,dtype='f4'):
 a=np.empty((len(seq),width),dtype=dtype);seq.foreach_get(field,a.ravel());return a

def _geometry(me):
 h=hashlib.sha256()
 for seq,field,n,d in [(me.vertices,'co',3,'f4'),(me.loops,'vertex_index',1,'i4'),(me.polygons,'loop_start',1,'i4'),(me.polygons,'loop_total',1,'i4'),(me.polygons,'use_smooth',1,'?')]:h.update(_values(seq,field,n,d).tobytes())
 return h.hexdigest()

def apply(scene,cfg,out):
 import bpy
 assert cfg=={'revision':1};start=time.monotonic();rows=[]
 for ob in scene.objects:
  if ob.type!='MESH' or not ob.name.startswith('Graded shoulder and alluvial plain '):continue
  me=ob.data;before=_geometry(me);names=[m.name if m else None for m in me.materials];old=_values(me.corner_normals,'vector',3);had=me.has_custom_normals
  # Blender's all-zero custom entries request its automatic normals, respecting
  # existing sharp/smooth topology. No averaging of mineral particle facets.
  me.normals_split_custom_set(np.zeros((len(me.loops),3),dtype='f4'));me.update();new=_values(me.corner_normals,'vector',3)
  assert np.isfinite(new).all();assert _geometry(me)==before;assert names==[m.name if m else None for m in me.materials]
  dot=np.sum(old.astype('f8')*new,axis=1);angle=np.rad2deg(np.arccos(np.clip(dot,-1,1)));rows.append(dict(object=ob.name,vertices=len(me.vertices),corners=len(me.loops),had_custom_normals=had,geometry_and_smoothing_flags_sha256=before,coordinates_topology_smooth_flags_material_slots_unchanged=True,old_corner_normals_sha256=hashlib.sha256(old.tobytes()).hexdigest(),new_corner_normals_sha256=hashlib.sha256(new.tobytes()).hexdigest(),angle_deg_p50_p90_p99_max=np.quantile(angle,[.5,.9,.99,1]).tolist(),corners_changed_over_5deg=int(np.sum(angle>5)),corners_changed_over_20deg=int(np.sum(angle>20))))
  del old,new,dot,angle;gc.collect()
 assert len(rows)==2; bpy.context.view_layer.update()
 r=dict(revision='DB broad soil normal reconstruction',objects=rows,source_cause='Actual receiver had a nearly horizontal geometric normal but a retained corner normal tilted about46deg with negative solar cosine. Center-sun ray was unobstructed.',scope='Only automatic broad shading normals on the two continuous soil meshes. All actual geometry, mineral particles, material node graphs, R5D/AZ metric microfields, camera, light, original mountains and color remain unchanged.',limits=['Broad shading follows current tessellated terrain; inherited below-grid analytic broad-normal detail is removed.','This is not a mineral geometry, physical grain-size, material contrast or color correction.','The measured dark patch is a diagnostic; visual qualification requires its matched actual render.'],elapsed_seconds=time.monotonic()-start);Path(out,'BROAD_SOIL_NORMALS_DB.json').write_text(json.dumps(r,indent=2)+'\n');print('DB_SOIL_NORMALS',json.dumps(r),flush=True);return r
