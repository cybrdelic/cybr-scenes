"""Resolve retained path spellings to the reviewed installed namespace package."""
from pathlib import Path
import hashlib,json
from cybrlight.scene_compat import runtime
R=Path(__file__).resolve().parents[1];package=Path(runtime.__file__).resolve().parent
manifest=json.loads((package/'DEPENDENCY_MANIFEST.json').read_text())
for name,row in manifest['files'].items():
 data=(package/name).read_bytes()
 assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],name
for name,target in [('work/iv-component-runtime/cybr_light',package),('work/cybr-light/data',package/'data')]:
 p=R/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() or p.is_symlink():assert p.resolve()==target.resolve(),p
 else:p.symlink_to(target,target_is_directory=True)
print(json.dumps({'installed_package':str(package),'reviewed_source_hash':manifest['executed_source_hash'],'source_bytes_verified':True}))
