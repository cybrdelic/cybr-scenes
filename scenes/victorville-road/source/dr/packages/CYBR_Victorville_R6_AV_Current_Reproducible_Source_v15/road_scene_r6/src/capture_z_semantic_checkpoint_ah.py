"""Capture strict Z source admission for portable component replay; no scene save."""
from pathlib import Path
import bpy,sys,json,hashlib,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
import semantic_scene_guard_z as guard
import prepare_physical_lenses as base
start=time.monotonic();source=R/'preview/road_r6_z_runoff_film.blend';expected='29a2e1ca28867182554594981482e704ccbc97d9fb2806b48bc0c06f8375231a'
assert base.sha256(source)==expected
manifest=R/'receipts/z_semantic_source_guard_ah.json';proof=R/'receipts/z_semantic_admission_proof_ah.json'
assert not manifest.exists() and not proof.exists()
bpy.ops.wm.open_mainfile(filepath=str(source));snapshot=guard.scene_snapshot(bpy)
record=dict(source_sha256=expected,snapshot=snapshot,semantic_sha256=guard.digest_record(snapshot),helper_sha256=base.sha256(R/'src/semantic_scene_guard_z.py'),base_helper_sha256=base.sha256(R/'src/prepare_physical_lenses.py'))
manifest.write_text(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n');assert guard.verify_scene(bpy,record)==record['semantic_sha256']
rejections={}
def reject(name):
 try:guard.verify_scene(bpy,record)
 except ValueError as error:rejections[name]=str(error)
 else:raise AssertionError('Deliberate '+name+' change passed admission')
obj=bpy.context.scene.objects['Crowned asphalt crust / longitudinal rise'];mesh=obj.data;co=mesh.vertices[0].co.copy();mesh.vertices[0].co.z+=.001;mesh.update();reject('road_geometry_1mm');mesh.vertices[0].co=co;mesh.update();assert guard.verify_scene(bpy,record)==record['semantic_sha256']
mat=obj.data.materials[0];bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');socket=bs.inputs['Roughness'];old=socket.default_value;socket.default_value=.137 if old!=.137 else .238;reject('material_graph_default');socket.default_value=old;assert guard.verify_scene(bpy,record)==record['semantic_sha256']
result=dict(passed=True,source_sha256=expected,manifest_sha256=base.sha256(manifest),semantic_sha256=record['semantic_sha256'],helper_sha256=record['helper_sha256'],base_helper_sha256=record['base_helper_sha256'],unchanged_source_admitted=True,geometry_mutation_rejected=True,material_mutation_rejected=True,rejections=rejections,different_serialized_bytes_qualified=False,complete_clean_rebuild_verified=False,scene_saved=False,rendered=False,elapsed_seconds=time.monotonic()-start)
proof.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
