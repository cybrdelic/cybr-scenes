"""BW source-preserving historical fine-area closure on the current shoulder.

Removes AQ's unqualified channel-dependent coarse multiplier, then uses the
existing ap_fines coverage to mix the inherited surface with the approved AZ
fine-only endpoint as a separate dielectric closure. No new tint, maps, normal
amplification, geometry, particles, burial, stock or terrain field is generated.
"""
from pathlib import Path
import json,time
import numpy as np
from fine_coating_az import graph_stamp
GROUND='Graded shoulder and alluvial plain -1'

def require(ok,message):
 if not ok:raise ValueError(message)
def source(socket):
 return socket.links[0].from_socket if len(socket.links)==1 else None
def constant(socket,value):
 return not socket.is_linked and np.allclose(socket.default_value,value,rtol=0,atol=1e-6)
def scaled_attr(socket,name,amount):
 q=source(socket)
 if q is None or q.node.bl_idname!='ShaderNodeMath' or q.node.operation!='MULTIPLY' or q.node.mute:return False
 a=source(q.node.inputs[0]);return a is not None and a.name=='Fac' and a.node.bl_idname=='ShaderNodeAttribute' and a.node.attribute_name==name and constant(q.node.inputs[1],amount)
def hooks(m):
 require(m.use_nodes and m.get('az_fine_endpoint') and not m.get('bw_historical_fine_area'),'Expected current AZ material without BW')
 n=m.node_tree.nodes;b=n.get('Linked dry dielectric');require(b is not None and b.type=='BSDF_PRINCIPLED','Original dielectric missing')
 q=source(b.inputs['Base Color']);require(q is not None and q.node.bl_idname=='ShaderNodeMixRGB' and q.node.blend_type=='MIX' and not q.node.mute,'Expected AQ final color mixture')
 mix=q.node;require(scaled_attr(mix.inputs[0],'ap_coarse',.7),'Expected AQ coarse field factor')
 base=source(mix.inputs[1]);product=source(mix.inputs[2]);require(base is not None and product is not None,'Missing AQ color inputs')
 p=product.node;require(p.bl_idname=='ShaderNodeMixRGB' and p.blend_type=='MULTIPLY' and not p.mute and constant(p.inputs[0],1.) and constant(p.inputs[2],(.78,.82,.87,1.)) and source(p.inputs[1])==base,'Changed AQ optical multiplier topology')
 out=[q for q in n if q.type=='OUTPUT_MATERIAL' and q.is_active_output];require(len(out)==1 and source(out[0].inputs['Surface'])==b.outputs['BSDF'],'Expected direct current surface closure')
 c=n.get('AZ / linear fine color');normal=n.get('AZ / fine-coat endpoint normal');slope=n.get('AZ / metric fine XY slopes')
 require(c is not None and slope is not None and normal is not None and c.type=='TEX_IMAGE' and slope.type=='TEX_IMAGE' and normal.type=='VECT_MATH' and normal.operation=='NORMALIZE','Qualified AZ fine endpoint missing')
 for q,label in ((c,'linear color'),(slope,'metric XY slope')):
  require(q.image is not None and q.image.name=='AZ / original R5D fines '+label and list(q.image.size)==[1101,1101] and q.image.colorspace_settings.name=='Non-Color' and q.interpolation=='Linear' and q.extension=='EXTEND','AZ physical image contract differs')
  coords=source(q.inputs['Vector']);require(coords is not None and coords.node.name=='AZ / matched mirrored texel centers','AZ metric mapping differs')
 require(source(normal.inputs[0]).node.name=='AZ / broad plus fine only','AZ normal endpoint differs')
 return b,base,out[0],c.outputs['Color'],normal.outputs['Vector'],mix,p

