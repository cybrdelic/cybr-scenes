"""Metric source-grain exposure and broad-face rigid clast resting.
Keeps every source mesh, body count, prototype, ID, yaw of fine-grain banks and
all body XY. It changes only embed depth and the orientation of tall AS clasts.
No new solid stock or screen-space geometry is introduced.
"""
import numpy as np
from pathlib import Path
import json,hashlib
import bpy
from mathutils import Vector,Matrix
from field_du import hash2,smooth

def read(seq,p,w=1,d='f4'):
 a=np.empty((len(seq),w),d)if w>1 else np.empty(len(seq),d);seq.foreach_get(p,a.ravel());return a

def apply(scene,cfg,out,field,sample,offsets):
 f=np.load(cfg['cap']);q=field.evaluate(f['co'][:,:2]);height=(f['co'][:,2].astype(float)+q['gate']*(q['raw_height']-offsets[-1])).astype('f4')
 def ground(xy):return sample(np.asarray(xy),height)
 bounds=(-6.92,-3.44,-.82,17.92)
 def inside(xy,r=0):return (xy[:,0]>=bounds[0]+r)&(xy[:,0]<=bounds[1]-r)&(xy[:,1]>=bounds[2]+r)&(xy[:,1]<=bounds[3]-r)
 base=Path(cfg['cap']).parent.parent/'stable_grains_dq';catalog=np.load(base/'VIEW_normal_2000.npz');meta=json.loads((base/'VIEW_normal_2000.json').read_text())['prototype_metadata'];order=np.argsort(catalog['id']);ids=catalog['id'][order];roles=catalog['role'][order];fine=[]
 for name,band in [('U approved R5D density / projected chip and grit supplement',0),('CZ current-view original sand instances',64)]:
  ob=scene.objects[name];co=read(ob.data.vertices,'co',3);pi=read(ob.data.attributes['prototype'].data,'value',d='i4')+band;lo=read(ob.data.attributes['grain_id_lo'].data,'value',d='i4');hi=read(ob.data.attributes['grain_id_hi'].data,'value',d='i4');identity=(hi.view('u4').astype('u8')<<np.uint64(32))|lo.view('u4').astype('u8');ix=np.searchsorted(ids,identity);assert np.array_equal(ids[ix],identity);role=roles[ix];chosen=np.flatnonzero(role&inside(co[:,:2],.004));before=co[:,2].copy();low=np.array([v['minimum']for v in meta])[pi[chosen]];high=np.array([v['maximum']for v in meta])[pi[chosen]];h=high-low
  # Original metric source prototypes; representative role lives at this surface.
  z=ground(co[chosen,:2])-(.40*h)-low-.00005;co[chosen,2]=z.astype('f4');ob.data.vertices.foreach_set('co',co.ravel());ob.data.update()
  fine.append({'object':name,'surface_role_count':len(chosen),'source_height_range_m':[float(h.min()),float(h.max())],'source_XY_uint64_ID_and_meshes_unchanged':True,'z_shift_quantiles_m':np.quantile(co[:,2]-before,[0,.1,.5,.9,1]).tolist()})
 ob=scene.objects['CG finite 18–60 mm historical gravel pockets'];co=read(ob.data.vertices,'co',3);before=co.copy();pi=read(ob.data.attributes['prototype'].data,'value',d='i4');bank=sorted(bpy.data.collections['CG finite historical gravel prototype bank'].objects,key=lambda o:o.name);assert len(bank)==192
 lows=[];heights=[];radii=[]
 for p in bank:
  v=read(p.data.vertices,'co',3);lows.append(v[:,2].min());heights.append(np.ptp(v[:,2]));radii.append(np.linalg.norm(v[:,:2],axis=1).max())
 lows=np.array(lows);heights=np.array(heights);radii=np.array(radii);q=field.evaluate(co[:,:2]);cx=np.floor(co[:,0]/.25);cy=np.floor(co[:,1]/.25);pockets=hash2(cx,cy,76)>.66
 # Irregular exposed edge clusters are coherent with broad relief and fine cover.
 ring=smooth(.035,.11,q['root'])*(1-smooth(.20,.38,q['root']));strength=np.maximum(q['rough']**3*.42,ring)
 chosen=np.flatnonzero(inside(co[:,:2],.055)&pockets&(strength>.5));xy=co[chosen,:2];radius=radii[pi[chosen]];z=ground(xy)
 for direction in [(1,0),(-1,0),(0,1),(0,-1)]:z=np.minimum(z,ground(xy+radius[:,None]*np.array(direction)))
 frac=.30+.23*hash2(cx[chosen],cy[chosen],112);co[chosen,2]=(z-lows[pi[chosen]]-frac*heights[pi[chosen]]-.00010).astype('f4');ob.data.vertices.foreach_set('co',co.ravel());ob.data.update();assert np.array_equal(co[:,:2],before[:,:2])
 coarse={'exposed_cluster_bodies':len(chosen),'total_bodies':len(co),'all_XY_prototypes_and_meshes_unchanged':True,'solid_stock_change_m3':0.,'within_cell_solid_stock_change_m3':0.,'point_before_xyz_sha256':hashlib.sha256(before.tobytes()).hexdigest(),'point_after_xyz_sha256':hashlib.sha256(co.tobytes()).hexdigest(),'embedding_fraction_range':[float(frac.min()),float(frac.max())]}
 resting=[]
 for ob in scene.objects:
  if ob.hide_render or not ob.name.startswith('AS sparse outer fragment /'):continue
  mw=np.array(ob.matrix_world,float);local=read(ob.data.vertices,'co',3);world=local@mw[:3,:3].T+mw[:3,3];xy=world[:,:2]
  if not inside(xy,.06).all():continue
  extent=np.ptp(world,axis=0)
  dominant='actual metric fragment 039' in ob.data.name
  if not dominant and (extent[2]<.045 or extent[2]/max(extent[:2])<.68):continue
  centered=world-world.mean(0);values,vectors=np.linalg.eigh(centered.T@centered);normal=vectors[:,0]
  if normal[2]<0:normal=-normal
  rot=np.array(Vector(normal).rotation_difference(Vector((0,0,1))).to_matrix());m=mw.copy();m[:3,:3]=rot@mw[:3,:3];candidate=local@m[:3,:3].T+m[:3,3]
  if not inside(candidate[:,:2],.002).all():continue
  terrain=ground(candidate[:,:2]);embed=.048 if dominant else .004;dz=float(np.max(terrain-candidate[:,2])-embed);m[2,3]+=dz;ob.matrix_world=Matrix(m.tolist());after=local@m[:3,:3].T+m[:3,3]
  assert abs(np.linalg.det(m[:3,:3])-np.linalg.det(mw[:3,:3]))<1e-7
  resting.append({'object':ob.name,'mesh':ob.data.name,'source_mesh_sha256':hashlib.sha256(local.tobytes()).hexdigest(),'before_matrix':mw.tolist(),'after_matrix':m.tolist(),'source_mesh_and_true_solid_volume_unchanged':True,'before_world_extents_m':extent.tolist(),'after_world_extents_m':np.ptp(after,axis=0).tolist(),'actual_vertex_min_clearance_m':float(np.min(after[:,2]-terrain)),'intrinsic_embedding_m':embed,'support_model':'Authored broad-face resting pose; actual source vertex contact witness, no dynamic rigid-body solve'})
 bpy.context.view_layer.update();report={'fine':fine,'coarse':coarse,'broad_face_resting_clasts':resting,'source_meshes_scaled':False,'new_inventory':False,'limits':['Fine representatives use source-metric height and conservative small embedding; complete packed-grain contact is not simulated.','Exposed coarse clusters reassign static depth within unchanged per-cell solid inventory. No transported stock is asserted.']};Path(out,'DU_EXPOSURE.json').write_text(json.dumps(report,indent=2)+'\n');print('DU_EXPOSURE',json.dumps({'fine_counts':[x['surface_role_count']for x in fine],'coarse_exposed':len(chosen),'large_clasts_rested':len(resting)}),flush=True);return report
