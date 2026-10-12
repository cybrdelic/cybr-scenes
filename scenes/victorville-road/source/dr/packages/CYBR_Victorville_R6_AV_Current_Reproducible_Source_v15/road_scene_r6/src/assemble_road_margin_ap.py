"""AP scene-scale sorted shoulder and shared-mesh layered scrub, in memory.
Preserves intrinsic material/prototype inputs and road/contact geometry. Broad
sorting is an illustrative historical surface organization, not storm mass.
"""
from pathlib import Path
import gc,hashlib,time,math,json
import numpy as np
import bpy
from road_margin_composition_ap import fields
from sample_final_surface_an import PartialSurfaceSampler
from context_mesh_refine_ab import _read,intersecting_triangles
from approved_density_lod import CameraProjection,PackingIndex
GROUND='Graded shoulder and alluvial plain -1'
LAG='Gravel lag pockets beside shallow runoff arms'

def terrain_sampler(ob):
 co=_read(ob.data.vertices,'co',3);ob.data.calc_loop_triangles();tri=_read(ob.data.loop_triangles,'vertices',3,np.int32)
 ids=intersecting_triangles(co,tri,(-12,-3.25,-1,86));ts=tri[ids];used,iv=np.unique(ts,return_inverse=True)
 sampler=PartialSurfaceSampler(co[used],iv.reshape(-1,3),cell_m=.20,max_triangles=1500000,max_bin_entries=5000000,max_query_products=200000)
 return sampler,co

def surface_fields(sampler,xy):
 z=sampler.height(xy);e=.08
 zx=sampler.height(xy+np.array([e,0]));zm=sampler.height(xy-np.array([e,0]));zy=sampler.height(xy+np.array([0,e]));zn=sampler.height(xy-np.array([0,e]))
 gx=(zx-zm)/(2*e);gy=(zy-zn)/(2*e);g=np.c_[gx,gy];g[~np.isfinite(g)]=0
 return z,fields(xy,g)

def add_shader(ob,v):
 # Copy scene ground material, leaving approved original shader/maps untouched.
 old=ob.data.materials[0];m=old.copy();m.name='AP correlated historical fines and gravel / intrinsic inputs retained';ob.data.materials[0]=m
 for name,key in [('ap_coarse','coarse'),('ap_fines','fines')]:
  a=ob.data.attributes.new(name,'FLOAT','POINT');a.data.foreach_set('value',v[key].astype('f4'))
 n=m.node_tree.nodes;l=m.node_tree.links;b=n['Linked dry dielectric'];base=b.inputs['Base Color'].links[0].from_socket;rough=b.inputs['Roughness'].links[0].from_socket;normal=b.inputs['Normal'].links[0].from_socket
 def at(name):q=n.new('ShaderNodeAttribute');q.attribute_name=name;return q.outputs['Fac']
 def mul(a,c):q=n.new('ShaderNodeMath');q.operation='MULTIPLY';l.new(a,q.inputs[0]);q.inputs[1].default_value=c;return q.outputs[0]
 def mix(a,c,f):q=n.new('ShaderNodeMixRGB');l.new(a,q.inputs[1]);l.new(f,q.inputs[0]);l.new(c,q.inputs[2]) if hasattr(c,'node') else setattr(q.inputs[2],'default_value',c);return q.outputs[0]
 coarse=at('ap_coarse');fine=at('ap_fines')
 # Resolvable loose-gravel instances below carry exact K per-mineral values;
 # this only models unresolved interstitial fines and their pore normal response.
 q=n.new('ShaderNodeMixRGB');q.blend_type='MULTIPLY';q.inputs[0].default_value=1;l.new(base,q.inputs[1]);q.inputs[2].default_value=(.78,.82,.87,1)
 color=mix(base,q.outputs[0],mul(coarse,.7));color=mix(color,(.29535648,.24439612,.17515583,1),mul(fine,.38));l.new(color,b.inputs['Base Color'])
 r=mix(rough,(.86,.86,.86,1),mul(fine,.25));l.new(r,b.inputs['Roughness'])
 geo=n['World surface geometry'];nn=mix(normal,geo.outputs['Normal'],mul(fine,.22));q=n.new('ShaderNodeVectorMath');q.operation='NORMALIZE';l.new(nn,q.inputs[0]);l.new(q.outputs[0],b.inputs['Normal'])
 return {'source_material':old.name,'copy':m.name,'fine_linear_color_source':'Exact pinned approved microbed mean','unresolved_coarse_response':'Bounded optical mixture, no validated BRDF claim'}

