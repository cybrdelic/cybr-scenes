"""Validate the serialized kelp, bottom and water, rather than only inputs."""
import json,struct,hashlib,numpy as np
from iv_coastal_life import r
out=r/'evidence/full-iv-coastal-life';dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);rows=[]
for filename in ['kelp.clm','bottom.clm','ocean_transport.clm']:
 degenerate=0;count=0;area=0.;minimum=1e99;normal_error=0.;materials=set();objects=set();lo=np.full(3,np.inf);hi=-lo
 with (out/filename).open('rb') as f:
  magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
  for _ in range(packets):
   nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype);assert np.isfinite(v).all() and np.max(t['indices'])<nv;norm=np.linalg.norm(v[:,3:6],axis=1);normal_error=max(normal_error,float(abs(norm-1).max()));q=v[t['indices'],:3];cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);a=np.linalg.norm(cross,axis=1)*.5;minimum=min(minimum,float(a.min()));degenerate+=int((a<=1e-15).sum());count+=nt;area+=a.sum();lo=np.minimum(lo,q.min((0,1)));hi=np.maximum(hi,q.max((0,1)));materials.update(map(int,t['material']));objects.update(map(int,t['object']))
  assert count==total and not f.read(1)
 assert not degenerate and normal_error<1e-6
 rows.append({'file':filename,'sha256':hashlib.sha256((out/filename).read_bytes()).hexdigest(),'triangles':count,'meshlets':packets,'native_zero_area_faces':degenerate,'smallest_serialized_triangle_area_m2':minimum,'surface_area_m2':float(area),'maximum_normal_length_error':normal_error,'bounds':[lo.tolist(),hi.tolist()],'materials':sorted(materials),'object_count':len(objects)})
 if filename=='ocean_transport.clm':assert objects=={14000000} and materials=={190}
record={'passed':True,'meshes':rows,'scope':'Actual float32 serialized geometry is finite and has no native zero-area faces; normals are unit. Ocean boundary has one medium identity. This is geometric validation, not measured plant detail, optical validation or a simulation.'};(out/'SERIALIZED_VALIDATION.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
