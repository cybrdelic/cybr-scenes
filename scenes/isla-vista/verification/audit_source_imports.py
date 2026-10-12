"""Small scene/dependency import and material-callable probe; never renders.
Run from the scene root after fetching inputs and installing dependencies.
"""
import ast,hashlib,json,pathlib,sys
import numpy as np
from scipy.ndimage import gaussian_filter
root=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));sys.path.insert(0,str(root/'work'))
import replay
runtime=replay.runtime_contract()
import rebuild_lagoon_v11b as scene
import architecture_helpers,cybr_ucsb.ingest,cybr_ucsb.geometry,cybrlight.scene_compat.runtime
f=scene.features()
report={'runtime_contract':runtime,'source_features':len(f),'source_height_samples':scene.source_height(np.array([[1388,-489],[0,0]])).tolist(),'module_origins':{m.__name__:str(pathlib.Path(m.__file__).relative_to(root)) if pathlib.Path(m.__file__).is_relative_to(root) else 'installed dependency' for m in [architecture_helpers,cybr_ucsb.ingest,cybr_ucsb.geometry,cybrlight.scene_compat.runtime]},'legacy_module_imported':any(n=='cybr_light' or n.startswith('cybr_light.') or n=='cybr_terrain' or n.startswith('cybr_terrain.') for n in sys.modules)}
assert not report['legacy_module_imported']
sys.path.insert(0,str(root/'original/cybr-material-finishes/source'))
import generate_materials as gm
n=64;x=((np.arange(n,dtype=np.float32)+.5)/n)[None,:];y=x.T
report['material_functions']={}
for name,count in [('plaster',6),('linen',7)]:
 values=getattr(gm,name)(x,y,n);assert len(values)==count
 assert all(np.isfinite(v).all() for v in values)
 report['material_functions'][name]={'function_module':getattr(gm,name).__module__,'channels':len(values),'finite':True,'height_range':[float(np.min(values[1])),float(np.max(values[1]))]}
assert gm.plaster is gm.GENERATORS[8] and gm.linen is gm.GENERATORS[9]
report['retained_input_count']=len(json.loads((root/'INPUTS.json').read_text())['files'])
report['passed']=True
(root/'verification/PUBLIC_SOURCE_IMPORT_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
