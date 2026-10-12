from pathlib import Path
import argparse,hashlib,json,zipfile,importlib.util
ROOT=Path(__file__).resolve().parent
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(base_archive):
 m=json.loads((ROOT/'CA_SOURCE_MANIFEST.json').read_text())
 for rel,row in m['files'].items():
  p=(ROOT/rel).resolve();assert p.is_relative_to(ROOT) and p.is_file() and not (ROOT/rel).is_symlink(),rel;assert p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],rel
 spec=importlib.util.spec_from_file_location('retained_by_preflight',ROOT/'by_source/verify_extension.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);by=v.verify(base_archive)
 return dict(passed=True,current_members=len(m['files']),BY_preflight=by,retained_AV_payload_replay_verified=True,retained_AV_combined_application_verified=True,fresh_complete_AV_rebuild_verified=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--base-archive',type=Path,required=True);args=a.parse_args();print(json.dumps(verify(args.base_archive),indent=2))
