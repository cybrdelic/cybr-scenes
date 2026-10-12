"""Repair float32 UV collapse without changing any recovered contact geometry.

The new metric path finish has a 0.32 m period on a 1.25 m/unit chart.
Rebase each path triangle by whole periods before float32 serialization.
Source positions, normals, tint, materials, objects and triangle order remain
exact. This is a chart-precision adapter, not a terrain or footprint repair.
"""
from pathlib import Path
import argparse,hashlib,json,struct
import numpy as np
from cybr_light import Meshlets
R=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=R/'evidence/full-iv-contact/contact.clm');parser.add_argument('--output',type=Path,default=R/'evidence/full-iv-path-uv-rebased');args=parser.parse_args()
source=args.source.resolve()
OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
target=OUT/'contact.clm'
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
def rows(path):
 with path.open('rb') as f:
  magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
  for _ in range(packets):
   nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(f.read(nt*11),dtype)
   q=v[t['indices']];a=np.zeros((nt,36),'<f4');a[:,:9]=q[:,:,:3].reshape(nt,9);a[:,9:18]=q[:,:,3:6].reshape(nt,9);a[:,18]=t['material'];a[:,19]=t['object'];a[:,20:26]=q[:,:,6:8].reshape(nt,6);a[:,26:35]=q[:,:,8:11].reshape(nt,9)
   yield a
  assert not f.read(1)
def invariant_hash(path):
 h=hashlib.sha256();count=0
 for a in rows(path):
  h.update(np.ascontiguousarray(np.concatenate([a[:,:20],a[:,26:35]],axis=1),dtype='<f4').tobytes());count+=len(a)
 return h.hexdigest(),count
receipt=json.loads((source.parent/'CONTACT_RECEIPT.json').read_text())
edges={p['object'] for p in receipt['parts'] if p['name'].endswith('_closed_edges')}
changed=0;edge_count=0;maximum_phase_error=0.;cursor={};parity={}
with Meshlets(target) as writer:
 for a in rows(source):
  selected=a[:,18]==11
  if selected.any():
   position=a[selected,:9].reshape(-1,3,3).astype(float)
   uv=position[:,:,:2]/1.25
   selected_rows=np.flatnonzero(selected)
   for j,k in enumerate(selected_rows):
    oid=int(a[k,19])
    if oid not in edges:continue
    xyz=position[j];direction=xyz[1,:2]-xyz[0,:2];length=float(np.linalg.norm(direction))
    arc=cursor.get(oid,0.);u=np.full(3,arc)
    if length>0:u+=(xyz[:,:2]-xyz[0,:2])@(direction/length)
    uv[j]=np.c_[u,xyz[:,2]]/1.25
    old_parity=parity.get(oid,0);parity[oid]=1-old_parity
    if old_parity:cursor[oid]=arc+length
    edge_count+=1
   origin=np.floor(uv[:,:1,:]/.256)*.256
   local=(uv-origin).astype('<f4')
   maximum_phase_error=max(maximum_phase_error,float(np.max(abs(local.astype(float)+origin-uv))))
   a[selected,20:26]=local.reshape(-1,6);changed+=int(selected.sum())
  writer.add(a)
assert all(v==0 for v in parity.values())
before,count=invariant_hash(source);after,actual=invariant_hash(target)
assert before==after and count==actual==writer.triangles
record={'passed':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'triangles':count,'path_triangles_rebased':changed,'vertical_edge_triangles_with_physical_arclength_height_chart':edge_count,'positions_normals_tints_materials_objects_and_order_sha256':before,'all_non_uv_fields_exact':True,'chart_metres_per_unit':1.25,'texture_period_metres':.32,'periodic_rebase_uv_units':.256,'maximum_float32_phase_error_uv':maximum_phase_error,'qualification':'Original source geometry is unchanged. Path tops use serialized world XY; closed construction edges retain the authored cumulative quantized arclength and physical-height chart. Both receive integer texture-period translations before float32 conversion. Source object classification, not normal thresholds, selects the chart.'}
(OUT/'UV_REBASE_RECEIPT.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
