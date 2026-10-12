"""Illustrative high-desert road scene. Reuses immutable source material maps.
No scans, photograph maps or image generation. World coordinates are metres.
"""
import bpy, math, sys, json, hashlib, random, os
import numpy as np
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT.parents[1]
GROUND=ROOT.parent/'far_road_r5d/bake'
ASPHALT=ROOT.parent/'discrete_grains_r5/asphalt/native4096'
MODE=sys.argv[sys.argv.index('--')+1] if '--' in sys.argv else 'overview'
RES=int(sys.argv[sys.argv.index('--')+2]) if '--' in sys.argv and len(sys.argv)>sys.argv.index('--')+2 else 768
SAMPLES=int(sys.argv[sys.argv.index('--')+3]) if '--' in sys.argv and len(sys.argv)>sys.argv.index('--')+3 else 32
bpy.ops.wm.read_factory_settings(use_empty=True)
s=bpy.context.scene;s.unit_settings.system='METRIC';s.unit_settings.scale_length=1
s.render.engine='CYCLES';s.cycles.device='CPU';s.render.threads_mode='FIXED';s.render.threads=2;s.cycles.samples=SAMPLES;s.cycles.use_denoising=False;s.cycles.use_adaptive_sampling=False;s.cycles.use_light_tree=False;s.cycles.seed=1810;s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=4;s.cycles.sample_clamp_indirect=10
s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=0;s.view_settings.gamma=1
s.render.resolution_x=RES;s.render.resolution_y=round(RES*2/3);s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='8'
world=bpy.data.worlds.new('Daylight / analytic high-desert sky');world.use_nodes=True;s.world=world;wn=world.node_tree.nodes;wl=world.node_tree.links;wn.clear();sky=wn.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_disc=False;sky.sun_elevation=math.radians(34);sky.sun_rotation=math.radians(225);sky.altitude=800;sky.air_density=1.1;sky.dust_density=1.7;sky.ozone_density=1;bg=wn.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.11;wo=wn.new('ShaderNodeOutputWorld');wl.new(sky.outputs['Color'],bg.inputs['Color']);wl.new(bg.outputs[0],wo.inputs[0])
ld=bpy.data.lights.new('Daylight / sun','SUN');ld.energy=3.4;ld.angle=math.radians(.75);ld.color=(1,.97,.90);sun=bpy.data.objects.new(ld.name,ld);s.collection.objects.link(sun);sun.rotation_euler=(math.radians(56),0,math.radians(-135))
# Shared image fields are read only. Physically fixed0.25m repeats, no UV stretching.
m=bpy.data.materials.new('Road / Approved R5D soil + original dense asphalt');m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;n.clear()
def node(t,name):q=n.new(t);q.name=name;return q
def mathnode(op,a,b=None):q=node('ShaderNodeMath',op);q.operation=op;l.new(a,q.inputs[0]) if hasattr(a,'node') else setattr(q.inputs[0],'default_value',a);l.new(b,q.inputs[1]) if hasattr(b,'node') else setattr(q.inputs[1],'default_value',b if b is not None else 0);return q.outputs[0]
def vec(op,a,b=None,scale=None):q=node('ShaderNodeVectorMath',op);q.operation=op;l.new(a,q.inputs[0]) if hasattr(a,'node') else setattr(q.inputs[0],'default_value',a);l.new(b,q.inputs[1]) if hasattr(b,'node') else setattr(q.inputs[1],'default_value',b if b is not None else (0,0,0));setattr(q.inputs['Scale'],'default_value',scale) if scale is not None else None;return q.outputs['Vector']
def ramp(inp,low,hi):q=node('ShaderNodeMapRange','Bounded edge mask');q.clamp=True;q.interpolation_type='SMOOTHERSTEP';l.new(inp,q.inputs['Value']);q.inputs['From Min'].default_value=low;q.inputs['From Max'].default_value=hi;return q.outputs['Result']
def mix(a,b,f):q=node('ShaderNodeMixRGB','Linked field blend');l.new(f,q.inputs[0]) if hasattr(f,'node') else setattr(q.inputs[0],'default_value',f);l.new(a,q.inputs[1]) if hasattr(a,'node') else setattr(q.inputs[1],'default_value',a);l.new(b,q.inputs[2]) if hasattr(b,'node') else setattr(q.inputs[2],'default_value',b);return q.outputs[0]
geo=node('ShaderNodeNewGeometry','World surface geometry');pos=geo.outputs['Position'];uv=vec('SCALE',pos,scale=4);separate=node('ShaderNodeSeparateXYZ','World metres');l.new(pos,separate.inputs[0]);absx=mathnode('ABSOLUTE',separate.outputs['X']);edge=mathnode('SUBTRACT',3.2,absx)
noise=node('ShaderNodeTexNoise','Irregular centimetre-scale road edge');l.new(pos,noise.inputs['Vector']);noise.inputs['Scale'].default_value=19;noise.inputs['Detail'].default_value=3;noise.inputs['Roughness'].default_value=.72
edge=mathnode('ADD',edge,mathnode('MULTIPLY',mathnode('SUBTRACT',noise.outputs['Fac'],.5),.12))
chipped=ramp(edge,-.016,.024)
patch=node('ShaderNodeTexNoise','Uneven shoulder dust incursions');l.new(pos,patch.inputs['Vector']);patch.inputs['Scale'].default_value=2.8;patch.inputs['Detail'].default_value=3
inset=mathnode('ADD',edge,mathnode('MULTIPLY',mathnode('SUBTRACT',patch.outputs['Fac'],.5),.22));clean=ramp(inset,.015,.29);asphaltshare=mathnode('MULTIPLY',chipped,mathnode('ADD',.28,mathnode('MULTIPLY',clean,.72)))
def scale_by(v,k):
 q=node('ShaderNodeVectorMath','Metric slope scale');q.operation='SCALE';l.new(v,q.inputs[0]);l.new(k,q.inputs['Scale']);return q.outputs['Vector']

