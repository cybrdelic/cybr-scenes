"""Recreate the CA acceleration payload from a user-owned assembled AV scene.
No image textures are generated or borrowed; the exact existing data is read.
This command does not render or alter the input scene. Allow ~90 MB new disk.
"""
from pathlib import Path
import argparse,hashlib,io,json,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--av-scene',type=Path,required=True);a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--blender',default='blender');a.add_argument('--verify-payload-without-writing',action='store_true');args=a.parse_args();out=args.output_dir.resolve();assert not out.exists(),'Fresh output directory required';out.mkdir(parents=True)
 export=ROOT/'audits/metric_extension_ca/export_source_fixture.py'
 subprocess.run([args.blender,'-b','-t','1','--python-exit-code','1','--python',str(export),'--','--source',str(args.av_scene.resolve()),'--output-folder',str(out)],check=True)
 meta=json.loads((out/'actual_road_fixture.json').read_text());p=np.load(out/'actual_road_fixture.npz');pins=json.loads((ROOT/'audits/metric_extension_ca/source_array_pins.json').read_text())
 for key,wanted in pins.items():assert hashlib.sha256(p[key].tobytes()).hexdigest()==wanted,('Actual AV semantic source array differs; do not weaken guard',key)
 from metric_extension_math_ca import build
 result,record=build(p,meta);expected=json.loads((ROOT/'audits/metric_extension_ca/extension_payload.json').read_text())['payload_sha256']
 if args.verify_payload_without_writing:
  buf=io.BytesIO();np.savez_compressed(buf,**result);actual=hashlib.sha256(buf.getbuffer()).hexdigest();bytecount=buf.getbuffer().nbytes;del buf
 else:
  target=out/'extension_payload.npz';np.savez_compressed(target,**result);actual=digest(target);bytecount=target.stat().st_size
 assert actual==expected,('Payload byte replay differs; do not substitute it silently',actual,expected)
 record.update(payload_sha256=actual,payload_bytes=bytecount,exact_retained_payload_reproduced=True,payload_written=not args.verify_payload_without_writing,fresh_AV_source_rebuild_verified=False,source_scene_sha256=digest(args.av_scene));(out/'REGENERATION_CA.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
if __name__=='__main__':main()
