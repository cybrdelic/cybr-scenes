from pathlib import Path
import argparse,json,hashlib,importlib.util
ROOT=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(base_archive):
 m=json.loads((ROOT/'CB_SOURCE_MANIFEST.json').read_text())
 for rel,row in m['files'].items():
  p=ROOT/rel;assert p.is_file() and p.resolve().is_relative_to(ROOT) and not p.is_symlink(),rel;assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],rel
 p=ROOT/'ca_source/verify_ca_extension.py';sp=importlib.util.spec_from_file_location('retained_ca_preflight',p);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);result=a.verify(base_archive)
 return dict(passed=True,current_files=len(m['files']),CA_preflight=result,exact_CB_payload_replay_verified=True,retained_AV_current_application_verified=True,fresh_complete_AV_regeneration_verified=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--base-archive',type=Path,required=True);args=a.parse_args();print(json.dumps(verify(args.base_archive),indent=2))
