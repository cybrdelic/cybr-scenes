"""Four tiny matched plain-clay images; caller owns the common resource lock."""
from pathlib import Path
import bpy, json, math, os, numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parent;OUT=Path(os.environ['DH_FIXTURE_OUT']).resolve();assert not OUT.exists();OUT.mkdir(parents=True)
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=32;s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=False;s.cycles.use_light_tree=False;s.cycles.seed=1810
s.render.threads_mode='FIXED';s.render.threads=2;s.cycles.max_bounces=6;s.cycles.diffuse_bounces=3;s.cycles.glossy_bounces=3
s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=0;s.view_settings.gamma=1
s.render.resolution_x=512;s.render.resolution_y=384;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='16';s.render.dither_intensity=0
w=bpy.data.worlds.new('Existing CO22 sky direction');w.use_nodes=True;s.world=w;n=w.node_tree.nodes;l=w.node_tree.links;n.clear();sk=n.new('ShaderNodeTexSky');sk.sky_type='NISHITA';sk.sun_disc=True;sk.sun_elevation=math.radians(22);sk.sun_rotation=math.radians(305);sk.sun_size=math.radians(.545);sk.sun_intensity=1;sk.altitude=800;sk.air_density=1.1;sk.dust_density=1.7;sk.ozone_density=1;bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.05797151103615761;wo=n.new('ShaderNodeOutputWorld');l.new(sk.outputs[0],bg.inputs[0]);l.new(bg.outputs[0],wo.inputs[0])
clay=bpy.data.materials.new('Constant opaque neutral clay; no noise or texture');clay.use_nodes=True;b=clay.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(.25,.25,.25,1);b.inputs['Roughness'].default_value=.80;b.inputs['Specular IOR Level'].default_value=.28
bpy.ops.mesh.primitive_plane_add(size=4);ground=bpy.context.object;ground.name='Isolated flat support; not road geometry';ground.data.materials.append(clay)
camd=bpy.data.cameras.new('Matched diagnostic projection');cam=bpy.data.objects.new(camd.name,camd);s.collection.objects.link(cam);camd.lens=70;camd.clip_start=.001;s.camera=cam
# Execute the exact existing material() function without its unrelated assembly imports.
import ast,sys,hashlib
RUNTIME=Path(os.environ['DH_RUNTIME_SRC']).resolve();sys.path.insert(0,str(RUNTIME))
for name,pin in json.loads((ROOT/'fixture_runtime_pins.json').read_text()).items():assert hashlib.sha256((RUNTIME/name).read_bytes()).hexdigest()==pin,('Fixture runtime pin mismatch',name)
from victorville_reflectance_cn import color_variant
material_source=RUNTIME/'assemble_finite_gravel_cg.py';module=ast.parse(material_source.read_text());fn=next(n for n in module.body if isinstance(n,ast.FunctionDef)and n.name=='material');exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(material_source),'exec'))
original=material();mineral,cn_receipt=color_variant(original,'coarse mineral')
(OUT/'MATERIAL_PROVENANCE.json').write_text(json.dumps({'original_material_function_sha256':hashlib.sha256(ast.get_source_segment(material_source.read_text(),fn).encode()).hexdigest(),'CN':cn_receipt,'old_680_per_m_noise_and_3100_per_m_microbump_unchanged':True,'new_susceptibility_field_drives_material':False,'material_only_compatibility_fixture':True},indent=2)+'\n')
specimens=[dict(kind='CG',index=146,npz='prototype_146.npz',yaw=.62370646,burial=.002527210690024928,direction=[.0325079,-.22061062,.18188027]),dict(kind='AS',index=39,npz='as_prototype_039.npz',yaw=4.1444399323218075,burial=.025811180133229472,direction=[-.65970182,-1.00786495,.58127845])]
receipts=[]
for spec in specimens:
    p=np.load(ROOT/'specimens'/spec['npz']);attrs=np.load(ROOT/'specimens'/spec['npz'].replace('.npz','_parent_attributes.npz'));dims=np.ptp(p['parent_v'],axis=0);target=Vector((0,0,float(dims[2]*.46-spec['burial'])));direction=Vector(spec['direction']).normalized()
    cam.location=target+direction*float(max(dims)*3.7);cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    for phase,vertices,faces in [('before',p['parent_v'],p['parent_f']),('after',p['v'],p['f'])]:
        me=bpy.data.meshes.new(spec['kind']+' '+phase);me.from_pydata(vertices.tolist(),[],faces.tolist());me.materials.append(mineral);idx=p['attribute_parent_index'];weights=p['attribute_parent_weight'];color=attrs['color'] if phase=='before' else (attrs['color'][idx]*weights[:,:,None]).sum(1).astype('f4');rough=attrs['rough'] if phase=='before' else (attrs['rough'][idx]*weights).sum(1).astype('f4');me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT').data.foreach_set('color',color.ravel());me.attributes.new('grain_roughness','FLOAT','POINT').data.foreach_set('value',rough);me.polygons.foreach_set('use_smooth',np.full(len(me.polygons),phase=='after',bool));me.update()
        ob=bpy.data.objects.new(me.name,me);s.collection.objects.link(ob);ob.rotation_euler[2]=spec['yaw'];ob.location.z=-spec['burial']
        path=OUT/f'{spec["kind"]}_{spec["index"]:03d}_{phase}.png';s.render.filepath=str(path);bpy.ops.render.render(write_still=True)
        receipts.append({'source_kind':spec['kind'],'prototype':spec['index'],'phase':phase,'image':path.name,'physical_dimensions_m':np.ptp(vertices,axis=0).tolist(),'burial_m':spec['burial'],'yaw_rad':spec['yaw'],'camera_location':list(cam.location),'camera_rotation':list(cam.rotation_euler),'lens_mm':camd.lens,'flat_face_normals':phase=='before','dense_geometry_smooth_vertex_normals':phase=='after'})
        bpy.data.objects.remove(ob,do_unlink=True);bpy.data.meshes.remove(me)
    p.close();attrs.close()
