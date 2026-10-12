"""R5 bounded diagnostic: disconnected mineral particles, separate fines.
All dimensions metres. Source is procedural, no image or scan input.
"""
import bpy, numpy as np, math, json, time
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1]; rng=np.random.default_rng(501809)
t0=time.time(); bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene
s.unit_settings.system='METRIC';s.render.engine='CYCLES';s.cycles.device='CPU';s.render.threads_mode='FIXED';s.render.threads=2;s.cycles.samples=48;s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=False;s.cycles.use_light_tree=False;s.cycles.seed=1810;s.cycles.max_bounces=6;s.cycles.diffuse_bounces=3;s.cycles.glossy_bounces=3
s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=0;s.view_settings.gamma=1
s.render.resolution_x=800;s.render.resolution_y=640;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='16'
w=bpy.data.worlds.new('Analytic daylight');w.use_nodes=True;s.world=w;n=w.node_tree.nodes;l=w.node_tree.links;n.clear();sky=n.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_disc=False;sky.sun_elevation=math.radians(34);sky.sun_rotation=math.radians(225);sky.altitude=800;sky.dust_density=1.2;bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.07;out=n.new('ShaderNodeOutputWorld');l.new(sky.outputs[0],bg.inputs[0]);l.new(bg.outputs[0],out.inputs[0]);ld=bpy.data.lights.new('Sun','SUN');ld.energy=4.2;ld.angle=math.radians(.55);ld.color=(1,.96,.88);o=bpy.data.objects.new('Sun',ld);s.collection.objects.link(o);o.rotation_euler=(math.radians(56),0,math.radians(-135))

def noise(x,y,scale,seed=0):
 u=x/scale;v=y/scale;i=np.floor(u);j=np.floor(v);fx=u-i;fy=v-j;fx=fx*fx*(3-2*fx);fy=fy*fy*(3-2*fy)
 def h(a,b):
  q=np.sin(a*127.1+b*311.7+seed*17.37)*43758.5453123;return(q-np.floor(q))*2-1
 return (h(i,j)*(1-fx)+h(i+1,j)*fx)*(1-fy)+(h(i,j+1)*(1-fx)+h(i+1,j+1)*fx)*fy

def deposit(x,y):
 # Coherent sinuous sorting ribbon and adjacent compacted strip, in centimetres.
 return np.clip(.46+.32*noise(x,y,.031,8)+.16*noise(x,y,.008,28),.07,.94)
def ground(x,y):
 return .00009*noise(x,y,.031,5)+.000035*noise(x,y,.0035,6)

