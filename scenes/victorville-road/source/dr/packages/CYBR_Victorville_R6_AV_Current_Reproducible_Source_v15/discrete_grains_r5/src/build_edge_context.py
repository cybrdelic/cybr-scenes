"""Bounded physical edge context. Loads immutable R5D diagnostic and the
original dense asphalt source fields; no broad blend masks or ground recolor."""
import bpy,numpy as np,math,json,hashlib
from mathutils import Vector
from pathlib import Path
R=Path(__file__).resolve().parents[1];A=R/'asphalt/native4096'
bpy.ops.wm.open_mainfile(filepath=str(R/'preview/diagnostic_d.blend'));s=bpy.context.scene
h=np.load(A/'HeightState.npy');N=len(h)
def sample(x,y):
 u=(x/.25)%1*N-.5;v=(1-(y/.25)%1)*N-.5;i=np.floor(u).astype('i4');j=np.floor(v).astype('i4');a=u-i;b=v-j
 return (((h[j%N,i%N]*(1-a)+h[j%N,(i+1)%N]*a)*(1-b)+(h[(j+1)%N,i%N]*(1-a)+h[(j+1)%N,(i+1)%N]*a)*b)-.5)*.004+.0022
def hashnoise(y,spacing,seed):
 q=y/spacing;i=np.floor(q);t=q-i;t=t*t*(3-2*t)
 def ha(i):v=np.sin(i*311.7+seed*17.13)*43758.5453;return(v-np.floor(v))*2-1
 return ha(i)*(1-t)+ha(i+1)*t
def edge(y):return .002+.0015*hashnoise(y,.013,5)+.0007*hashnoise(y,.003,8)
m=bpy.data.materials.new('Original dense asphalt / preserved material fields');m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF');geo=n.new('ShaderNodeNewGeometry');sc=n.new('ShaderNodeVectorMath');sc.operation='SCALE';sc.inputs['Scale'].default_value=4;l.new(geo.outputs['Position'],sc.inputs[0])
fields={}
for filename,space,socket in [('BaseColor.png','sRGB','Base Color'),('Roughness.png','Non-Color','Roughness')]:
 im=n.new('ShaderNodeTexImage');im.image=bpy.data.images.load(str(A/filename));im.image.colorspace_settings.name=space;im.image.pack();im.extension='REPEAT';l.new(sc.outputs['Vector'],im.inputs[0]);l.new(im.outputs['Color'],bs.inputs[socket]);fields[socket]=im.outputs['Color']
im=n.new('ShaderNodeTexImage');im.image=bpy.data.images.load(str(A/'Normal_Object_RGB16.png'));im.image.colorspace_settings.name='Non-Color';im.image.pack();im.extension='REPEAT';l.new(sc.outputs['Vector'],im.inputs[0]);nm=n.new('ShaderNodeNormalMap');nm.space='OBJECT';l.new(im.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs[0],bs.inputs['Normal']);bs.inputs['IOR'].default_value=1.5

def mesh(name,v,f,mat,sediment=False):
 me=bpy.data.meshes.new(name);me.from_pydata(v.tolist(),[],f.tolist());me.materials.append(mat);o=bpy.data.objects.new(name,me);s.collection.objects.link(o)
 if name.startswith('Ragged'):
  dist=v[:,0]-edge(v[:,1]);patch=np.clip(.55+.60*hashnoise(v[:,1],.005,16),0,1);cavity=np.clip((.0026-v[:,2])/.0020,0,1);coat=np.clip(np.exp(-np.maximum(dist,0)/.0035)*patch*cavity*.72,0,.72);at=me.attributes.new('edge_dust','FLOAT','POINT');at.data.foreach_set('value',coat.astype('f4'))
 if sediment:
  c=np.ones((len(v),4),'f4');c[:,:3]=[.30,.236,.159];at=me.color_attributes.new(name='sediment',type='FLOAT_COLOR',domain='POINT');at.data.foreach_set('color',c.ravel())
 return o
