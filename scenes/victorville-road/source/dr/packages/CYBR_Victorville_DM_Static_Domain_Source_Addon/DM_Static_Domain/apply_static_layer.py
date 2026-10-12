"""DM exact-total static allocation. Original event and mixed reserves fixed."""
from pathlib import Path
import json,hashlib,time,gc
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def read(seq,key,n=3,d='f4'):
 a=np.empty((len(seq),n),d);seq.foreach_get(key,a.ravel());return a

def apply(scene,cfg,out):
 import bpy
 from context_mesh_refine_ab import SourceSampler
 import prepare_physical_lenses as legacy
 start=time.monotonic();out=Path(out);assert sha(cfg['field'])==cfg['field_sha256'];f=np.load(cfg['field']);co=f['co'];tri=f['tri'];sampler=SourceSampler(co,tri,np.arange(len(tri)),max_triangles=500000,max_bin_entries=4000000)
 bounds=(-7.,-3.36,-.9,18.);rows=[];saved={}
 def sample(xy):
  xy=np.asarray(xy);v=np.zeros(len(xy));inside=(xy[:,0]>=bounds[0])&(xy[:,0]<=bounds[1])&(xy[:,1]>=bounds[2])&(xy[:,1]<=bounds[3]);ids=np.flatnonzero(inside);ids=ids[np.lexsort((xy[ids,1],np.floor(xy[ids,0]/.045)))]
  for s in range(0,len(ids),2048):
   ii=ids[s:s+2048];v[ii]=sampler.sample(f['cap_m'],xy[ii])
  assert v.min()>=-1e-10 and v.max()<.013;return np.maximum(v,0)
 role=np.load(out/'DG_EXACT_ROLE_AND_Z_CHANGE.npz');selected=role['surface_representative'];classes=role['class_id']
 fine='U approved R5D density / projected chip and grit supplement';names=[fine,'AP graded margin / exact metric lag instances','CG finite 18–60 mm historical gravel pockets']
 for name in names:
  ob=scene.objects[name];assert np.array_equal(np.asarray(ob.matrix_world),np.eye(4));before=read(ob.data.vertices,'co');pi=read(ob.data.attributes['prototype'].data,'value',1,'i4');yaw=read(ob.data.attributes['yaw'].data,'vector');identity=digest(before[:,:2])+digest(pi)+digest(yaw);cap=sample(before[:,:2])
  if name==fine:
   n=len(before);assert np.all(classes[:n]>0);exempt=selected[:n];cap[exempt]=0
  else:exempt=np.zeros(len(before),bool)
  after=before.copy();after[:,2]-=cap.astype('f4');assert np.all(after[:,2]<=before[:,2]);ob.data.vertices.foreach_set('co',after.ravel());ob.data.update();assert digest(read(ob.data.vertices,'co')[:,:2])+digest(read(ob.data.attributes['prototype'].data,'value',1,'i4'))+digest(read(ob.data.attributes['yaw'].data,'vector'))==identity
  rows.append({'object':name,'bodies':len(before),'lowered_gt_0p1mm':int((cap>.0001).sum()),'lowered_gt_1mm':int((cap>.001).sum()),'finite_deposit_representatives_exempt':int(exempt.sum()),'cap_depth_quantiles_m':np.percentile(cap,[0,25,50,75,100]).tolist(),'identity_xy_prototype_yaw':identity,'before_z_sha256':digest(before[:,2]),'after_z_sha256':digest(after[:,2])});saved[name]={'before':before[:,2],'after':after[:,2],'cap':cap.astype('f4')}
 # Source-scale fine sand lives in the original fine layer or newer retained
 # deposits. Its exact existing bank and DG roles are preserved, not sunk below
 # its own fine substrate and not counted as an extra newly generated inventory.
 sand=scene.objects['CZ current-view original sand instances'];sand_pin=digest(read(sand.data.vertices,'co'))
 # Merged historical rigid bodies: move each connected component as a whole.
 old_bounds=legacy.PATCH_BOUNDS;legacy.PATCH_BOUNDS=(-7.25,-3.11,-1.15,18.25)
 try:
  for name in legacy.RIGID:
   ob=scene.objects[name];local=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,local);parts=legacy.local_components(ob.data,world);dz=np.zeros(len(local));moved=0
   for ii in parts:
    # Minimum field under a body's actual footprint avoids overclaiming full
    # cap support where a large fragment straddles a domain boundary.
    values=sample(world[ii,:2]);d=float(values.min());dz[ii]=-d;moved+=int(d>.0001)
   legacy.write_world_z(ob,local,dz);rows.append({'object':name,'connected_bodies':len(parts),'lowered_gt_0p1mm':moved,'maximum_rigid_shift_m':float(-dz.min()),'rigid_translation_only':True})
 finally:legacy.PATCH_BOUNDS=old_bounds
 as_rows=[]
 for ob in scene.objects:
  if ob.hide_render or not ob.name.startswith('AS sparse outer fragment /'):continue
  local=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,local);c=sample(world[:,:2]);d=float(c.min())
  if d<=0:continue
  before_mesh=digest(local);m=ob.matrix_world.copy();m.translation.z-=d;ob.matrix_world=m;assert digest(legacy.read_coordinates(ob.data))==before_mesh;as_rows.append({'object':ob.name,'shift_m':d,'geometry_sha256':before_mesh})
 # Use the very same original-stock partition to expose a finite fine-area
 # response. Existing event coating remains, with bounded union, not addition.
 ground=scene.objects['Graded shoulder and alluvial plain -1'];me=ground.data;before_co=read(me.vertices,'co');ids=f['source_vertex_ids'];assert np.array_equal(before_co[ids],co);v=read(me.attributes['ai_fine_coat'].data,'value',1).ravel();old=v[ids].copy();cap_fraction=f['cap_area_fraction'].astype(float);thickness=f['optical_layer_thickness_m'].astype(float);area=cap_fraction*(-np.expm1(-thickness/.00035));v[ids]=(1-(1-old)*(1-area)).astype('f4');me.attributes['ai_fine_coat'].data.foreach_set('value',v);assert np.array_equal(before_co,read(me.vertices,'co'));assert sand_pin==digest(read(sand.data.vertices,'co'))
 arrays={}
 for j,(name,row)in enumerate(saved.items()):
  for key,value in row.items():arrays[f'bank{j}_{key}']=value
 np.savez_compressed(out/'DL_EXACT_SUPPORT_CHANGES.npz',**arrays)
 report={'revision':'DM continuous exact-total static cap candidate','field_sha256':cfg['field_sha256'],'inventory':json.loads(Path(cfg['field']).with_suffix('.json').read_text()),'point_banks':rows,'AS_rigid_fragments':as_rows,'fine_sand_bank_unchanged_sha256':sand_pin,'terrain_geometry_unchanged_sha256':digest(before_co),'materials':'Original recipes, pigment and metric normals unchanged. ai_fine_coat bounded union with the finite original cap coverage; existing CC/CE single-authority ordering retained.','old_fine_coat_range':[float(old.min()),float(old.max())],'new_fine_coat_range':[float(v[ids].min()),float(v[ids].max())],'new_mean_area_factor_lumped':float(np.dot((v[ids]-old).astype(float),f['area'])/sum(f['area'])),'physical_sizes_xy_ids_yaw_and_solid_geometry_unchanged':True,'contact':'Only downward translations of already placed bodies. Actual terrain unchanged. No new floating contact can be introduced by vertical lowering; full packing/collision is not solved.','limits':['Authored static geographic reassignment of the same fine-cap total; mixed reserves and events remain fixed. No inferred transport.','Pre-existing heuristic intrinsic embedding is retained; added depth is the explicitly partitioned original fine cap, separate from event overburden.','Finite surface representatives are exempt; original source-size fine sand remains the visible fine-layer representation.','Merged/AS fragments use minimum cap depth on their actual footprint; not dynamic rigid-body settling.','This candidate changes geometry exposure and the corresponding finite surface field together; it is not an isolated material attribution proof.'],'elapsed_seconds':time.monotonic()-start}
 (out/'STATIC_FINE_SUPPORT_DL.json').write_text(json.dumps(report,indent=2)+'\n');print('DL_STATIC_FINE_SUPPORT',json.dumps({'elapsed_seconds':report['elapsed_seconds'],'banks':rows,'AS_bodies':len(as_rows)}),flush=True);del sampler,co,tri,f;gc.collect();return report
