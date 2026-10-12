"""CZ: source sand and grit represented at current camera footprint, metric SI.
Approved source bank/materials stay unchanged; new sand bank replays original RNG.
Unresolved geometry remains a documented LOD approximation, never enlarged grains.
"""
from pathlib import Path
import gc,hashlib,json,math,time
import numpy as np
GROUND='Graded shoulder and alluvial plain -1'

def apply(scene,cfg,out):
 import bpy
 from mathutils import Vector
 import approved_density_lod as a
 from context_mesh_refine_ab import _read,SourceSampler,intersecting_triangles
 t=time.monotonic();out=Path(out);ground=scene.objects[GROUND];co=_read(ground.data.vertices,'co',3);ground.data.calc_loop_triangles();tri=_read(ground.data.loop_triangles,'vertices',3,np.int32)
 bounds=tuple(cfg.get('bounds',[-7.,-3.52,4.7,11.5]));ids=intersecting_triangles(co,tri,(bounds[0]-.03,bounds[1]+.03,bounds[2]-.03,bounds[3]+.03));surface=SourceSampler(co,tri,ids,max_triangles=500000,max_bin_entries=4000000)
 if cfg.get('close_center'):
  centre=np.array(cfg['close_center'],float);z=float(a._height(surface,centre[None])[0]);target=Vector((*centre,z));scene.camera.location=target+Vector((.065,-.18,.18));scene.camera.rotation_euler=(target-scene.camera.location).to_track_quat('-Z','Y').to_euler();scene.camera.data.lens=50
 bpy.context.view_layer.update()
 projection=a.CameraProjection(scene,cfg['width'],cfg['height']);audit=[]
 for name in [a.ORIGINS,a.OUTPUT]:
  ob=scene.objects[name];v=a._world(ob,a._co(ob.data));visible=projection.visible(v);audit.append(dict(object=name,count=len(v),visible_frustum_count=int(visible.sum()),bounds_xy=[v[:,:2].min(0).tolist(),v[:,:2].max(0).tolist()],visible_xy_bounds=[v[visible,:2].min(0).tolist(),v[visible,:2].max(0).tolist()]if visible.any()else None))
 if cfg.get('audit_only'):
  report=dict(mode='matched baseline',existing=audit,camera_location=list(scene.camera.location),camera_rotation=list(scene.camera.rotation_euler));(out/'VISIBLE_FINE_GRAINS_CZ.json').write_text(json.dumps(report,indent=2));return report
 old=scene.objects[a.OUTPUT];oldcount=len(old.data.vertices);bpy.data.objects.remove(old,do_unlink=True)
 # Same physical source density, now allocated to the camera actually rendered.
 density=a.restore_approved_density(scene,surface,bounds=bounds,max_instances=int(cfg.get('grit_budget',135000)),width=cfg['width'],height=cfg['height'],diagnostic_view=None,cell_size=.09)
 bank=json.loads(Path(cfg['sand_bank']).read_text());assert hashlib.sha256(Path(cfg['sand_bank']).read_bytes()).hexdigest()==cfg['sand_bank_sha256'];assert [r[1]for r in bank['counts']]==[297,8859,64577]
 records,group,_=a._bank(scene.objects[a.ORIGINS]);source_collection=next(n for n in group.nodes if n.bl_idname=='GeometryNodeCollectionInfo').inputs['Collection'].default_value
 material=next(iter(source_collection.objects)).data.materials[0]
 col=bpy.data.collections.new('CZ exact original sand bank / independent64 identity')
 radii=[];diameters=[];heights=[]
 for i,p in enumerate(bank['particles']):
  v=np.asarray(p['vertices'],'f4');f=np.asarray(p['faces'],'i4');me=bpy.data.meshes.new('CZ sand source '+str(p['source_id']));me.from_pydata(v.tolist(),[],f.tolist());me.materials.append(material)
  attr=me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');attr.data.foreach_set('color',np.asarray(p['colors'],'f4').ravel());attr=me.attributes.new('grain_roughness','FLOAT','POINT');attr.data.foreach_set('value',np.asarray(p['roughness'],'f4'));ob=bpy.data.objects.new('CZ sand %03d'%i,me);col.objects.link(ob)
  radii.append(float(np.linalg.norm(v[:,:2],axis=1).max()));diameters.append(float(np.linalg.norm(v[:,None,:2]-v[None,:,:2],axis=-1).max()));heights.append(float(v[:,2].max()))
 radii=np.array(radii);diameters=np.array(diameters);heights=np.array(heights)
 # Stable cell grid; conservative nonoverlap uses true source footprints.
 step=.06;x0,x1,y0,y1=bounds;nx=int(math.ceil((x1-x0)/step));ny=int(math.ceil((y1-y0)/step));dx=(x1-x0)/nx;dy=(y1-y0)/ny;ix,iy=np.meshgrid(np.arange(nx),np.arange(ny));lo=np.c_[x0+ix.ravel()*dx,y0+iy.ravel()*dy];centres=lo+[dx/2,dy/2];zz=a._height(surface,centres);w=np.c_[centres,zz];uv,depth=projection.project(w);visible=projection.visible(w,margin=4)
 # Sand caster plus its finite22-degree shadow is the resolve criterion; this
 # does not enlarge bodies. Max100k additive budget explicitly reduces coverage.
 px=(diameters+np.maximum(heights,0)/math.tan(math.radians(22)))[None,:]*projection.f[0]/np.maximum(depth[:,None],.01)
 physical=a.DENSITIES['sand']*dx*dy/64*visible[:,None];fraction=lambda factor: a.lod_fraction(px,factor)
 budget=int(cfg.get('sand_budget',85000));factor=1.
 while float((physical*fraction(factor)).sum())>budget:factor*=1.1
 wanted=physical*fraction(factor);rng=np.random.default_rng(2610110745);quotas=np.floor(wanted).astype('i4');quotas+=(rng.random(wanted.shape)<wanted-quotas);packing=a.PackingIndex(float(max(radii.max(),max(r['radius']for r in records))))
 # Existing exact chip/grit footprints occupy space; sand fills interstices.
 for name in (a.ORIGINS,a.OUTPUT):
  ob=scene.objects[name];v=a._world(ob,a._co(ob.data));proto=np.empty(len(v),'i4');ob.data.attributes['prototype'].data.foreach_get('value',proto);inside=(v[:,0]>=x0-.01)&(v[:,0]<=x1+.01)&(v[:,1]>=y0-.01)&(v[:,1]<=y1+.01)
  for q,k in zip(v[inside],proto[inside]):packing.add(q[:2],records[int(k)]['radius'])
 xy=[];pi=[];yaw=[];attempted=0
 for c in np.flatnonzero(quotas.sum(1)):
  todo=np.repeat(np.arange(64),quotas[c]);rng.shuffle(todo)
  for repeat in range(4):
   if not len(todo):break
   q=lo[c]+rng.random((len(todo),2))*[dx,dy];keep=projection.visible(np.c_[q,np.full(len(q),zz[c])],margin=2);retry=[]
   for p,k,vis in zip(q,todo,keep):
    attempted+=1
    if vis and packing.clear(p,radii[k]):packing.add(p,radii[k]);xy.append(p);pi.append(k);yaw.append(rng.uniform(0,math.tau))
    else:retry.append(k)
   todo=np.array(retry,'i4')
 xy=np.asarray(xy).reshape(-1,2);z=a._height(surface,xy,allow_missing=True);valid=np.isfinite(z);xy=xy[valid];z=z[valid];pi=np.asarray(pi,'i4')[valid];yaw=np.asarray(yaw,'f4')[valid]
 me=bpy.data.meshes.new('CZ current-view original sand instances');me.vertices.add(len(xy));me.vertices.foreach_set('co',np.c_[xy,z].astype('f4').ravel());me.attributes.new('prototype','INT','POINT').data.foreach_set('value',pi);rot=np.zeros((len(xy),3),'f4');rot[:,2]=yaw;me.attributes.new('yaw','FLOAT_VECTOR','POINT').data.foreach_set('vector',rot.ravel());me.update();ob=bpy.data.objects.new(me.name,me);scene.collection.objects.link(ob);g=group.copy();g.name='CZ sand / verified separate bank';node=next(n for n in g.nodes if n.bl_idname=='GeometryNodeCollectionInfo');node.inputs['Collection'].default_value=col;ob.modifiers.new('Exact metric sand / no realization','NODES').node_group=g
 report=dict(revision='CZ1',existing=audit,replaced_old_camera_supplement_count=oldcount,grit=density,sand=dict(source_count_per_m2=a.DENSITIES['sand'],added_count=len(xy),budget=budget,requested_count=int(quotas.sum()),attempts=attempted,lod_threshold_factor=factor,shadow_resolve_angle_deg=22,body_diameter_mm_min_median_max=(np.array([diameters.min(),np.median(diameters),diameters.max()])*1000).tolist(),source_bank_sha256=cfg['sand_bank_sha256'],source_material=material.name,prototype_scale=[1,1,1],physical_count_in_frustum_estimate=float(physical.sum()*64)),camera_location=list(scene.camera.location),camera_rotation=list(scene.camera.rotation_euler),elapsed_seconds=time.monotonic()-t,limits=['Budgeted current-view LOD is not complete source population or exact far-field transport equivalence.','Sand placed at actual broad terrain datum with original per-prototype burial; native microbed remains normal-only.','Visibility is frustum only, no terrain/vegetation occlusion; large clasts can hide allocated grains.','Source native dimensions and material unchanged; no grain enlargement.'])
 (out/'VISIBLE_FINE_GRAINS_CZ.json').write_text(json.dumps(report,indent=2)+'\n');print('CZ_GRAINS',json.dumps({k:report[k]for k in('revision','existing','sand','elapsed_seconds')}),flush=True)
 del co,tri,surface,packing;gc.collect();return report