def grain_bank(source,collection):
 me=source.data;co=_read(me.vertices,'co',3);me.calc_loop_triangles();tri=_read(me.loop_triangles,'vertices',3,np.int32)
 parent=np.arange(len(co),dtype=np.int32)
 def root(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 for a,b,c in tri:
  a=root(a);parent[root(b)]=a;parent[root(c)]=a
 labels=np.array([root(i) for i in range(len(co))]);unique=np.unique(labels)
 color=_read(me.color_attributes['mineral'].data,'color',4);rough=_read(me.attributes['grain_roughness'].data,'value',1)
 picked=unique[np.linspace(0,len(unique)-1,min(64,len(unique)),dtype=int)];records=[];h=hashlib.sha256()
 for k,label in enumerate(picked):
  ix=np.flatnonzero(labels==label);p=co[ix].copy();centre=(p.min(0)+p.max(0))*.5;p-=centre;remap=np.full(len(co),-1,np.int32);remap[ix]=np.arange(len(ix));f=remap[tri[np.all(labels[tri]==label,axis=1)]]
  mesh=bpy.data.meshes.new(f'AP exact source lag {k:03d}');mesh.from_pydata(p.tolist(),[],f.tolist())
  for mat in me.materials:mesh.materials.append(mat)
  ca=mesh.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');ca.data.foreach_set('color',color[ix].ravel());ra=mesh.attributes.new('grain_roughness','FLOAT','POINT');ra.data.foreach_set('value',rough[ix]);mesh.update()
  ob=bpy.data.objects.new(f'AP exact lag {k:03d}',mesh);collection.objects.link(ob);ob.hide_render=True;ob.hide_viewport=True
  h.update(p.tobytes());h.update(f.tobytes());h.update(color[ix].tobytes());h.update(rough[ix].tobytes())
  records.append({'name':ob.name,'radius':float(np.linalg.norm(p[:,:2],axis=1).max()),'zmin':float(p[:,2].min()),'zmax':float(p[:,2].max()),'diameter':float(np.linalg.norm(np.ptp(p[:,:2],axis=0)))})
 return records,h.hexdigest()

def instances(scene,collection,points,indices,yaws):
 mesh=bpy.data.meshes.new('AP metric sorted lag positions');mesh.from_pydata(points.tolist(),[],[]);a=mesh.attributes.new('prototype','INT','POINT');a.data.foreach_set('value',indices.astype('i4'));a=mesh.attributes.new('yaw','FLOAT_VECTOR','POINT');a.data.foreach_set('vector',np.c_[np.zeros((len(points),2)),yaws].astype('f4').ravel())
 ob=bpy.data.objects.new('AP graded margin / exact metric lag instances',mesh);scene.collection.objects.link(ob)
 group=bpy.data.node_groups.new('AP exact prototype selection','GeometryNodeTree');group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry');n=group.nodes;l=group.links;i=n.new('NodeGroupInput');o=n.new('NodeGroupOutput');c=n.new('GeometryNodeCollectionInfo');c.inputs['Collection'].default_value=collection;c.inputs['Separate Children'].default_value=True;c.inputs['Reset Children'].default_value=True
 p=n.new('GeometryNodeInstanceOnPoints');p.inputs['Pick Instance'].default_value=True;l.new(i.outputs['Geometry'],p.inputs['Points']);l.new(c.outputs['Instances'],p.inputs['Instance']);a=n.new('GeometryNodeInputNamedAttribute');a.data_type='INT';a.inputs['Name'].default_value='prototype';l.new(a.outputs['Attribute'],p.inputs['Instance Index']);a=n.new('GeometryNodeInputNamedAttribute');a.data_type='FLOAT_VECTOR';a.inputs['Name'].default_value='yaw';l.new(a.outputs['Attribute'],p.inputs['Rotation']);l.new(p.outputs['Instances'],o.inputs['Geometry']);m=ob.modifiers.new('True shared mesh instances','NODES');m.node_group=group
 return ob

def apply(scene,config,out):
 started=time.monotonic();rng=np.random.default_rng(2610100825);ground=scene.objects[GROUND];sampler,co=terrain_sampler(ground)
 norm=_read(ground.data.vertices,'normal',3);gradient=-norm[:,:2]/np.maximum(norm[:,2,None],.15);v=fields(co[:,:2],gradient);del norm,gradient;shader=add_shader(ground,v);del co,v;gc.collect()
 projection=CameraProjection(scene,1000,667)
 coll=bpy.data.collections.new('AP exact coarse lag bank');scene.collection.children.link(coll);records,bank_sha=grain_bank(scene.objects[LAG],coll)
 # Metric allocation: dense near-camera clasts only where individually resolvable;
 # distant interstitial mixture stays in the field, never enlarged pebbles.
 xy=np.vstack([np.c_[rng.uniform(-5.5,-3.43,18000),rng.uniform(-.05,8,18000)],np.c_[rng.uniform(-9,-3.45,18000),rng.uniform(8,70,18000)]])
 z,v=surface_fields(sampler,xy);pr=rng.integers(0,len(records),len(xy));rad=np.array([r['radius'] for r in records])[pr];good=np.isfinite(z);vis=projection.visible(np.c_[xy,np.nan_to_num(z)],margin=40);px,_=projection.project(np.c_[xy,np.nan_to_num(z)]);q=projection.area_vectors(np.c_[xy,np.nan_to_num(z)]);dp=2*rad*np.sqrt(np.linalg.norm(q,axis=1));prob=(.025+.86*v['coarse']**1.7)*(1-.82*v['fines']);good &=vis&(rng.random(len(xy))<prob)&(dp>.25)
 rows=np.flatnonzero(good);packing=PackingIndex(max(r['radius'] for r in records));selected=[]
 for i in rows:
  if packing.clear(xy[i],rad[i]):packing.add(xy[i],rad[i]);selected.append(i)
 selected=np.asarray(selected,int);xy=xy[selected];z=z[selected];pr=pr[selected];fv=v['fines'][selected]
 bottom=np.array([r['zmin'] for r in records])[pr];top=np.array([r['zmax'] for r in records])[pr];yaw=rng.uniform(0,math.tau,len(xy));bury=(top-bottom)*(.16+.58*fv);zz=z-bottom-bury
 instances(scene,coll,np.c_[xy,zz],pr,yaw)
 # Existing approved fine grains keep exact shape/material/size, with limited
 # historical fine-skin burial. No raising, scaling, or source-bank mutation.
 buried={}
 for name in ('True approved R5D near-camera grain geometry','U approved R5D density / projected chip and grit supplement'):
  ob=scene.objects.get(name)
  if ob is None:continue
  pp=_read(ob.data.vertices,'co',3);ff=fields(pp[:,:2]);dz=.00075*ff['fines']*(1-ff['coarse']);pp[:,2]-=dz;ob.data.vertices.foreach_set('co',pp.ravel());ob.data.update();buried[name]={'origins':len(pp),'max_burial_m':float(dz.max(initial=0)),'moved':int(np.count_nonzero(dz>1e-8))}
 # Replace visible corridor's old isolated shrubs, retaining far landscape.
 removed=0
 for ob in list(scene.objects):
  if ob.name.startswith(('Scrub group /','Established irregular','Scrub patch /','Sparse dry straw')) and -12<ob.location.x<-3.5 and -.4<ob.location.y<85:
   ob.hide_render=True;removed+=1
 from layered_scrub_ap import create_variants
 pc=bpy.data.collections.new('AP layered scrub source bank');scene.collection.children.link(pc);protos=create_variants(pc,seed=261010)
 if isinstance(protos,dict):protos=protos.get('shrubs',protos.get('prototypes'))
 # Use joint receiving/bank field. Cluster centres carry unequal densities and
 # overlapping low skirts; candidate coordinates cover the actual visible view.
 candidates=np.c_[rng.uniform(-11,-3.85,1400),rng.uniform(.6,85,1400)];pz,pv=surface_fields(sampler,candidates);screen=projection.visible(np.c_[candidates,np.nan_to_num(pz)+.15],margin=95);valid=np.flatnonzero(np.isfinite(pz)&screen&(rng.random(len(pz))<pv['plants']*.30))
 centres=[]
 for i in valid:
  if all(np.linalg.norm(candidates[i]-c)>1.25 for c in centres):centres.append(candidates[i])
 # Explicit unequal visible groups select the same field; no decorative uniform
 # row. Keep lower foreground texture area and pavement unobstructed.
 for p in [(-4.38,2.0),(-4.67,4.8),(-4.95,9.6),(-5.6,16.5),(-6.1,28.0),(-6.8,43.0)]:centres.append(np.array(p))
 roots=[];plant_records=[]
 for ci,c in enumerate(centres):
  number=int(rng.integers(3,8));spread=rng.uniform(.18,.55)
  for j in range(number):
   p=c+rng.normal(0,spread,2)
   if p[0]>-3.86:continue
   h=float(sampler.height(p[None])[0])
   if not np.isfinite(h):continue
   family=0 if j else 1;proto=protos[int(rng.integers(len(protos)))];ob=bpy.data.objects.new('AP layered scrub / joint sediment pocket',proto.data);scene.collection.objects.link(ob)
   scale=rng.uniform(.70,1.12) if j==0 else rng.uniform(.40,.78);ob.location=(*p,h-.005);ob.rotation_euler=(rng.uniform(-.06,.06),rng.uniform(-.06,.06),rng.uniform(0,math.tau));ob.scale=(scale*rng.uniform(.85,1.15),scale*rng.uniform(.85,1.15),scale)
   roots.append((*p,h));plant_records.append({'prototype':proto.name,'xyz_m':list(ob.location),'scale':list(ob.scale)})
 roots=np.asarray(roots).reshape(-1,3);uv,depth=projection.project(roots) if len(roots) else (np.empty((0,2)),np.empty(0));visible=projection.visible(roots+.15*np.array([0,0,1]),margin=0) if len(roots) else []
 report={'kind':'AP shared historical roadside sorting and layered scrub, illustrative rather than validated process','elapsed_seconds':time.monotonic()-started,'new_coarse_instances':len(selected),'exact_source_bank_sha256':bank_sha,'bank_identity_order':[r['name'] for r in records],'diameter_m_range':[min(r['diameter'] for r in records),max(r['diameter'] for r in records)],'new_clast_contact':'lowest point embedded16–74%of actual source thickness; individual body collision dynamics not solved','new_clast_coarse_fraction_mean':float(v['coarse'][selected].mean()) if len(selected) else 0,'existing_fine_grain_burial':buried,'shader':shader,'old_corridor_shrubs_hidden':removed,'new_shared_mesh_plants':len(roots),'new_plant_roots_projected_visible':int(np.sum(visible)),'root_pixels':uv.tolist(),'plant_instances':plant_records,'terrain_geometry_changed':False,'road_geometry_changed':False,'approved_R5D_prototype_materials_scale_changed':False,'actual_ground_sampler':sampler.report,'limits':['Authored historical scene composition, not new event inventory','Reference used for observation only; no site reconstruction','Preview uses existing bounded AL texture/grid LOD','New metric gravel reuses actual legacy K source bodies; not enlarged R5D particles']}
 del sampler;gc.collect();return report
