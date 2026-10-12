from pathlib import Path
import json,struct,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent;out=r/'evidence/full-iv-del-playa-walks';receipt=json.loads((out/'WALKS_RECEIPT.json').read_text());dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);seen=set();areas={};bad=0;uv_min=float('inf');gram_min=float('inf');normal_error=0.;bump=0
with (out/'walks.clm').open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==receipt['triangles']
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype);assert np.isfinite(v).all();q=v[t['indices'],:3];cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);length=np.linalg.norm(cross,axis=1);bad+=int((length<=2e-15).sum());normal_error=max(normal_error,float(np.max(abs(np.linalg.norm(v[:,3:6],axis=1)-1))));seen.update(t['object'].tolist())
  for ob in np.unique(t['object']):areas[int(ob)]=areas.get(int(ob),0.)+float(abs(cross[t['object']==ob,2]).sum()/2)
  mask=t['material']==186;bump+=int(mask.sum())
  if mask.any():
   uv=v[t['indices'][mask],6:8];d=uv[:,1]-uv[:,0];e=uv[:,2]-uv[:,0];det=d[:,0]*e[:,1]-d[:,1]*e[:,0];uv_min=min(uv_min,float(np.min(abs(det))));assert np.min(abs(det))>1e-14
   a=q[mask,1]-q[mask,0];b=q[mask,2]-q[mask,0];u=(a*e[:,1,None]-b*d[:,1,None])/det[:,None];w=(b*d[:,0,None]-a*e[:,0,None])/det[:,None];gram=np.sum(u*u,1)*np.sum(w*w,1)-np.sum(u*w,1)**2;gram_min=min(gram_min,float(gram.min()));assert gram.min()>1e-20
 assert not f.read(1)
assert seen=={p['object'] for p in receipt['parts']} and bad==0 and normal_error<1e-6
area_error=abs(areas[13000000]+areas[13000001]-receipt['walk_area_m2']);assert area_error<.01
record={'passed':True,'triangles':total,'parts':len(seen),'zero_area_faces':bad,'normal_length_max_error':normal_error,'metric_bump_triangles_checked':bump,'minimum_abs_serialized_UV_determinant':uv_min,'minimum_metric_Gram_determinant':gram_min,'serialized_horizontal_area_error_m2':area_error,'original_sidewalk_source_ids':receipt['source_sidewalk_ids'],'restored_crossing_area_m2':receipt['restored_driveway_crossing_area_m2'],'mesh_sha256':hashlib.sha256((out/'walks.clm').read_bytes()).hexdigest(),'limits':'Source-aligned bounded construction with estimated width/heights/apron ramps. Retained terrain triangles provide contact; this does not validate engineering or accessibility compliance.'};(out/'WALKS_VALIDATION.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
