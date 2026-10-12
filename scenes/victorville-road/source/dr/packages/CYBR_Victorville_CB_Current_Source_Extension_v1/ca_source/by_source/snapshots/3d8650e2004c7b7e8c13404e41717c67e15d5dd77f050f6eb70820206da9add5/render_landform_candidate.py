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
 names=['preview_mesh_cull.py','render.py','oidn_image_bridge.py','clean_receipt.py','clean_render.sh','render.sh','png_precision_check.py','oidn_contract.py','verify_pipeline_snapshot.py','capture_modes.py','raw_receipt.py','transport_components.py','component_image_bridge.py','component_receipt.py']
 sources={n:root/n for n in names};sources.update({'render.py':root/'render_landform_candidate.py','render.sh':root/'render_landform_candidate.sh','clean_render.sh':root/'clean_render_landform_candidate.sh'});sources.update({n:root/n for n in ('render_landform_candidate.py','render_landform_candidate.sh','clean_render_landform_candidate.sh')});sources.update(extra_sources or {})
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
def camera_cull_dense_offscreen(job,s):
 if 'camera_cull_prefixes' not in job:return None
 from bpy_extras.object_utils import world_to_camera_view
 prefixes=job['camera_cull_prefixes'];guard=float(job.get('camera_cull_margin',.12))
 assert isinstance(prefixes,list) and prefixes==['Original asphalt native tile '], 'Only qualified native asphalt prefix is supported'
 assert guard>=.12, 'Keep a conservative off-screen margin'
 for layer in s.view_layers:layer.update()
 removed=[];meshes=set()
 for ob in list(s.objects):
  if ob.type!='MESH' or not any(ob.name.startswith(p) for p in prefixes):continue
  points=[world_to_camera_view(s,s.camera,ob.matrix_world@Vector(v)) for v in ob.bound_box]
  bounds=[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]
  # The convex object's bounds must be wholly in front of the eye, and
  # wholly outside one expanded camera half-space. No crossing boxes culled.
  if bounds[2][0]<=0:continue
  outside=bounds[0][1]<-guard or bounds[0][0]>1+guard or bounds[1][1]<-guard or bounds[1][0]>1+guard
  if not outside:continue
  removed.append({'object':ob.name,'mesh':ob.data.name,'camera_bounds':bounds});meshes.add(ob.data.name)
  bpy.data.objects.remove(ob,do_unlink=True)
 discarded=[]
 for name in meshes:
  m=bpy.data.meshes.get(name)
  if m is not None and m.users==0:discarded.append({'mesh':name,'vertices':len(m.vertices),'polygons':len(m.polygons)});bpy.data.meshes.remove(m)
 return {'removed_offscreen_instances':removed,'discarded_now_unreferenced_meshes':discarded,'expanded_camera_margin':guard,'scope':'Preview only. Retains all visible geometry and a12percent frame margin. Distant indirect paths may differ; identical culling is used for matched baseline. Full source scene unchanged.'}