def imagefield(directory,filename,space):
 if directory!=GROUND:
  q=node('ShaderNodeTexImage','Approved original asphalt / '+filename);q.image=bpy.data.images.load(str(directory/filename));q.image.colorspace_settings.name=space;q.image.pack();q.extension='REPEAT';q.interpolation='Linear';l.new(vec('SCALE',pos,scale=4),q.inputs['Vector']);return q.outputs['Color']
 aliases={'BaseColor.png':'R5D_BaseColor.png','Roughness.png':'R5D_Roughness.png','Normal_Object_RGB16.png':'R5D_Normal.png'}
 img=bpy.data.images.get(aliases[filename]) or bpy.data.images.load(str(GROUND/aliases[filename]));img.colorspace_settings.name=space;img.pack()
 # Stochastic four-neighbour texture synthesis for distant, subpixel grains.
 # Rotations and offsets preserve the0.18m material scale; no global repeat.
 lattice=vec('SCALE',pos,scale=1/.27);cell=vec('FLOOR',lattice);fract=vec('FRACTION',lattice);sep=node('ShaderNodeSeparateXYZ','LOD cell fractions');l.new(fract,sep.inputs[0]);fx=ramp(sep.outputs['X'],.44,.56);fy=ramp(sep.outputs['Y'],.44,.56);total=None
 for i,j in [(0,0),(1,0),(0,1),(1,1)]:
  anchor=vec('ADD',cell,(i,j,0));rand=node('ShaderNodeTexWhiteNoise','World-cell immutable offsets');rand.noise_dimensions='3D';l.new(anchor,rand.inputs['Vector']);ang=mathnode('MULTIPLY',rand.outputs['Value'],math.tau)
  rotate=node('ShaderNodeVectorRotate','Metric tile rotation');rotate.rotation_type='AXIS_ANGLE';rotate.inputs['Axis'].default_value=(0,0,1);l.new(vec('SCALE',pos,scale=1/.18),rotate.inputs['Vector']);l.new(ang,rotate.inputs['Angle']);uv=vec('ADD',rotate.outputs[0],vec('SCALE',rand.outputs['Color'],scale=17.31))
  q=node('ShaderNodeTexImage','Approved R5D distance LOD / '+filename);q.image=img;q.extension='REPEAT';q.interpolation='Linear';l.new(uv,q.inputs['Vector']);v=q.outputs['Color']
  if filename.startswith('Normal'):
   nr=node('ShaderNodeVectorRotate','Rotate full normal back to world');nr.rotation_type='AXIS_ANGLE';nr.inputs['Axis'].default_value=(0,0,1);l.new(vec('SUBTRACT',vec('SCALE',v,scale=2),(1,1,1)),nr.inputs['Vector']);l.new(mathnode('MULTIPLY',ang,-1),nr.inputs['Angle']);v=nr.outputs[0]
  wx=fx if i else mathnode('SUBTRACT',1,fx);wy=fy if j else mathnode('SUBTRACT',1,fy);w=mathnode('MULTIPLY',wx,wy);v=scale_by(v,w);total=v if total is None else vec('ADD',total,v)
 if filename.startswith('Normal'):total=vec('SCALE',vec('ADD',vec('NORMALIZE',total),(1,1,1)),scale=.5)
 return total
