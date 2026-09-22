from pathlib import Path
import json,hashlib,argparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--other',type=Path,default=ROOT.parent/'v3_delivery_stage'/ROOT.name)
OTHER=parser.parse_args().other.resolve()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(4*1024*1024):h.update(b)
 return h.hexdigest()
items=[]
for sub in ['assets/built_v3/scene.meshbin']+[f'assets/built_v3/textures/{k}.cvtex' for k in range(5)]+['cathedral_v3']:
 a=sha(ROOT/sub);b=sha(OTHER/sub);items.append({'file':sub,'production_sha256':a,'isolated_rebuild_sha256':b,'byte_identical':a==b})
report={'method':'Copied only source, original inputs and notices into an isolated project directory; ran its build.sh; compared generated mesh, five converted texture files and compiled executable','original_conversation_archives_required':False,'files':items,'passed':all(r['byte_identical'] for r in items)}
(ROOT/'verification_v3/rebuild.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
assert report['passed']
