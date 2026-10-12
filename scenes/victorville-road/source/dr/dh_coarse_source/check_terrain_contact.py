"""Bounded true-terrain vertex contact check after a reviewed coarse replacement.
No rigid-body/contact-area proof. Optional downward settling changes only Z.
"""
from pathlib import Path
import gc,hashlib,json
import numpy as np

def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def read(data,key,width=3,dtype='f4'):
 a=np.empty((len(data),width),dtype=dtype) if width>1 else np.empty(len(data),dtype=dtype)
 data.foreach_get(key,a.ravel());return a

def sample_indices(world,limit=512):
 # Stratify the entire footprint, selecting each cell's lowest actual vertex.
 xy=world[:,:2];lo=xy.min(0);span=np.maximum(xy.max(0)-lo,1e-12)
 q=np.minimum(((xy-lo)/span*16).astype(int),15);cell=q[:,0]+16*q[:,1]
 order=np.lexsort((world[:,2],cell));_,first=np.unique(cell[order],return_index=True)
 ids=order[first];low=np.argsort(world[:,2],kind='stable')[:min(256,len(world))]
 return np.unique(np.r_[ids,low])[:limit]

# These exact support errors are the only failures converted to a missing value.
# Memory, invalid-input and numerical errors must remain fatal.
SUPPORT_ERRORS = {
 'Source query outside bounded support',
 'Source query has a coverage gap',
 'Point is outside actual source triangles; no extrapolation',
}
def supported_heights(sampler, xy, block=512):
 xy=np.asarray(xy,dtype=float).reshape(-1,2)
 assert np.isfinite(xy).all()
 out=np.full(len(xy),np.nan)
 def query(ids):
  if not len(ids):return
  try:out[ids]=sampler.height(xy[ids])
  except ValueError as error:
   if str(error) not in SUPPORT_ERRORS:raise
   if len(ids)>1:
    mid=len(ids)//2;query(ids[:mid]);query(ids[mid:])
 for first in range(0,len(xy),block):query(np.arange(first,min(first+block,len(xy))))
 return out