# Shared geometry/material ownership mask. CPU vertices and shader use one field.
shareattr=node('ShaderNodeAttribute','Coupled dust-and-asphalt ownership');shareattr.attribute_name='asphalt_share';asphaltshare=shareattr.outputs['Fac']
color=[];rough=[];norm=[]
for d in (GROUND,ASPHALT):
 color.append(imagefield(d,'BaseColor.png','sRGB'));rough.append(imagefield(d,'Roughness.png','Non-Color'));raw=imagefield(d,'Normal_Object_RGB16.png','Non-Color');norm.append(vec('SUBTRACT',vec('SCALE',raw,scale=2),(1,1,1)))
# Input normal maps encode full planar relief. Scene mesh carries ONLY broad
# terrain/camber, so add that broad slope once rather than double-counting it.
def slopes(v):
 split=node('ShaderNodeSeparateXYZ','Normal slope denominator');l.new(v,split.inputs[0]);denom=mathnode('MAXIMUM',split.outputs['Z'],.04);return scale_by(v,mathnode('DIVIDE',1,denom))
macroattr=node('ShaderNodeAttribute','Broad terrain normal only');macroattr.attribute_name='terrain_normal'
micronormal=vec('ADD',scale_by(slopes(norm[0]),mathnode('SUBTRACT',1,asphaltshare)),scale_by(slopes(norm[1]),asphaltshare));fullnormal=vec('NORMALIZE',vec('SUBTRACT',vec('ADD',micronormal,slopes(geo.outputs['Normal'])),(0,0,1)))
bs=node('ShaderNodeBsdfPrincipled','Linked dry dielectric');base=mix(color[0],color[1],asphaltshare); tint=node('ShaderNodeAttribute','Deposits and pavement wear at physical scene scale');tint.attribute_name='macro_tint';mul=node('ShaderNodeMixRGB','Scene mineral and oxidation variation');mul.blend_type='MULTIPLY';mul.inputs[0].default_value=1;l.new(base,mul.inputs[1]);l.new(tint.outputs['Color'],mul.inputs[2]);l.new(mul.outputs[0],bs.inputs['Base Color']);l.new(mix(rough[0],rough[1],asphaltshare),bs.inputs['Roughness']);l.new(fullnormal,bs.inputs['Normal']);bs.inputs['IOR'].default_value=1.5;out=node('ShaderNodeOutputMaterial','Surface');l.new(bs.outputs[0],out.inputs[0])
# R6 scene earthworks, kilometre-scale context and projected-footprint LOD.
def field(x,y,spacing,seed):
 u=np.asarray(x)/spacing;v=np.asarray(y)/spacing;i=np.floor(u);j=np.floor(v);fx=u-i;fy=v-j;fx=fx*fx*(3-2*fx);fy=fy*fy*(3-2*fy)
 def h(a,b):
  q=np.sin(a*127.1+b*311.7+seed*17.37)*43758.5453123;return(q-np.floor(q))*2-1
 return(h(i,j)*(1-fx)+h(i+1,j)*fx)*(1-fy)+(h(i,j+1)*(1-fx)+h(i+1,j+1)*fx)*fy

def grade(y):
 y=np.asarray(y);return .003*y+1.2*np.exp(-((y-105)/85)**2)-1.2*np.exp(-(105/85)**2)+.55*np.exp(-((y-430)/150)**2)
def edge_y(y,sign):
 return sign*(3.2+.023*field(0,y,.34,41+sign)+.013*field(0,y,.083,51+sign)-.065*np.maximum(field(0,y,2.1,81+sign)-.27,0))
def road_z(x,y):return grade(y)+.07+.064*(1-np.minimum(np.sqrt(np.asarray(x)**2+.02**2)/3.2,1))
def wash(x,y):
 ax=np.abs(x);side=np.sign(x);center=7.4+1.4*field(0,y,18,42)+.021*y
 main=np.exp(-((ax-center)/(1.0+.014*np.maximum(y,0)))**2)*(.55+.45*field(x,y,22,44))
 branchcenter=10.5+.12*(y-35)+1.5*field(0,y,21,43)
 branch=np.exp(-((ax-branchcenter)/.85)**2)*np.exp(-((y-35)/40)**2)
 return np.clip(main+branch*.7,0,1)
