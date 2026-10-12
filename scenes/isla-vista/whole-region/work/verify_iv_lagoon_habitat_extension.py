"""Verify the real serialized habitat extension and source seam."""
from pathlib import Path
import hashlib,json,struct
import numpy as np
r=Path(__file__).resolve().parent.parent;o=r/'evidence/full-iv-lagoon-habitat-extension';j=json.loads((o/'HABITAT_EXTENSION_RECEIPT.json').read_text());seen=set();bad=0;min_area=np.inf;normal_error=0;dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
with (o/'habitat_extension.clm').open('rb') as f:
 magic,total,n=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==j['triangles']
 for _ in range(n):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype);assert np.isfinite(v).all() and t['indices'].max()<nv and t['material'].max()<331 and t['object'].max()<(1<<24)
  p=v[t['indices'],:3];area=.5*np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1);bad+=int((area<=1e-15).sum());min_area=min(min_area,float(area.min()));normal_error=max(normal_error,float(abs(np.linalg.norm(v[:,3:6],axis=1)-1).max()));seen.update(map(int,t['object']))
 assert not f.read(1)
assert bad==0 and seen=={x['object'] for x in j['parts']} and normal_error<1e-6 and j['terrain_seam_max_error_m']<1e-9
result={'passed':True,'triangles':total,'zero_area_faces':bad,'minimum_serialized_area_m2':min_area,'normal_length_max_error':normal_error,'source_seam_max_error_m':j['terrain_seam_max_error_m'],'mesh_sha256':hashlib.file_digest((o/'habitat_extension.clm').open('rb'),'sha256').hexdigest(),'source_coverage_sha256':j['source_coverage_sha256'],'limits':'Numerical source and geometry check only. Visibility, water appearance and modeled-extent concealment require the actual grounded camera capture.'}
(o/'HABITAT_EXTENSION_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