# Shelter-linked thin dust coating, restricted to a few millimetres of edge.
at=n.new('ShaderNodeAttribute');at.attribute_name='edge_dust';mix=n.new('ShaderNodeMixRGB');l.new(at.outputs['Fac'],mix.inputs[0]);l.new(fields['Base Color'],mix.inputs[1]);mix.inputs[2].default_value=(.29,.23,.155,1);l.new(mix.outputs[0],bs.inputs['Base Color']);rm=n.new('ShaderNodeMixRGB');l.new(at.outputs['Fac'],rm.inputs[0]);l.new(fields['Roughness'],rm.inputs[1]);rm.inputs[2].default_value=(.86,.86,.86,1);l.new(rm.outputs[0],bs.inputs['Roughness'])
ys=np.linspace(-.11,.11,701);u=np.linspace(0,1,361);yy=np.broadcast_to(ys[:,None],(len(ys),len(u)));xx=edge(yy)+u[None,:]*(.12-edge(yy));zz=sample(xx,yy);v=np.stack((xx,yy,zz),-1).reshape(-1,3);nx=len(u);q=(np.arange(len(ys)-1)[:,None]*nx+np.arange(nx-1)[None,:]).ravel();f=np.stack((q,q+1,q+nx+1,q+nx),1);mesh('Ragged true asphalt edge and displaced pavement',v,f,m)
# Fine loose particles rest on the pavement near the ragged shoulder.
# Move whole disconnected grains, preserving each grain's actual fracture mesh.
g=bpy.data.objects['Discrete angular sand grit and fragments'];me=g.data;vv=np.empty((len(me.vertices),3),'f4');me.vertices.foreach_get('co',vv.ravel());ids=np.empty(len(vv),dtype='i4');me.attributes['particle_id'].data.foreach_get('value',ids);count=np.bincount(ids);nc=len(count);center=np.stack([np.bincount(ids,weights=vv[:,k])/count for k in range(3)],1);minimum=np.full((nc,3),np.inf);maximum=np.full((nc,3),-np.inf)
for k in range(3):np.minimum.at(minimum[:,k],ids,vv[:,k]);np.maximum.at(maximum[:,k],ids,vv[:,k])
diameter=(maximum[:,:2]-minimum[:,:2]).max(1);dist=center[:,0]-edge(center[:,1]);rng=np.random.default_rng(62003);prob=np.exp(-np.maximum(dist,0)/.0028)*(.45+.45*np.clip(hashnoise(center[:,1],.007,29)+.4,0,1));selected=(dist>0)&(dist<.011)&(diameter<.00105)&(rng.random(nc)<prob);under=(dist>0)&~selected;vv[under[ids],2]-=.005
sel=selected[ids];vv[sel,2]=sample(vv[sel,0],vv[sel,1])+(vv[sel,2]-minimum[ids[sel],2])*.55-.000025;me.vertices.foreach_set('co',vv.ravel());me.update();print('Actual edge grains',int(selected.sum()))
s.camera.location=(-.020,-.130,.160);target=Vector((-.005,0,.001));s.camera.rotation_euler=(target-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.ortho_scale=.14;s.render.resolution_x=800;s.render.resolution_y=640;s.cycles.use_denoising=False
p=R/'preview/edge_context_d.blend';bpy.ops.wm.save_as_mainfile(filepath=str(p));receipt=dict(asphalt_model='Original dense packed-grain asphalt',asphalt_tile_m=.25,asphalt_height_scale_m=.004,ground_source='R5D discrete particle diagnostic',true_boundary='Jagged physical asphalt mesh; no color, height or normal blending band',dust='Shelter-linked thin coating and independently placed fine-grain meshes; no continuous raised dust ribbon',edge_grains=int(selected.sum()),crop_width_m=.14,qualification='Road-edge integration diagnostic only, not a wide road scene');(R/'receipts/edge_context_d.json').write_text(json.dumps(receipt,indent=2));print('EDGE_CONTEXT_BUILT',str(p))
