"""Remove unreachable packet storage while preserving active triangle order."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import sys
import tempfile
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/iv-component-runtime')]
import numpy as np
from cybr_light.runtime import publish
out=r/'evidence/full-iv-active-meshlets'
audit=json.loads((out/'ACTIVE_MESHLET_AUDIT.json').read_text())
assert shutil.disk_usage(out).free>(1<<30)+audit['estimated_filtered_output_bytes']*2+20_000_000
rows=[];dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
for row in audit['meshes']:
 # A wholly excluded file is omitted, with no replacement file needed.
 if row['active_triangles'] and row['unused_vertex_bytes']<10_000_000:continue
 src=r/row['source'];dst=out/(src.parent.name+'__'+src.name)
 record={k:v for k,v in row.items() if k!='excluded_objects'}
 if not row['active_triangles']:
  record['replacement']=None;rows.append(record);continue
 assert not dst.exists(),str(dst)
 skip=np.asarray(row['excluded_objects'],dtype='u4')
 digest=hashlib.sha256();source_digest=hashlib.sha256();count=packets=0
 with tempfile.NamedTemporaryFile(prefix='iv-active-',suffix='.clm',delete=False) as f:
  temp=Path(f.name);f.write(struct.pack('<4sQI',b'CLM1',row['active_triangles'],row['active_packets']))
  with src.open('rb') as g:
   header=g.read(16);source_digest.update(header);magic,total,n=struct.unpack('<4sQI',header)
   assert magic==b'CLM1'
   for _ in range(n):
    header=g.read(4);nv,nt=struct.unpack('<HH',header);vb,tb=g.read(nv*44),g.read(nt*11);source_digest.update(header+vb+tb)
    t=np.frombuffer(tb,dtype);positions=np.searchsorted(skip,t['object']);keep=(positions==len(skip))|(skip[np.minimum(positions,len(skip)-1)]!=t['object']);k=int(keep.sum())
    if not k:continue
    payload=struct.pack('<HH',nv,k)+vb+t[keep].tobytes();f.write(payload);digest.update(payload);count+=k;packets+=1
   assert not g.read(1)
 assert count==row['active_triangles'] and packets==row['active_packets'] and digest.hexdigest()==row['active_packet_sha256']
 publish(temp,dst)
 # Independent readback of the actual saved bytes.
 actual=hashlib.sha256()
 with dst.open('rb') as f:
  magic,nt,np_=struct.unpack('<4sQI',f.read(16));assert (magic,nt,np_)==(b'CLM1',count,packets)
  for b in iter(lambda:f.read(8<<20),b''):actual.update(b)
 assert actual.hexdigest()==row['active_packet_sha256'] and dst.stat().st_size==row['filtered_bytes']
 record.update(replacement=str(dst.relative_to(r)),source_sha256=source_digest.hexdigest(),active_payload_exact=True)
 rows.append(record)
result={'passed':True,'meshes':rows,'primitive_order_preserved':True,'active_vertex_attributes_byte_exact':True,'engine_change':False,
 'qualification':'Only excluded triangles and wholly unreachable packets are removed from generated input. Kept packet vertex arrays and active triangle bytes/order are exact; unused vertices in partially kept packets remain. Source files and preceding views are preserved. A matched native raw-pixel gate is still required.'}
(out/'ACTIVE_MESHLET_BUILD.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
