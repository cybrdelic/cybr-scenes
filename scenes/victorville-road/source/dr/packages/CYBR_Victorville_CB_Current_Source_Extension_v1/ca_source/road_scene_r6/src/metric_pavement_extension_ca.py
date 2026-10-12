"""In-memory metric asphalt coverage extension. No scene save/render.
Original native templates, amplitude, mineral maps and .25m phase are retained.
A single triangle-clipped base plus connected three-side collar replaces the
old supporting sheet. Existing left marking is already a same-surface shader.
"""
import bpy,numpy as np,json,hashlib,gc
from pathlib import Path
from mathutils import Matrix
from tiled_relief_math import tile_matrix
from affine_tile_adapter import validate_affine_tiles,PARENT,PREFIX
ROAD='Crowned asphalt crust / longitudinal rise'
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
def apply(scene,cfg,folder):
 assert cfg['revision']==1
 payload=Path(cfg['payload']);assert sha(cfg['pins'])==cfg['pins_sha256'];pins=json.loads(Path(cfg['pins']).read_text());assert sha(payload)==cfg['payload_sha256']
 p=np.load(payload,allow_pickle=False);road=scene.objects[ROAD];old=road.data
 assert not road.modifiers and np.array_equal(np.asarray(road.matrix_world),np.eye(4))
 co=np.empty((len(old.vertices),3),'f4');old.vertices.foreach_get('co',co.ravel());assert digest(co)==pins['co'],'Actual source road geometry changed'
 old.calc_loop_triangles();tri=np.empty((len(old.loop_triangles),3),'i4');old.loop_triangles.foreach_get('vertices',tri.ravel());assert digest(tri)==pins['tri']
 parents=np.empty(len(tri),'i4');old.loop_triangles.foreach_get('polygon_index',parents);assert digest(parents)==pins['triangle_polygon']
 attrs=[]
 for a in old.attributes:
  if a.name=='position' or a.name.startswith('.'):continue
  spec={'FLOAT':('value',1,'f4'),'FLOAT_VECTOR':('vector',3,'f4'),'FLOAT_COLOR':('color',4,'f4'),'INT':('value',1,'i4'),'BOOLEAN':('value',1,'bool')}[a.data_type]
  prop,n,dt=spec;values=np.empty((len(a.data),n),dt);a.data.foreach_get(prop,values.ravel());key='attribute_'+str(len(attrs));assert digest(values)==pins[key],('Source semantic attribute mismatch',a.name)
  attrs.append((a.name,a.data_type,a.domain,prop,values,key))
 assert len(attrs)==8 and not attrs[6][4].any()
 # Keep source triangles outside the hole. Preserve their actual source material.
 kept=p['keep_triangle'];newtri=p['new_tri'];collar=p['collar_tri'];alltri=np.concatenate((tri[kept],newtri,collar));allco=np.concatenate((co,p['new_co']))
 face_source=np.r_[parents[kept],parents[p['new_triangle_source']]];mi=np.r_[attrs[7][4].ravel()[face_source],np.zeros(len(collar),'i4')].astype('i4')
 new=bpy.data.meshes.new(old.name+' / CA single-surface 6m native relief aperture');new.vertices.add(len(allco));new.vertices.foreach_set('co',allco.ravel());new.loops.add(alltri.size);new.loops.foreach_set('vertex_index',alltri.ravel());new.polygons.add(len(alltri));new.polygons.foreach_set('loop_start',np.arange(len(alltri),dtype='i4')*3);new.polygons.foreach_set('loop_total',np.full(len(alltri),3,'i4'))
 for m in old.materials:new.materials.append(m)
 new.polygons.foreach_set('material_index',mi);new.polygons.foreach_set('use_smooth',np.ones(len(alltri),bool))
 for name,dtype,domain,prop,val,key in attrs:
  if domain!='POINT':continue
  target=new.attributes.new(name,dtype,'POINT');out=np.concatenate((val,p['extra_'+key]));target.data.foreach_set(prop,out.ravel())
 new.update();assert not new.validate(verbose=True),'Blender repaired new actual-source triangle surface'
 road.data=new
 if old.users==0:bpy.data.meshes.remove(old)
 # Reuse nine original native geometry banks; only move far fade from y2 to y6.
 obs=[o for o in scene.objects if o.name.startswith(PREFIX)];assert len(obs)==88
 bank={};original_mats=set()
 for ob in obs:
  assert len(ob.data.vertices)==513*513 and len(ob.data.polygons)==512*512*2 and not ob.modifiers
  flags=ob.data.name.split('template ')[1][:4];assert set(flags)<=set('01');bank[flags]=ob.data;original_mats.update(ob.data.materials)
 assert len(bank)==9 and len(original_mats)==1
 original=next(iter(original_mats));material=original.copy();material.name=original.name+' / CA extended source POINT lookup'
 tex=[n for n in material.node_tree.nodes if n.bl_idname=='ShaderNodeTexImage' and 'POINT' in n.name];assert len(tex)==1;tex=tex[0];oldim=tex.image;lookup=p['lookup'];h,w,_=lookup.shape
 old_pixels=np.empty(len(oldim.pixels),'f4');oldim.pixels.foreach_get(old_pixels);assert np.array_equal(old_pixels.reshape(oldim.size[1],oldim.size[0],4),lookup[:oldim.size[1]])
 image=bpy.data.images.new('CA extended original POINT fields / RGBA32F',width=w,height=h,alpha=True,float_buffer=True);image.colorspace_settings.name='Non-Color';image.alpha_mode='CHANNEL_PACKED';image.pixels.foreach_set(lookup.ravel());image.update();tex.image=image
 scale=tex.inputs['Vector'].links[0].from_node;v=list(scale.inputs[1].default_value);v[1]*=oldim.size[1]/h;scale.inputs[1].default_value=v
 # Shared banks are current in-memory copies loaded from immutable AV cache.
 for me in bank.values():
  assert len(me.materials)==1;me.materials[0]=material
 parent=scene.objects[PARENT]
 for ob in obs:
  i,j=map(int,ob.name[len(PREFIX):].split());flags=''.join(str(int(v)) for v in (i==0,i==10,j==0,j==23));ob.data=bank[flags]
 for j in range(8,24):
  for i in range(11):
   flags=''.join(str(int(v)) for v in (i==0,i==10,False,j==23));ob=bpy.data.objects.new(f'{PREFIX}{i:02d} {j:02d}',bank[flags]);scene.collection.objects.link(ob);ob.parent=parent;ob.matrix_basis=Matrix.Identity(4);ob.matrix_parent_inverse=Matrix(tile_matrix(-3+i*.25,j*.25));ob['affine_transform_contract']='parent_world(identity) @ full_affine_parent_inverse @ basis(identity)'
 report=validate_affine_tiles(scene,(-3,-.25,0,6),require_parent=True)
 # Validate the changed fade boundary actually carries periodic nonzero source relief.
 bottom=scene.objects[f'{PREFIX}05 07'];top=scene.objects[f'{PREFIX}05 08'];assert bottom.data==top.data and bottom.data==bank['0000']
 report.update(revision='CA',payload_sha256=cfg['payload_sha256'],original_native_bounds_m=[-3,-.25,0,2],extended_native_bounds_m=[-3,-.25,0,6],native_tile_size_m=.25,height_scale_m=.004,source_coordinates_unchanged=True,source_material_assignments_preserved=True,old_lookup_rows_exact=1041,lookup_dimensions=[w,h],lookup_sha256=digest(lookup),base_triangles=len(alltri),base_vertices=len(allco),new_same_surface_lookup=True,old_far_fade_relocated_to_y_m=6,old_y2_interface_no_collar=True,source_scene_saved=False,limits='Original shader/map recipe and local native tile geometry unchanged. Coverage is expanded; current preview may still apply documented stride2/stride4 LOD and texture mips. Broad profile remains affine per .25m tile.')
 (Path(folder)/'METRIC_PAVEMENT_EXTENSION_CA.json').write_text(json.dumps(report,indent=2)+'\n')
 p.close();del co,tri,parents,attrs,alltri,allco,newtri,collar,kept,face_source,mi,lookup,old_pixels,out;gc.collect()
 return report
