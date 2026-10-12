"""Reuse exact captured CK world-space community independently of camera."""
from pathlib import Path
import hashlib,json,bpy,numpy as np
import architectural_scrub_cj as bank

def apply(scene,cfg,out):
 assert cfg['revision']==1;path=Path(cfg['layout']);assert hashlib.sha256(path.read_bytes()).hexdigest()==cfg['layout_sha256'];j=json.loads(path.read_text())
 assert hashlib.sha256(Path(bank.__file__).read_bytes()).hexdigest()==j['workshop_source_sha256']
 current=json.loads((Path(out)/'FIXED_GRAVEL_SUPPORT_CI.json').read_text());assert current['exact_identity_xy_yaw_sha256']==j['ci_identity_xy_yaw_sha256']
 palette=[bpy.data.materials.get(n)for n in j['original_palette']];assert all(palette)
 coll=bpy.data.collections.new('CL canonical CK architectures');scene.collection.children.link(coll);protos=bank.create_variants(coll,seed=26101020,materials=palette)['shrubs']
 for name in j['hidden_names']:
  ob=scene.objects.get(name);assert ob is not None,('Missing canonical old shrub',name);ob.hide_render=True
 for name in j['preserved_near_left_names']:assert not scene.objects[name].hide_render
 created=[]
 for p in j['placements']:
  assert scene.objects.get(p['name']) is None,'Do not apply layout twice'
  ob=bpy.data.objects.new(p['name'],protos[p['architecture']].data);scene.collection.objects.link(ob);ob.location=p['root_m'];ob.rotation_euler[2]=p['yaw_rad'];ob.scale=(p['scale'],)*3;created.append(ob)
 bpy.context.view_layer.update()
 for ob in created:assert np.array_equal(np.asarray(ob.matrix_world,dtype=np.float32),np.asarray(j['matrices'][ob.name],dtype=np.float32)),('Canonical world transform changed',ob.name)
 report=dict(revision='CL immutable CK layout',plants=len(created),hidden_old=len(j['hidden_names']),preserved_near_left=len(j['preserved_near_left_names']),layout_sha256=cfg['layout_sha256'],exact_canonical_float32_world_matrices=True,camera_dependent_scatter_removed=True,geometry_material_roots_yaws_scales_unchanged=True,limits=j['contact_scope'])
 (Path(out)/'FROZEN_ARCHITECTURE_LAYOUT_CL.json').write_text(json.dumps(report,indent=2)+'\n');print('FROZEN_ARCHITECTURE_LAYOUT_CL',json.dumps(report),flush=True);return report
