"""Render actual admitted handler ASTs and RNA float32 native crop regressions.

blender -b -t 2 --python-exit-code 1 --python this.py --
  admitted-v1-render.py prepared-v2-render.py fresh-output
Uses unchanged full camera pixels, including the 394/1334 rounding failure.
"""
from pathlib import Path
import ast,sys,json,hashlib,math
import bpy,numpy as np
from mathutils import Vector
old,new,out=map(Path,sys.argv[sys.argv.index('--')+1:]);out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(new.parent.parent/'src'))

def handlers(path):
 tree=ast.parse(path.read_text())
 return [n for n in ast.walk(tree) if isinstance(n,ast.If) and (
  isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Constant) and n.test.left.value=='render_border' or
  isinstance(n.test,ast.BoolOp) and ast.unparse(n.test)=="'render_border' in job or 'render_border_pixels' in job")]
assert len(handlers(old))==1 and len(handlers(new))==1
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=4;s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=False;s.cycles.seed=0
s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='16';s.render.dither_intensity=0;s.view_settings.view_transform='Standard'
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=.55,location=(.05,0,.55));m=bpy.data.materials.new('fixed fixture material');m.diffuse_color=(.23,.38,.16,1);bpy.context.object.data.materials.append(m);bpy.ops.mesh.primitive_plane_add(size=20)
bpy.ops.object.camera_add(location=(1.3,-2.2,1.5));s.camera=bpy.context.object;s.camera.data.lens=48;s.camera.rotation_euler=(Vector((0,0,.4))-s.camera.location).to_track_quat('-Z','Y').to_euler();bpy.ops.object.light_add(type='SUN',rotation=(.7,-.4,-.6));bpy.context.object.data.energy=2.;s.world.color=(.15,.15,.15)
results={};arrays={}
def capture(tag,path,res,job):
 w,h=res;s.render.resolution_x=w;s.render.resolution_y=h;s.render.resolution_percentage=100;s.render.use_border=False;s.render.use_crop_to_border=False
 env={'job':job,'s':s,'math':math,'width':w,'height':h,'projection_resolution':[w,h],'adaptations':[],'border_capture':None}
 for node in handlers(path):exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),env)
 file=out/(tag+'.png');s.render.filepath=str(file);bpy.ops.render.render(write_still=True);im=bpy.data.images.load(str(file),check_existing=False);size=list(im.size[:]);a=np.asarray(im.pixels[:],dtype='f4').reshape(size[1],size[0],4)[:,:,:3].copy();bpy.data.images.remove(im)
 arrays[tag]=a;results[tag]={'observed_size':size,'requested_size':[env['width'],env['height']],'png_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'border':env['border_capture']}
 return a
capture('old_normal',old,[64,48],{});capture('fixed_normal',new,[64,48],{})
assert np.array_equal(arrays['old_normal'],arrays['fixed_normal'])
cases=[('small',[64,48],[8,41,7,34]),('near_edges',[97,89],[1,93,7,83]),('road_failure',[2000,1334],[800,1300,0,394]),('road_nonzero',[2000,1334],[801,1299,1,393])]
full={}
for name,res,bounds in cases:
 key=tuple(res)
 if key not in full:full[key]=capture(name+'_full',new,res,{})
 a=capture(name+'_integer',new,res,{'render_border_pixels':bounds});x0,x1,y0,y1=bounds
 assert list(a.shape[:2])==[y1-y0,x1-x0]
 assert np.array_equal(full[key][y0:y1,x0:x1],a),(name,'literal pixel mismatch')
 legacy=[v/n for v,n in zip(bounds,[res[0],res[0],res[1],res[1]])]
 b=capture(name+'_legacy',new,res,{'render_border':legacy})
 assert np.array_equal(a,b),(name,'legacy mismatch')
 if name=='road_failure':
  broken=capture('old_road_failure',old,res,{'render_border':legacy})
  assert results['old_road_failure']['observed_size']==[500,393]
  assert np.array_equal(broken,full[key][0:393,800:1300])
report={'renderer':'Blender '+bpy.app.version_string+' Cycles CPU','samples':4,
 'actual_admitted_handler_AST_executed':True,'old_vs_fixed_normal_RGB_exact':True,
 'fixed_native_crops_vs_full_literal_RGB_exact':True,'legacy_integer_API_RGB_exact':True,
 'old_394_over_1334_failure_reproduced':True,'images':results,
 'scope':'Actual native crop and float32 RNA regression; no scene appearance change or resampling.'}
(out/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n');print('NATIVE_PIXEL_BORDER_PASS',json.dumps(report),flush=True)