def terrain(x,y):
 ax=np.abs(x);d=ax-3.2;fade=np.clip((d-.8)/2.1,0,1);fade=fade*fade*(3-2*fade)
 # worked strip falls outward, then opens into irregular alluvial drainage.
 near=grade(y)+.072+.010*field(0,y,3.5,19)-np.clip(d,0,1.6)*.037+.009*field(x,y,.55,10)+.004*field(x,y,.12,11)
 # Irregular shallow graded ruts and a discontinuous loose outside berm.
 near-=.035*(np.exp(-((d-.65)/.10)**2)+np.exp(-((d-1.27)/.11)**2))*(.5+.5*field(x,y,2.7,20))
 # Partly eroded shallow vehicle tread across the compacted shoulder tracks.
 for track in(.65,1.27):
  offset=d-track;phase=((np.asarray(y)+np.abs(offset)*.72)/.23)%1;tread=np.clip(1-np.abs(phase-.5)/.13,0,1);treadfade=np.clip(.4+field(x,y,1.4,98),0,1);near-=.009*tread*np.exp(-(offset/.16)**6)*treadfade
 near+=.036*np.exp(-((d-1.8)/.35)**2)*(1+field(x,y,.28,24))
 regional=grade(y)-.04+.065*field(x,y,17,12)+.035*field(x,y,3.2,13)+.012*field(x,y,.55,14)
 regional-=.20*wash(x,y)
 return near*(1-fade)+regional*fade

def tint_ground(x,y):
 d=np.abs(x)-3.2;w=wash(x,y);deposit=np.clip(.48+.5*field(x,y,1.6,100)+.23*field(x,y,.19,101)+w*.45,0,1)
 # Meter-scale sorting governs colour and relief together; no enlarged grains.
 t=np.zeros(np.shape(x)+(4,),dtype='f4');t[:,:,:3] if t.ndim==3 else None
 t[...,:3]=np.array([.97,.95,.90])+(deposit[...,None]-.5)*np.array([.46,.34,.19]);lag=np.clip((d-1.1)/1.3,0,1)*(1-deposit);t[...,:3]*=(1-.24*lag)[...,None]
 t[...,:3]*=(1+.085*field(x,y,7,99))[...,None];t[...,3]=1;return t

def mesh(name,v,f,share=0,tint=None,material=m,smooth=True):
 me=bpy.data.meshes.new(name);v=np.asarray(v,dtype='f4');f=np.asarray(f,dtype='i4');me.vertices.add(len(v));me.vertices.foreach_set('co',v.ravel());me.loops.add(f.size);me.loops.foreach_set('vertex_index',f.ravel());me.polygons.add(len(f));me.polygons.foreach_set('loop_start',np.arange(len(f),dtype='i4')*f.shape[1]);me.polygons.foreach_set('loop_total',np.full(len(f),f.shape[1],dtype='i4'));me.polygons.foreach_set('use_smooth',np.full(len(f),smooth));me.update();me.materials.append(material)
 if material==m:
  attr=me.attributes.new('asphalt_share','FLOAT','POINT');attr.data.foreach_set('value',np.broadcast_to(np.asarray(share,dtype='f4'),(len(v),)))
  ca=me.color_attributes.new(name='macro_tint',type='FLOAT_COLOR',domain='POINT');ca.data.foreach_set('color',np.asarray(tint if tint is not None else np.ones((len(v),4)),dtype='f4').ravel())
 ob=bpy.data.objects.new(name,me);s.collection.objects.link(ob);return ob

def grid(xs,ys,zfun):
 x,y=np.meshgrid(xs,ys);z=zfun(x,y);q=(np.arange(len(ys)-1)[:,None]*len(xs)+np.arange(len(xs)-1)[None,:]).ravel();f=np.stack((q,q+1,q+len(xs)+1,q+len(xs)),1);return np.stack((x,y,z),-1).reshape(-1,3),f