def material(name,grains=False):
 m=bpy.data.materials.new(name);m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF');bs.inputs['IOR'].default_value=1.48
 geom=n.new('ShaderNodeNewGeometry');noise1=n.new('ShaderNodeTexNoise');noise1.inputs['Scale'].default_value=5100 if grains else 9200;noise1.inputs['Detail'].default_value=2;noise1.inputs['Roughness'].default_value=.7;l.new(geom.outputs['Position'],noise1.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000045 if grains else .000015;bump.inputs['Strength'].default_value=.6;l.new(noise1.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
 if grains:
  a=n.new('ShaderNodeAttribute');a.attribute_name='mineral';mn=n.new('ShaderNodeTexNoise');l.new(geom.outputs['Position'],mn.inputs['Vector']);mn.inputs['Scale'].default_value=3200;mn.inputs['Detail'].default_value=3;mn.inputs['Roughness'].default_value=.76;cr=n.new('ShaderNodeValToRGB');cr.color_ramp.elements[0].position=.20;cr.color_ramp.elements[0].color=(.52,.55,.61,1);cr.color_ramp.elements[1].position=.74;cr.color_ramp.elements[1].color=(1.27,1.23,1.14,1);l.new(mn.outputs['Fac'],cr.inputs[0]);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;l.new(a.outputs['Color'],mix.inputs[1]);l.new(cr.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color']);r=n.new('ShaderNodeAttribute');r.attribute_name='grain_roughness';l.new(r.outputs['Fac'],bs.inputs['Roughness'])
 else:
  a=n.new('ShaderNodeAttribute');a.attribute_name='sediment';l.new(a.outputs['Color'],bs.inputs['Base Color']);bs.inputs['Roughness'].default_value=.84
 return m

def mesh(name,v,f,colors,rough=None):
 me=bpy.data.meshes.new(name);me.vertices.add(len(v));me.vertices.foreach_set('co',np.asarray(v,dtype='f4').ravel());ff=np.asarray(f,dtype='i4');me.loops.add(ff.size);me.loops.foreach_set('vertex_index',ff.ravel());me.polygons.add(len(ff));me.polygons.foreach_set('loop_start',np.arange(len(ff),dtype='i4')*ff.shape[1]);me.polygons.foreach_set('loop_total',np.full(len(ff),ff.shape[1],dtype='i4'));me.polygons.foreach_set('use_smooth',np.zeros(len(ff),dtype=bool));me.update()
 c=me.color_attributes.new(name='mineral' if rough is not None else 'sediment',type='FLOAT_COLOR',domain='POINT');c.data.foreach_set('color',np.asarray(colors,dtype='f4').ravel())
 if rough is not None:
  a=me.attributes.new('grain_roughness','FLOAT','POINT');a.data.foreach_set('value',np.asarray(rough,dtype='f4'));pid=me.attributes.new('particle_id','INT','POINT');pid.data.foreach_set('value',np.asarray(particle_ids,dtype='i4'))
 me.materials.append(material(name,rough is not None));o=bpy.data.objects.new(name,me);s.collection.objects.link(o);return o
# Real fines surface at0.2mm sampling, no unified stone height displacement.
microbed=np.load(R/'prototypes/microbed.npz');N=microbed['height'].shape[0];side=.18;axis=np.linspace(-side/2,side/2,N);xx,yy=np.meshgrid(axis,axis);zz=ground(xx,yy)+microbed['height']*(.65+.55*(1-deposit(xx,yy)))
v=np.stack((xx,yy,zz),-1).reshape(-1,3);q=(np.arange(N-1)[:,None]*N+np.arange(N-1)[None,:]).ravel();f=np.stack((q,q+1,q+N+1,q+N),1);col=np.ones((N*N,4),dtype='f4');dep=deposit(xx,yy).ravel();var=noise(xx,yy,.003,12).ravel();col[:,:3]=microbed['color'].reshape(-1,3)*(1+var[:,None]*.06)+dep[:,None]*np.array([.013,.010,.006]);o=mesh('Compacted sandy fines / separate substrate',v,f,col);o.data.polygons.foreach_set('use_smooth',np.ones(len(f),dtype=bool));del v,f,col,xx,yy,zz
# Hierarchical random sequential packing: coarse fragments first, smaller grains
# fill spaces without overlapping their projected footprints. Circles are only
# the conservative placement bounds; rendered particles have irregular polygons.
cell=.00009;gridN=int(np.ceil(side/cell));occ=np.zeros((gridN,gridN),dtype=np.uint8)
particles=[];counts=[]
for band,attempts,lo,hi in [('chips',800,.0016,.0058),('grit',24000,.0006,.0019),('sand',200000,.00016,.00064)]:
 count=0
 for k in range(attempts):
  x,y=rng.uniform(-side/2+.003,side/2-.003,2);dep=float(deposit(x,y));prob=(.10+.92*(1-dep)**1.8) if band=='chips' else ((.26+.78*(1-dep)) if band=='grit' else (.30+.83*dep))
  if rng.random()>prob:continue
  diameter=float(np.exp(rng.uniform(np.log(lo),np.log(hi))));r=diameter/2
  ix=int((x+side/2)/cell);iy=int((y+side/2)/cell);rpx=max(1,int(math.ceil(r*.83/cell)));x0=max(0,ix-rpx);x1=min(gridN,ix+rpx+1);y0=max(0,iy-rpx);y1=min(gridN,iy+rpx+1)
  gy,gx=np.ogrid[y0:y1,x0:x1];mask=(gx-ix)**2+(gy-iy)**2<(r*.83/cell)**2
  if np.any(occ[y0:y1,x0:x1][mask]):continue
  occ[y0:y1,x0:x1][mask]=1;particles.append((x,y,diameter,dep,band));count+=1
 counts.append([band,count,lo,hi]);print('PACKED',counts[-1],flush=True)
# Bounded angular chips with real side walls and narrow fracture bevels.
# Each particle has independent mineral/color/roughness; no blanket recoloring.
verts=[];faces=[];colors=[];roughness=[];particle_ids=[];palette=np.array([[.56,.53,.45],[.39,.315,.225],[.265,.205,.135],[.145,.163,.154],[.49,.385,.26],[.165,.108,.062],[.34,.34,.31]])
prototypes=json.loads((R/'prototypes/fracture_solids.json').read_text())
for particle_id,(x,y,d,dep,band) in enumerate(particles):
 proto=prototypes[int(rng.integers(0,len(prototypes)))];fine=d<.0009
 local=np.array(proto['fine_vertices' if fine else 'vertices']);fs=proto['fine_faces' if fine else 'faces']
 aspect=rng.uniform(.20,.50) if rng.random()<.20 else rng.uniform(.53,1.0)
 local[:,0]*=d;local[:,1]*=d*aspect
 thick=d*rng.uniform(.22,.61) if band=='chips' else d*rng.uniform(.38,.83)
 burial=np.clip(.34+dep*.46+rng.uniform(-.15,.14),.15,.85)
 z0=float(ground(x,y))-thick*burial;local[:,2]*=thick
 theta=rng.uniform(0,math.tau);rot=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]]);local[:,:2]=local[:,:2]@rot.T
 # Extra random lean avoids all fractured solids sharing upright extrusion axes.
 local[:,:2]+=(local[:,2]-thick*.5)[:,None]*rng.normal(0,.18,2)
 local+=np.array([x,y,z0]);off=len(verts);verts.extend(local.tolist());faces.extend(tuple(off+k for k in face) for face in fs)
 mineral=int(rng.choice(len(palette),p=[.23,.23,.19,.08,.11,.07,.09]));base=palette[mineral]*rng.uniform(.83,1.17);dust=np.array([.29,.231,.16]);coating=rng.uniform(.01,.12)+dep*.07
 cc=np.ones((len(local),4));rr=np.ones(len(local));r0=(.48 if mineral in(0,4) else .67)+rng.uniform(-.09,.08)
 for j in range(len(local)):
  coat=np.clip(coating+(1-np.clip((local[j,2]-z0)/thick,0,1))*.30,0,.65);cc[j,:3]=base*(1-coat)+dust*coat;rr[j]=min(.91,r0+coat*.2)
 colors.extend(cc.tolist());roughness.extend(rr.tolist());particle_ids.extend([particle_id]*len(local))
