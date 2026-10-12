"""CE in-memory terrain/surface/placement coupling, never saves a scene."""
from pathlib import Path
from types import SimpleNamespace
import json,time,hashlib,gc
import bpy,numpy as np
from context_mesh_refine_ab import _read,SourceSampler
from terrain_normal_transfer_ah import update_normals
import prepare_physical_lenses as legacy
GROUND='Graded shoulder and alluvial plain -1'
BOUNDS=(-7.,-3.36,-.9,18.)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def apply(scene,cfg,out):
 if cfg.get('safe_normal_transfer'):
  from terrain_normal_transfer_cg import update_normals as selected_normal_transfer
 else:selected_normal_transfer=update_normals
 start=time.monotonic();assert cfg['revision']==1 and sha(cfg['payload'])==cfg['payload_sha256'];p=np.load(cfg['payload'],allow_pickle=False);report=json.loads(Path(cfg['report']).read_text());ground=scene.objects[GROUND];me=ground.data
 assert me.users==1 and not ground.modifiers and np.array_equal(np.asarray(ground.matrix_world),np.eye(4))
 co=_read(me.vertices,'co',3);assert hashlib.sha256(co.tobytes()).hexdigest()==report['source']['source_full_co_sha256'];me.calc_loop_triangles();tri=_read(me.loop_triangles,'vertices',3,np.int32);assert hashlib.sha256(tri.tobytes()).hexdigest()==report['source']['source_full_tri_sha256']
 ids=p['source_vertex_ids'];lc=p['source_coordinates'];lt=p['tri'];assert np.array_equal(co[ids],lc);delta=np.zeros(len(co));delta[ids]=p['delta'];foundation=p['foundation'];sediment=p['sediment'];move=foundation+np.minimum(sediment,0)
 # Geometry changing triangles must lie entirely outside the fixed CB pavement
 # top. This is stronger than a changed-vertex test.
 active=np.any(abs(delta[tri])>1e-10,axis=1);maxx=float(co[tri[active],0].max())
 strip=scene.objects['CB continuous pavement edge top'];sc=_read(strip.data.vertices,'co',3);stripxmin=float(sc[:,0].min());assert maxx<stripxmin,('Changed soil triangles overlap pavement XY',maxx,stripxmin);del sc
 sampler=SourceSampler(lc,lt,np.arange(len(lt)),max_triangles=500000,max_bin_entries=4000000)
 def sample(values,xy):
  q=np.asarray(xy).reshape(-1,2);v=np.zeros(len(q));rows=np.flatnonzero(legacy.in_bounds(q,BOUNDS))
  for a in range(0,len(rows),2048):
   ix=rows[a:a+2048];v[ix]=sampler.sample(values,q[ix])
  return v
 point=[]
 for name in (legacy.ORIGINS,'U approved R5D density / projected chip and grit supplement','AP graded margin / exact metric lag instances'):
  ob=scene.objects[name];before=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,before);dz=sample(move,world[:,:2]);legacy.write_world_z(ob,before,dz);point.append(dict(object=name,moved=int(np.count_nonzero(dz)),delta_range_m=[float(dz.min()),float(dz.max())]))
 legacy.EDIT_BOUNDS=BOUNDS;legacy.PATCH_BOUNDS=(BOUNDS[0]-.22,BOUNDS[1]+.22,BOUNDS[2]-.22,BOUNDS[3]+.22);legacy.in_bounds.__defaults__=(BOUNDS,0.)
 rigid=[]
 for name in legacy.RIGID:
  ob=scene.objects[name];before=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,before);parts=legacy.local_components(ob.data,world);dz=np.zeros(len(before));count=0
  for ii in parts:
   q=world[ii,:2];centre=(q.min(0)+q.max(0))*.5
   if legacy.in_bounds(centre[None],BOUNDS)[0]:dz[ii]=float(sample(move,q).min());count+=int(np.max(abs(dz[ii]))>1e-10)
  legacy.write_world_z(ob,before,dz);rigid.append(dict(object=name,moved_complete_bodies=count))
 roots=[];prefixes=legacy.PLANT_PREFIXES+('AP layered scrub /','AQ layered scrub /','AS sparse outer fragment /')
 for ob in scene.objects:
  if ob.hide_render or not ob.name.startswith(prefixes):continue
  q=np.asarray(ob.matrix_world.translation,float)
  if not legacy.in_bounds(q[None,:2],BOUNDS)[0]:continue
  if ob.name.startswith('AS sparse outer fragment /'):
   w=legacy.world_coordinates(ob,legacy.read_coordinates(ob.data));dz=float(sample(move,w[:,:2]).min())
  else:dz=float(sample(p['delta'],q[:2])[0])
  m=ob.matrix_world.copy();m.translation.z+=dz;ob.matrix_world=m;roots.append(dict(object=ob.name,z_shift_m=dz))
 normal=_read(me.corner_normals,'vector',3);after=co.copy();after[:,2]+=delta;me.vertices.foreach_set('co',after.astype('f4').ravel());me.update();nr=selected_normal_transfer(me,SimpleNamespace(triangles=tri),co,after,delta,normal)
 # Retain original intrinsic material endpoints. Change scene response fields
 # from the same finite stock that changed terrain, not an unrelated tint mask.
 def read(name):return _read(me.attributes[name].data,'value',1)
 gate=p['gate'];removed=p['removed'];dep=p['deposited'];remaining=p['stock']-removed;scour=removed.sum(1)
 coat=read('ai_fine_coat');oldcoat=coat[ids].copy();skin=-np.log1p(-np.clip(oldcoat,0,1-1e-8))*.00035;newcoat=-np.expm1(-(np.maximum(skin-scour,0)+dep[:,0])/.00035);coat[ids]=oldcoat*(1-gate)+newcoat*gate
 lag=read('ai_coarse_lag');mix=remaining/np.maximum(remaining.sum(1)[:,None],1e-20);enrich=np.clip((mix[:,1:].sum(1)-.25)/.45,0,1);exposure=np.maximum(lag[ids],enrich*(-np.expm1(-scour/.001)))*(1-newcoat);lag[ids]=lag[ids]*(1-gate)+exposure*gate
 matrix=read('ak_historical_matrix');matrix[ids]=matrix[ids]*(1-gate)+np.clip((mix[:,0]-.68)/.16,0,1)*gate
 compact=read('ak_historical_compaction');compact[ids]=compact[ids]*(1-gate)+(.72*(1-p['core'])+.28)*np.exp(-scour/.015)*gate
 for name,v in [('ai_fine_coat',coat),('ai_coarse_lag',lag),('ak_historical_matrix',matrix),('ak_historical_compaction',compact)]:me.attributes[name].data.foreach_set('value',v.astype('f4'))
 auth=np.zeros(len(co),'f4');auth[ids]=gate;attr=me.attributes.new('ce_surface_domain','FLOAT','POINT');attr.data.foreach_set('value',auth)
 report.update(changed_vertices=int(np.count_nonzero(delta)),point_placements=point,rigid_placements=rigid,roots=roots,normals=nr,changed_triangles_max_x_m=maxx,pavement_strip_min_x_m=stripxmin,changed_soil_vs_pavement_xy_disjoint=True,pavement_support_objects_unchanged=True,instance_policy='Existing particles move by foundation plus erosion; deposited sediment buries them. Roots follow total terrain. Rigid bodies translate by minimum footprint shift; no shape/scale/identity/material edits.',contact_limits='Continuous pavement top XY-disjoint from changed ground triangles. Individual particle packing and complete body collisions are not dynamically solved.',material_policy='Intrinsic R5D and AZ endpoints retained; fine exposure, residual lag and matrix/compaction derived from same finite class redistribution. No new tint or texture noise.',fresh_hydraulic_simulation=False,source_scene_saved=False,elapsed_seconds=time.monotonic()-start)
 (Path(out)/'COUPLED_SHOULDER_CE.json').write_text(json.dumps(report,indent=2)+'\n');print('CE_APPLIED',json.dumps(report),flush=True)
 del p,co,after,tri,delta,normal,sampler,coat,lag,matrix,compact;gc.collect();return report

def claim_surface_authority(scene,out):
 me=scene.objects[GROUND].data;cd=_read(me.attributes['ce_surface_domain'].data,'value',1);cc=_read(me.attributes['cc_finite_surface_authority'].data,'value',1);me.attributes['cc_finite_surface_authority'].data.foreach_set('value',np.maximum(cc,cd).astype('f4'));return dict(policy='Same finite current surface owns closure in CE domain; no second BW historical overcoat',vertices_with_new_authority=int((cd>cc).sum()))
