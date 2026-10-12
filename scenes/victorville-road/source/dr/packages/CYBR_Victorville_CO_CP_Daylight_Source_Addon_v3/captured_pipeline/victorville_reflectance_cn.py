"""CN: local warm alluvial reflectance variant, unchanged illumination/geometry.

Qualitatively constrained by Victorville-area survey photographs and USDA soil
color descriptions. Values are authored linear RGB, not calibrated Munsell RGB.
Original material recipes remain intact; only derivative soil closures change.
"""
from pathlib import Path
import json,hashlib
import bpy
from fine_coating_az import graph_stamp

def socket_source(s):return s.links[0].from_socket if len(s.links)==1 else None

def color_variant(old,role):
 m=old.copy();m.name='CN Victorville '+role+' / '+old.name;n,l=m.node_tree.nodes,m.node_tree.links;before=graph_stamp(old);records=[]
 for b in list(n):
  if b.type!='BSDF_PRINCIPLED':continue
  original=socket_source(b.inputs['Base Color']);const=list(b.inputs['Base Color'].default_value)
  if role=='soil':
   # Retain existing fine-sediment distribution. The two tints represent a
   # pale deposited sand endpoint and more ochre weathered matrix, never orange
   # applied to sky, plants, paint or asphalt.
   tint=n.new('ShaderNodeMixRGB');tint.name='CN / existing fines palette '+b.name;tint.blend_type='MIX'
   tint.inputs[1].default_value=(1.38,1.015,.70,1);tint.inputs[2].default_value=(1.31,1.025,.80,1)
   a=n.new('ShaderNodeAttribute');a.attribute_name='ap_fines';a.name='CN / inherited fine area '+b.name;l.new(a.outputs['Fac'],tint.inputs[0]);out=tint.outputs[0]
  else:
   # Only chromatically warm minerals receive stronger ochre/rust response.
   # Neutral quartz and green/gray clasts stay nearly unchanged. This retains
   # the source identity contrast instead of coloring every stone orange.
   sep=n.new('ShaderNodeSeparateRGB')
   if original:l.new(original,sep.inputs[0])
   else:sep.inputs[0].default_value=const
   sub=n.new('ShaderNodeMath');sub.operation='SUBTRACT';l.new(sep.outputs['R'],sub.inputs[0]);l.new(sep.outputs['G'],sub.inputs[1])
   scale=n.new('ShaderNodeMapRange');scale.inputs['From Min'].default_value=.025;scale.inputs['From Max'].default_value=.10;scale.inputs['To Min'].default_value=0.;scale.inputs['To Max'].default_value=.85;scale.clamp=True;l.new(sub.outputs[0],scale.inputs['Value'])
   tint=n.new('ShaderNodeMixRGB');tint.name='CN / retained warm mineral identity';tint.inputs[1].default_value=(1,1,1,1);tint.inputs[2].default_value=(1.19,.99,.78,1);l.new(scale.outputs[0],tint.inputs[0]);out=tint.outputs[0]
  product=n.new('ShaderNodeMixRGB');product.name='CN / authored reflectance '+b.name;product.blend_type='MULTIPLY';product.inputs[0].default_value=1
  if original:l.new(original,product.inputs[1])
  else:product.inputs[1].default_value=const
  l.new(out,product.inputs[2]);l.new(product.outputs[0],b.inputs['Base Color'])
  records.append({'closure':b.name,'old_source':[original.node.name,original.name]if original else const,'new_multiplier_policy':'Inherited ap_fines blends ochre matrix (1.38,1.015,.70) with pale sand (1.31,1.025,.80)'if role=='soil'else 'Original R-G difference selects warm-mineral-only tint; neutral/green mineral response preserved'})
 assert records and graph_stamp(old)==before
 return m,{'source':old.name,'derivative':m.name,'source_graph_sha256':before,'source_graph_unchanged':True,'role':role,'closures':records}

def apply(scene,cfg,out):
 assert cfg=={'revision':1};original_lights=[(o.name,list(o.matrix_world),tuple(o.data.color),o.data.energy)for o in scene.objects if o.type=='LIGHT'];view=(scene.view_settings.view_transform,scene.view_settings.look,scene.view_settings.exposure,scene.view_settings.gamma);world=graph_stamp(scene.world) if False else None
 targets=[scene.objects['Graded shoulder and alluvial plain '+str(s)]for s in(-1,1)];records=[];assigned=[];cache={}
 for o in targets:
  for i,old in enumerate(list(o.data.materials)):
   assert old and old.use_nodes
   key=(old.name,'soil')
   if key not in cache:cache[key],r=color_variant(old,'soil');records.append(r)
   o.data.materials[i]=cache[key];assigned.append({'object':o.name,'slot':i,'material':cache[key].name,'ap_fines_present':bool(o.data.attributes.get('ap_fines'))})
 # New historical coarse tiers are separate from immutable approved R5D sources.
 # Reassign only explicitly named AS/CG mesh slots that use these exact materials.
 mineral_names={'CG original mineral gravel / metric fracture roughness','AS new metric rock / shared regional mineral palette'}
 for oldname in mineral_names:
  old=bpy.data.materials.get(oldname)
  if old is None:continue
  m,r=color_variant(old,'coarse mineral');records.append(r)
  for me in bpy.data.meshes:
   for i,slot in enumerate(list(me.materials)):
    if slot==old:me.materials[i]=m;assigned.append({'mesh':me.name,'slot':i,'material':m.name})
 assert view==(scene.view_settings.view_transform,scene.view_settings.look,scene.view_settings.exposure,scene.view_settings.gamma)
 for name,matrix,color,energy in original_lights:
  o=scene.objects[name];assert list(o.matrix_world)==matrix and tuple(o.data.color)==color and o.data.energy==energy
 report={'revision':'CN1','operation':'Only authored local soil and already-warm new coarse-tier reflectance closures; no image color grading','materials':records,'assignments':assigned,'unchanged':['geometry','normal/height/roughness fields','stone IDs and burial','CK plant layout and morphology','original AV mountains','asphalt and road markings','world/sun/exposure/view transform'],'reference_observation':'Victorville Residential Care Facility Biological Resources Assessment, Jericho Systems, August2016, AttachmentC PDFpage27; two actual daylight photos visually inspected. Warm pale ochre/peach-tan open fines, gray-brown scrub/shadows; uncalibrated photographs.','soil_evidence':'USDA Bryman/Cajon/Cuddeback and local site mapped soil units constrain qualitative pale brown/yellowish brown surface variation; redder subsoil is not assumed uniformly at surface.','limits':['Authored linear-RGB palette change, not measured reflectance or calibrated Munsell conversion.','Existing field masks express historical material distribution; this does not infer oxidation from the newest small transport event.','Approved original R5D and asphalt source recipes remain unchanged. Candidate material differs intentionally.','Mountain materials remain unchanged to preserve the chosen backdrop during this first attribution comparison.']}
 (Path(out)/'VICTORVILLE_REFLECTANCE_CN.json').write_text(json.dumps(report,indent=2)+'\n');print('VICTORVILLE_REFLECTANCE_CN',json.dumps({k:v for k,v in report.items()if k!='assignments'}),flush=True);return report