yaxis=np.unique(np.r_[np.arange(-15,12,.030),np.arange(12,55,.17),np.arange(55,180,.5),np.arange(180,600,1.7),np.arange(600,1800,7)])
# Each half shoulder begins underneath the physical slab edge. Higher frequencies
# restricted to near-view mesh; farther terrain uses bandlimited broad fields.
for sign in (-1,1):
 distances=np.unique(np.r_[np.arange(0,3,.023),np.arange(3,12,.18),np.arange(12,65,.7),np.arange(65,220,3),np.arange(220,1800,18)])
 dd,yy=np.meshgrid(distances,yaxis);xx=edge_y(yy,sign)+sign*dd
 zz=terrain(xx,yy);far=np.clip((np.abs(xx)-45)/35,0,1);broad=grade(yy)-.04+.18*field(xx,yy,35,12);zz=zz*(1-far)+broad*far
 nx=len(distances);q=(np.arange(len(yaxis)-1)[:,None]*nx+np.arange(nx-1)[None,:]).ravel();ff=np.stack((q,q+1,q+nx+1,q+nx),1)
 if sign<0:ff=ff[:,::-1]
 mesh('Graded shoulder and alluvial plain '+str(sign),np.stack((xx,yy,zz),-1).reshape(-1,3),ff,tint=tint_ground(xx,yy).reshape(-1,4))
# Top road uses a genuine irregular edge and a longitudinal rise.
u=np.linspace(-1,1,145);uu,yy=np.meshgrid(u,yaxis);left=edge_y(yy,-1);right=edge_y(yy,1);xx=left*(1-(uu+1)/2)+right*(uu+1)/2;zz=road_z(xx,yy)
nx=len(u);q=(np.arange(len(yaxis)-1)[:,None]*nx+np.arange(nx-1)[None,:]).ravel();ff=np.stack((q,q+1,q+nx+1,q+nx),1)
# Restrained broad oxidation, patchy edge fines; keep the approved dense aggregate.
pav=1.15+.18*field(xx,yy,1.7,40)+.045*field(xx,yy,.19,41);pav-=.045*(np.exp(-((np.abs(xx)-1.02)/.23)**2)+np.exp(-((np.abs(xx)-2.42)/.26)**2));t=np.ones(xx.shape+(4,),dtype='f4');t[...,:3]=pav[...,None]
road=mesh('Crowned asphalt crust / longitudinal rise',np.stack((xx,yy,zz),-1).reshape(-1,3),ff,share=1,tint=t.reshape(-1,4))
for sign in(-1,1):
 x=edge_y(yaxis,sign);top=road_z(x,yaxis);bottom=np.minimum(terrain(x,yaxis)-.003,top-.0005);v=np.stack((np.repeat(x,2),np.repeat(yaxis,2),np.stack((bottom,top),1).ravel()),1);q=np.arange(len(yaxis)-1)*2;f=np.stack((q,q+2,q+3,q+1),1);f=f if sign<0 else f[:,::-1];mesh('Broken exposed asphalt edge '+str(sign),v,f,share=1,tint=np.tile([.68,.67,.65,1],(len(v),1)),smooth=False)
# Separate shallow dust tongues feather onto occasional sections of the edge,
# rather than dissolving normals across the entire road.
rng=np.random.default_rng(260910)
for sign in(-1,1):
 for k in range(70):
  cy=rng.uniform(-8,220);length=rng.uniform(.18,2.1);width=rng.uniform(.015,.17);ys=np.linspace(cy-length,cy+length,25);xs=np.linspace(0,1,8);u,v=np.meshgrid(xs,ys);profile=(1-((v-cy)/length)**2)*width*(.8+.2*field(0,v,.12,k));edge=edge_y(v,sign);x=edge-sign*u*profile;z=road_z(x,v)+.0004*(1-u)+.00015;vs=np.stack((x,v,z),-1).reshape(-1,3);q=(np.arange(24)[:,None]*8+np.arange(7)[None,:]).ravel();fs=np.stack((q,q+1,q+9,q+8),1);mesh('Wind and grading dust deposit',vs,fs,share=0,tint=tint_ground(x,v).reshape(-1,4))
# Drape worn marking geometry on the actual camber and grade.
def paint_material(name,color):
 ma=bpy.data.materials.new(name);ma.use_nodes=True;nn=ma.node_tree.nodes;ll=ma.node_tree.links;bs=nn.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Roughness'].default_value=.88;g=nn.new('ShaderNodeNewGeometry');nt=nn.new('ShaderNodeTexNoise');nt.inputs['Scale'].default_value=26;nt.inputs['Detail'].default_value=3;ll.new(g.outputs['Position'],nt.inputs['Vector']);mr=nn.new('ShaderNodeMapRange');mr.inputs['From Min'].default_value=.34;mr.inputs['From Max'].default_value=.53;ll.new(nt.outputs['Fac'],mr.inputs['Value']);ll.new(mr.outputs[0],bs.inputs['Alpha']);return ma