print('MESH',len(verts),len(faces),flush=True);mesh('Discrete angular sand grit and fragments',verts,faces,colors,roughness)
cd=bpy.data.cameras.new('Diagnostic10cm crop');cam=bpy.data.objects.new(cd.name,cd);s.collection.objects.link(cam);s.camera=cam;cam.location=(.023,-.126,.141);target=Vector((0,0,0));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cd.type='ORTHO';cd.ortho_scale=.105;cd.clip_start=.001;cd.clip_end=10
receipt=dict(version='R5D fractured mineral grains and compacted microbed',seed=501809,extent_m=side,frame_width_m=.105,representation='separate bounded particle meshes and fines substrate',bands=counts,particle_count=len(particles),particle_vertices=len(verts),particle_triangles=len(faces),occupied_conservative_mask_fraction=float(occ.mean()),note='One diagnostic only. No road context rebuilt. No site reconstruction claim.',build_seconds=time.time()-t0)
(R/'receipts/geometry_d.json').write_text(json.dumps(receipt,indent=2));s.render.filepath=str(R/'deliverables/CYBR_Victorville_R5D_Mineral_Microbed_Diagnostic.png');bpy.ops.wm.save_as_mainfile(filepath=str(R/'preview/diagnostic_d.blend'));print('BUILT',receipt,flush=True)
