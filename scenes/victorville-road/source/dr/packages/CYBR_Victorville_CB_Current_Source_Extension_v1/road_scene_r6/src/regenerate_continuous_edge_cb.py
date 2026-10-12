"""Recreate the exact bounded CB edge payload from qualified CA inputs.
No .blend save, rendering or original data mutation. Allow25MB output if writing.
"""
from pathlib import Path
import argparse,hashlib,json,io
import numpy as np
from continuous_edge_top_cb import build
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--ca-data',type=Path,required=True);a.add_argument('--height',type=Path,required=True);a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--verify-without-writing',action='store_true');args=a.parse_args();out=args.output_dir.resolve();assert not out.exists();out.mkdir(parents=True)
 pins=json.loads((ROOT/'audits/edge_continuity_cb/edge_payload_step2.json').read_text());fixture=args.ca_data/'actual_road_fixture.npz';ca=args.ca_data/'extension_payload.npz';assert sha(fixture)=='82e6a784715fde999764e5f01f57de75f35ac120867934e536de92460a279313';assert sha(ca)=='d1c7a52a2ca1845aa377eca3679135159e3c71762658a39488db0aa1cb472fd3'
 arrays,report=build(ROOT,args.height,step=2,fixture_path=fixture,ca_payload_path=ca);buf=io.BytesIO();np.savez_compressed(buf,**arrays);actual=hashlib.sha256(buf.getbuffer()).hexdigest();assert actual==pins['payload_sha256'];assert report['source_POINT_fields_sha256']==pins['source_POINT_fields_sha256']
 if not args.verify_without_writing:(out/'edge_payload_step2.npz').write_bytes(buf.getbuffer())
 report.update(payload_sha256=actual,compressed_bytes=len(buf.getbuffer()),exact_payload_reproduced=True,payload_written=not args.verify_without_writing,fresh_complete_AV_regeneration_verified=False);(out/'CB_REGENERATION.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':main()
