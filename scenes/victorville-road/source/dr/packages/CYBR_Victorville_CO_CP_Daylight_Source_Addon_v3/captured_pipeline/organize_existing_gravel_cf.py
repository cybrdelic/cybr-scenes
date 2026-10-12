"""CF finite-count reconstruction of historical gravel pockets.
Relocates existing 7–31mm AP bodies, retaining every prototype, yaw and mineral.
Not a claim that the latest small storm transported this entire historical lag.
"""
from pathlib import Path
import json,time,hashlib,gc
import numpy as np
import bpy
from context_mesh_refine_ab import _read,SourceSampler
from coupled_shoulder_ce import history,region
from approved_density_lod import PackingIndex
NAME='AP graded margin / exact metric lag instances'

def apply(scene,cfg,out):
 start=time.monotonic();assert cfg['revision']==1;ob=scene.objects[NAME];assert np.array_equal(np.asarray(ob.matrix_world),np.eye(4)) and len(ob.modifiers)==1
 before=_read(ob.data.vertices,'co',3);pr=_read(ob.data.attributes['prototype'].data,'value',1,np.int32);yaw=_read(ob.data.attributes['yaw'].data,'vector',3);assert len(before)==5939
 coll=bpy.data.collections['AP exact coarse lag bank'];bank=sorted(coll.objects,key=lambda q:q.name);assert len(bank)==64 and [x.name for x in bank]==[f'AP exact lag {i:03d}' for i in range(64)]
 dims=[];mins=[];maxs=[];rad=[];vol=[];hashes=[]
 for o in bank:
  co=_read(o.data.vertices,'co',3);o.data.calc_loop_triangles();tri=_read(o.data.loop_triangles,'vertices',3,np.int32);v=co[tri].astype(float);volume=abs(float(np.sum(v[:,0]*np.cross(v[:,1],v[:,2]))/6));vol.append(volume);rad.append(np.linalg.norm(co[:,:2],axis=1).max());mins.append(co[:,2].min());maxs.append(co[:,2].max());dims.append(np.linalg.norm(np.ptp(co[:,:2],axis=0)));hashes.append(hashlib.sha256(co.tobytes()+tri.tobytes()).hexdigest())
 rad=np.asarray(rad);vol=np.asarray(vol);mins=np.asarray(mins);maxs=np.asarray(maxs);dims=np.asarray(dims);assert dims.max()<.032 and dims.min()>.006
 # Rebuild only the nearby historical pocket layout, not farther scrub or the
 # fine-grain substrate. Total coarse body count and solid volume remain exact.
 q=before[:,:2];eligible=(q[:,0]>-6.4)&(q[:,0]<-3.50)&(q[:,1]>-.65)&(q[:,1]<8.0);ids=np.flatnonzero(eligible)
 p=np.load(cfg['terrain_payload'],allow_pickle=False);assert hashlib.sha256(Path(cfg['terrain_payload']).read_bytes()).hexdigest()==cfg['terrain_sha256'];co=p['source_coordinates'].astype(float);co[:,2]+=p['delta'];tri=p['tri'];sampler=SourceSampler(co,tri,np.arange(len(tri)),max_triangles=500000,max_bin_entries=4000000)
 rng=np.random.default_rng(2610101856);proposal=np.c_[rng.uniform(-5.65,-3.52,200000),rng.uniform(-.58,6.5,200000)];cut,core,receive,owner=history(proposal)
 # Coarse windows follow winnowed reaches, interrupted by fine receivers.
 # Density differences arise from that same history, not a texture/noise field.
 score=(.04+.96*core**1.25)*(1-.93*receive)*region(proposal)
 proposal=proposal[rng.random(len(proposal))<score];rng.shuffle(proposal)
 # Packing preserves finite individual silhouettes; no enlarged source bodies.
 packing=PackingIndex(float(rad.max()));unmoved=np.flatnonzero(~eligible)
 for i in unmoved:
  if -5.75<before[i,0]<-3.42 and -.68<before[i,1]<6.6:packing.add(before[i,:2],rad[pr[i]])
 # Exclude existing decimetre fragment footprints. The dense microbed remains
 # underneath, just as a larger partly embedded clast occludes its fine matrix.
 exclusions=[]
 for o in scene.objects:
  if o.hide_render or not o.name.startswith('AS sparse outer fragment /'):continue
  loc=np.asarray(o.matrix_world.translation,float);w=np.array(o.bound_box)@np.asarray(o.matrix_world)[:3,:3].T+loc;r=np.linalg.norm(w[:,:2]-loc[:2],axis=1).max()
  if -5.9<loc[0]<-3.3 and -.8<loc[1]<6.8:exclusions.append((loc[:2],r))
 def blocked(v,r):return any(np.sum((v-c)**2)<(r+rr)**2 for c,rr in exclusions)
 after=before.copy();cursors=[0,0];pools=[proposal,proposal[proposal[:,1]>=3.0]];selected=[];order=ids[np.argsort(-rad[pr[ids]],kind='stable')]
 for i in order:
  rr=rad[pr[i]];pool=1 if dims[pr[i]]>.013 else 0
  while cursors[pool]<len(pools[pool]):
   v=pools[pool][cursors[pool]];cursors[pool]+=1
   if not blocked(v,rr) and packing.clear(v,rr):packing.add(v,rr);selected.append((i,v));break
  else:continue
 assert len(selected)>=.90*len(ids),('Insufficient bounded pocket capacity',len(selected),len(ids))
 ix=np.array([a[0] for a in selected]);xy=np.array([a[1] for a in selected]);z=np.empty(len(xy));coat=np.empty(len(xy));dep=np.empty(len(xy))
 for first in range(0,len(xy),2048):
  sl=slice(first,first+2048);z[sl]=sampler.height(xy[sl]);dep[sl]=sampler.sample(p['deposited'][:,0],xy[sl]);coat[sl]=-np.expm1(-dep[sl]/.00035)
 embed=(maxs-mins)[pr[ix]]*(.23+.52*coat);after[ix,:2]=xy;after[ix,2]=z-mins[pr[ix]]-embed
 assert np.isfinite(after).all();ob.data.vertices.foreach_set('co',after.astype('f4').ravel());ob.data.update();assert np.array_equal(_read(ob.data.attributes['prototype'].data,'value',1,np.int32),pr) and np.array_equal(_read(ob.data.attributes['yaw'].data,'vector',3),yaw)
 report=dict(revision='CF',kind='Authored pre-existing gravel-pocket reconstruction using same connected scoured/fine-receiving history',existing_points=len(before),moved_existing_points=len(ix),unchanged_prototype_histogram=np.bincount(pr,minlength=64).tolist(),prototype_geometry_hashes=hashes,prototype_diameter_range_m=[float(dims.min()),float(dims.max())],exact_total_body_solid_volume_m3=float(vol[pr].sum()),moved_body_solid_volume_m3=float(vol[pr[ix]].sum()),new_particles=0,deleted_particles=0,prototype_shapes_materials_sizes_yaws_changed=False,terrain_changed_by_this_adapter=False,old_and_new_positions_sha256=[hashlib.sha256(a.tobytes()).hexdigest() for a in (before,after.astype('f4'))],pocket_bounds_m=[-5.65,-3.52,-.58,6.5],placement_count_by_y=[int(np.sum((xy[:,1]>=a)&(xy[:,1]<b))) for a,b in [(-.58,.3),(.3,1),(1,3),(3,6.5)]],minimum_embed_fraction=.23,maximum_embed_fraction=.75,source_near_shape_guard='Original AP rule retained: diameters above13mm remain at y>=3m because larger legacy facets are not qualified for close inspection.',largest_fragment_exclusions=len(exclusions),history='Finite number/solid volume of already present bodies reorganized as historical gravel lag. This is not the latest event mass flux, calibrated transport, or a claim of preserved per-cell stock.',contact_limit='Nonoverlapping enclosing disks within this bank and excluded large-fragment footprints; dense underlying micrograins can be occluded. Full multi-body settling is not solved.',elapsed_seconds=time.monotonic()-start)
 np.savez_compressed(Path(out)/'CF_EXACT_POINT_CHANGE.npz',before=before,after=after.astype('f4'),prototype=pr,yaw=yaw)
 (Path(out)/'EXISTING_GRAVEL_POCKETS_CF.json').write_text(json.dumps(report,indent=2)+'\n');p.close();del sampler,co,tri,before,after;gc.collect();print('CF_GRAVEL_POCKETS',json.dumps(report),flush=True);return report
