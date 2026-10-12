"""Run one retained authoring script against the reviewed installed LIGHT runtime."""
from pathlib import Path
import hashlib,json,runpy,sys
import cybrlight.scene_compat as compatibility
from cybrlight.scene_compat import runtime,finishing
package=Path(runtime.__file__).parent
manifest=json.loads((package/'DEPENDENCY_MANIFEST.json').read_text())
for name,row in manifest['files'].items():
 data=(package/name).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],name
sys.modules['cybr_light']=compatibility;sys.modules['cybr_light.runtime']=runtime;sys.modules['cybr_light.finishing']=finishing
R=Path(__file__).resolve().parents[1];script=(R/'work'/sys.argv[1]).resolve();assert script.parent==R/'work' and script.suffix=='.py'
sys.argv=[str(script),*sys.argv[2:]];sys.path.insert(0,str(script.parent));print('RETAINED_SCRIPT',script.name,'installed LIGHT',manifest['executed_source_hash'],flush=True);runpy.run_path(str(script),run_name='__main__')