def apply(scene,cfg,out):
 assert cfg['revision']==1
 from context_mesh_refine_ab import SourceSampler
 path=Path(cfg['payload']);assert hashlib.sha256(path.read_bytes()).hexdigest()==cfg['payload_sha256']
 p=np.load(path,allow_pickle=False);co=p['source_coordinates'].copy();co[:,2]+=p['delta'];tri=p['tri']
 sampler=SourceSampler(co,tri,np.arange(len(tri)),max_triangles=500000,max_bin_entries=4000000)
 xy_min=co[:,:2].min(0);xy_max=co[:,:2].max(0)
 rows=[];xyz_witness={};fallback=None;fallback_report=None;settle=bool(cfg.get('settle_downward',False));tol=float(cfg.get('embedding_m',.000020));assert 0<tol<=.000050
 def check(label,world,allow_scene=False):
  nonlocal fallback,fallback_report
  ids=sample_indices(world);xy=world[ids,:2];inside=np.all((xy>=xy_min)&(xy<=xy_max),axis=1)
  z=np.full(len(ids),np.nan)
  # Unsupported exact-triangle queries are reported; never extrapolated.
  if inside.any():z[inside]=supported_heights(sampler,xy[inside])
  fallback_count=0
  if allow_scene and np.any(~np.isfinite(z)):
   if fallback is None:
    # Reuse the existing exact current-mesh sampler for farther AS instances.
    # This is actual Blender loop triangulation, not a terrain formula or BVH.
    from sample_final_surface_an import _mesh_sampler,SampleConfig
    assert all(o.matrix_world.translation.x<0 for o in as_objects)
    boxes=np.concatenate([np.asarray([o.matrix_world@__import__('mathutils').Vector(v) for v in o.bound_box])[:,:2]for o in as_objects])
    lo=boxes.min(0)-.02;hi=boxes.max(0)+.02
    limits=SampleConfig(local_triangle_cap=1000000,source_triangle_cap=3000000,source_vertex_cap=1600000,bin_entry_cap=4000000,query_product_cap=250000)
    fallback=_mesh_sampler(scene.objects['Graded shoulder and alluvial plain -1'],(lo[0],hi[0],lo[1],hi[1]),limits,.20)
    fallback_report=fallback.report
   missing=~np.isfinite(z);z[missing]=fallback.height(xy[missing]);fallback_count=int(np.isfinite(z[missing]).sum())
  valid=np.isfinite(z);minimum=float(np.min(world[ids[valid],2]-z[valid])) if valid.any() else None
  drop=max(0.,minimum+tol) if minimum is not None and settle else 0.
  assert drop<.025,('Unexpected large settling, stop instead of hiding source mismatch',label,drop)
  row={'body':label,'sampled_vertices':len(ids),'valid_terrain_samples':int(valid.sum()),'current_scene_fallback_samples':fallback_count,'minimum_vertex_clearance_before_m':minimum,'settled_down_m':drop,'minimum_vertex_clearance_after_m':minimum-drop if minimum is not None else None}
  rows.append(row);return drop
 cg=scene.objects['CG finite 18–60 mm historical gravel pockets'];assert np.array_equal(np.asarray(cg.matrix_world),np.eye(4));pos=read(cg.data.vertices,'co');oldpos=pos.copy();ind=read(cg.data.attributes['prototype'].data,'value',1,'i4');yaw=read(cg.data.attributes['yaw'].data,'vector');xyz_witness['CG_ids_yaw']=digest(np.frombuffer(ind.tobytes()+yaw.tobytes(),dtype='u1'))
 for proto in cfg['CG_prototypes']:
  mesh=scene.objects[f'CG finite gravel {proto:03d}'].data;v=read(mesh.vertices,'co').astype(float)
  for i in np.flatnonzero(ind==proto):
   from mathutils import Euler
   rotation=np.asarray(Euler(yaw[i].astype(float).tolist(),'XYZ').to_matrix(),dtype=float)
   world=v@rotation.T+pos[i];drop=check('CG point '+str(int(i)),world);pos[i,2]-=drop
 if settle:cg.data.vertices.foreach_set('co',pos.ravel());cg.data.update()
 as_objects=[o for o in scene.objects if o.type=='MESH' and o.data.name in cfg['AS_mesh_names'] and not o.hide_render]
 for ob in as_objects:
  v=read(ob.data.vertices,'co').astype(float);m=np.asarray(ob.matrix_world,dtype=float);world=v@m[:3,:3].T+m[:3,3]
  drop=check(ob.name,world,allow_scene=True)
  if drop:
   # Change world Z correctly even if a source instance is parented.
   matrix=ob.matrix_world.copy();matrix.translation.z-=drop;ob.matrix_world=matrix
 assert np.array_equal(pos[:,:2],oldpos[:,:2]);assert np.all(pos[:,2]<=oldpos[:,2]);assert digest(np.frombuffer(read(cg.data.attributes['prototype'].data,'value',1,'i4').tobytes()+read(cg.data.attributes['yaw'].data,'vector').tobytes(),dtype='u1'))==xyz_witness['CG_ids_yaw']
 report={'revision':1,'terrain_payload_sha256':cfg['payload_sha256'],'bodies':rows,'current_scene_fallback_sampler':fallback_report,'CG_before_positions_sha256':digest(oldpos),'CG_after_positions_sha256':digest(pos),'CG_XY_ids_yaws_unchanged':True,'downward_settling_enabled':settle,'settled_bodies':sum(r['settled_down_m']>0 for r in rows),'unsupported_bodies':sum(r['valid_terrain_samples']==0 for r in rows),'embedding_m':tol,'limits':['Actual source-triangle height at up to512 footprint-stratified/low vertices per body; not full triangle-intersection or rigid-body equilibrium proof.','AS samples outside CE use actual current left-soil mesh triangles; any remaining unsupported body is reported, never settled against an invented plane.','Contact is an explicitly separate representation correction; historical sediment ledgers remain unchanged.']}
 (Path(out)/'COARSE_ACTUAL_TERRAIN_CONTACT.json').write_text(json.dumps(report,indent=2)+'\n');del sampler,fallback,co,tri,p;gc.collect();return report
