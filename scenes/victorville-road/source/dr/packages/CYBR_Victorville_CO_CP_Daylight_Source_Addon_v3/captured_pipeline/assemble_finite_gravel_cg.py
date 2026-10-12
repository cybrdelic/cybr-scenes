"""CG instanced finite historical gravel, applied after CE and CF in memory."""
from pathlib import Path
import time,json,hashlib,gc,math
import numpy as np
import bpy
from context_mesh_refine_ab import _read,SourceSampler
from approved_density_lod import PackingIndex
from finite_historical_gravel_cg import bank,cells,cell_ids,proposed_points,BOUNDS,SOLID_FRACTION
import prepare_physical_lenses as legacy

# Scale-specific mineral response retained verbatim from the existing AS material helper.
def material():
    m=bpy.data.materials.new('AS new metric rock / shared regional mineral palette');m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;b=n.get('Principled BSDF');b.inputs['Specular IOR Level'].default_value=.28
    g=n.new('ShaderNodeNewGeometry');a=n.new('ShaderNodeAttribute');a.attribute_name='mineral';r=n.new('ShaderNodeAttribute');r.attribute_name='grain_roughness'
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=680;noise.inputs['Detail'].default_value=3;noise.inputs['Roughness'].default_value=.73;l.new(g.outputs['Position'],noise.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.21;ramp.color_ramp.elements[0].color=(.65,.68,.73,1);ramp.color_ramp.elements[1].position=.78;ramp.color_ramp.elements[1].color=(1.15,1.10,1.02,1);l.new(noise.outputs['Fac'],ramp.inputs[0]);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;l.new(a.outputs['Color'],mix.inputs[1]);l.new(ramp.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],b.inputs['Base Color'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1;rough.inputs['To Min'].default_value=-.04;rough.inputs['To Max'].default_value=.05;l.new(noise.outputs['Fac'],rough.inputs['Value']);add=n.new('ShaderNodeMath');add.operation='ADD';l.new(r.outputs['Fac'],add.inputs[0]);l.new(rough.outputs['Result'],add.inputs[1]);l.new(add.outputs[0],b.inputs['Roughness'])
    micro=n.new('ShaderNodeTexNoise');micro.inputs['Scale'].default_value=3100;micro.inputs['Detail'].default_value=2;l.new(g.outputs['Position'],micro.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000085;bump.inputs['Strength'].default_value=.65;l.new(micro.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])
    # Mineral inclusions affect sub-mm face relief and roughness together, while
    # actual fracture planes/edge weathering remain mesh geometry with flat normals.
    bump2=n.new('ShaderNodeBump');bump2.inputs['Distance'].default_value=.00025;bump2.inputs['Strength'].default_value=.5;l.new(noise.outputs['Fac'],bump2.inputs['Height']);l.new(bump.outputs['Normal'],bump2.inputs['Normal']);l.new(bump2.outputs['Normal'],b.inputs['Normal']);return m

def apply(scene,cfg,out):
 start=time.monotonic();assert cfg['revision']==1;path=Path(cfg['fractured_prototypes']);assert hashlib.sha256(path.read_bytes()).hexdigest()==cfg['fractured_prototypes_sha256'];records=bank(path);transition=cfg.get('worked_edge_transition',False);ledger=cells(transition=transition);initial=ledger['initial_solid'].copy();existing=np.zeros(len(initial));used=np.zeros(len(initial));c=ledger;bnds=(c['x'][0],c['x'][-1],c['y'][0],c['y'][-1])
 rad=np.array([r['radius'] for r in records]);vol=np.array([r['volume'] for r in records]);h=np.array([r['height'] for r in records]);diam=np.array([r['diameter'] for r in records]);packing=PackingIndex(float(rad.max()))
 # Existing AP bodies in the new size class are accounted first. Their shapes,
 # positions and source mapping remain unchanged. Smaller grains form the matrix.
 ob=scene.objects['AP graded margin / exact metric lag instances'];q=_read(ob.data.vertices,'co',3);pid=_read(ob.data.attributes['prototype'].data,'value',1,np.int32);oldbank=sorted(bpy.data.collections['AP exact coarse lag bank'].objects,key=lambda o:o.name);assert len(oldbank)==64
 oldrad=[];oldvol=[];oldd=[]
 for o in oldbank:
  v=_read(o.data.vertices,'co',3);o.data.calc_loop_triangles();f=_read(o.data.loop_triangles,'vertices',3,np.int32);vv=v[f].astype(float);oldrad.append(np.linalg.norm(v[:,:2],axis=1).max());oldvol.append(abs(np.sum(vv[:,0]*np.cross(vv[:,1],vv[:,2]))/6));oldd.append(np.linalg.norm(np.ptp(v[:,:2],axis=0)))
 oldrad=np.asarray(oldrad);oldvol=np.asarray(oldvol);oldd=np.asarray(oldd);cid,ok=cell_ids(q[:,:2],c);oldclass=ok&(oldd[pid]>=.018)&(oldd[pid]<=.060)
 for j in np.flatnonzero(ok):
  # All old >7mm rocks are spacing exclusions; buried sand is allowed underneath.
  packing.add(q[j,:2],float(oldrad[pid[j]]))
 for j in np.flatnonzero(oldclass):existing[cid[j]]+=oldvol[pid[j]]
 exclusions=[];other_assigned=0.
 for o in scene.objects:
  if o.hide_render or not o.name.startswith('AS sparse outer fragment /'):continue
  v=_read(o.data.vertices,'co',3).astype(float);M=np.asarray(o.matrix_world,float);v=v@M[:3,:3].T+M[:3,3];centre=(v[:,:2].min(0)+v[:,:2].max(0))/2;cc,ok=cell_ids(centre[None],c)
  if not ok[0]:continue
  rr=np.linalg.norm(v[:,:2]-centre,axis=1).max();exclusions.append((centre,rr));d=np.linalg.norm(np.ptp(v[:,:2],axis=0))
  if .018<=d<=.060:
   o.data.calc_loop_triangles();f=_read(o.data.loop_triangles,'vertices',3,np.int32);vv=(v-v.mean(0))[f];vvv=abs(np.sum(vv[:,0]*np.cross(vv[:,1],vv[:,2]))/6);existing[cc[0]]+=vvv;other_assigned+=vvv
 # Exclude every pre-existing merged rigid body as well as the point bank.
 # Their old volume is outside this NEW authored stock, not a hidden second debit.
 legacy_excluded=[]
 for name in legacy.RIGID:
  old=scene.objects[name];vv=legacy.world_coordinates(old,legacy.read_coordinates(old.data));parts=legacy.local_components(old.data,vv);count=0
  for ix in parts:
   xy0=vv[ix,:2];center=(xy0.min(0)+xy0.max(0))/2;rr=float(np.linalg.norm(xy0-center,axis=1).max())
   if center[0]+rr<bnds[0] or center[0]-rr>bnds[1] or center[1]+rr<bnds[2] or center[1]-rr>bnds[3]:continue
   packing.add(center,rr);count+=1
  legacy_excluded.append(dict(object=name,body_footprints_excluded=count))
  del vv,parts
 target=initial*c['target_fraction']
 xy,pi,yaw,receive=proposed_points(transition=transition)
 if transition:
  # The worked inner shoulder retains a sparse smaller, more buried tail.
  near=xy[:,0]>-3.70;small=np.flatnonzero(diam<.027);pi[near]=np.random.default_rng(2610101921).choice(small,near.sum())
 cid,ok=cell_ids(xy,c);chosen=[]
 for i in range(len(xy)):
  k=int(pi[i]);ci=int(cid[i]);vv=vol[k]
  if not ok[i] or used[ci]+vv>target[ci]+1e-15:continue
  r=rad[k]
  if any(np.sum((xy[i]-center)**2)<(r+rr)**2 for center,rr in exclusions):continue
  if not packing.clear(xy[i],r):continue
  packing.add(xy[i],r);used[ci]+=vv;chosen.append(i)
  if len(chosen)>=14000:break
 chosen=np.array(chosen,int);xy=xy[chosen];pi=pi[chosen];yaw=yaw[chosen];receive=receive[chosen];cid=cid[chosen];assert len(xy)>1000,('Insufficient finite gravel count',len(xy))
 p=np.load(cfg['terrain_payload'],allow_pickle=False);assert hashlib.sha256(Path(cfg['terrain_payload']).read_bytes()).hexdigest()==cfg['terrain_sha256'];co=p['source_coordinates'].astype(float);co[:,2]+=p['delta'];sampler=SourceSampler(co,p['tri'],np.arange(len(p['tri'])),max_triangles=500000,max_bin_entries=4000000)
 z=np.empty(len(xy));dep=np.empty(len(xy))
 for first in range(0,len(xy),2048):
  sl=slice(first,first+2048);z[sl]=sampler.height(xy[sl]);dep[sl]=sampler.sample(p['deposited'][:,0],xy[sl])
 rng=np.random.default_rng(2610101913);bury=np.clip(.32+.37*receive+.18*(-np.expm1(-dep/.00035))+rng.uniform(-.14,.12,len(xy)) + (np.clip((xy[:,0]+3.76)/.41,0,1)*.30 if transition else 0),.20,.92 if transition else .88);points=np.c_[xy,z-h[pi]*bury]
 print('CG_PACKED',len(points),float(used.sum()),flush=True)
 # Support audit evaluates the real final triangles under every body's lowest
 # vertex. A minimum embedded depth is enforced, not a floating center sample.
 contact=[]
 for i in range(len(points)):
  v=records[int(pi[i])]['v'];j=np.argmin(v[:,2]);a=yaw[i];cs,sn=np.cos(a),np.sin(a);q=xy[i]+v[j,:2]@np.array([[cs,sn],[-sn,cs]])
  zz=float(sampler.height(q[None])[0]);points[i,2]=min(points[i,2],zz-.0001);contact.append(zz-points[i,2])
 coll=bpy.data.collections.new('CG finite historical gravel prototype bank');scene.collection.children.link(coll);mat=material();mat.name='CG original mineral gravel / metric fracture roughness'
 for k,r in enumerate(records):
  me=bpy.data.meshes.new(f'CG metric gravel mesh {k:03d}');me.from_pydata(r['v'].tolist(),[],r['f'].tolist());me.materials.append(mat);me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT').data.foreach_set('color',r['color'].ravel());me.attributes.new('grain_roughness','FLOAT','POINT').data.foreach_set('value',r['rough']);me.polygons.foreach_set('use_smooth',np.zeros(len(me.polygons),bool));me.update();o=bpy.data.objects.new(f'CG finite gravel {k:03d}',me);coll.objects.link(o);o.hide_render=True;o.hide_viewport=True
 me=bpy.data.meshes.new('CG finite accounted positions');me.from_pydata(points.tolist(),[],[]);me.attributes.new('prototype','INT','POINT').data.foreach_set('value',pi.astype('i4'));rot=np.c_[np.zeros((len(points),2)),yaw].astype('f4');me.attributes.new('yaw','FLOAT_VECTOR','POINT').data.foreach_set('vector',rot.ravel());ob=bpy.data.objects.new('CG finite 18–60 mm historical gravel pockets',me);scene.collection.objects.link(ob)
 group=bpy.data.node_groups.new('CG exact 192 identity instance selection','GeometryNodeTree');group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry');n=group.nodes;l=group.links;i=n.new('NodeGroupInput');o=n.new('NodeGroupOutput');col=n.new('GeometryNodeCollectionInfo');col.inputs['Collection'].default_value=coll;col.inputs['Separate Children'].default_value=True;col.inputs['Reset Children'].default_value=True;inst=n.new('GeometryNodeInstanceOnPoints');inst.inputs['Pick Instance'].default_value=True;l.new(i.outputs['Geometry'],inst.inputs['Points']);l.new(col.outputs['Instances'],inst.inputs['Instance']);attr=n.new('GeometryNodeInputNamedAttribute');attr.data_type='INT';attr.inputs['Name'].default_value='prototype';l.new(attr.outputs['Attribute'],inst.inputs['Instance Index']);attr=n.new('GeometryNodeInputNamedAttribute');attr.data_type='FLOAT_VECTOR';attr.inputs['Name'].default_value='yaw';l.new(attr.outputs['Attribute'],inst.inputs['Rotation']);l.new(inst.outputs['Instances'],o.inputs['Geometry']);ob.modifiers.new('Finite shared gravel meshes','NODES').node_group=group
 residual=initial-used;assert residual.min()>-1e-12;assert np.max(abs(initial-used-residual))<1e-14
 report=dict(revision='CG with CH inner transition' if transition else 'CG',worked_edge_transition=transition,inner_tail_points=int((xy[:,0]>-3.70).sum()),representation='New explicit historical 18–60mm class, independent of AH 1.66–5.9mm chip/event inventory',new_body_count=len(points),bank_count=len(records),diameter_range_m=[float(diam.min()),float(diam.max())],solid_packing_fraction_assumption=SOLID_FRACTION,historical_bulk_thickness_range_m=[float(c['bulk_thickness'].min()),float(c['bulk_thickness'].max())],ledger_cell_m=.25,initial_historical_solid_m3=float(initial.sum()),existing_ap_in_size_range_count=int(oldclass.sum()),legacy_bodies_excluded=legacy_excluded,existing_bodies_inventory_separate=True,new_explicit_body_solid_m3=float(used.sum()),buried_or_unrepresented_solid_reserve_m3=float(residual.sum()),per_cell_minimum_residual_solid_m3=float(residual.min()),full_class_solid_residual_m3=float(initial.sum()-used.sum()-residual.sum()),new_body_projected_footprint_sum_m2=float(sum(records[int(k)]['area'] for k in pi)),finite_body_volume_sha256=hashlib.sha256(vol.tobytes()).hexdigest(),placement_count_by_y=[int(((xy[:,1]>=a)&(xy[:,1]<b)).sum()) for a,b in [(-.58,.3),(.3,1),(1,3),(3,6.5),(6.5,10.8)]],burial_fraction_range=[float(bury.min()),float(bury.max())],minimum_lowest_vertex_embedded_m=float(min(contact)),geometry_policy='Independent shared meshes, flat fracture planes and scale-specific mineral microrelief; approved R5D particles never scaled',size_identity='New original metric tier from retained normalized fractured construction; not rescaled existing scene bodies',stock_policy='Authored historical gravel stock partition. Only newly authored stock is partitioned; existing AP/AS/merged bodies remain separate and have excluded footprints. Buried reserve includes unresolved subsurface. AH/event ledger unchanged.',limitations=['Historical stock and packing fraction are authored assumptions, not field measurements or calibrated transport','No claim that the latest small storm transported 2–6cm gravel','Stock partition conserves its declared solid budget; terrain elevation is an authored fines envelope and does not solve a packed multiphase continuum','Enclosing disks exclude peer gravel and existing AP/AS clasts; fine grains beneath partly buried bodies can overlap the subsurface','192 bank index order was verified using the exact graph code in a separate bounded Blender probe'],elapsed_seconds=time.monotonic()-start)
 np.savez_compressed(Path(out)/'CG_FINITE_GRAVEL_LEDGER.npz',cell_xy=c['xy'],cell_area=c['area'],initial_solid=initial,existing_volume_diagnostic_only=existing,explicit_new_solid=used,buried_reserve=residual,points=points.astype('f4'),prototype=pi.astype('i4'),yaw=yaw.astype('f4'),cell=cid,bank_volume=vol)
 (Path(out)/'FINITE_HISTORICAL_GRAVEL_CG.json').write_text(json.dumps(report,indent=2)+'\n');print('CG_FINITE_GRAVEL',json.dumps(report),flush=True);p.close();del sampler,co,records;gc.collect();return report
