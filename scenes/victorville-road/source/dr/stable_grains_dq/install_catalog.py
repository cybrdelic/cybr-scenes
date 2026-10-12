"""Install a view subset of a previously frozen world-space grain catalog.

No packing, allocation, contact, or retry happens here. Original geometry and
material endpoints are shared. This bounded fixture replaces only CZ display.
"""
from pathlib import Path
import hashlib,json,gc
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def apply(scene,cfg,out):
 import bpy
 from mathutils import Vector
 import approved_density_lod as a
 from context_mesh_refine_ab import _read,SourceSampler,intersecting_triangles
 from stable_catalog import _uniform,_mix64,lod_fraction
 out=Path(out);assert sha(cfg['catalog'])==cfg['catalog_sha256'];catalog=np.load(cfg['catalog']);receipt=json.loads(Path(cfg['catalog_receipt']).read_text());assert receipt['catalog_sha256']==cfg['catalog_sha256'];rows=receipt['prototype_metadata']
 co=catalog['xy'];z=catalog['z'];pi=catalog['prototype'];ids=catalog['id'];N=len(ids)
 if cfg.get('close_center'):
  ground=scene.objects['Graded shoulder and alluvial plain -1'];v=_read(ground.data.vertices,'co',3);ground.data.calc_loop_triangles();tri=_read(ground.data.loop_triangles,'vertices',3,np.int32);bounds=receipt['scope_bounds_m'];local=intersecting_triangles(v,tri,(bounds[0]-.03,bounds[1]+.03,bounds[2]-.03,bounds[3]+.03));surface=SourceSampler(v,tri,local,max_triangles=500000,max_bin_entries=4000000);centre=np.array(cfg['close_center']);height=float(a._height(surface,centre[None])[0]);target=Vector((*centre,height));scene.camera.location=target+Vector((.065,-.18,.18));scene.camera.rotation_euler=(target-scene.camera.location).to_track_quat('-Z','Y').to_euler();scene.camera.data.lens=50;del v,tri,surface
 bpy.context.view_layer.update();projection=a.CameraProjection(scene,cfg['width'],cfg['height']);world=np.c_[co,z];visible=projection.visible(world,margin=0);_,depth=projection.project(world)
 diameter=np.array([r['diameter']for r in rows])[pi];height=np.maximum(np.array([r['maximum']for r in rows])[pi],0);px=(diameter+np.where(pi>=64,height/np.tan(np.radians(22)),0))*projection.f[0]/np.maximum(depth,.001);lod=_uniform(ids,'lod');rank=_mix64(ids^np.uint64(0xCBBB9D5DC1059ED8));selected=[]
 for is_sand,budget in [(False,cfg.get('grit_budget',135000)),(True,cfg.get('sand_budget',85000))]:
  ii=np.flatnonzero(visible&((pi>=64)==is_sand)&(lod<lod_fraction(px)))
  if len(ii)>budget:ii=ii[np.lexsort((ids[ii],rank[ii]))[:budget]]
  selected.append(np.sort(ii))
 # Source identity contract is checked before sharing the original instance tree.
 records,group,_=a._bank(scene.objects[a.ORIGINS]);assert [r['source_id']for r in records]==[r['source_id']for r in rows[:64]]
 collection=next(n for n in group.nodes if n.bl_idname=='GeometryNodeCollectionInfo').inputs['Collection'].default_value;material=next(iter(collection.objects)).data.materials[0];bank=json.loads(Path(cfg['sand_bank']).read_text());assert sha(cfg['sand_bank'])==cfg['sand_bank_sha256'];sandcol=bpy.data.collections.new('DQ unchanged original sand bank')
 for i,p in enumerate(bank['particles']):
  assert p['source_id']==rows[i+64]['source_id'];v=np.array(p['vertices'],'f4');faces=np.array(p['faces'],'i4');me=bpy.data.meshes.new('DQ sand '+str(p['source_id']));me.from_pydata(v.tolist(),[],faces.tolist());me.materials.append(material);me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT').data.foreach_set('color',np.array(p['colors'],'f4').ravel());me.attributes.new('grain_roughness','FLOAT','POINT').data.foreach_set('value',np.array(p['roughness'],'f4'));ob=bpy.data.objects.new('DQ sand %03d'%i,me);sandcol.objects.link(ob)
 names=[a.OUTPUT,'CZ current-view original sand instances'];summaries=[];allindices=[]
 for band,(name,ii)in enumerate(zip(names,selected)):
  if name in scene.objects:bpy.data.objects.remove(scene.objects[name],do_unlink=True)
  me=bpy.data.meshes.new(name);me.vertices.add(len(ii));pos=np.c_[co[ii],catalog['precap_z'][ii]].astype('f4');me.vertices.foreach_set('co',pos.ravel());me.attributes.new('prototype','INT','POINT').data.foreach_set('value',(pi[ii].astype('i4')-band*64));rot=np.zeros((len(ii),3),'f4');rot[:,2]=catalog['yaw'][ii];me.attributes.new('yaw','FLOAT_VECTOR','POINT').data.foreach_set('vector',rot.ravel())
  # Blender stores INT32 attributes. Two lossless halves preserve the uint64 ID.
  for key,part in [('grain_id_lo',(ids[ii]&np.uint64(0xffffffff)).astype('u4')),('grain_id_hi',(ids[ii]>>np.uint64(32)).astype('u4'))]:me.attributes.new(key,'INT','POINT').data.foreach_set('value',part.view('i4'))
  me.update();ob=bpy.data.objects.new(name,me);scene.collection.objects.link(ob);g=group if band==0 else group.copy()
  if band:next(n for n in g.nodes if n.bl_idname=='GeometryNodeCollectionInfo').inputs['Collection'].default_value=sandcol
  ob.modifiers.new('DQ stable IDs / shared physical geometry','NODES').node_group=g;allindices.extend(ii.tolist());summaries.append({'object':name,'count':len(ii),'selected_id_sha256':hashlib.sha256(ids[ii].tobytes()).hexdigest()})
 allindices=np.array(allindices,'i4');budget=np.load(cfg['budget']);flow=np.array([r['flow_class']for r in rows]);np.savez_compressed(out/'DG_EXACT_ROLE_AND_Z_CHANGE.npz',point_id=ids[allindices],before_z=catalog['precap_z'][allindices],after_z=catalog['precap_z'][allindices],class_id=flow[pi[allindices]].astype('i1'),surface_representative=catalog['role'][allindices],static_cover_m=catalog['cover'][allindices],budget=budget['budget'],canonical_selected_volume=budget['selected_volume'])
 np.savez_compressed(out/'DQ_SELECTED_IDENTITY.npz',id=ids[allindices],xyz=np.c_[co[allindices],catalog['z'][allindices]].astype('f4'),prototype=pi[allindices],yaw=catalog['yaw'][allindices],role=catalog['role'][allindices])
 report={'revision':'DQ fixed world-space catalog / pure camera subset','catalog_sha256':cfg['catalog_sha256'],'objects':summaries,'catalog_count':N,'source_bank_identity_checked':True,'new_packing_or_burial_at_render':False,'role_and_contact_before_view_selection':True,'width':cfg['width'],'height':cfg['height'],'camera_location':list(scene.camera.location),'camera_rotation':list(scene.camera.rotation_euler),'limits':receipt['limits']};(out/'STABLE_GRAIN_CATALOG_DQ.json').write_text(json.dumps(report,indent=2)+'\n');print('DQ_INSTALLED',json.dumps(report),flush=True);gc.collect();return report