def configure_asphalt_preview_mips(job):
 if 'asphalt_preview_map_size' not in job:return None
 size=job['asphalt_preview_map_size'];assert type(size) is int and size in (1024,2048),'Qualified preview map size only'
 records=[]
 for name in ('BaseColor.png','Normal_Object_RGB16.png','Roughness.png'):
  im=bpy.data.images.get(name);assert im is not None and list(im.size)==[4096,4096], 'Expected original native asphalt map'
  before=list(im.size);space=im.colorspace_settings.name;im.scale(size,size);im.update()
  assert list(im.size)==[size,size] and im.colorspace_settings.name==space
  records.append({'image':name,'native_size':before,'preview_size':list(im.size),'colorspace':space})
 return {'images':records,'scope':'In-memory preview mip only. Source packed native maps and all geometry unchanged; same settings must be used for a matched baseline. Normal variance is not reconstructed into roughness, so this is not a native-detail fidelity proof.'}
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
 else:
  extra_sources={}
  if job.get('allocator_policy_bx'):
   extra_sources['allocator_policy_bx.py']=pathlib.Path(__file__).resolve().parent/'allocator_policy_bx.py'
  if job.get('historical_fine_area_bw'):
   extra_sources['historical_fine_area_bw.py']=pathlib.Path(__file__).resolve().parent.parent/'src/historical_fine_area_bw.py'
  if job.get('road_surface_wear_by'):
   for name in ('road_surface_wear_by.py','road_wear_field_by.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('aligned_context_daylight'):
   extra_sources['align_context_daylight_bt.py']=pathlib.Path(__file__).resolve().parent.parent/'src/align_context_daylight_bt.py'
  if job.get('asphalt_context_grid_stride'):
   extra_sources['asphalt_context_lod.py']=pathlib.Path(__file__).resolve().parent/'asphalt_context_lod.py'
  if job.get('discard_unused_render_data'):
   extra_sources['discard_unused_render_data.py']=pathlib.Path(__file__).resolve().parent/'discard_unused_render_data.py'
  if job.get('landform_candidate'):
   config_landform=job['landform_candidate'];manifest_path=pathlib.Path(config_landform['source_manifest'])
   assert hash_file(manifest_path)==config_landform['source_manifest_sha256'],'Landform source manifest changed'
   for relative,pin in json.loads(manifest_path.read_text()).items():
    candidate_path=pathlib.Path(__file__).resolve().parent.parent/relative
    assert hash_file(candidate_path)==pin,'Landform source input changed: '+relative
    basename=candidate_path.name
    if basename in extra_sources:assert extra_sources[basename]==candidate_path,'Source basename collision'
    extra_sources[basename]=candidate_path
  if job.get('edge_ravel_aa'):
   for name in ('metric_edge_strip_aa.py','edge_ravel_field_aa.py','assemble_raveled_edge_aa.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('pavement_contact_ac'):
   for name in ('metric_edge_strip_aa.py','edge_ravel_field_aa.py','assemble_raveled_edge_aa.py','pavement_contact_ac.py','assemble_pavement_contact_ac.py','prepare_physical_lenses.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('visible_shoulder_ad'):
   for name in ('assemble_visible_shoulder_ad.py','context_mesh_refine_ab.py','visible_shoulder_flow_ad.py','flow_sediment_model_z.py','prepare_physical_lenses.py','context_field_cache_ad.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('graded_shoulder_af'):
   for name in ('assemble_graded_shoulder_af.py','graded_shoulder_foundation_af.py','assemble_visible_shoulder_ad.py','context_mesh_refine_ab.py','visible_shoulder_flow_ad.py','flow_sediment_model_z.py','flow_transport_ae.py','prepare_physical_lenses.py','context_field_cache_ad.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('graded_shoulder_ah'):
   for name in ('assemble_graded_shoulder_ah.py','graded_shoulder_foundation_ah.py','terrain_normal_transfer_ah.py','assemble_visible_shoulder_ad.py','context_mesh_refine_ab.py','visible_shoulder_flow_ad.py','flow_sediment_model_z.py','flow_transport_ae.py','prepare_physical_lenses.py','context_field_cache_ad.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('graded_shoulder_ah',{}).get('foundation_revision')=='AT':
   extra_sources['graded_shoulder_foundation_at.py']=pathlib.Path(__file__).resolve().parent.parent/'src/graded_shoulder_foundation_at.py'
  if job.get('graded_shoulder_ah',{}).get('historical_substrate'):
   extra_sources['substrate_history_ak.py']=pathlib.Path(__file__).resolve().parent.parent/'src/substrate_history_ak.py'
  if job.get('refresh_view_grains_au'):
   for name in ('refresh_view_grains_au.py','approved_density_lod.py','context_mesh_refine_ab.py','visible_shoulder_flow_ad.py','prepare_physical_lenses.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('assembled_scene_cache_av'):
   extra_sources['assembled_scene_cache_av.py']=pathlib.Path(__file__).resolve().parent.parent/'src/assembled_scene_cache_av.py'
  if job.get('legacy_profile_aw'):
   for name in ('apply_legacy_profile_aw.py','legacy_shoulder_profile_aw.py','graded_shoulder_foundation_at.py','graded_shoulder_foundation_ah.py','context_mesh_refine_ab.py','visible_shoulder_flow_ad.py','terrain_normal_transfer_ah.py','prepare_physical_lenses.py','flow_sediment_model_z.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('jointed_ridges_ax'):
   extra_sources['jointed_ridge_fields_ax.py']=pathlib.Path(__file__).resolve().parent.parent/'src/jointed_ridge_fields_ax.py'
   revision=job['jointed_ridges_ax'].get('revision','AX')
   if revision not in ('AX','AY','BA','BB'):raise ValueError('Unrecognized ridge candidate revision')
   if revision=='AY':
    extra_sources['jointed_ridge_fields_ay.py']=pathlib.Path(__file__).resolve().parent.parent/'src/jointed_ridge_fields_ay.py'
   if revision=='BA':
    extra_sources['ridge_faces_ba.py']=pathlib.Path(__file__).resolve().parent.parent/'src/ridge_faces_ba.py'
   if revision=='BB':
    extra_sources['spur_gully_ridges_bb.py']=pathlib.Path(__file__).resolve().parent.parent/'src/spur_gully_ridges_bb.py'
  if job.get('fine_coating_az'):
   extra_sources['fine_coating_az.py']=pathlib.Path(__file__).resolve().parent.parent/'src/fine_coating_az.py'
   extra_sources['fine_response.py']=pathlib.Path(__file__).resolve().parent.parent/'audits/fines_response_az/fine_response.py'
  if job.get('sediment_surface_ai'):
   for name in ('assemble_sediment_surface_ai.py','sediment_surface_ai.py','transported_grain_exposure.py','approved_density_lod.py','runoff_edge_support_ai.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('sample_final_surface_an'):
   extra_sources['sample_final_surface_an.py']=pathlib.Path(__file__).resolve().parent.parent/'src/sample_final_surface_an.py'
  if job.get('refined_film_an'):
   extra_sources['apply_refined_film_an.py']=pathlib.Path(__file__).resolve().parent.parent/'src/apply_refined_film_an.py'
  if job.get('contact_bank_continuity_al'):
   for name in ('contact_bank_continuity_al.py','contact_triangle_clearance_al.py','context_mesh_refine_ab.py','metric_edge_strip_aa.py','runoff_edge_support_ai.py','terrain_normal_transfer_ah.py','approved_density_lod.py','prepare_physical_lenses.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('road_film_ownership_al'):
   extra_sources['road_film_ownership_al.py']=pathlib.Path(__file__).resolve().parent.parent/'src/road_film_ownership_al.py'
  if job.get('continuous_contact_aq') or job.get('road_margin_aq') or job.get('current_contact_film_aq'):
   for name in ('continuous_contact_aq.py','assemble_road_margin_aq.py','current_contact_film_aq.py','road_margin_composition_ap.py','sample_final_surface_an.py','context_mesh_refine_ab.py','approved_density_lod.py','contact_bank_continuity_al.py','contact_triangle_clearance_al.py','prepare_physical_lenses.py','metric_edge_strip_aa.py','refined_film_event_an.py','flow_sediment_model_ao.py','road_film_shader_z.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
   for name in ('layered_scrub_ap.py','desert_scrub.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'vegetation'/name
  if job.get('fractured_boundary_ar'):
   for name in ('fractured_boundary_ar.py','soil_rim_bridge_ar.py','integrate_fracture_ar.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  if job.get('metric_fragments_as'):
   for name in ('metric_margin_fragments_as.py','assemble_metric_fragments_as.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
   if job['metric_fragments_as'].get('geometry_revision')=='fractured_candidate':
    extra_sources['metric_margin_fragments_as_fractured_candidate.py']=pathlib.Path(__file__).resolve().parent.parent/'src/metric_margin_fragments_as_fractured_candidate.py'
  if job.get('road_margin_ap'):
   for name in ('assemble_road_margin_ap.py','road_margin_composition_ap.py','sample_final_surface_an.py','context_mesh_refine_ab.py','approved_density_lod.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
   for name in ('layered_scrub_ap.py','desert_scrub.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'vegetation'/name
  if job.get('shoulder_context_ab'):
   for name in ('assemble_shoulder_context_ab.py','context_mesh_refine_ab.py','shoulder_context_flow_ab.py','flow_sediment_model_z.py','prepare_physical_lenses.py','context_field_cache_ab.py'):
    extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name
  pipeline=pipeline_snapshot(extra_sources)
 allocator_report=None
 if job.get('allocator_policy_bx'):
  assert job['allocator_policy_bx']=={'revision':1},'Unexpected allocator policy'
  from allocator_policy_bx import inspect as inspect_allocator
  allocator_report=inspect_allocator(required=True)
  print('ACTIVE_ALLOCATOR_POLICY',json.dumps(allocator_report),flush=True)
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
 if allocator_report:adaptations.append({'allocator_policy_bx':allocator_report})
 if job.get('aligned_context_daylight'):
  sys.path.insert(0,pipeline['snapshot'])
  from align_context_daylight_bt import apply as align_daylight
  report=align_daylight(s,job['aligned_context_daylight'],pathlib.Path(job['output']).parent);adaptations.append({'aligned_context_daylight':report})
 if job.get('legacy_profile_aw'):
  assert not any(job.get(k) for k in ('graded_shoulder_ah','fractured_boundary_ar','assembled_scene_cache_av')),'AW is an in-memory admitted-cache diagnostic, not a duplicate assembly'
  sys.path.insert(0,pipeline['snapshot'])
  from apply_legacy_profile_aw import apply as apply_legacy_profile
  report=apply_legacy_profile(s,job['legacy_profile_aw'],pathlib.Path(job['output']).parent);adaptations.append({'legacy_profile_aw':report})
 if job.get('jointed_ridges_ax'):
  sys.path.insert(0,pipeline['snapshot'])
  revision=job['jointed_ridges_ax'].get('revision','AX')
  if revision=='AY':
   from jointed_ridge_fields_ay import apply_in_memory as apply_jointed_ridges
  elif revision=='BA':
   from ridge_faces_ba import apply_in_memory as apply_jointed_ridges
  elif revision=='BB':
   from spur_gully_ridges_bb import apply_in_memory as apply_jointed_ridges
  else:
   from jointed_ridge_fields_ax import apply_in_memory as apply_jointed_ridges
  report=apply_jointed_ridges(s);adaptations.append({'jointed_ridges_ax':report})
  (pathlib.Path(job['output']).parent/('JOINTED_RIDGES_'+revision+'.json')).write_text(json.dumps(report,indent=2))
 if job.get('fine_coating_az'):
  sys.path.insert(0,pipeline['snapshot'])
  from fine_coating_az import apply as apply_fine_coating_az
  report=apply_fine_coating_az(s,job['fine_coating_az'],pathlib.Path(job['output']).parent)
  adaptations.append({'fine_coating_az':report})
 if job.get('edge_ravel_aa'):
  assert not mapping_config,'AA diagnostic requires pinned local source inputs'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_raveled_edge_aa import apply as assemble_edge
  edge_report=assemble_edge(s,job['edge_ravel_aa']);adaptations.append({'edge_ravel_aa':edge_report})
  (pathlib.Path(job['output']).parent/'EDGE_RAVEL_AA.json').write_text(json.dumps(edge_report,indent=2))
 if job.get('visible_shoulder_ad'):
  assert not mapping_config,'AD diagnostic requires pinned local source inputs'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_visible_shoulder_ad import apply as assemble_visible_shoulder
  visible_report=assemble_visible_shoulder(s,job['visible_shoulder_ad'],pathlib.Path(job['output']).parent);adaptations.append({'visible_shoulder_ad':visible_report})
  (pathlib.Path(job['output']).parent/'VISIBLE_SHOULDER_AD.json').write_text(json.dumps(visible_report,indent=2))
 if job.get('graded_shoulder_af'):
  assert not mapping_config,'AF diagnostic requires pinned local source inputs'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_graded_shoulder_af import apply as assemble_graded_shoulder
  graded_report=assemble_graded_shoulder(s,job['graded_shoulder_af'],pathlib.Path(job['output']).parent);adaptations.append({'graded_shoulder_af':graded_report})
  (pathlib.Path(job['output']).parent/'GRADED_SHOULDER_AF.json').write_text(json.dumps(graded_report,indent=2))
 if job.get('graded_shoulder_ah'):
  assert not mapping_config,'AH diagnostic requires pinned local source inputs'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_graded_shoulder_ah import apply as assemble_graded_shoulder
  graded_report=assemble_graded_shoulder(s,job['graded_shoulder_ah'],pathlib.Path(job['output']).parent);adaptations.append({'graded_shoulder_ah':graded_report})
  (pathlib.Path(job['output']).parent/'GRADED_SHOULDER_AH.json').write_text(json.dumps(graded_report,indent=2))
 if job.get('refresh_view_grains_au'):
  assert job.get('graded_shoulder_ah') and job.get('sediment_surface_ai'),'AU requires current AH geometry and subsequent finite-stock AI exposure'
  sys.path.insert(0,pipeline['snapshot'])
  from refresh_view_grains_au import apply as refresh_grains_au
  print('VIEW_GRAIN_REFRESH_BEGIN',flush=True)
  report=refresh_grains_au(s,job['refresh_view_grains_au'],pathlib.Path(job['output']).parent);adaptations.append({'refresh_view_grains_au':report})
  (pathlib.Path(job['output']).parent/'VIEW_GRAIN_REFRESH_AU.json').write_text(json.dumps(report,indent=2))
  print('VIEW_GRAIN_REFRESH_COMPLETE',report.get('elapsed_seconds'),flush=True)
 if job.get('pavement_contact_ac'):
  assert not mapping_config,'AC diagnostic requires pinned local source inputs'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_pavement_contact_ac import apply as assemble_contact
  contact_config=dict(job['pavement_contact_ac'])
  if contact_config.get('runoff_support'):
   contact_config['runoff_support_fields']=str(pathlib.Path(job['output']).parent/'AH_FIELDS.npz')
  contact_report=assemble_contact(s,contact_config);adaptations.append({'pavement_contact_ac':contact_report})
  (pathlib.Path(job['output']).parent/'PAVEMENT_CONTACT_AC.json').write_text(json.dumps(contact_report,indent=2))
 if job.get('contact_bank_continuity_al'):
  assert job.get('graded_shoulder_ah') and job.get('pavement_contact_ac')
  sys.path.insert(0,pipeline['snapshot'])
  from contact_bank_continuity_al import apply as continue_bank_support
  bank_report=continue_bank_support(s,job['contact_bank_continuity_al'],pathlib.Path(job['output']).parent);adaptations.append({'contact_bank_continuity_al':bank_report})
  (pathlib.Path(job['output']).parent/'CONTACT_BANK_CONTINUITY_AL.json').write_text(json.dumps(bank_report,indent=2))
 if job.get('road_film_ownership_al'):
  sys.path.insert(0,pipeline['snapshot'])
  from road_film_ownership_al import apply as assign_film_ownership
  ownership_report=assign_film_ownership(s,job['road_film_ownership_al']);adaptations.append({'road_film_ownership_al':ownership_report})
  (pathlib.Path(job['output']).parent/'ROAD_FILM_OWNERSHIP_AL.json').write_text(json.dumps(ownership_report,indent=2))
 if job.get('sample_final_surface_an'):
  sys.path.insert(0,pipeline['snapshot'])
  from sample_final_surface_an import sample as sample_final_film_surface
  surface_report=sample_final_film_surface(s,pathlib.Path(job['output']).parent,{})
  adaptations.append({'sample_final_surface_an':surface_report})
  if job.get('probe_only'):
   assert hash_file(source)==before,'Immutable source changed during probe'
   (pathlib.Path(job['output']).parent/'SURFACE_PROBE_RECEIPT.json').write_text(json.dumps({'source_sha256':before,'pipeline':pipeline,'job':job,'adaptations':adaptations,'rendered':False,'scene_saved':False},indent=2))
   print('SURFACE_PROBE_TERMINAL',surface_report['fields_path'],flush=True)
   continue
 if job.get('refined_film_an'):
  config=job['refined_film_an']
  assert job.get('road_film_ownership_al') and job.get('contact_bank_continuity_al'),'AN requires complete AL supported ownership baseline'
  for name,expected in config['required_component_sha256'].items():
   assert pipeline['files'].get(name)==expected,'Sampled AN geometry source changed: '+name
  for key,expected in config['required_geometry_configuration'].items():
   assert job.get(key)==expected,'Sampled AN geometry settings changed: '+key
  sys.path.insert(0,pipeline['snapshot'])
  from apply_refined_film_an import apply as apply_current_film
  film_report=apply_current_film(s,config);adaptations.append({'refined_film_an':film_report})
  (pathlib.Path(job['output']).parent/'REFINED_FILM_AN.json').write_text(json.dumps(film_report,indent=2))
 if job.get('sediment_surface_ai'):
  assert job.get('graded_shoulder_ah'),'AI requires contemporaneous AH fields'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_sediment_surface_ai import apply as assemble_sediment
  sediment_report=assemble_sediment(s,job['sediment_surface_ai'],pathlib.Path(job['output']).parent);adaptations.append({'sediment_surface_ai':sediment_report})
  (pathlib.Path(job['output']).parent/'SEDIMENT_SURFACE_AI.json').write_text(json.dumps(sediment_report,indent=2))
 if job.get('fractured_boundary_ar'):
  assert job.get('continuous_contact_aq') and job.get('current_contact_film_aq'),'AR requires fresh complete contact and film audits'
  sys.path.insert(0,pipeline['snapshot'])
  from integrate_fracture_ar import apply as apply_fracture_ar
  report=apply_fracture_ar(s,job['fractured_boundary_ar'],pathlib.Path(job['output']).parent);adaptations.append({'fractured_boundary_ar':report})
  if job.get('stop_after_fracture_ar'):
   assert job.get('probe_only') and hash_file(source)==before,'AR probe must preserve source and never render'
   (pathlib.Path(job['output']).parent/'AR_GEOMETRY_PROBE.json').write_text(json.dumps({'source_sha256':before,'pipeline':pipeline,'job':job,'adaptations':adaptations,'rendered':False,'scene_saved':False,'contact_audit_pending':True},indent=2))
   print('AR_GEOMETRY_PROBE_TERMINAL',flush=True)
   continue
 if job.get('continuous_contact_aq'):
  sys.path.insert(0,pipeline['snapshot'])
  from continuous_contact_aq import apply as apply_contact_aq
  report=apply_contact_aq(s,job['continuous_contact_aq'],pathlib.Path(job['output']).parent);adaptations.append({'continuous_contact_aq':report})
  (pathlib.Path(job['output']).parent/'CONTINUOUS_CONTACT_AQ.json').write_text(json.dumps(report,indent=2))
 if job.get('road_margin_aq'):
  assert not job.get('road_margin_ap'),'Choose exactly one margin representation'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_road_margin_aq import apply as assemble_margin_aq
  report=assemble_margin_aq(s,job['road_margin_aq'],pathlib.Path(job['output']).parent);adaptations.append({'road_margin_aq':report})
  (pathlib.Path(job['output']).parent/'ROAD_MARGIN_AQ.json').write_text(json.dumps(report,indent=2))
 if job.get('current_contact_film_aq'):
  assert job.get('continuous_contact_aq'),'Recompute film only after final AQ contact'
  sys.path.insert(0,pipeline['snapshot'])
  from current_contact_film_aq import apply as apply_film_aq
  report=apply_film_aq(s,job['current_contact_film_aq'],pathlib.Path(job['output']).parent);adaptations.append({'current_contact_film_aq':report})
 if job.get('metric_fragments_as'):
  assert job.get('road_margin_aq'),'AS requires current AQ margin fields and actual geometry'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_metric_fragments_as import apply as assemble_fragments_as
  report=assemble_fragments_as(s,job['metric_fragments_as'],pathlib.Path(job['output']).parent);adaptations.append({'metric_fragments_as':report})
  (pathlib.Path(job['output']).parent/'METRIC_FRAGMENTS_AS.json').write_text(json.dumps(report,indent=2))
 if job.get('road_margin_ap'):
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_road_margin_ap import apply as assemble_road_margin
  margin_report=assemble_road_margin(s,job['road_margin_ap'],pathlib.Path(job['output']).parent);adaptations.append({'road_margin_ap':margin_report})
  (pathlib.Path(job['output']).parent/'ROAD_MARGIN_AP.json').write_text(json.dumps(margin_report,indent=2))
 if job.get('shoulder_context_ab'):
  assert not mapping_config,'AB diagnostic requires pinned local source inputs'
  sys.path.insert(0,pipeline['snapshot'])
  from assemble_shoulder_context_ab import apply as assemble_context
  context_report=assemble_context(s,job['shoulder_context_ab'],pathlib.Path(job['output']).parent);adaptations.append({'shoulder_context_ab':context_report})
  (pathlib.Path(job['output']).parent/'SHOULDER_CONTEXT_AB.json').write_text(json.dumps(context_report,indent=2))
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
 projection_resolution=[width,height]
 if job.get('assembled_scene_cache_av'):
  sys.path.insert(0,pipeline['snapshot'])
  from assembled_scene_cache_av import save as save_assembled_cache
  cache_report=save_assembled_cache(s,job['assembled_scene_cache_av'],source,before,pipeline,job,adaptations,image_dependencies())
  adaptations.append({'assembled_scene_cache_av':cache_report})
 cull_adaptation=camera_cull_dense_offscreen(job,s)
 if cull_adaptation:adaptations.append({'camera_cull_dense_offscreen':cull_adaptation})
 mip_adaptation=configure_asphalt_preview_mips(job)
 if mip_adaptation:adaptations.append({'asphalt_preview_mips':mip_adaptation})
 from preview_mesh_cull import apply as apply_preview_mesh_cull
 terrain_cull=apply_preview_mesh_cull(s,job)
 if terrain_cull:adaptations.append({'preview_terrain_cull':terrain_cull})
 from preview_mesh_cull import asphalt_lod
 if job.get('asphalt_context_grid_stride'):
  assert 'asphalt_preview_grid_stride' not in job,'Choose one explicit preview grid adapter'
  from asphalt_context_lod import asphalt_lod as context_asphalt_lod
  native_lod=context_asphalt_lod(s,job)
 else:native_lod=asphalt_lod(s,job)
 if native_lod:adaptations.append({'asphalt_preview_grid_lod':native_lod})
 if job.get('landform_candidate'):
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'src'))
  adapter=job['landform_candidate'].get('installation_adapter','integrate_landform_candidate')
  assert adapter in ('integrate_landform_candidate','integrate_faceted_landform_bs','integrate_faceted_landform_bs_float','integrate_faceted_landform_bt'),'Unqualified installation adapter'
  apply_landform_candidate=__import__(adapter,fromlist=['apply']).apply
  report=apply_landform_candidate(s,job['landform_candidate'],pathlib.Path(job['output']).parent)
  adaptations.append({'landform_candidate':report})
 if job.get('historical_fine_area_bw'):
  bw_path=pathlib.Path(pipeline['snapshot'])/'historical_fine_area_bw.py'
  bw_spec=importlib.util.spec_from_file_location('captured_historical_fine_area_bw',bw_path);bw=importlib.util.module_from_spec(bw_spec);bw_spec.loader.exec_module(bw)
  report=bw.apply(s,job['historical_fine_area_bw'],pathlib.Path(job['output']).parent);adaptations.append({'historical_fine_area_bw':report})
 if job.get('road_surface_wear_by'):
  sys.path.insert(0,pipeline['snapshot'])
  from road_surface_wear_by import apply as apply_road_surface_wear_by
  report=apply_road_surface_wear_by(s,job['road_surface_wear_by'],pathlib.Path(job['output']).parent);adaptations.append({'road_surface_wear_by':report})
 if job.get('discard_unused_render_data'):
  from discard_unused_render_data import apply as discard_unused_render_data
  released_data=discard_unused_render_data(s);adaptations.append({'discard_unused_render_data':released_data})
  print('UNUSED_RENDER_DATA_RELEASE',json.dumps(released_data),flush=True)
 border_capture=None
 if 'render_border' in job:
  bounds=job['render_border'];assert isinstance(bounds,(list,tuple)) and len(bounds)==4,'Border is [xmin,xmax,ymin,ymax] in normalized camera space'
  xmin,xmax,ymin,ymax=map(float,bounds);assert all(math.isfinite(v) for v in bounds) and 0<=xmin<xmax<=1 and 0<=ymin<ymax<=1,'Invalid camera border'
  # Exact pixel-grid bounds avoid ambiguous ceil/floor output dimensions.
  pixels=[xmin*width,xmax*width,ymin*height,ymax*height];assert all(abs(v-round(v))<1e-6 for v in pixels),'Border must align with native pixel edges'
  s.render.use_border=True;s.render.use_crop_to_border=True
  s.render.border_min_x=xmin;s.render.border_max_x=xmax;s.render.border_min_y=ymin;s.render.border_max_y=ymax
  width=round(pixels[1]-pixels[0]);height=round(pixels[3]-pixels[2]);assert width>0 and height>0
  border_capture={'full_projection_resolution':projection_resolution,'normalized_bounds':[xmin,xmax,ymin,ymax],'native_pixel_bounds_xy':pixels,'output_resolution':[width,height],'camera_geometry_material_scale_changed':False}
  adaptations.append({'native_render_border':border_capture,'scope':'Render crop at native pixel density; unchanged camera projection, no bitmap enlargement'})
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
 if job.get('release_unused_heap'):
  import gc,ctypes
  def current_rss_mib():
   for line in pathlib.Path('/proc/self/status').read_text().splitlines():
    if line.startswith('VmRSS:'):return int(line.split()[1])/1024
   return None
  prior_rss=current_rss_mib();collected=gc.collect();libc=ctypes.CDLL(None);trim=getattr(libc,'malloc_trim',None)
  trimmed=bool(trim(0)) if trim is not None else False
  after_rss=current_rss_mib();heap=dict(before_RSS_MiB=prior_rss,after_RSS_MiB=after_rss,gc_objects_collected=collected,malloc_trim_available=trim is not None,malloc_trim_released=trimmed,scope='Only unreferenced Python/C allocator pages; scene geometry, images, shaders and sampling untouched')
  adaptations.append({'released_unused_build_heap':heap});print('HEAP_RELEASE',json.dumps(heap),flush=True)
 if allocator_report:
  allocator_before_render=inspect_allocator(required=True);adaptations.append({'allocator_before_render_bx':allocator_before_render});print('ALLOCATOR_BEFORE_RENDER',json.dumps(allocator_before_render),flush=True)
 if curve_cache_adaptation or memory_adaptation:
  (out.parent/'PRE_RENDER_MEMORY_ADAPTATIONS.json').write_text(json.dumps({'source_sha256':before,'pipeline':pipeline,'curve_cache':curve_cache_adaptation,'compact_bvh':memory_adaptation,'all_adaptations':adaptations,'effective_capture':capture},indent=2))
 start=time.monotonic();bpy.ops.render.render(write_still=True);elapsed=time.monotonic()-start
 after=hash_file(source);assert after==before
 assert image_dependencies()==dependencies,'Image dependency changed during capture'
 if relocation:assert path_config.configuration_state()==mapping_state,'Path-map config or helper changed during capture'
 report={'job':job,'source_sha256':before,'render_seconds':elapsed,'engine':s.render.engine,'blender_version':bpy.app.version_string,'adaptations':adaptations,'camera':s.camera.name,'camera_location':list(s.camera.location),'camera_rotation':list(s.camera.rotation_euler),'missing_images':missing,'objects':len(s.objects),'resolution':[width,height],'guide_paths':guide_paths}
 report['display_settings']={k:getattr(s.view_settings,k) for k in ['view_transform','look','exposure','gamma']}
 report['projection_resolution']=projection_resolution;report['render_border']=border_capture
 report['pipeline']=pipeline;report['image_dependencies']=dependencies;report['effective_capture']=capture;report['frame']=s.frame_current;report['blender_build_hash']=bpy.app.build_hash.decode(errors='replace')
 report['guide_passes']=guide_passes
 if capture_mode(job)=='component-recombined':report['transport_paths']=transport_paths
 if s.render.engine=='BLENDER_WORKBENCH':report['workbench_settings']={'geometry_only':True,'render_aa':s.display.render_aa,'lighting':s.display.shading.light,'color_type':s.display.shading.color_type,'single_color':list(s.display.shading.single_color),'material_shaders_evaluated':False}
 if relocation:report['relocation']=relocation
 if slab_receipt:report['slab_studio']=slab_receipt
 out.with_suffix(out.suffix+'.json').write_text(json.dumps(report,indent=2));print('VIEW_COMPLETE '+str(out)+' '+str(round(elapsed,2))+' s',flush=True)
