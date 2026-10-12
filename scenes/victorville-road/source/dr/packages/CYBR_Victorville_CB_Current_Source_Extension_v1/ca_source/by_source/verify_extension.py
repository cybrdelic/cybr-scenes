"""Source/package preflight only. Does not build, load, save or render a scene."""
from pathlib import Path
import argparse,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parent
BASE_NAME='CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15.zip'
BASE_SHA='daae4846d4ef9506b01c40bfa9b1ecfd369fbd17f457d0a63c68f168a79aaa04'
BASE_BYTES=13559633
BASE_PIPELINE='5b16c6dcf685765ed2cb1c70bb55b4a535432638cb4c5c77265637aca24ddf86'
def require(ok,message):
 if not ok:raise ValueError(message)
def digest(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(base_archive,root=ROOT):
 p=Path(base_archive).resolve();require(p.stat().st_size==BASE_BYTES and digest(p)==BASE_SHA,'Required retained AV v15 archive differs')
 with zipfile.ZipFile(p) as z:
  require(z.testzip() is None,'AV archive CRC failed');template=json.loads(z.read('road_scene_r6/receipts/integrated_render_templates_av.json'))
 row=next(r for r in template['captures'] if r.get('generation')=='AV' and r.get('default_latest'));require(row['pipeline_sha256']==BASE_PIPELINE,'Wrong AV source pipeline')
 manifest=json.loads((root/'EXTENSION_MANIFEST.json').read_text())
 for rel,r in manifest['files'].items():
  f=(root/rel).resolve();require(f.is_relative_to(root.resolve()) and f.is_file() and not(root/rel).is_symlink(),'Missing or unsafe member '+rel);require(f.stat().st_size==r['bytes'] and digest(f)==r['sha256'],'Member mismatch '+rel)
 for d in (root/'snapshots').iterdir():
  m=json.loads((d/'manifest.json').read_text());require(hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()==d.name,'Snapshot identity differs')
  for n,h in m.items():require(digest(d/n)==h,'Captured source bytes differ '+n)
 return dict(passed=True,base_archive_sha256=BASE_SHA,extension_members_verified=len(manifest['files']),fresh_AV_regeneration_verified=False,combined_delta_replay_verified=False,blender_wrapper_execution_verified=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base-archive',required=True);a=p.parse_args();print(json.dumps(verify(a.base_archive),indent=2))
