"""Validate the serialized lagoon component without changing its geometry."""
from pathlib import Path
import sys,json,struct,hashlib
r=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(r/'geo-deps'));import numpy as np
out=r/'evidence/full-iv-lagoon-context';rec=json.loads((out/'LAGOON_CONTEXT_RECEIPT.json').read_text());ids={x['object'] for x in rec['parts']};seen=set();bad=0;smallest=1e99;maxn=0;mat=set();dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
with (out/'lagoon_context.clm').open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==rec['triangles']
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(f.read(nt*11),dtype);assert np.isfinite(v).all() and t['indices'].max()<nv and t['material'].max()<331 and t['object'].max()<16777216;q=v[t['indices'],:3].astype(float);area=np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1)*.5;bad+=int((area<=1e-14).sum());smallest=min(smallest,float(area.min()));maxn=max(maxn,float(abs(np.linalg.norm(v[:,3:6],axis=1)-1).max()));seen.update(t['object']);mat.update(t['material'])
 assert not f.read(1)
assert seen==ids and bad==0 and maxn<1e-6
result={'passed':True,'triangles':total,'parts':len(ids),'packets':packets,'minimum_serialized_triangle_area_m2':smallest,'zero_area_triangles':bad,'maximum_normal_length_error':maxn,'material_ids':sorted(map(int,mat)),'mesh_sha256':hashlib.file_digest((out/'lagoon_context.clm').open('rb'),'sha256').hexdigest(),'geographic_and_height_basis':'Complete UCSB lagoon polygon and retained projected frame, with separately identified USGS hydroflattened export level. No current water measurement.'}
(out/'SERIALIZED_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
