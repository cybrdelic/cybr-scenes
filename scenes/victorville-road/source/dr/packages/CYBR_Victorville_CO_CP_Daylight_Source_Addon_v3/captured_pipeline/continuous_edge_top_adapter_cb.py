"""One connected metric pavement edge top on immutable CA source; no scene save.
The original physical rim, subgrade and approved asphalt recipe are retained.
CB preview topology is explicitly matched to the native stride2 boundary.
"""
from pathlib import Path
import bpy,numpy as np,json,hashlib,gc
from affine_tile_adapter import PREFIX,validate_affine_tiles
ROAD='Crowned asphalt crust / longitudinal rise'
STRIP='CB continuous pavement edge top'
NAMES=('asphalt_share','road_edge_inset_m','road_deposit_depth_m','relief_original_left_paint_z','macro_tint','relief_original_broad_normal')
SPECS=(('FLOAT','value',1),)*4+(('FLOAT_COLOR','color',4),('FLOAT_VECTOR','vector',3))
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def normal_contract(mat):
 n=mat.node_tree.nodes
 attrs=[q for q in n if q.bl_idname=='ShaderNodeAttribute' and q.attribute_name==NAMES[-1] and q.outputs['Vector'].is_linked]
 geom=[q for q in n if q.bl_idname=='ShaderNodeNewGeometry' and q.outputs['Normal'].is_linked]
 assert attrs and not geom,('Need full metric normal plus broad datum once',mat.name,len(attrs),len(geom))
 return dict(material=mat.name,broad_datum_attribute=NAMES[-1],connected_broad_attributes=len(attrs),displaced_geometric_normal_links=0)
def mesh_from_payload(p,prefix,name,mats):
 co=p[prefix+'_co'];tri=p[prefix+'_tri'];me=bpy.data.meshes.new(name)
 me.vertices.add(len(co));me.vertices.foreach_set('co',co.ravel());me.loops.add(tri.size);me.loops.foreach_set('vertex_index',tri.ravel());me.polygons.add(len(tri));me.polygons.foreach_set('loop_start',np.arange(len(tri),dtype='i4')*3);me.polygons.foreach_set('loop_total',np.full(len(tri),3,'i4'));me.polygons.foreach_set('use_smooth',np.ones(len(tri),bool))
 for mat in mats:me.materials.append(mat)
 if prefix=='base':me.polygons.foreach_set('material_index',p['base_material'])
 for i,(aname,(dtype,prop,width)) in enumerate(zip(NAMES,SPECS)):
  vals=p[f'{prefix}_attr_{i}'];assert vals.shape==(len(co),width) and np.isfinite(vals).all();a=me.attributes.new(aname,dtype,'POINT');a.data.foreach_set(prop,vals.ravel())
 me.update();assert not me.validate(verbose=True),'Blender repaired CB topology';return me

