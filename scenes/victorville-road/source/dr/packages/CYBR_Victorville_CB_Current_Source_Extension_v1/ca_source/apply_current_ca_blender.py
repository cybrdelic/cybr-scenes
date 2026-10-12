"""Apply the current BY material/daylight extension followed by CA physical relief.
Explicit fresh AV file load; no save/render. A fresh complete AV rebuild is still unverified.
"""
from pathlib import Path
import sys,json,argparse,hashlib,importlib.util
ROOT=Path(__file__).resolve().parent
EXPECTED_PAYLOAD='d1c7a52a2ca1845aa377eca3679135159e3c71762658a39488db0aa1cb472fd3'
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(base_archive,z_admission,payload,output_dir,av_scene):
 import bpy
 out=Path(output_dir).resolve();assert not out.exists(),'Fresh output directory required';payload=Path(payload).resolve();assert digest(payload)==EXPECTED_PAYLOAD,'Regenerated CA payload differs; do not weaken the source guard'
 by=ROOT/'by_source';sys.path.insert(0,str(by));spec=importlib.util.spec_from_file_location('captured_by_apply_wrapper',ROOT/'apply_by_with_fresh_load.py');wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
 # This independently retains all strict AV build/admission/material guards.
 by_result=wrapper.run(base_archive,z_admission,out/'by_materials',variant='candidate',with_aw=False,fresh_source=av_scene)
 ca=ROOT/'road_scene_r6';sys.path.insert(0,str(ca/'relief_correction'));sys.path.insert(0,str(ca/'src'))
 from metric_pavement_extension_ca import apply
 pins=ca/'audits/metric_extension_ca/source_array_pins.json'
 cfg=dict(revision=1,payload=str(payload),payload_sha256=EXPECTED_PAYLOAD,pins=str(pins),pins_sha256=digest(pins))
 ca_result=apply(bpy.context.scene,cfg,out)
 report=dict(BY=by_result,CA=ca_result,scene_saved=False,rendered=False,original_mountains_retained=True,fresh_complete_AV_rebuild_verified=False,scope='Current source application, before any optional preview LOD. Regenerate payload from the same unedited AV scene before applying BY/CA.')
 (out/'CURRENT_CA_APPLICATION.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--base-archive',required=True);a.add_argument('--av-scene',required=True);a.add_argument('--z-admission',required=True);a.add_argument('--payload',required=True);a.add_argument('--output-dir',required=True);args=a.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(run(**vars(args)),indent=2))
