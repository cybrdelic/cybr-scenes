"""Small pinned numerical cache for AB renders, guarded by actual sampled inputs.
Cache reuse skips only the exact finite-stock solve. Geometry and projection
validation still execute for every render. Old input mismatch always rejects.
"""
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
import hashlib,json,numpy as np
from visible_shoulder_flow_ad import ContextResult,inventory_mobility
FIELDS=('height_delta_m','retained_deposit_by_class_m','surface_fraction','lag_exposure','flow_strength')
def input_manifest(x,y,z,spec):
    def sha(a):return hashlib.sha256(np.ascontiguousarray(a,dtype='<f8').tobytes()).hexdigest()
    root=Path(__file__).resolve().parent
    return dict(x_sha256=sha(x),y_sha256=sha(y),actual_triangle_z_sha256=sha(z),spec=asdict(spec),solver_sha256=hashlib.sha256((root/'flow_sediment_model_z.py').read_bytes()).hexdigest(),adapter_sha256=hashlib.sha256((root/'visible_shoulder_flow_ad.py').read_bytes()).hexdigest())
def write(path,result):
    path=Path(path)
    if path.exists():raise FileExistsError('Preserve existing numerical cache')
    meta=dict(inputs=input_manifest(result.x_m,result.y_m,result.source_z_m,result.spec),context_receipt=result.receipt)
    np.savez_compressed(path,x_m=result.x_m,y_m=result.y_m,source_z_m=result.source_z_m,metadata=np.array(json.dumps(meta,sort_keys=True)),**{key:getattr(result.flow,key) for key in FIELDS})
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path,x,y,z,spec,expected_sha256):
    path=Path(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=expected_sha256:raise ValueError('Pinned numerical cache hash mismatch')
    with np.load(path,allow_pickle=False) as cache:
        meta=json.loads(str(cache['metadata']));current=input_manifest(x,y,z,spec)
        if json.dumps(meta['inputs'],sort_keys=True)!=json.dumps(current,sort_keys=True):raise ValueError('Cache belongs to different actual terrain/grid/model/spec')
        fields={key:cache[key].copy() for key in FIELDS}
    for value in fields.values():
        if value.shape[:2]!=z.shape or not np.isfinite(value).all():raise ValueError('Nonfinite/misshaped cache field')
    fields['receipt']=meta['context_receipt']['solver']
    result=ContextResult(x.copy(),y.copy(),z.copy(),SimpleNamespace(**fields),inventory_mobility(x,y,spec),spec,meta['context_receipt'])
    return result
