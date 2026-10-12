"""Next bounded R6 scene layer: weathered road binder, wind-deposited fines,
and aggregate-following worn markings. Loads immutable E and writes new I.
Original R5D and asphalt input maps remain unchanged. Never renders itself.
"""
import bpy,math,json,hashlib,ast
import numpy as np
from pathlib import Path
R=Path(__file__).resolve().parents[1];source=R/'preview/road_r6_e.blend';bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene
# Close the contact edge where soil already banks above the road. Extend only
# its first mesh row a few centimetres onto the slab and land it on the asphalt
# datum, instead of leaving an unsupported zero-thickness soil boundary.
_tree=ast.parse((R/'src/build_scene.py').read_text());_defs=[q for q in _tree.body if isinstance(q,ast.FunctionDef) and q.name in {'field','grade','edge_y','road_z'}];_fn={'np':np};exec(compile(ast.Module(body=_defs,type_ignores=[]),'<road-profile>','exec'),_fn);contact_rows=0
for side in(-1,1):
 ob=bpy.data.objects['Graded shoulder and alluvial plain '+str(side)];me=ob.data;co=np.empty(len(me.vertices)*3,dtype='f4');me.vertices.foreach_get('co',co);co=co.reshape(-1,3).astype('f8');edge=_fn['edge_y'](co[:,1],side);mask=np.abs(co[:,0]-edge)<.0003;indices=np.flatnonzero(mask);old=co[indices];above=old[:,2]-_fn['road_z'](old[:,0],old[:,1]);width=np.clip(above/.013,0,1)*.055;covered=width>.001;ids=indices[covered];co[ids,0]-=side*width[covered];co[ids,2]=_fn['road_z'](co[ids,0],co[ids,1])+.0002;me.vertices.foreach_set('co',co.ravel());me.update();contact_rows+=len(ids);print('CONTACT_BANK',side,'boundary_vertices',len(indices),'covered_vertices',len(ids),flush=True)
# Represent sub-millimetre deposits on the exact road surface. The former
# free dust strips interpolated their own edges and left detached triangular
# overhangs. A paired depth/inset attribute cannot cross or leave a gap.
road=bpy.data.objects['Crowned asphalt crust / longitudinal rise'];co=np.array([v.co[:] for v in road.data.vertices],dtype='f8');x,y=co[:,0],co[:,1]
left=_fn['edge_y'](y,-1);right=_fn['edge_y'](y,1);inset=np.minimum(x-left,right-x)
depth=np.zeros(len(co));rng=np.random.default_rng(260910)
for sign in(-1,1):
 for k in range(70):
  cy=rng.uniform(-8,220);length=rng.uniform(.18,2.1);width=rng.uniform(.015,.17)
  profile=np.maximum(1-((y-cy)/length)**2,0)*width*(.8+.2*_fn['field'](0,y,.12,k))
  depth=np.maximum(depth,np.where(np.sign(x)==sign,profile,0))
for name,values in [('road_edge_inset_m',inset),('road_deposit_depth_m',depth)]:
 a=road.data.attributes.new(name,'FLOAT','POINT');a.data.foreach_set('value',values.astype('f4'))
removed=0
for ob in list(s.objects):
 if ob.name.startswith('Wind and grading dust deposit'):
  bpy.data.objects.remove(ob,do_unlink=True);removed+=1
