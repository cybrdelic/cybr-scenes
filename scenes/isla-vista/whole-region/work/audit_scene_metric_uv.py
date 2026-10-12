"""Preflight actual serialized metric-height faces before spending a render."""
from pathlib import Path
import sys,json,struct,shlex,numpy as np
scene=Path(sys.argv[1]).resolve();metrics=set();meshes=[]
for line in scene.read_text().splitlines():
 q=shlex.split(line)
 if not q:continue
 if q[0]=='metric_bump':metrics.add(int(q[1]))
 if q[0] in {'meshlets','meshlets_excluding'}:meshes.append(((scene.parent/q[1]).resolve(),set(map(int,q[3:])) if q[0]=='meshlets_excluding' else set()))
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);rows=[];bad=[]
for path,skip in meshes:
 tested=0;degenerate=0
 with path.open('rb') as f:
  magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
  for packet in range(packets):
   nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),dtype='<f4').reshape(nv,11);t=np.frombuffer(f.read(nt*11),dtype=dtype);mask=np.array([int(m) in metrics and int(o) not in skip for m,o in zip(t['material'],t['object'])],dtype=bool)
   if not np.any(mask):continue
   tt=t[mask];q=v[tt['indices']].astype(float);e1=q[:,1,:3]-q[:,0,:3];e2=q[:,2,:3]-q[:,0,:3];valid=np.linalg.norm(np.cross(e1,e2),axis=1)>1e-14;degenerate+=int((~valid).sum());d1=q[:,1,6:8]-q[:,0,6:8];d2=q[:,2,6:8]-q[:,0,6:8];det=d1[:,0]*d2[:,1]-d1[:,1]*d2[:,0];uvok=abs(det)>1e-14;safe=np.where(uvok,det,1);a=(e1*d2[:,1,None]-e2*d1[:,1,None])/safe[:,None];b=(e2*d1[:,0,None]-e1*d2[:,0,None])/safe[:,None];gram=(a*a).sum(1)*(b*b).sum(1)-(a*b).sum(1)**2;failure=valid&(~uvok|(gram<=1e-20));tested+=int(valid.sum())
   for j in np.flatnonzero(failure)[:max(0,20-len(bad))]:bad.append({'mesh':path.name,'packet':packet,'object':int(tt['object'][j]),'material':int(tt['material'][j]),'uv_determinant':float(det[j]),'metric_gram_determinant':float(gram[j]),'vertices':q[j,:,:3].tolist(),'uv':q[j,:,6:8].tolist()})
  assert not f.read(1)
 rows.append({'mesh':str(path),'metric_faces_tested':tested,'geometrically_degenerate_faces_ignored':degenerate});print('AUDITED',path.name,tested,'bad_samples',len(bad),flush=True)
record={'scene':str(scene),'metric_material_ids':sorted(metrics),'meshes':rows,'failed_face_samples':bad,'passed':not bad};scene.with_name(scene.stem+'_metric_uv_audit.json').write_text(json.dumps(record,indent=2)+'\n');print('METRIC_UV_AUDIT',json.dumps(record),flush=True)
if bad:raise SystemExit(1)
