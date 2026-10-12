import bpy, numpy as np, json, time, zlib, struct
from pathlib import Path
R=Path(__file__).resolve().parent
t=time.time();s=bpy.context.scene
s.render.engine='CYCLES';s.cycles.device='CPU';s.render.threads_mode='FIXED';s.render.threads=2;s.cycles.samples=1;s.cycles.use_adaptive_sampling=False;s.cycles.use_denoising=False;s.cycles.max_bounces=0;s.cycles.use_light_tree=False
s.cycles.pixel_filter_type='BOX';s.render.resolution_x=s.render.resolution_y=1024;s.render.resolution_percentage=100;s.render.film_transparent=True;s.render.use_compositing=True
s.view_settings.view_transform='Standard';s.view_settings.look='None';s.view_settings.exposure=0;s.view_settings.gamma=1
for o in s.objects:
 if o.type=='LIGHT':o.hide_render=True
if s.world and s.world.use_nodes:
 for n in s.world.node_tree.nodes:
  if n.type=='BACKGROUND':n.inputs['Strength'].default_value=0
cam=s.camera;cam.location=(0,0,.2);cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=.18;cam.data.clip_start=.001;cam.data.clip_end=1
vl=s.view_layers[0]
for a in list(vl.aovs):vl.aovs.remove(a)
for name in ('R5D_BaseColor','R5D_Roughness','R5D_Normal','R5D_Height'):
 a=vl.aovs.add();a.name=name;a.type='COLOR'
materials=[]
for m in bpy.data.materials:
 if not m.use_nodes:continue
 n=m.node_tree.nodes;l=m.node_tree.links;bs=next((q for q in n if q.type=='BSDF_PRINCIPLED'),None)
 if not bs:continue
 source={}
 for name,slot in [('R5D_BaseColor','Base Color'),('R5D_Roughness','Roughness')]:
  a=n.new('ShaderNodeOutputAOV');a.name=a.aov_name=name;p=bs.inputs[slot]
  if p.is_linked:l.new(p.links[0].from_socket,a.inputs['Color']);source[slot]=p.links[0].from_node.name+'.'+p.links[0].from_socket.name
  else:
   v=p.default_value;a.inputs['Color'].default_value=(v,v,v,1) if isinstance(v,float) else v;source[slot]=list(v) if not isinstance(v,float) else v
 geom=n.new('ShaderNodeNewGeometry');normal=bs.inputs['Normal'].links[0].from_socket if bs.inputs['Normal'].is_linked else geom.outputs['Normal']
 scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY_ADD';scale.inputs[1].default_value=(.5,.5,.5);scale.inputs[2].default_value=(.5,.5,.5);l.new(normal,scale.inputs[0]);a=n.new('ShaderNodeOutputAOV');a.name=a.aov_name='R5D_Normal';l.new(scale.outputs[0],a.inputs['Color'])
 sep=n.new('ShaderNodeSeparateXYZ');l.new(geom.outputs['Position'],sep.inputs[0]);a=n.new('ShaderNodeOutputAOV');a.name=a.aov_name='R5D_Height';l.new(sep.outputs['Z'],a.inputs['Color']);source['Normal']=normal.node.name+'.'+normal.name
 materials.append({'name':m.name,'source':source})
s.use_nodes=True;n=s.node_tree.nodes;l=s.node_tree.links;n.clear();rl=n.new('CompositorNodeRLayers');rl.layer=vl.name
out=n.new('CompositorNodeOutputFile');out.base_path=str(R);out.format.file_format='OPEN_EXR';out.format.color_mode='RGBA';out.format.color_depth='32';out.format.exr_codec='ZIP';out.file_slots.clear()
for name in ('R5D_BaseColor','R5D_Roughness','R5D_Normal','R5D_Height'):
 out.file_slots.new(name);l.new(rl.outputs[name],out.inputs[name])
print('BAKE_BEGIN',materials,flush=True);bpy.ops.render.render();print('BAKE_RENDER_DONE',time.time()-t,flush=True)
def png16(path,rgb):
 a=np.rint(np.clip(rgb,0,1)*65535).astype('>u2');h,w,c=a.shape
 def chunk(typ,data):return struct.pack('>I',len(data))+typ+data+struct.pack('>I',zlib.crc32(typ+data)&0xffffffff)
 raw=b''.join(b'\0'+row.tobytes() for row in a)
 path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,16,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b''))
stats={};arrays={}
for name in ('BaseColor','Roughness','Normal','Height'):
 path=R/('R5D_'+name+'0001.exr');im=bpy.data.images.load(str(path),check_existing=False);im.colorspace_settings.name='Non-Color';a=np.array(im.pixels[:],dtype=np.float32).reshape(1024,1024,4)[::-1,:,:3];arrays[name]=a
 stats[name]={'min':a.min(axis=(0,1)).tolist(),'max':a.max(axis=(0,1)).tolist(),'mean':a.mean(axis=(0,1)).tolist(),'std':a.std(axis=(0,1)).tolist(),'finite':bool(np.isfinite(a).all())}
 if name=='Height':np.save(R/'R5D_HeightState_m.npy',a[:,:,0])
 else:
  if name=='BaseColor':a=np.where(a<=.0031308,a*12.92,1.055*np.maximum(a,0)**(1/2.4)-.055)
  png16(R/('R5D_'+name+'.png'),a)
assert arrays['BaseColor'].std()>.01 and arrays['Roughness'].mean()>.1 and arrays['Normal'][:,:,2].mean()>.5
receipt={'source_blend':'discrete_grains_r5/preview/diagnostic_d.blend','source_blend_modified':False,'resolution':[1024,1024],'footprint_m':.18,'world_bounds_xy_m':[-.09,.09,-.09,.09],'pixel_size_m':.18/1024,'orientation':'PNG/numpy top row is world +Y, right is +X. UV (0,0) corresponds world (-0.09,-0.09); UV (1,1) is (+0.09,+0.09).','basecolor_encoding':'16bit RGB PNG, exact linear shader Base Color converted to sRGB transfer; load as sRGB. No lighting included.','roughness_encoding':'16bit RGB PNG repeated scalar, raw 0..1 data; load Non-Color.','normal_encoding':'16bit RGB PNG, world-space shaded normal including existing material Bump node; encoded RGB=0.5*N+0.5; load Non-Color, decode then normalize. Source objects untransformed so world and object axes coincide.','height_encoding':'float32 numpy physical world Z metres, top-row +Y. No normalization.','raw_linear_aovs':'32bit float RGBA EXR for all four maps','materials':materials,'stats':stats,'seconds':time.time()-t}
(R/'bake_receipt.json').write_text(json.dumps(receipt,indent=2));print('VERIFIED',json.dumps(receipt),flush=True)
