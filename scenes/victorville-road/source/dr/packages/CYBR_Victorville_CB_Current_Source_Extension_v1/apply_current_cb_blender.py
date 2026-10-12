"""Fresh admitted AV -> BY/CA -> continuous CB edge. No automatic save or render."""
from pathlib import Path
import sys,argparse,json,hashlib,importlib.util
ROOT=Path(__file__).resolve().parent
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(base_archive,z_admission,ca_payload,cb_payload,output_dir,av_scene):
 import bpy
 out=Path(output_dir).resolve();assert not out.exists();out.mkdir(parents=True)
 path=ROOT/'ca_source/apply_current_ca_blender.py';spec=importlib.util.spec_from_file_location('ca_current_wrapper',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 before=m.run(base_archive,z_admission,ca_payload,out/'CA',av_scene)
 r6=ROOT/'road_scene_r6';sys.path.insert(0,str(r6/'relief_correction'));sys.path.insert(0,str(r6/'src'))
 from continuous_edge_top_adapter_cb import apply,bind_current_edge_material
 cfg=dict(revision=1,step=2,payload=str(Path(cb_payload).resolve()),pins=str(r6/'audits/edge_continuity_cb/edge_payload_step2.json'),clearance=str(r6/'audits/edge_continuity_cb/ground_clearance.json'))
 for key in ('payload','pins','clearance'):cfg[key+'_sha256']=sha(cfg[key])
 assert cfg['payload_sha256']=='aef0aee3894aa18f3353faffc4f3f824e99f953779cbd8933dce5578daaee5ee'
 cb=apply(bpy.context.scene,cfg,out);binding=bind_current_edge_material(bpy.context.scene,out)
 # The CB preview boundary is matched to this native stride. No arbitrary LOD.
 sys.path.insert(0,str(ROOT/'captured_pipeline'))
 from preview_mesh_cull import asphalt_lod
 lod=asphalt_lod(bpy.context.scene,{'asphalt_preview_grid_stride':2})
 result=dict(CA=before,CB=cb,final_material=binding,native_tile_preview_lod=lod,source_scene_saved=False,rendered=False,original_mountains_retained=True,fresh_complete_AV_rebuild_verified=False,scope='Current bounded CB representation; geometry remains metric. Optional texture mip, camera and conservative offscreen culling are captured separately and not applied here.')
 (out/'CURRENT_CB_APPLICATION.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__)
 for key in ('base-archive','z-admission','ca-payload','cb-payload','output-dir','av-scene'):a.add_argument('--'+key,required=True)
 args=a.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(run(**vars(args)),indent=2))