def apply(scene,config,out):
 start=time.monotonic();out=Path(out);receipt=out/'HISTORICAL_FINE_AREA_BW.json';require(not receipt.exists(),'Refusing BW receipt overwrite');require(config=={'revision':1},'Unexpected BW parameter contract')
 o=scene.objects.get(GROUND);require(o is not None and o.type=='MESH' and o.data.users==1,'Expected independent current shoulder')
 attrs={}
 for key in ('ap_fines','ap_coarse'):
  a=o.data.attributes.get(key);require(a is not None and a.domain=='POINT' and a.data_type=='FLOAT','Missing historical attribute '+key);v=np.empty(len(a.data),dtype='f4');a.data.foreach_get('value',v);require(np.isfinite(v).all() and v.min()>=-1e-6 and v.max()<=1+1e-6,'Invalid historical coverage');attrs[key]={'range':[float(v.min()),float(v.max())],'vertex_mean_not_area_fraction':float(v.mean()),'vertices':len(v)}
 old=o.data.materials[0];hooks(old);stamp=graph_stamp(old);m=old.copy();m.name='BW source-derived historical fine area / original inputs retained';committed=False
 try:
  b,base,output,fcolor,fnormal,mix,product=hooks(m);names={n.name for n in m.node_tree.nodes};allowed={(b.name,b.inputs['Base Color'].identifier),(output.name,output.inputs['Surface'].identifier)};protected=graph_stamp(m,names,allowed);n,l=m.node_tree.nodes,m.node_tree.links
  l.new(base,b.inputs['Base Color'])
  f=n.new('ShaderNodeBsdfPrincipled');f.name='BW / original fine-only dielectric';f.inputs['Roughness'].default_value=.84;f.inputs['IOR'].default_value=1.48;l.new(fcolor,f.inputs['Base Color']);l.new(fnormal,f.inputs['Normal'])
  a=n.new('ShaderNodeAttribute');a.name='BW / existing historical fine area';a.attribute_name='ap_fines'
  bounded=n.new('ShaderNodeClamp');bounded.name='BW / bounded existing area';bounded.inputs['Min'].default_value=0.;bounded.inputs['Max'].default_value=1.;l.new(a.outputs['Fac'],bounded.inputs['Value'])
  combine=n.new('ShaderNodeMixShader');combine.name='BW / two source closures area mixture';l.new(bounded.outputs['Result'],combine.inputs[0]);l.new(b.outputs['BSDF'],combine.inputs[1]);l.new(f.outputs['BSDF'],combine.inputs[2]);l.new(combine.outputs[0],output.inputs['Surface'])
  require(graph_stamp(m,names,allowed)==protected,'Protected source graph changed');require(graph_stamp(old)==stamp,'Original material changed');m['bw_historical_fine_area']=True;o.data.materials[0]=m;committed=True
  r={'source_material':old.name,'source_graph_sha256':stamp,'protected_source_unchanged':True,'staged_material':m.name,'protected_non_hook_graph_sha256':protected,'bypassed_proxy':{'mix_node':mix.name,'product_node':product.name,'rgb_multiplier':[.78,.82,.87],'factor':'0.7 * ap_coarse','replacement':'Original inherited color socket; no replacement tint'},'historical_attributes_unchanged':attrs,'fine_source':{'color_socket':[fcolor.node.name,fcolor.identifier],'normal_socket':[fnormal.node.name,fnormal.identifier],'physical_side_m':.18,'roughness':.84,'IOR':1.48,'image_inputs_reused':True,'source_color_changed':False},'mixture':'MixShader of intact inherited closure and original fine-only closure, using existing bounded ap_fines. Union-like bounded area response; already fine-covered branch remains fine, no thickness or stock added.','geometry_particles_material_prototypes_unchanged':True,'lighting_exposure_unchanged':True,'scene_saved':False,'elapsed_seconds':time.monotonic()-start,'limitations':['Authored historical area fraction, not measured mineral abundance or a calibrated sediment mass-to-optics model.','Closure mixing is preferable to interpolated roughness/normals but exact statistical multiscale reflectance is unvalidated.','Native finite texture filtering remains; no grain enlargement or invented lost-variance compensation.']}
  receipt.write_text(json.dumps(r,indent=2)+'\n');return r
 except BaseException:
  if committed:o.data.materials[0]=old
  import bpy;bpy.data.materials.remove(m);raise
