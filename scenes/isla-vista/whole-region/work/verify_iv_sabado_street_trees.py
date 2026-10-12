"""Validate actual near-street serialization and source anchors before capture."""
from pathlib import Path
import hashlib,json,struct
import numpy as np
r=Path(__file__).resolve().parent.parent;o=r/'evidence/full-iv-sabado-street-trees'
j=json.loads((o/'VEGETATION_RECEIPT.json').read_text());regional=json.loads((r/'evidence/full-iv-regional-vegetation/REGIONAL_VEGETATION_RECEIPT.json').read_text());old={x['source_id']:x for x in regional['trees']}
for row in j['source_features']:
 prior=old[row['source_id']];assert row['source_xy_m']==prior['source_xy_m'];assert row['height_m']==prior['retained_height_parameter_m']
source_of={x['object']:x['source'] for x in j['parts']};bounds={x['source_id']:[np.full(3,np.inf),np.full(3,-np.inf)] for x in j['source_features']}
seen=set();bad=0;min_area=np.inf;normal_error=0;dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
with (o/'vegetation.clm').open('rb') as f:
 magic,total,n=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==j['triangles']
 for _ in range(n):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype)
  assert np.isfinite(v).all() and t['indices'].max()<nv and t['material'].max()<331 and t['object'].max()<(1<<24)
  q=v[t['indices'],:3];area=.5*np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1);bad+=int((area<=1e-15).sum());min_area=min(min_area,float(area.min()));normal_error=max(normal_error,float(abs(np.linalg.norm(v[:,3:6],axis=1)-1).max()))
  for obj in np.unique(t['object']):
   seen.add(int(obj));xyz=q[t['object']==obj].reshape(-1,3);b=bounds[source_of[int(obj)]];b[0]=np.minimum(b[0],xyz.min(0));b[1]=np.maximum(b[1],xyz.max(0))
 assert not f.read(1)
assert bad==0 and seen==set(source_of) and normal_error<1e-6
camera=np.array([519.2692708155955,-291.7469537849538]);inside=[k for k,b in bounds.items() if np.all(camera>=b[0][:2]) and np.all(camera<=b[1][:2])]
assert not inside,inside
result={'passed':True,'mapped_root_and_retained_height_parameter_checks':len(j['source_features']),'triangles':total,'zero_area_faces':bad,'minimum_serialized_triangle_area_m2':min_area,'normal_length_max_error':normal_error,'mesh_sha256':hashlib.file_digest((o/'vegetation.clm').open('rb'),'sha256').hexdigest(),'serialized_tree_bounds_m':{k:[v.tolist() for v in b] for k,b in bounds.items()},'camera_inside_tree_axis_aligned_bounds':inside,'limits':'Source root positions and prior height parameters are retained. New botanical silhouettes are authored, with measured serialized bounds recorded; no surveyed leaf dimensions or exact species is inferred for generic tree points.'}
(o/'VEGETATION_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
