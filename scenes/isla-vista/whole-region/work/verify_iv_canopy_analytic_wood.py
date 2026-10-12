"""Independently validate serialized foliage identity and wood geometry limits."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import struct
import sys

r=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(r/'geo-deps'))
import numpy as np
source=r/'evidence/full-iv-canopy-supported-crowns'
out=r/'evidence/full-iv-canopy-analytic-wood'
original=json.loads((source/'CANOPY_SUPPORTED_CROWNS_RECEIPT.json').read_text())
receipt=json.loads((out/'ANALYTIC_WOOD_RECEIPT.json').read_text())
rows={x['source_id']:x for x in original['trees']}
objects={x['object']:x['source'] for x in original['parts']}
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])

def packets(path):
 with path.open('rb') as f:
  magic,total,n=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
  count=0
  for _ in range(n):
   header=f.read(4);nv,nt=struct.unpack('<HH',header)
   vb,tb=f.read(nv*44),f.read(nt*11)
   v=np.frombuffer(vb,'<f4').reshape(nv,11);t=np.frombuffer(tb,dtype)
   assert np.isfinite(v).all() and t['indices'].max()<nv
   count+=nt
   yield header+vb+tb,v[t['indices']],t
  assert count==total and not f.read(1)

def file_sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()

low,high={},{}
def bounds(obj,a,b):
 sid=objects[obj];low[sid]=np.minimum(low.get(sid,a),a);high[sid]=np.maximum(high.get(sid,b),b)

pending=Counter();retained_count=leaf_count=0
for payload,q,t in packets(out/'retained_wood.clm'):
 assert (t['material']==39).all()
 for tri,obj in zip(q,t['object']):
  pending[(int(obj),tri.tobytes())]+=1
  bounds(int(obj),tri[:,:3].min(0),tri[:,:3].max(0));retained_count+=1
leaf_hash=hashlib.sha256()
for payload,q,t in packets(out/'exact_foliage.clm'):
 assert (t['material']==42).all();leaf_hash.update(payload);leaf_count+=len(q)
 for obj in np.unique(t['object']):
  xyz=q[t['object']==obj,:,:3];bounds(int(obj),xyz.min((0,1)),xyz.max((0,1)))
source_leaf_hash=hashlib.sha256()
for payload,q,t in packets(source/'canopy_supported_crowns.clm'):
 if (t['material']==42).all():source_leaf_hash.update(payload)
 else:
  assert (t['material']==39).all()
  for tri,obj in zip(q,t['object']):
   k=(int(obj),tri.tobytes())
   if pending.get(k,0):
    pending[k]-=1
    if not pending[k]:del pending[k]
assert not pending,'Retained wood triangle attributes changed'
assert leaf_hash.hexdigest()==source_leaf_hash.hexdigest()==receipt['foliage_packet_sha256']
count=0;max_height_excess=max_xy_excess=0.;minimum_length=float('inf');maximum_diameter=0.
with (out/'analytic_wood.cys').open() as f:
 for line in f:
  q=line.split();assert q[0]=='cylinder' and q[1]=='39' and len(q)==13
  obj=int(q[2]);values=np.asarray(q[3:],float);assert np.isfinite(values).all()
  a,b,radius=values[:3],values[3:6],values[6]
  assert radius>0 and np.array_equal(values[7:],np.zeros(3))
  axis=b-a;length=np.linalg.norm(axis);axis/=length
  extent=radius*np.sqrt(np.maximum(0.,1-axis*axis))
  lo,hi=np.minimum(a,b)-extent,np.maximum(a,b)+extent
  prior_lo,prior_hi=np.asarray(rows[objects[obj]]['candidate_bounds_m'])
  excess=np.maximum(prior_lo-lo,hi-prior_hi)
  max_height_excess=max(max_height_excess,float(excess[2]));max_xy_excess=max(max_xy_excess,float(excess[:2].max()))
  bounds(obj,lo,hi);minimum_length=min(minimum_length,float(length));maximum_diameter=max(maximum_diameter,2*radius);count+=1
height_error=0.
for sid,row in rows.items():
 lo,hi=np.asarray(row['previous_bounds_m'])
 height_error=max(height_error,abs(float(low[sid][2]-lo[2])),abs(float(high[sid][2]-hi[2])))
assert count==receipt['analytic_cylinders'] and retained_count==receipt['retained_wood_triangles'] and leaf_count==receipt['foliage_triangles']
assert height_error<1e-5 and max_height_excess<1e-7 and max_xy_excess<1e-7 and maximum_diameter<=.08
result={'passed':True,'foliage_packets_byte_identical':True,'foliage_packet_sha256':leaf_hash.hexdigest(),
 'retained_wood_triangle_attributes_exact':True,'retained_wood_triangles':retained_count,
 'foliage_triangles':leaf_count,'analytic_cylinders':count,'maximum_visible_height_bound_error_m':height_error,
 'maximum_cylinder_height_excess_m':max_height_excess,'maximum_cylinder_xy_bound_excess_m':max_xy_excess,
 'minimum_cylinder_length_m':minimum_length,'maximum_cylinder_diameter_m':maximum_diameter,
 'source_root_height_tags_retained':all(x['source_xy_m']==rows[x['source_id']]['source_xy_m'] and x['source_height_tag_m']==rows[x['source_id']]['source_height_tag_m'] for x in receipt['trees']),
 'files':{n:file_sha(out/n) for n in ['exact_foliage.clm','retained_wood.clm','analytic_wood.cys']},
 'limits':'Constant-radius subpixel wood approximates original taper and faceted normals. Exact foliage support validation transfers by packet byte identity; source dates and correspondence uncertainty remain unchanged. Actual visual and runtime evidence remains required.'}
assert result['source_root_height_tags_retained']
(out/'SERIALIZED_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
