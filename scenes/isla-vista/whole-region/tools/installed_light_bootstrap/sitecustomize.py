"""Explicit retained-name adapter for child processes in the recovery build."""
import hashlib,json,sys
from pathlib import Path
import cybrlight.scene_compat as compatibility
from cybrlight.scene_compat import runtime,finishing
root=Path(runtime.__file__).parent
manifest=json.loads((root/'DEPENDENCY_MANIFEST.json').read_text())
for name,row in manifest['files'].items():
 data=(root/name).read_bytes()
 if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise RuntimeError('Installed LIGHT source mismatch: '+name)
sys.modules['cybr_light']=compatibility
sys.modules['cybr_light.runtime']=runtime
sys.modules['cybr_light.finishing']=finishing
