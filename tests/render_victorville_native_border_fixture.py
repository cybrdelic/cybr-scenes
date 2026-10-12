"""Actual Cycles regression for the admitted pipeline native-border adapter.

Usage: blender -b -t 2 --python-exit-code 1 --python this.py --
    old-render.py fixed-render.py fresh-output
This extracts and executes the actual admitted handler AST, not a copy of the
crop calculation. The old normal path, fixed normal path and fixed native crop
are all rendered. Full scene geometry/appearance is outside this tiny test.
"""
from pathlib import Path
import ast,sys,json,hashlib,math
import bpy,numpy as np
from mathutils import Vector
old,new,out=map(Path,sys.argv[sys.argv.index('--')+1:]);out.mkdir(parents=True,exist_ok=False)
def handlers(path):
 tree=ast.parse(path.read_text());nodes=[n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Constant) and n.test.left.value=='render_border' and len(n.test.ops)==1 and isinstance(n.test.ops[0],ast.In)];return sorted(nodes,key=lambda n:n.lineno)
assert len(handlers(old))==2 and len(handlers(new))==1
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=16;s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=False;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='16';s.render.dither_intensity=0;s.view_settings.view_transform='Standard'
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=.55,location=(.05,0,.55));m=bpy.data.materials.new('fixed fixture material');m.diffuse_color=(.23,.38,.16,1);bpy.context.object.data.materials.append(m);bpy.ops.mesh.primitive_plane_add(size=20)
bpy.ops.object.camera_add(location=(1.3,-2.2,1.5));s.camera=bpy.context.object;s.camera.data.lens=48;s.camera.rotation_euler=(Vector((0,0,.4))-s.camera.location).to_track_quat('-Z','Y').to_euler();bpy.ops.object.light_add(type='SUN',rotation=(.7,-.4,-.6));bpy.context.object.data.energy=2.;s.world.color=(.15,.15,.15)
results={};arrays={}
for tag,path,border in [('old_normal',old,None),('fixed_normal',new,None),('fixed_crop',new,[8/64,41/64,7/48,34/48])]:
 s.render.resolution_x=64;s.render.resolution_y=48;s.render.resolution_percentage=100;s.render.use_border=False;s.render.use_crop_to_border=False
 env={'job':{} if border is None else {'render_border':border},'s':s,'math':math,'width':64,'height':48,'projection_resolution':[64,48],'adaptations':[],'border_capture':None}
 for node in handlers(path):exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),env)
 expected=(64,48) if border is None else (33,27);assert (env['width'],env['height'])==expected
 file=out/(tag+'.png');s.render.filepath=str(file);bpy.ops.render.render(write_still=True);im=bpy.data.images.load(str(file),check_existing=False);assert tuple(im.size[:])==expected;arrays[tag]=np.asarray(im.pixels[:]).reshape(expected[1],expected[0],4)[:,:,:3];results[tag]={'size':list(expected),'png_sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
assert np.array_equal(arrays['old_normal'],arrays['fixed_normal'])
assert np.array_equal(arrays['fixed_normal'][7:34,8:41],arrays['fixed_crop'])
report={'renderer':'Blender '+bpy.app.version_string+' Cycles CPU','samples':16,'actual_admitted_handler_AST_executed':True,'old_vs_fixed_normal_RGB_exact':True,'fixed_native_crop_vs_full_RGB_exact':True,'crop_edges_bottom_origin':[8,41,7,34],'images':results,'scope':'Tiny native-border regression; full normal DU5 render remains separately qualified.'};(out/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n');print('NATIVE_BORDER_REGRESSION_PASS',json.dumps(report))