yellow=paint_material('Faded ochre center paint',(.32,.23,.045));white=paint_material('Worn pale edge marking',(.41,.39,.33))
for cx,wi,ma in[(-.115,.10,yellow),(.115,.10,yellow),(-2.91,.105,white),(2.91,.105,white)]:
 v,f=grid(np.linspace(cx-wi/2,cx+wi/2,4),yaxis,lambda x,y:road_z(x,y)+.0006);mesh('Worn marking following road profile',v,f,material=ma)
# Sparse irregular shrinkage cracks, 3–8 mm wide, integrated into pavement.
crackmat=bpy.data.materials.new('Weathered narrow fissures');crackmat.use_nodes=True;cb=crackmat.node_tree.nodes.get('Principled BSDF');cb.inputs['Base Color'].default_value=(.013,.012,.011,1);cb.inputs['Roughness'].default_value=.94
for k in range(24):
 cy=rng.uniform(2,120);x0=rng.uniform(-3.2,.3);length=rng.uniform(.6,2.7);xs=np.linspace(x0,min(x0+length,3.15),30);ys=cy+.10*field(xs,np.zeros_like(xs),.20,k+50)+.08*(xs-x0);wi=rng.uniform(.002,.005);vv=[]
 for x,y in zip(xs,ys):vv.extend([(x,y-wi,road_z(x,y)+.00015),(x,y+wi,road_z(x,y)+.00015)])
 q=np.arange(len(xs)-1)*2;mesh('Sparse narrow transverse pavement fissure',vv,np.stack((q,q+1,q+3,q+2),1),material=crackmat)
