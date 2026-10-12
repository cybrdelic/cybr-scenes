"""Bounded final semantic-admission controls; scenes stay exclusively in memfd.
Uses valid trailing zstd skippable metadata instead of memory-heavy recompression.
"""
from pathlib import Path
import os,sys,json,hashlib,subprocess,time,struct,importlib.util,gc
import numpy as np
import bpy
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
import prepare_physical_lenses as u
start=time.monotonic();proof_path=R/'receipts/z_portable_admission_validation_v3.json';assert not proof_path.exists()
m=json.loads((R/'archives/Y_delta_verified_reorganization.json').read_text());base=R/m['base']['path'];archive=R/m['archive'];assert u.sha256(base)==m['base']['sha256'] and u.sha256(archive)==m['archive_sha256']
fd=os.memfd_create('Y_semantic_final_validation.blend')
with os.fdopen(os.dup(fd),'wb') as out:subprocess.run(['zstd','-dc','--memory=1024MiB','--patch-from='+str(base),str(archive)],stdout=out,check=True)
source=Path('/proc/self/fd/'+str(fd));assert os.fstat(fd).st_size==m['target']['bytes'] and u.sha256(source)==m['target']['sha256']
portable_path=R/'src/prepare_runoff_film_z_portable.py';spec=importlib.util.spec_from_file_location('portable_z_admission',portable_path);entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
def forbidden(*args,**kwargs):raise AssertionError('Validation-only entered model/material body')
entry.simulate_shoulder=forbidden;entry.apply=forbidden
positive=R/'receipts/z_portable_original_Y_admission_v3_qualified.json';assert not positive.exists()
sys.argv=['portable_z','--','--source',str(source),'--validate-only','--admission-receipt',str(positive)];entry.main();positive_record=json.loads(positive.read_text());assert positive_record['semantic_match'] and positive_record['actual_source_sha256']==m['target']['sha256']
# Small actual road topology requested by the parent, with no scene mutation.
fixture=R/'receipts/aa_actual_road_topology.npz'
if not fixture.exists():
    mesh=bpy.context.scene.objects['Crowned asphalt crust / longitudinal rise'].data;mesh.calc_loop_triangles()
    co=np.empty((len(mesh.vertices),3),np.float64);mesh.vertices.foreach_get('co',co.ravel())
    tri=np.empty((len(mesh.loop_triangles),3),np.int32);mesh.loop_triangles.foreach_get('vertices',tri.ravel())
    polygon=np.empty(len(mesh.loop_triangles),np.int32);mesh.loop_triangles.foreach_get('polygon_index',polygon)
    np.savez_compressed(fixture,vertexco=co,loop_triangles=tri,loop_triangle_polygon_index=polygon,polygon_count=np.array(len(mesh.polygons),np.int32))
    assert fixture.stat().st_size<10_000_000
    fixture.with_suffix('.json').write_text(json.dumps(dict(source_Y_sha256=m['target']['sha256'],mesh=mesh.name,object='Crowned asphalt crust / longitudinal rise',vertices=len(co),triangles=len(tri),polygon_count=len(mesh.polygons),npz_bytes=fixture.stat().st_size,sha256=u.sha256(fixture),keys=['vertexco','loop_triangles','loop_triangle_polygon_index','polygon_count'],coordinates_dtype='float64',topology_dtype='int32',scene_mutation=False),indent=2)+'\n')
    del co,tri,polygon;gc.collect()
rejections={}
def rejection(name,change,restore):
    change();bpy.context.view_layer.update()
    try:entry.validate_loaded_scene()
    except ValueError as exc:rejections[name]=str(exc)
    else:raise AssertionError('Semantic guard admitted deliberate '+name+' change')
    finally:restore();bpy.context.view_layer.update()
ob=bpy.context.scene.objects[u.GROUND];old=ob.data.vertices[0].co.copy();rejection('geometry',lambda:setattr(ob.data.vertices[0].co,'z',old.z+.00001),lambda:setattr(ob.data.vertices[0],'co',old))
material=next(m for m in bpy.data.materials if m.use_nodes and any(n.bl_idname=='ShaderNodeBsdfPrincipled' for n in m.node_tree.nodes));node=next(n for n in material.node_tree.nodes if n.bl_idname=='ShaderNodeBsdfPrincipled');socket=node.inputs['Roughness'];original=float(socket.default_value);rejection('material',lambda:setattr(socket,'default_value',original+.001 if original<.999 else original-.001),lambda:setattr(socket,'default_value',original))
s=bpy.context.scene;camera=s.camera;rejection('active_camera_binding',lambda:setattr(s,'camera',None),lambda:setattr(s,'camera',camera));exposure=s.view_settings.exposure;rejection('display_exposure',lambda:setattr(s.view_settings,'exposure',exposure+.01),lambda:setattr(s.view_settings,'exposure',exposure))
entry.validate_loaded_scene();gc.collect()
proof=dict(passed=True,portable_builder_sha256=u.sha256(portable_path),guard_file_sha256=entry.SEMANTIC_GUARD_FILE_SHA256,guard_helper_sha256=u.sha256(R/'src/semantic_scene_guard_z.py'),semantic_sha256=positive_record['semantic_sha256'],unchanged_source_admitted=True,geometry_change_rejected=True,material_change_rejected=True,active_camera_binding_change_rejected=True,display_exposure_change_rejected=True,
    same_semantics_different_serialized_bytes_admitted=False,optional_serialization_qualified=False,
    optional_serialization_status='Attempted external zstd payload extraction returned exit 1. No different-byte serialization is qualified; required controls rerun separately to terminal success.',
    original_Y_sha256=m['target']['sha256'],rejection_messages=rejections,
    model_executed=False,material_body_executed=False,scene_written=False,new_image_rendered=False,memfd_only=True,Blender_version=bpy.app.version_string,CPU_threads=2,elapsed_seconds=time.monotonic()-start,
    prior_failed_attempts=['receipts/z_portable_semantic_v3_validation_resources.json','receipts/z_portable_semantic_v3_retry_validation_resources.json','receipts/z_portable_semantic_v3_final_validation_resources.json'],scope='Real original Y admission and restored deliberate geometry/material/camera/display negatives. Different-byte serialization and complete fresh source regeneration remain unqualified.')
os.close(fd)
proof_path.write_text(json.dumps(proof,indent=2)+'\n');print('Z_PORTABLE_GUARD_V3_REQUIRED_PASS',json.dumps(proof),flush=True)
