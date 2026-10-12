"""Resolve retained runtime aliases and separately licensed repository CIE data."""
from pathlib import Path
import hashlib,json
from cybrlight.scene_compat import runtime
CIE_SHA256='fa663e3535a7e0763a745993a1f0a192eb0275ac46ad2d1befd7626841e713c1'

def bind(path,target,obsolete=None):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.is_symlink():
  if path.resolve()==target.resolve():return 'unchanged'
  if obsolete is not None and path.resolve()==obsolete.resolve():
   path.unlink();path.symlink_to(target,target_is_directory=True);return 'repaired historical runtime-data alias'
  raise RuntimeError('Unexpected existing source alias; refusing replacement: '+str(path))
 if path.exists():
  if path.resolve()==target.resolve():return 'unchanged'
  raise RuntimeError('Unexpected existing source directory; refusing replacement: '+str(path))
 path.symlink_to(target,target_is_directory=True);return 'created'

def link_runtime_paths(root,package):
 # The snapshot wheel deliberately contains runtime source only. CIE remains
 # a distinct CC BY-SA 4.0 repository input, accompanied by official metadata.
 data=root.parent/'work/cybr-light/data'
 observer=data/'CIE_xyz_1931_2deg.csv'
 if not observer.is_file() or hashlib.sha256(observer.read_bytes()).hexdigest()!=CIE_SHA256:
  raise RuntimeError('Missing or changed separately retained CIE observer table')
 metadata=json.loads((root.parent/'verification/CIE_SOURCE_METADATA.json').read_text())
 if metadata['official_sha256']!=CIE_SHA256 or metadata['local_sha256']!=CIE_SHA256:
  raise RuntimeError('CIE input metadata no longer matches the pinned source')
 result={}
 result['runtime']=bind(root/'work/iv-component-runtime/cybr_light',package)
 result['observer']=bind(root/'work/cybr-light/data',data,obsolete=package/'data')
 assert (root/'work/cybr-light/data/CIE_xyz_1931_2deg.csv').is_file()
 return {'links':result,'observer_sha256':CIE_SHA256,'observer_source':str(observer.resolve())}

def main():
 root=Path(__file__).resolve().parents[1];package=Path(runtime.__file__).resolve().parent
 manifest=json.loads((package/'DEPENDENCY_MANIFEST.json').read_text())
 for name,row in manifest['files'].items():
  data=(package/name).read_bytes()
  assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],name
 result=link_runtime_paths(root,package)
 print(json.dumps({'installed_package':str(package),'reviewed_source_hash':manifest['executed_source_hash'],'source_bytes_verified':True,**result}))

if __name__=='__main__':main()