assert removed==140
print('CONTACT_SAFE_DEPOSIT_FIELD',removed,'free sheets removed',int(np.count_nonzero(depth>inset)),flush=True)
m=bpy.data.materials['Road / Approved R5D soil + original dense asphalt'];n=m.node_tree.nodes;l=m.node_tree.links
bs=n['Linked dry dielectric'];base=bs.inputs['Base Color'].links[0].from_socket;rough=bs.inputs['Roughness'].links[0].from_socket;normal=bs.inputs['Normal'].links[0].from_socket;pos=n['World surface geometry'].outputs['Position'];share=n['Coupled dust-and-asphalt ownership'].outputs['Fac']
def val(node,input,v):l.new(v,node.inputs[input]) if hasattr(v,'node') else setattr(node.inputs[input],'default_value',v)
def math_(op,a,b=0):q=n.new('ShaderNodeMath');q.operation=op;val(q,0,a);val(q,1,b);return q.outputs[0]
def mix(a,b,f):q=n.new('ShaderNodeMixRGB');val(q,0,f);val(q,1,a);val(q,2,b);return q.outputs[0]
def noise(scale,detail):q=n.new('ShaderNodeTexNoise');q.inputs['Scale'].default_value=scale;q.inputs['Detail'].default_value=detail;q.inputs['Roughness'].default_value=.69;l.new(pos,q.inputs['Vector']);return q.outputs['Fac']
def range_(v,a,b,c,d):q=n.new('ShaderNodeMapRange');q.clamp=True;q.interpolation_type='SMOOTHERSTEP';l.new(v,q.inputs['Value']);q.inputs['From Min'].default_value=a;q.inputs['From Max'].default_value=b;q.inputs['To Min'].default_value=c;q.inputs['To Max'].default_value=d;return q.outputs[0]
# Link true soil colour/roughness/slope only in bounded, thin edge deposits.
# Coordinates are attributes of the road mesh itself; no competing surfaces.
share_node=n['Coupled dust-and-asphalt ownership'];old_links=list(share_node.outputs['Fac'].links)
ai=n.new('ShaderNodeAttribute');ai.attribute_name='road_edge_inset_m'
ad=n.new('ShaderNodeAttribute');ad.attribute_name='road_deposit_depth_m'
inside=math_('SUBTRACT',ad.outputs['Fac'],ai.outputs['Fac'])
coverage=range_(inside,-.003,.005,0,1)
active=math_('GREATER_THAN',ad.outputs['Fac'],.0005)
coverage=math_('MULTIPLY',coverage,active)
coating=math_('MULTIPLY',coverage,range_(noise(170,2),.2,.8,.85,1))
share=math_('MULTIPLY',share_node.outputs['Fac'],math_('SUBTRACT',1,coating))
for link in old_links:l.new(share,link.to_socket)
sep=n.new('ShaderNodeSeparateXYZ');l.new(pos,sep.inputs[0]);ax=math_('ABSOLUTE',sep.outputs['X']);edge=range_(ax,2.50,3.20,0,1)
patch=noise(.70,3);grit=noise(7.5,2)
# Longitudinal traffic history is broad and restrained, not black tire stripes.
an=n.new('ShaderNodeVectorMath');an.operation='MULTIPLY';an.inputs[1].default_value=(1.4,.12,1);l.new(pos,an.inputs[0]);aniso=n.new('ShaderNodeTexNoise');aniso.inputs['Scale'].default_value=1;aniso.inputs['Detail'].default_value=2;l.new(an.outputs[0],aniso.inputs['Vector']);aged=range_(aniso.outputs['Fac'],.22,.78,.99,1.34)
mult=n.new('ShaderNodeMixRGB');mult.blend_type='MULTIPLY';mult.inputs[0].default_value=1;l.new(base,mult.inputs[1]);l.new(aged,mult.inputs[2]);weathered=mix(base,mult.outputs[0],share)
# A thin fine-mineral coating, sparse in the wheel corridors and strongest
# where pale edge deposits can supply windblown/graded fines.
wheel=math_('MINIMUM',math_('ABSOLUTE',math_('SUBTRACT',ax,1.0)),math_('ABSOLUTE',math_('SUBTRACT',ax,2.25)));clean=range_(wheel,.13,.43,.25,1)
dust=math_('MULTIPLY',math_('MULTIPLY',share,clean),math_('ADD',.028,math_('MULTIPLY',edge,range_(patch,.32,.74,0,.24))))
dust=math_('MULTIPLY',dust,range_(grit,.20,.79,.65,1.18));coated=mix(weathered,(.27,.224,.166,1),dust);l.new(coated,bs.inputs['Base Color']);l.new(math_('MINIMUM',.95,math_('ADD',rough,math_('MULTIPLY',dust,.32))),bs.inputs['Roughness'])
# Preserve full metric original aggregate normal under marking fragments.
normal_image=next(q.image for q in n if q.type=='TEX_IMAGE' and q.image and q.image.name.startswith('Normal_Object'))
for name in('Faded ochre center paint','Worn pale edge marking'):
 ma=bpy.data.materials[name];nn=ma.node_tree.nodes;ll=ma.node_tree.links;pb=nn.get('Principled BSDF');geo=next(q for q in nn if q.type=='NEW_GEOMETRY');position=geo.outputs['Position'];oldalpha=pb.inputs['Alpha'].links[0].from_socket
 nt=nn.new('ShaderNodeTexNoise');nt.inputs['Scale'].default_value=110;nt.inputs['Detail'].default_value=2;ll.new(position,nt.inputs['Vector']);loss=nn.new('ShaderNodeMath');loss.operation='GREATER_THAN';loss.inputs[1].default_value=.31;ll.new(nt.outputs['Fac'],loss.inputs[0]);ll.new(loss.outputs[0],pb.inputs['Alpha'])
 if name.startswith('Worn'):pb.inputs['Base Color'].default_value=(.29,.275,.24,1)
 else:pb.inputs['Base Color'].default_value=(.27,.195,.04,1)
 scale=nn.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs['Scale'].default_value=4;ll.new(position,scale.inputs[0]);tex=nn.new('ShaderNodeTexImage');tex.image=normal_image;tex.extension='REPEAT';tex.interpolation='Linear';ll.new(scale.outputs[0],tex.inputs[0]);nm=nn.new('ShaderNodeNormalMap');nm.space='OBJECT';ll.new(tex.outputs[0],nm.inputs['Color'])
 def slope(v):
  sep=nn.new('ShaderNodeSeparateXYZ');ll.new(v,sep.inputs[0]);den=nn.new('ShaderNodeMath');den.operation='MAXIMUM';den.inputs[1].default_value=.04;ll.new(sep.outputs['Z'],den.inputs[0]);div=nn.new('ShaderNodeMath');div.operation='DIVIDE';div.inputs[0].default_value=1;ll.new(den.outputs[0],div.inputs[1]);sc=nn.new('ShaderNodeVectorMath');sc.operation='SCALE';ll.new(v,sc.inputs[0]);ll.new(div.outputs[0],sc.inputs['Scale']);return sc.outputs['Vector']
 add=nn.new('ShaderNodeVectorMath');add.operation='ADD';ll.new(slope(nm.outputs[0]),add.inputs[0]);ll.new(slope(geo.outputs['Normal']),add.inputs[1]);sub=nn.new('ShaderNodeVectorMath');sub.operation='SUBTRACT';sub.inputs[1].default_value=(0,0,1);ll.new(add.outputs[0],sub.inputs[0]);norm=nn.new('ShaderNodeVectorMath');norm.operation='NORMALIZE';ll.new(sub.outputs[0],norm.inputs[0]);ll.new(norm.outputs[0],pb.inputs['Normal'])

s['scene_version']='R6 I contact-safe road weathering layer over corrected supporting shoulder';out=R/'preview/road_r6_i.blend';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(out),compress=True);(R/'receipts/weather_layer_i.json').write_text(json.dumps({'source_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scene_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'changes':'Thin linked fines/aged binder, metric aggregate normals beneath markings, crisp paint losses, and a 0–55 mm contact-bank extension only where soil already covers the edge. Original material map bytes unchanged.','contact_vertices_adjusted':contact_rows,'free_dust_sheets_removed':removed,'deposit_representation':'Bounded thickness coverage on original road tessellation; exact shared-surface contact, no second geometry sheet','threads':2},indent=2));print('WEATHER_LAYER_PREPARED',out,flush=True)
