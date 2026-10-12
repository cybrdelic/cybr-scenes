"""Scene-specific DU5 soil binding. Reusable fields are owned by CYBR MATERIAL."""
from pathlib import Path
import hashlib,importlib.util,json

def install(scene,cfg,out):
 source=Path(cfg['matrix_source']);profiles=Path(cfg['matrix_profile'])
 assert hashlib.sha256(source.read_bytes()).hexdigest()==cfg['matrix_source_sha256']
 assert hashlib.sha256(profiles.read_bytes()).hexdigest()==cfg['matrix_profile_sha256']
 spec=importlib.util.spec_from_file_location('cybr_material_granular_matrix',source);owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner);profile=owner.load_profile(profiles)
 changed=[];angular_pitch=scene.camera.data.sensor_width/scene.camera.data.lens/scene.render.resolution_x
 for sign in (-1,1):
  ob=scene.objects['Graded shoulder and alluvial plain '+str(sign)]
  for slot,old in enumerate(list(ob.data.materials)):
   m=old.copy();m.name='DU5 coupled granular matrix / '+old.name;builder=owner.Nodes(m.node_tree);n,l=builder.n,builder.l;node,calc=builder.node,builder.calc
   def attribute(name):
    p=node('ShaderNodeAttribute',name);p.attribute_name=name;return p.outputs['Fac']
   geom=node('ShaderNodeNewGeometry','world metre coordinates');cam=node('ShaderNodeCameraData','ray pixel footprint')
   footprint=owner.surface_footprint(builder,geom.outputs['Normal'],geom.outputs['Incoming'],cam.outputs['View Distance'],angular_pitch)
   root=attribute('du_shelter');rough=attribute('du_rough');compact=attribute('du_compact');gate=attribute('du_gate')
   relief_gain=calc('MULTIPLY',gate,calc('ADD',.68,calc('ADD',calc('MULTIPLY',rough,.36),calc('MULTIPLY',root,.16))))
   fields=owner.aggregate_fields(builder,geom.outputs['Position'],footprint,relief_gain,profile)
   zone=calc('SUBTRACT',1.02,calc('ADD',calc('MULTIPLY',root,.055),calc('MULTIPLY',rough,.035)))
   tone=calc('ADD',1.,calc('MULTIPLY',gate,calc('SUBTRACT',calc('ADD',zone,fields['pigment_delta']),1.)))
   for b in list(n):
    if b.type!='BSDF_PRINCIPLED':continue
    roughness_offset=calc('MULTIPLY',gate,calc('ADD',fields['roughness_proxy'],calc('MULTIPLY',calc('SUBTRACT',1.,compact),.045)))
    owner.attach_closure(builder,b,fields['height_m'],tone,roughness_offset,profile)
   ob.data.materials[slot]=m;changed.append({'object':ob.name,'source_material':old.name,'candidate_material':m.name,'node_count':len(n)})
 report={'revision':'DU5 owner split','changed':changed,'source_images_modified':False,'photo_textures':False,'new_solid_inventory_m3':0.,'material_owner':'cybrdelic/cybr-material','matrix_source_sha256':cfg['matrix_source_sha256'],'matrix_profile_sha256':cfg['matrix_profile_sha256'],'profile_id':profile['id'],'bands':profile['bands'],'pixel_angular_pitch':angular_pitch,'palette':'Unchanged CN chromatic endpoints with achromatic reflectance variation.','limits':profile['limits']}
 (Path(out)/'DU_MATERIAL.json').write_text(json.dumps(report,indent=2)+'\n');return report