def apply(scene,cfg,folder):
 assert cfg['revision']==1 and cfg['step']==2
 assert not scene.objects.get(STRIP),'CB already applied'
 for name in ('payload','pins','clearance'):
  assert sha(cfg[name])==cfg[name+'_sha256'],('CB input pin mismatch',name)
 pins=json.loads(Path(cfg['pins']).read_text());clearance=json.loads(Path(cfg['clearance']).read_text());assert clearance['penetrating_overlap_polygons']==0 and not clearance['soil_geometry_changed']
 # The clearance proof only qualifies this exact supporting mesh.
 ground=scene.objects['Graded shoulder and alluvial plain -1'];assert not ground.modifiers and np.array_equal(np.asarray(ground.matrix_world),np.eye(4))
 gm=ground.data;gc0=np.empty((len(gm.vertices),3),'f4');gm.vertices.foreach_get('co',gc0.ravel());assert digest(gc0)=='07eb9c84ee97224a82ca61243ea635e92a7a80d194f364bc969456b7617c3794'
 gm.calc_loop_triangles();gt=np.empty((len(gm.loop_triangles),3),'i4');gm.loop_triangles.foreach_get('vertices',gt.ravel());assert digest(gt)=='df6f2b4504334ff909dfadcc7a147507a5e7fffec0d44434c945666e25a03088';del gc0,gt
 road=scene.objects[ROAD];old=road.data;assert not road.modifiers and np.array_equal(np.asarray(road.matrix_world),np.eye(4))
 co=np.empty((len(old.vertices),3),'f4');old.vertices.foreach_get('co',co.ravel());assert digest(co)==pins['original_scene_road_co_sha256']
 old.calc_loop_triangles();tri=np.empty((len(old.loop_triangles),3),'i4');old.loop_triangles.foreach_get('vertices',tri.ravel());assert digest(tri)==pins['original_scene_road_tri_sha256']
 for i,(aname,(_,prop,width)) in enumerate(zip(NAMES,SPECS)):
  a=old.attributes[aname];assert a.domain=='POINT';val=np.empty((len(a.data),width),'f4');a.data.foreach_get(prop,val.ravel());assert digest(val)==pins['source_POINT_fields_sha256'][i],('Changed CB source field',aname)
 del co,tri,val
 # Material1 is the existing approved displaced-edge normal contract. Material0
 # still shades the broad undisplaced base and must not be copied blindly.
 assert len(old.materials)==2;edge_material=old.materials[1];normal=normal_contract(edge_material)
 p=np.load(cfg['payload'],allow_pickle=False);base=mesh_from_payload(p,'base',old.name+' / CB compact retained base',list(old.materials));strip=mesh_from_payload(p,'strip','CB continuous metric edge geometry',[edge_material]);ob=bpy.data.objects.new(STRIP,strip);scene.collection.objects.link(ob);road.data=base
 if old.users==0:bpy.data.meshes.remove(old)
 obs=[o for o in scene.objects if o.name.startswith(PREFIX)];assert len(obs)==264;bank={}
 for o in obs:
  flags=o.data.name.split('template ')[1][:4];assert len(o.data.vertices)==513*513;bank[flags]=o.data
 changed=[]
 for ob in obs:
  i,j=map(int,ob.name[len(PREFIX):].split())
  if i!=0:continue
  flags=ob.data.name.split('template ')[1][:4];assert flags[0]=='1';ob.data=bank['0'+flags[1:]];changed.append(ob.name)
 assert len(changed)==24
 affine=validate_affine_tiles(scene,(-3,-.25,0,6),require_parent=True)
 # Check the actual transformed native edge, not an analytic substitute.
 sc=p['strip_co'];sel=np.flatnonzero((sc[:,0]==-3)&(sc[:,1]>=0)&(sc[:,1]<=6));order=sel[np.argsort(sc[sel,1])];rim=sc[order].astype(float);assert len(rim)==24*256+1
 err=0.
 for j in range(24):
  ob=scene.objects[f'{PREFIX}00 {j:02d}'];v=np.empty((513*513,3),'f4');ob.data.vertices.foreach_get('co',v.ravel());vv=v.reshape(513,513,3)[::2,0].astype(float);m=np.asarray(ob.matrix_world,float);world=vv@m[:3,:3].T+m[:3,3];err=max(err,float(np.max(abs(world-rim[j*256:(j+1)*256+1]))))
 assert err<5e-7,('Native-to-strip seam',err)
 removed=[]
 for me in list(bank.values()):
  if me.users==0:removed.append(me.name);bpy.data.meshes.remove(me)
 report=dict(revision='CB',payload_sha256=cfg['payload_sha256'],native_stride=2,geometry=pins,normal_contract=normal,physical_outer_rim_xyz_unchanged=True,soil_geometry_changed=False,contact_clearance=clearance,native_seam_max_xyz_error_m=err,native_affine=affine,old_left_fade_removed_instances=changed,unused_fade_templates_released=removed,top_surface_overlap_added=False,source_scene_saved=False,limits='Adaptive preview grid:0.977mm near0..2m,1.953mm strip2..6m; native inner boundary0.977mm throughout. No new native-step1 qualification. Ground contact audit excludes discrete grains.')
 (Path(folder)/'CONTINUOUS_EDGE_TOP_CB.json').write_text(json.dumps(report,indent=2)+'\n');p.close();del sc,rim,v,vv;gc.collect();return report

def bind_current_edge_material(scene,folder):
 road=scene.objects[ROAD];strip=scene.objects[STRIP];material=road.data.materials[1];report=normal_contract(material);strip.data.materials[0]=material;report['same_current_road_edge_material']=True;report['BY_applied']=bool(material.get('BY_applied'));assert report['BY_applied'];(Path(folder)/'CB_FINAL_MATERIAL_BINDING.json').write_text(json.dumps(report,indent=2)+'\n');return report
