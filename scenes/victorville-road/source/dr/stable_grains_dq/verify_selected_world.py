"""Require bitwise unchanged payload for common world IDs and the frozen macro."""
from pathlib import Path
import numpy as np,json,hashlib
O=Path(__file__).resolve().parent;macro=np.load(O/'ACTUAL_CATALOG.npz');files=[p for p in [O/'VIEW_normal_2000.npz',O/'VIEW_macro_1800.npz']if p.exists()];assert files
rows=[]
def compare(a,b,label):
 ids,ia,ib=np.intersect1d(a['id'],b['id'],return_indices=True);fields={}
 for k in ['xy','prototype','yaw','precap_z','z','role','cover','static_cap']:
  assert np.array_equal(a[k][ia],b[k][ib]),(label,k);fields[k]=hashlib.sha256(np.ascontiguousarray(a[k][ia]).tobytes()).hexdigest()
 return {'comparison':label,'common_ids':len(ids),'bitwise_payload_equal':True,'common_id_sha256':hashlib.sha256(ids.tobytes()).hexdigest(),'field_sha256':fields}
loaded=[np.load(p)for p in files]
for p,a in zip(files,loaded):rows.append(compare(macro,a,'retained macro versus '+p.name))
if len(loaded)==2:rows.append(compare(*loaded,'normal versus macro current camera subsets'))
rep={'status':'passed','actual_blender_geometry_check_is_separate':True,'comparisons':rows,'view_file_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in files}};(O/'WORLD_VIEW_IDENTITY.json').write_text(json.dumps(rep,indent=2)+'\n');print(json.dumps(rep),flush=True)
