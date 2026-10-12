"""Matched actual Cycles plant fixture. No terrain or road placement changes."""
from pathlib import Path
import bpy,numpy as np,sys,json,math,hashlib
from mathutils import Vector
import argparse
p=argparse.ArgumentParser();p.add_argument('--dr-runtime',required=True,type=Path);p.add_argument('--material-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
R=Path(__file__).resolve().parent;sys.path[:0]=[str(R),str(a.dr_runtime.resolve()/'pipeline')]
import coherent_shrub_cm as owner
from woody_form import geometry_from_owner
assert hashlib.sha256(Path(owner.__file__).read_bytes()).hexdigest()=='b309bedda2117358913f0a0c35d6b6cfbbb4d15489648a8610ec390b7998ad91'
pins=json.loads((R/'MATERIAL_DEPENDENCY.json').read_text());cfg={}
for key,row in zip(['bark_source','bark_profile'],pins['files']):
 file=a.material_root.resolve()/row['path'];assert hashlib.sha256(file.read_bytes()).hexdigest()==row['sha256'];cfg[key]=str(file);cfg[key+'_sha256']=row['sha256']
O=a.output.resolve();O.mkdir(exist_ok=False,parents=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=32;s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=False;s.render.resolution_x=700;s.render.resolution_y=700;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='16';s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.unit_settings.system='METRIC';s.unit_settings.scale_length=1.
collection=bpy.data.collections.new('Original owner recipe comparison');s.collection.children.link(collection);palette=owner.base._palette();seed=26101020+104729*3;baseline=owner.geometry(3,seed);candidate=geometry_from_owner(owner,3,seed)
a=baseline.object('CM exact baseline',collection,palette,{'family':'coherent_shrub_cm','nominal_height_m':owner.SPECS[3].height,**baseline.cm_stats});b=candidate.object('DV candidate',collection,palette,{'family':'woody_form_dv','nominal_height_m':owner.SPECS[3].height,**candidate.cm_stats})
from wood_surface import install
candidate_bark=palette[0].copy();candidate_bark.name='DV original opt-in wood surface';b.data.materials[0]=candidate_bark;surface_report=install(candidate_bark,cfg)
for ob in [a,b]:ob.hide_viewport=False;ob.hide_render=False
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0));plane=bpy.context.object;mat=bpy.data.materials.new('Same neutral ground');mat.use_nodes=True;p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(.27,.19,.11,1);p.inputs['Roughness'].default_value=.85;plane.data.materials.append(mat)
bpy.ops.object.camera_add(location=(.81,-1.16,.58));s.camera=bpy.context.object;s.camera.rotation_euler=(Vector((0,0,.29))-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.lens=46;s.camera.data.clip_start=.001
bpy.ops.object.light_add(type='SUN',rotation=(math.radians(38),math.radians(-24),math.radians(-35)));bpy.context.object.data.energy=3.;bpy.context.object.data.angle=math.radians(.53)
s.world=bpy.data.worlds.new('Fixed fixture daylight');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.65,.75,1.,1);s.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.22
for view in ['whole','basal']:
 if view=='basal':
  s.render.resolution_x=600;s.render.resolution_y=480;s.camera.location=(.24,-.34,.14);s.camera.rotation_euler=(Vector((0,0,.077))-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.lens=63
 for label,ob in [('baseline',a),('candidate',b)]:
  a.hide_render=ob!=a;b.hide_render=ob!=b;s.render.filepath=str(O/(view+'_'+label+'.png'));bpy.ops.render.render(write_still=True)
report={'renderer':'Blender '+bpy.app.version_string+' Cycles CPU','samples':32,'owner_source_sha256':hashlib.sha256(Path(owner.__file__).read_bytes()).hexdigest(),'candidate_source_sha256':hashlib.sha256((R/'woody_form.py').read_bytes()).hexdigest(),'baseline':baseline.cm_stats,'candidate':candidate.cm_stats,'baseline_vertices':len(baseline.vertices),'candidate_vertices':len(candidate.vertices),'same_original_palette':True,'candidate_bark_shader':surface_report,'same_camera_lights_between_comparisons':True,'instance_transforms_changed':False,'candidate_extent_m':np.ptp(candidate.vertices,axis=0).tolist(),'baseline_extent_m':np.ptp(baseline.vertices,axis=0).tolist(),'qualification':'Isolated geometry test only. No road-view acceptance or complete fused branch union proof.'};(O/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