print('EARTHWORKS BUILT',flush=True)
# Three irregular overlapping relief masses, with resolved branching gullies.
def hill_material(name,base,dust):
 ma=bpy.data.materials.new(name);ma.use_nodes=True;nn=ma.node_tree.nodes;ll=ma.node_tree.links;nn.clear();ge=nn.new('ShaderNodeNewGeometry');nt=nn.new('ShaderNodeTexNoise');ll.new(ge.outputs['Position'],nt.inputs['Vector']);nt.inputs['Scale'].default_value=.075;nt.inputs['Detail'].default_value=3;ra=nn.new('ShaderNodeValToRGB');ra.color_ramp.elements[0].color=(*base,1);ra.color_ramp.elements[1].color=(*dust,1);ll.new(nt.outputs['Fac'],ra.inputs[0]);bs=nn.new('ShaderNodeBsdfPrincipled');ll.new(ra.outputs[0],bs.inputs['Base Color']);bs.inputs['Roughness'].default_value=.95
 # Distance-based aerial perspective for distant opaque ridge scenery.
 cam=nn.new('ShaderNodeCameraData');mul=nn.new('ShaderNodeMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=.00038;ll.new(cam.outputs['View Distance'],mul.inputs[0]);em=nn.new('ShaderNodeEmission');em.inputs[0].default_value=(.44,.52,.63,1);em.inputs[1].default_value=.6;mixs=nn.new('ShaderNodeMixShader');ll.new(mul.outputs[0],mixs.inputs[0]);ll.new(bs.outputs[0],mixs.inputs[1]);ll.new(em.outputs[0],mixs.inputs[2]);o=nn.new('ShaderNodeOutputMaterial');ll.new(mixs.outputs[0],o.inputs[0]);return ma
for index,(cx,cy,sx,sy,height) in enumerate([(-480,690,360,240,125),(740,1400,500,350,100),(-810,1850,820,450,160)]):
 hx=np.arange(cx-sx*1.55,cx+sx*1.55,4.5 if index==0 else 7);hy=np.arange(cy-sy*1.6,cy+sy*1.6,4.5 if index==0 else 7);xx,yy=np.meshgrid(hx,hy);ridgecenter=cy+sy*.27*field(xx,0,115,index+66);radx=(xx-cx)/sx;rady=(yy-ridgecenter)/sy
 ridge=np.maximum(0,1-np.abs(rady))**1.3*np.maximum(0,1-radx**2)**.65
 jag=.69+.20*field(xx,yy,93,index+88)+.12*field(xx,yy,29,index+89)
 gully=np.abs(field(xx+.32*yy,yy*.45,48,index+104));zz=height*ridge*jag*(.75+.25*gully)
 zz+=ridge*3.3*field(xx,yy,14,index+118);zz+=grade(yy)-.04;nx=len(hx);q=(np.arange(len(hy)-1)[:,None]*nx+np.arange(nx-1)[None,:]).ravel();f=np.stack((q,q+1,q+nx+1,q+nx),1);mat=hill_material('Weathered granitic ridge '+str(index),(.105,.102,.095),(.29,.245,.185));mesh('Irregular ridge and talus '+str(index),np.stack((xx,yy,zz),-1).reshape(-1,3),f,material=mat)
# Actual airy, varied scrub outside the worked shoulder. Sparse wetting zones,
# mineral pockets and broad bare areas govern placement instead of uniform scatter.
sys.path.insert(0,str(ROOT/'vegetation'));from desert_scrub import create_variants
pc=bpy.data.collections.new('Procedural shrub source bank');bank=create_variants(pc,260910)
counts={'shrubs':0,'grass':0}
for k in range(13500):
 y0=rng.uniform(-3,150) if k<6000 else rng.uniform(-5,650);x0=rng.uniform(-34,34) if k<6000 else rng.uniform(-140,140)
 if abs(x0)<4.8:continue
 patch=float(field(x0,y0,13,303));prob=np.clip(.18+.46*patch+.22*float(wash(x0,y0)),.015,.78)
 if rng.random()>prob:continue
 base=bank['shrubs'][int(rng.integers(0,len(bank['shrubs'])))];ob=bpy.data.objects.new('Scrub patch / rooted to alluvial plain',base.data);s.collection.objects.link(ob);ob.location=(x0,y0,float(terrain(x0,y0)));ob.rotation_euler[2]=rng.uniform(0,math.tau);sc=rng.uniform(.7,1.5);ob.scale=(sc*rng.uniform(.85,1.28),sc*rng.uniform(.85,1.28),sc*rng.uniform(.60,1.12));ob.rotation_euler[0]=rng.uniform(-.12,.12);ob.rotation_euler[1]=rng.uniform(-.12,.12);counts['shrubs']+=1
for k in range(2300):
 y0=rng.uniform(-3,160);x0=rng.uniform(-20,20)
 if abs(x0)<3.65 or rng.random()>np.clip(.18+.55*field(x0,y0,4,371),.01,.8):continue
 base=bank['grass'][int(rng.integers(0,len(bank['grass'])))];ob=bpy.data.objects.new('Sparse dry straw tufts',base.data);s.collection.objects.link(ob);ob.location=(x0,y0,float(terrain(x0,y0)));ob.rotation_euler[2]=rng.uniform(0,math.tau);sc=rng.uniform(.3,.9);ob.scale=(sc,sc,sc);counts['grass']+=1
print('LANDSCAPE BUILT',counts,flush=True)
# Extract actual approved R5D particle bodies, keeping their geometry, colours,
# roughness and physical dimensions. Reposition individual particles continuously
# so there is no rectangular 18 cm patch footprint in the wider shot.
with bpy.data.libraries.load(str(ROOT.parent/'discrete_grains_r5/preview/diagnostic_d.blend'),link=False) as(src,dst):dst.objects=['Discrete angular sand grit and fragments']
source=dst.objects[0];me=source.data;v=np.empty(len(me.vertices)*3,dtype='f4');me.vertices.foreach_get('co',v);v=v.reshape(-1,3);ids=np.empty(len(v),dtype='i4');me.attributes['particle_id'].data.foreach_get('value',ids);colors=np.empty(len(v)*4,dtype='f4');me.color_attributes['mineral'].data.foreach_get('color',colors);colors=colors.reshape(-1,4);rr=np.empty(len(v),dtype='f4');me.attributes['grain_roughness'].data.foreach_get('value',rr);tri=np.empty(len(me.loops),dtype='i4');me.loops.foreach_get('vertex_index',tri);tri=tri.reshape(-1,3)
starts=np.r_[0,np.flatnonzero(np.diff(ids))+1];ends=np.r_[starts[1:],len(v)];faceids=ids[tri[:,0]];proto_col=bpy.data.collections.new('Exact R5D individual grains / hidden instance source');proto=[]
for ii in np.r_[rng.choice(297,48,replace=False),297+rng.choice(8859,16,replace=False)]:
 a,b=starts[ii],ends[ii];vs=v[a:b].copy();cx,cy=vs[:,:2].mean(axis=0);gz=.00009*field(cx,cy,.031,5)+.000035*field(cx,cy,.0035,6);vs-=np.array([cx,cy,gz]);fs=tri[faceids==ii]-a;mm=bpy.data.meshes.new('Approved particle '+str(ii));mm.from_pydata(vs.tolist(),[],fs.tolist());mm.materials.append(me.materials[0]);ca=mm.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');ca.data.foreach_set('color',colors[a:b].ravel());ra=mm.attributes.new('grain_roughness','FLOAT','POINT');ra.data.foreach_set('value',rr[a:b]);ob=bpy.data.objects.new(mm.name,mm);proto_col.objects.link(ob);proto.append(ob)
# Geometry nodes retain shared mesh prototypes and all material attributes.
points=[];pi=[];rot=[]
for k in range(65000):
 x0=rng.uniform(-6.2,-3.20);y0=rng.uniform(-.65,5.0);distance=math.sqrt((x0+4.15)**2+(y0+.8)**2+.52**2);density=np.clip((3.7-distance)/2.0,0,1);density*=.65+.35*(1-float(wash(x0,y0)))
 if rng.random()>density:continue
 points.append((x0,y0,float(terrain(x0,y0))+.00002));pi.append(int(rng.integers(0,64 if distance<1.8 else 48)));rot.append((0,0,float(rng.uniform(0,math.tau))))
pm=bpy.data.meshes.new('Projected-size filtered particle origins');pm.from_pydata(points,[],[]);a=pm.attributes.new('prototype','INT','POINT');a.data.foreach_set('value',pi);a=pm.attributes.new('yaw','FLOAT_VECTOR','POINT');a.data.foreach_set('vector',np.array(rot,dtype='f4').ravel());po=bpy.data.objects.new('True approved R5D near-camera grain geometry',pm);s.collection.objects.link(po);ng=bpy.data.node_groups.new('Particle detail at true metric scale','GeometryNodeTree');ng.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');ng.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry');nn=ng.nodes;ll=ng.links;gi=nn.new('NodeGroupInput');go=nn.new('NodeGroupOutput');ci=nn.new('GeometryNodeCollectionInfo');ci.inputs['Collection'].default_value=proto_col;ci.inputs['Separate Children'].default_value=True;ci.inputs['Reset Children'].default_value=True;ins=nn.new('GeometryNodeInstanceOnPoints');ins.inputs['Pick Instance'].default_value=True;at=nn.new('GeometryNodeInputNamedAttribute');at.data_type='INT';at.inputs['Name'].default_value='prototype';ro=nn.new('GeometryNodeInputNamedAttribute');ro.data_type='FLOAT_VECTOR';ro.inputs['Name'].default_value='yaw';ll.new(gi.outputs[0],ins.inputs['Points']);ll.new(ci.outputs['Instances'],ins.inputs['Instance']);ll.new(at.outputs['Attribute'],ins.inputs['Instance Index']);ll.new(ro.outputs['Attribute'],ins.inputs['Rotation']);ll.new(ins.outputs['Instances'],go.inputs[0]);mo=po.modifiers.new('Metric particle instances','NODES');mo.node_group=ng
bpy.data.objects.remove(source);del v,ids,colors,rr,tri,faceids
print('NEAR GRAINS',len(points),flush=True)
exec(compile((ROOT/'src/roadside_clasts.py').read_text(),str(ROOT/'src/roadside_clasts.py'),'exec'))
cd=bpy.data.cameras.new('Whole road with foreground material');cam=bpy.data.objects.new(cd.name,cd);s.collection.objects.link(cam);s.camera=cam;cam.location=(-3.97,-.8,.35);target=Vector((-.5,7.0,-.32));cd.lens=26;cd.clip_start=.01;cd.clip_end=5000;cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
s['qualification']='Representative high-desert road interpretation, not a specific-site reconstruction';s['ground_source']='User-approved R5D physical particle geometry and exact shader-derived maps';s['distance_LOD']='Dominant stochastic tile weights; individual metric particles near camera';s['scene_version']='R6 earthwork and coherent desert landscape diagnostic E'
ROOT.joinpath('preview').mkdir(exist_ok=True);p=ROOT/'preview/road_r6_e.blend';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(p),compress=True)
receipt=dict(scene=str(p),scene_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),road_width_m=6.4,camber_center_above_edge_m=.064,edge_top_m=.07,sky_strength=.11,sun_energy=3.4,near_particle_instances=len(points),vegetation=counts,camera=list(cam.location),target=list(target),lens=26,threads=2,source_ground='R5D exact source particles + physical 0.18m LOD',scene_interpretation=s['qualification'])
(ROOT/'receipts/scene_e.json').write_text(json.dumps(receipt,indent=2));print('BUILT_R6',receipt,flush=True)
