"""Central non-saving EEVEE adapter. -- JSON job or list. Source geometry/material preserved unless job records an explicit adaptation."""
import bpy,sys,json,time,hashlib,pathlib,math,shutil,os,importlib.util
from mathutils import Vector, Matrix
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from capture_modes import capture_mode
from transport_components import LIGHT_PASSES
def hash_file(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  while block:=f.read(8*1024*1024):h.update(block)
 return h.hexdigest()
def image_dependencies():
 result=[]
 for im in bpy.data.images:
  if im.source!='FILE' or not im.filepath:continue
  p=pathlib.Path(bpy.path.abspath(im.filepath));packed=im.packed_file
  digest=hashlib.sha256(bytes(packed.data)).hexdigest() if packed else hash_file(p)
  result.append({'image':im.name,'path':str(p),'packed':bool(packed),'sha256':digest,'colorspace':im.colorspace_settings.name})
 return sorted(result,key=lambda x:(x['image'],x['path']))
def pipeline_snapshot(extra_sources=None):
 root=pathlib.Path(__file__).resolve().parent
 names=['render.py','oidn_image_bridge.py','clean_receipt.py','clean_render.sh','render.sh','png_precision_check.py','oidn_contract.py','verify_pipeline_snapshot.py','capture_modes.py','raw_receipt.py','transport_components.py','component_image_bridge.py','component_receipt.py']
 sources={n:root/n for n in names};sources.update(extra_sources or {})
 hashes={n:hash_file(p) for n,p in sources.items()};digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest();dest=root/'pipeline_snapshots'/digest;dest.mkdir(parents=True,exist_ok=True)
 for n in hashes:
  if not (dest/n).exists():shutil.copyfile(sources[n],dest/n)
  assert hash_file(dest/n)==hashes[n],'Pipeline snapshot mismatch'
 (dest/'manifest.json').write_text(json.dumps(hashes,indent=2));return {'sha256':digest,'files':hashes,'snapshot':str(dest)}
def configure_curve_cache(job,s):
 if 'native_curve_cache_resolution' not in job:return None
 import array
 targets=job['native_curve_cache_resolution']
 assert isinstance(targets,dict) and targets,'Explicit nonempty curve cache targets required'
 assert job.get('engine')=='CYCLES' and s.cycles_curves.shape=='THICK','Curve cache adapter requires round Cycles curves'
 def digest(data):
  h=hashlib.sha256()
  for coll,prop,code,width in [(data.position_data,'vector','f',3),(data.attributes['radius'].data,'value','f',1),(data.attributes['curve_type'].data,'value','i',1)]:
   values=array.array(code,[0])* (len(coll)*width);coll.foreach_get(prop,values);h.update(memoryview(values).cast('B'));del values
  return h.hexdigest()
 records=[]
 for name,value in targets.items():
  assert type(value) is int and value==1,'Only qualified resolution 1 is supported'
  ob=s.objects.get(name);assert ob is not None and ob.type=='CURVES' and not ob.modifiers,'Unmodified native curve object required'
  for mat in ob.data.materials:
   assert mat and mat.use_nodes,'Audited node material required'
   assert all(n.bl_idname not in {'ShaderNodeBsdfHair','ShaderNodeBsdfHairPrincipled','ShaderNodeGroup','ShaderNodeAttribute'} for n in mat.node_tree.nodes),'Material may depend on optional curve normal or generic cache attributes'
  data=ob.data;attr=data.attributes.get('resolution');assert attr is not None and attr.domain=='CURVE' and attr.data_type=='INT','Existing per-curve resolution required'
  before=digest(data);old=array.array('i',[0])*len(attr.data);attr.data.foreach_get('value',old)
  count=len(attr.data);data.attributes.remove(attr);attr=data.attributes.new('resolution','INT','CURVE')
  attr.data.foreach_set('value',array.array('i',[value])*count);data.update_tag();ob.update_tag()
  assert digest(data)==before,'Curve positions, radii or types changed'
  records.append({'object':name,'prior_resolution_values':sorted(set(old)),'resolution':value,'curves':len(attr.data),'points':len(data.position_data),'unchanged_position_radius_type_sha256':before})
 return records
def configure_compact_bvh(job,s):
 if 'compact_bvh' not in job:return None
 assert type(job['compact_bvh']) is bool,'compact_bvh must be boolean'
 assert s.render.engine=='CYCLES' and s.cycles.device=='CPU','Compact BVH adapter requires Cycles CPU'
 assert hasattr(s.cycles,'debug_use_compact_bvh'),'Compact BVH is unavailable'
 s.cycles.debug_use_compact_bvh=job['compact_bvh']
 return 'CPU compact BVH acceleration '+str(job['compact_bvh'])+'; source geometry, curve keys/radii and materials unchanged'
def effective_capture(s):
 # Newly created objects and recent location/rotation edits can retain stale
 # matrix_world values until the dependency graph is evaluated.
 for layer in s.view_layers:layer.update()
 c=s.camera
 fields=['debug_use_compact_bvh','samples','seed','use_animated_seed','max_bounces','diffuse_bounces','glossy_bounces','transmission_bounces','transparent_max_bounces','volume_bounces','sample_clamp_direct','sample_clamp_indirect','blur_glossy','caustics_reflective','caustics_refractive','use_adaptive_sampling','adaptive_threshold','adaptive_min_samples']
 return {'frame':s.frame_current,'unit_scale':s.unit_settings.scale_length,'cycles':{k:getattr(s.cycles,k) for k in fields if hasattr(s.cycles,k)},'camera':{'matrix_world':list(map(list,c.matrix_world)),**{k:getattr(c.data,k) for k in ['type','ortho_scale','lens','clip_start','clip_end','sensor_width','sensor_height','shift_x','shift_y']}},'lights':{o.name:{'matrix_world':list(map(list,o.matrix_world)),'type':o.data.type,'energy':o.data.energy,'color':list(o.data.color),**{k:getattr(o.data,k) for k in ['shape','size','size_y','shadow_soft_size'] if hasattr(o.data,k)}} for o in s.objects if o.type=='LIGHT'},'specimen_transforms':{o.name:list(map(list,o.matrix_world)) for o in s.objects if o.type in {'MESH','CURVE','CURVES'}},'world':s.world.name if s.world else None,'display_device':s.display_settings.display_device,'film_transparent':s.render.film_transparent,'pixel_aspect':[s.render.pixel_aspect_x,s.render.pixel_aspect_y],'png_color_depth':s.render.image_settings.color_depth,'png_color_mode':s.render.image_settings.color_mode,'dither_intensity':s.render.dither_intensity}
config=json.load(open(sys.argv[sys.argv.index('--')+1]));jobs=config if isinstance(config,list) else [config]
for job in jobs:
 capture_mode(job)
 if capture_mode(job)=='component-recombined':assert job.get('engine')=='CYCLES' and job.get('save_guides'),'Component capture requires Cycles and native guides'
 source=pathlib.Path(job['source']);before=hash_file(source)
 if job.get('source_sha256'):assert before==job['source_sha256'],'Expected source SHA256 mismatch; refusing capture'
 mapping_config=os.environ.get('MATERIAL_PATH_MAP_FILE');relocation=None
 if mapping_config:
  mapping_path=pathlib.Path(mapping_config).resolve();mapping_sha=hash_file(mapping_path)
  helper=pathlib.Path(__file__).resolve().parent.parent/'material-production'/'materials'/'path_config.py'
  pipeline=pipeline_snapshot({'path_config.py':helper})
  spec=importlib.util.spec_from_file_location('capture_path_config',pathlib.Path(pipeline['snapshot'])/'path_config.py');path_config=importlib.util.module_from_spec(spec);spec.loader.exec_module(path_config)
  mapping_state=path_config.configuration_state();assert mapping_state['config_sha256']==mapping_sha,'Path-map config changed before capture'
 else:pipeline=pipeline_snapshot()
 bpy.ops.wm.open_mainfile(filepath=str(source))
 if mapping_config:
  relocation={'config_path':str(mapping_path),'config_sha256':mapping_sha,'helper_sha256':pipeline['files']['path_config.py'],'mappings':mapping_state['prefixes'],'images':path_config.remap_scene_images(bpy,mapping_state)}
  assert hash_file(mapping_path)==mapping_sha,'Path-map config changed during image relocation'
 if job.get('scene'):bpy.context.window.scene=bpy.data.scenes[job['scene']]
 s=bpy.context.scene
 curve_cache_adaptation=configure_curve_cache(job,s)
 if job.get('camera'):s.camera=bpy.data.objects[job['camera']]
 assert s.camera,'No active camera'
 missing=[im.filepath for im in bpy.data.images if im.source=='FILE' and im.filepath and not im.packed_file and not pathlib.Path(bpy.path.abspath(im.filepath)).is_file()]
 if missing:raise RuntimeError('Missing images: '+str(missing))
 adaptations=['Engine/resolution/samples changed in memory only']
 if curve_cache_adaptation:adaptations.append({'native_curve_cache_resolution':curve_cache_adaptation,'scope':'Only Blender evaluation-cache resolution changes; Cycles round Catmull-Rom keys/radii preserved by hash'})
 if relocation:adaptations.append('Explicit image prefix relocation applied in memory; source file unchanged')
 slab_receipt=None
 if job.get('slab_studio'):
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'material-slabs'/'source'));from studio import configure
  slab_receipt=configure(job['slab_studio']);adaptations.append('Shared neutral slab studio applied in memory; source SI geometry and shader scale preserved')
 if job.get('gray_diffuse_prefix') or job.get('gray_all'):
  mat=bpy.data.materials.new('QA gray diffuse override');mat.use_nodes=True;ns=mat.node_tree.nodes;ns.clear();d=ns.new('ShaderNodeBsdfDiffuse');d.inputs['Color'].default_value=(.25,.25,.25,1);d.inputs['Roughness'].default_value=1;o=ns.new('ShaderNodeOutputMaterial');mat.node_tree.links.new(d.outputs[0],o.inputs['Surface'])
  changed=[]
  for ob in s.objects:
   if ob.type in {'MESH','CURVE','CURVES','SURFACE','FONT'} and (job.get('gray_all') or ob.name.lower().startswith(job['gray_diffuse_prefix'].lower())):
    ob.data.materials.clear();ob.data.materials.append(mat);changed.append(ob.name)
  assert changed,'No gray override targets';adaptations.append('Gray rough diffuse override on: '+', '.join(changed))
 if job.get('camera_focus_prefix'):
  bpy.context.view_layer.update();obs=[o for o in s.objects if o.name.startswith(job['camera_focus_prefix'])];assert obs,'No focus objects'
  pts=[o.matrix_world@Vector(p) for o in obs for p in o.bound_box];center=sum(pts,Vector())/len(pts);s.camera.location=center+Vector(job.get('focus_offset',[.3,-1.05,.3]));s.camera.rotation_euler=(center-s.camera.location).to_track_quat('-Z','Y').to_euler();adaptations.append('Object-bounds detail camera framing')
 if 'ortho_scale' in job:s.camera.data.ortho_scale=job['ortho_scale'];adaptations.append('Orthographic detail framing')
 if job.get('studio_lights_downward'):
  for ob in s.objects:
   if ob.type=='LIGHT' and ob.data.type=='AREA' and ob.name.startswith('Slab /'):
    ob.rotation_euler=(0,0,0)
  adaptations.append('Studio area emitters face vertically downward to eliminate floor hemisphere-cutoff arc; positions, powers and sizes retained')
 if job.get('metal_reflection_softbox'):
  bounds=s.get('slab_bounds_m');assert bounds,'Physical studio bounds are required for reflection card'
  lo=Vector(bounds[:3]);hi=Vector(bounds[3:]);center=(lo+hi)/2;extent=max(hi-lo)
  ld=bpy.data.lights.new('Slab / metal reflection softbox','AREA');ld.energy=job.get('metal_softbox_power',12)*extent*extent;ld.shape='RECTANGLE';ld.size=extent*job.get('metal_softbox_width',.35);ld.size_y=extent*job.get('metal_softbox_height',1.6)
  ob=bpy.data.objects.new(ld.name,ld);s.collection.objects.link(ob);ob.location=center+Vector((-.82,1.10,1.02))*extent;ob.rotation_euler=(0,0,0)
  adaptations.append('Neutral metal reflection softbox added at camera-reflected direction to reveal physically dark metallic satin surface')
 if job.get('explicit_uv_tangent'):
  changed=[]
  for mat in bpy.data.materials:
   if not mat.use_nodes:continue
   for node in list(mat.node_tree.nodes):
    anisotropy=(node.inputs.get('Anisotropic IOR Level') or node.inputs.get('Anisotropic')) if node.type=='BSDF_PRINCIPLED' else None
    if anisotropy and anisotropy.default_value>0 and not node.inputs['Tangent'].is_linked:
     tangent=mat.node_tree.nodes.new('ShaderNodeTangent');tangent.direction_type='UV_MAP';tangent.uv_map='UVMap';mat.node_tree.links.new(tangent.outputs['Tangent'],node.inputs['Tangent']);node.inputs['Anisotropic Rotation'].default_value=.25;changed.append(mat.name)
  adaptations.append('Explicit UV anisotropic tangent replaces implicit radial tangent: '+str(changed))
 if 'camera_location' in job:s.camera.location=job['camera_location'];s.camera.rotation_euler=(Vector(job['camera_target'])-s.camera.location).to_track_quat('-Z','Y').to_euler();adaptations.append('Preview camera pose changed')
 if 'camera_matrix_world' in job:
  matrix=job['camera_matrix_world'];assert len(matrix)==4 and all(len(row)==4 for row in matrix),'Camera matrix must be4x4';assert all(math.isfinite(float(v)) for row in matrix for v in row),'Nonfinite camera matrix';s.camera.matrix_world=Matrix(matrix);adaptations.append('Exact camera matrix applied from recorded matched macro configuration')
 if 'camera_ortho_scale' in job:
  assert s.camera.data.type=='ORTHO' and float(job['camera_ortho_scale'])>0,'Positive orthographic scale required';s.camera.data.ortho_scale=float(job['camera_ortho_scale']);adaptations.append('Exact orthographic scale applied from recorded matched macro configuration')
 if 'lens' in job:s.camera.data.lens=job['lens']
 if 'key_location' in job:
  for o in s.objects:
   if o.type=='LIGHT' and 'key' in o.name.lower():o.location=job['key_location'];o.rotation_euler=(Vector(job.get('key_target',[0,0,0]))-o.location).to_track_quat('-Z','Y').to_euler();adaptations.append('Key moved for raking-light proof')
 if 'light_size' in job:
  for o in s.objects:
   if o.type=='LIGHT' and 'key' in o.name.lower():o.data.size=job['light_size'];adaptations.append('Key size changed for hard-light proof')
 if job.get('visible_prefixes'):
  hidden=[];kept=[]
  for ob in s.objects:
   if ob.type in {'MESH','CURVE','CURVES','SURFACE','FONT'}:
    retain=any(ob.name.startswith(p) for p in job['visible_prefixes']);ob.hide_render=not retain;(kept if retain else hidden).append(ob.name)
  adaptations.append('Isolated construction geometry only; retained '+str(kept)+'; hidden non-contact objects count '+str(len(hidden)))
 s.render.engine=job.get('engine','BLENDER_EEVEE_NEXT')
 if s.render.engine=='BLENDER_WORKBENCH':
  color_type=job.get('workbench_color_type','SINGLE');assert color_type in {'SINGLE','MATERIAL','OBJECT'},'Unsupported Workbench diagnostic color mode'
  s.display.shading.light='STUDIO';s.display.shading.color_type=color_type;s.display.shading.single_color=(.55,.55,.55);s.display.shading.show_shadows=True;s.display.shading.show_cavity=False;s.display.shading.show_object_outline=False;s.display.render_aa='32';adaptations.append('Workbench deterministic construction proof; diagnostic color mode '+color_type+'; not source BSDF or scene lighting evaluation')
 if s.render.engine=='CYCLES':
  s.cycles.device='CPU';s.cycles.samples=job.get('samples',128);s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=job.get('use_adaptive_sampling',True);s.cycles.adaptive_threshold=job.get('adaptive_threshold',.02);s.cycles.adaptive_min_samples=job.get('adaptive_min_samples',64);adaptations.append('Cycles CPU optical proof, denoising disabled because unavailable')
 else:s.eevee.taa_render_samples=job.get('samples',64)
 memory_adaptation=configure_compact_bvh(job,s)
 if memory_adaptation:adaptations.append(memory_adaptation)
 if s.render.engine=='CYCLES' and 'light_tree' in job:s.cycles.use_light_tree=job['light_tree'];adaptations.append('Cycles light-tree acceleration '+str(job['light_tree']))
 if hasattr(s.eevee,'use_raytracing'):s.eevee.use_raytracing=job.get('raytracing',True)
 for m in bpy.data.materials:
  if m.use_nodes and any(n.type=='BSDF_PRINCIPLED' and n.inputs.get('Transmission Weight') and n.inputs['Transmission Weight'].default_value>0 for n in m.node_tree.nodes):
   if hasattr(m,'use_screen_refraction'):m.use_screen_refraction=True
 width=job.get('width',960);height=job.get('height',round(width*s.render.resolution_y/s.render.resolution_x));s.render.resolution_x=width;s.render.resolution_y=height;s.render.resolution_percentage=100
 out=pathlib.Path(job['output']);out.parent.mkdir(parents=True,exist_ok=True);s.render.filepath=str(out);s.render.image_settings.file_format='PNG'
 if 'color_depth' in job:s.render.image_settings.color_depth=str(job['color_depth']);adaptations.append('Capture PNG precision '+str(job['color_depth'])+' bit')
 if 'dither_intensity' in job:s.render.dither_intensity=job['dither_intensity'];adaptations.append('PNG quantization dither '+str(job['dither_intensity']))
 guide_paths=[];transport_paths={}
 guide_passes={'beauty':'Image','albedo':'Denoising Albedo','normal':'Denoising Normal'}
 custom_guides=('guide_albedo_pass' in job,'guide_normal_pass' in job)
 assert custom_guides[0]==custom_guides[1],'Custom albedo and normal passes must be specified together'
 if custom_guides[0]:
  for label,key in [('albedo','guide_albedo_pass'),('normal','guide_normal_pass')]:
   assert isinstance(job[key],str) and job[key].strip(),'Custom guide pass must be a nonempty name'
   guide_passes[label]=job[key]
 if job.get('save_guides'):
  assert s.render.engine=='CYCLES','Guided exports require Cycles'
  vl=s.view_layers[0];vl.cycles.denoising_store_passes=True
  if capture_mode(job)=='component-recombined':
   for family in ['diffuse','glossy','transmission']:
    for part in ['direct','indirect','color']:setattr(vl,'use_pass_'+family+'_'+part,True)
   vl.use_pass_emit=True;vl.use_pass_environment=True;vl.cycles.use_pass_volume_direct=True;vl.cycles.use_pass_volume_indirect=True
  vl.update_render_passes();s.use_nodes=True;s.render.use_compositing=True
  nodes=s.node_tree.nodes;rl=nodes.new('CompositorNodeRLayers');rl.scene=s;rl.layer=vl.name
  fn=nodes.new('CompositorNodeOutputFile');gd=out.parent/(out.stem+'_guides');gd.mkdir(parents=True,exist_ok=True);fn.base_path=str(gd);fn.format.file_format='OPEN_EXR';fn.format.color_depth='32';fn.format.color_mode='RGB';fn.format.exr_codec='ZIP'
  for idx,(label,socket) in enumerate(guide_passes.items()):
   
   if idx:fn.file_slots.new(label)
   assert socket in rl.outputs,'Declared guide pass is absent: '+socket
   slot=fn.file_slots[idx];slot.path=label+'_';s.node_tree.links.new(rl.outputs[socket],fn.inputs[idx]);guide_paths.append(str(gd/(label+'_'+str(s.frame_current).zfill(4)+'.exr')))
  if capture_mode(job)=='component-recombined':
   for label,socket in LIGHT_PASSES.items():
    assert socket in rl.outputs,'Required transport pass absent: '+socket
    fn.file_slots.new(label);slot=fn.file_slots[-1];slot.path=label+'_';s.node_tree.links.new(rl.outputs[socket],fn.inputs[-1]);transport_paths[label]=str(gd/(label+'_'+str(s.frame_current).zfill(4)+'.exr'))
   adaptations.append('Native physical transport passes exported for explicit component-recombined processing; no filtering in render stage')
  adaptations.append('Linear32bit EXR beauty plus denoising albedo/normal guides exported, no filtering')
 dependencies=image_dependencies();capture=effective_capture(s)
 if curve_cache_adaptation or memory_adaptation:
  (out.parent/'PRE_RENDER_MEMORY_ADAPTATIONS.json').write_text(json.dumps({'source_sha256':before,'pipeline':pipeline,'curve_cache':curve_cache_adaptation,'compact_bvh':memory_adaptation,'effective_capture':capture},indent=2))
 start=time.monotonic();bpy.ops.render.render(write_still=True);elapsed=time.monotonic()-start
 after=hash_file(source);assert after==before
 assert image_dependencies()==dependencies,'Image dependency changed during capture'
 if relocation:assert path_config.configuration_state()==mapping_state,'Path-map config or helper changed during capture'
 report={'job':job,'source_sha256':before,'render_seconds':elapsed,'engine':s.render.engine,'blender_version':bpy.app.version_string,'adaptations':adaptations,'camera':s.camera.name,'camera_location':list(s.camera.location),'camera_rotation':list(s.camera.rotation_euler),'missing_images':missing,'objects':len(s.objects),'resolution':[width,height],'guide_paths':guide_paths}
 report['display_settings']={k:getattr(s.view_settings,k) for k in ['view_transform','look','exposure','gamma']}
 report['pipeline']=pipeline;report['image_dependencies']=dependencies;report['effective_capture']=capture;report['frame']=s.frame_current;report['blender_build_hash']=bpy.app.build_hash.decode(errors='replace')
 report['guide_passes']=guide_passes
 if capture_mode(job)=='component-recombined':report['transport_paths']=transport_paths
 if s.render.engine=='BLENDER_WORKBENCH':report['workbench_settings']={'geometry_only':True,'render_aa':s.display.render_aa,'lighting':s.display.shading.light,'color_type':s.display.shading.color_type,'single_color':list(s.display.shading.single_color),'material_shaders_evaluated':False}
 if relocation:report['relocation']=relocation
 if slab_receipt:report['slab_studio']=slab_receipt
 out.with_suffix(out.suffix+'.json').write_text(json.dumps(report,indent=2));print('VIEW_COMPLETE '+str(out)+' '+str(round(elapsed,2))+' s',flush=True)
