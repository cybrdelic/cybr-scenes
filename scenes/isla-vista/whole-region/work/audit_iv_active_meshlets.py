"""Count inactive serialized storage without changing the selected scene."""
from pathlib import Path
import hashlib
import json
import shlex
import struct
import sys
r=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(r/'geo-deps'))
import numpy as np
source=r/'evidence/full-iv-canopy-analytic-wood-overview/candidate.cys'
out=r/'evidence/full-iv-active-meshlets';out.mkdir(exist_ok=True)
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
rows=[]
print('AUDIT_SOURCE_SHA256',hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),flush=True)
with source.open() as scene:
 for line in scene:
  if not line.startswith('meshlets_excluding '):continue
  q=shlex.split(line);path=(source.parent/q[1]).resolve();skip=np.sort(np.array(list(map(int,q[3:])),dtype='u4'));assert len(skip)==int(q[2])
  digest=hashlib.sha256();kept_bytes=16;active=packets_kept=unused_vertices=partial=0
  with path.open('rb') as f:
   magic,total,n=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
   for _ in range(n):
    header=f.read(4);nv,nt=struct.unpack('<HH',header);vb,tb=f.read(nv*44),f.read(nt*11);t=np.frombuffer(tb,dtype)
    positions=np.searchsorted(skip,t['object']);keep=(positions==len(skip)) | (skip[np.minimum(positions,len(skip)-1)]!=t['object']);k=int(keep.sum())
    if not k:unused_vertices+=nv;continue
    packets_kept+=1;active+=k;partial+=int(k!=nt)
    payload=struct.pack('<HH',nv,k)+vb+t[keep].tobytes();digest.update(payload);kept_bytes+=len(payload)
  rows.append({'source':str(path.relative_to(r)),'source_bytes':path.stat().st_size,'source_triangles':total,'active_triangles':active,'excluded_triangles':total-active,'source_packets':n,'active_packets':packets_kept,'partially_filtered_packets':partial,'filtered_bytes':kept_bytes if active else 0,'unused_vertex_bytes':unused_vertices*44,'active_packet_sha256':digest.hexdigest(),'excluded_objects':skip.astype(int).tolist()})
summary={'scene_source':str(source.relative_to(r)),'meshes':rows,'total_unused_vertex_bytes':sum(x['unused_vertex_bytes'] for x in rows),'estimated_filtered_output_bytes':sum(x['filtered_bytes'] for x in rows if x['unused_vertex_bytes']>=10_000_000)}
(out/'ACTIVE_MESHLET_AUDIT.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='meshes'}));print(json.dumps([{k:v for k,v in row.items() if k!='excluded_objects'} for row in rows],indent=2),flush=True)