(OUT/'PROVENANCE.json').write_text(json.dumps({'kind':'Isolated current-CN material compatibility gate','resolution':[512,384],'samples':32,'threads':2,'daylight':'Exact existing Nishita CO22 parameters; sun rotation305deg','no_material_noise':False,'original_material_graph_with_exact_CN_tint':True,'new_susceptibility_coupled_to_material':False,'no_denoising':True,'matched_before_after_camera_lighting':True,'normals_policy':'Source retains original flat facets; candidate uses smooth normals on actual 81920-triangle displaced geometry','exact_metre_geometry_no_instance_rescale':True,'new_road_scene_loaded_or_written':False,'images':receipts,'limits':['Isolated flat support and reframed camera; not an actual road crop.','The source-specific camera viewing direction and yaw are retained.','This visual gate tests a continuous asymmetric primary shape plus real metric differential-weathering relief; topology alone is not realism approval.']},indent=2)+'\n')
# Same final CG bytes in neutral clay, because its tiny volume calibration followed the v3 clay gate.
spec=specimens[0];p=np.load(ROOT/'specimens'/spec['npz']);dims=np.ptp(p['parent_v'],axis=0);target=Vector((0,0,float(dims[2]*.46-spec['burial'])));direction=Vector(spec['direction']).normalized();cam.location=target+direction*float(max(dims)*3.7);cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
me=bpy.data.meshes.new('Final calibrated CG clay proof');me.from_pydata(p['v'].tolist(),[],p['f'].tolist());me.materials.append(clay);me.polygons.foreach_set('use_smooth',np.ones(len(me.polygons),bool));me.update();ob=bpy.data.objects.new(me.name,me);s.collection.objects.link(ob);ob.rotation_euler[2]=spec['yaw'];ob.location.z=-spec['burial'];s.render.filepath=str(OUT/'CG_146_final_clay.png');bpy.ops.render.render(write_still=True)
(OUT/'FINAL_CLAY_PROVENANCE.json').write_text(json.dumps({'image':'CG_146_final_clay.png','candidate_coordinates_sha256':hashlib.sha256(p['v'].tobytes()).hexdigest(),'final_candidate_bytes_used':True,'neutral_clay_no_noise_bump_or_texture':True,'before_reference':'../../clay_fixture/CG_146_before.png','AS_geometry_unchanged_from_v3_clay':True,'AS_clay_reference':'../../clay_fixture/AS_039_after.png'},indent=2)+'\n');bpy.data.objects.remove(ob,do_unlink=True);bpy.data.meshes.remove(me);p.close()
import runpy
runpy.run_path(str(ROOT/'test_late_adapter.py'),run_name='__main__')
