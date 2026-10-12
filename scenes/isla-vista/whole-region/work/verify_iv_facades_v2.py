"""Read-only checks of serialized v2 facade geometry and source identities."""
from pathlib import Path
import collections,hashlib,json,struct
import numpy as np
import shapely
from shapely.geometry import shape
R=Path(__file__).resolve().parents[1]
out=R/'evidence/full-iv-facades-v2';mesh=out/'facades.clm'
old=json.loads((R/'evidence/full-iv-facades/FACADE_RECEIPT.json').read_text());new=json.loads((out/'FACADE_RECEIPT.json').read_text())
assert {b['source_id'] for b in old['buildings']}=={b['source_id'] for b in new['buildings']}
assert old['replace_sector_components']==new['replace_sector_components']
oldstory={b['source_id']:b['stories'] for b in old['buildings']}
assert all(oldstory[b['source_id']]==b['stories'] for b in new['buildings'])
parts={p['object']:p for p in new['parts']};assert len(parts)==len(new['parts'])
features=json.loads((R/'evidence/full-iv-roofs/normalized.geojson').read_text())['features']
polygons={f['id']:shape(f['geometry']) for f in features if f['id'] in oldstory}
# Collect only roof height bounds from the actual retained serialized source.
layout=json.loads((R/'evidence/full-iv-roofs/glb-part-layout.json').read_text())
roof_map={}
for group in layout.values():
 for part in group['parts']:
  if part['part'].endswith('_roof') or '_roof_tagged_' in part['part']:
   source=next((sid for sid in oldstory if part['part'].startswith(sid.replace(':','_')+'_')),None)
   if source:roof_map[part['component']]=source
DT0=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
roof_max=collections.defaultdict(lambda:-float('inf'))
with (R/'evidence/full-iv-roofs/sector.clm').open('rb') as f:
 magic,total0,packets0=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
 for _ in range(packets0):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(f.read(nt*11),DT0)
  for obj in np.unique(t['object']):
   if int(obj) in roof_map:
    sid=roof_map[int(obj)];roof_max[sid]=max(roof_max[sid],float(v[t['indices'][t['object']==obj],2].max()))
 assert not f.read(1)
assert set(roof_max)==set(oldstory)
maximum_wall_outside_m=0.;maximum_component_outside_m=0.;maximum_roof_height_excess_m=0.

DT=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);counts=collections.Counter();normal_error=0.;normal_worst=None;uv_scale_error=0.;minarea=float('inf');total_read=0
with mesh.open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),DT);assert np.isfinite(v).all();q=v[t['indices']];total_read+=nt
  assert all(int(x) in parts for x in t['object'])
  assert set(t['material']).issubset(set(range(57,72)))
  cross=np.cross(q[:,1,:3]-q[:,0,:3],q[:,2,:3]-q[:,0,:3]);length=np.linalg.norm(cross,axis=1);minarea=min(minarea,float(length.min()/2));assert length.min()>1e-10
  expected=cross/length[:,None]
  # Saved face normal is constant per triangle; float32 positions cause tiny drift.
  error=np.linalg.norm(expected[:,None,:]-q[:,:,3:6],axis=2)
  if error.max()>normal_error:
   normal_error=float(error.max());j=int(np.argmax(error)//3);normal_worst={'vertices':q[j,:,:3].tolist(),'stored_normals':q[j,:,3:6].tolist(),'object':int(t['object'][j]),'material':int(t['material'][j]),'error':normal_error}
  uv=q[:,:,6:8];det=np.linalg.det(np.stack([uv[:,1]-uv[:,0],uv[:,2]-uv[:,0]],axis=1));assert abs(det).min()>1e-12
  counts.update(map(int,t['object']))
  for obj in np.unique(t['object']):
   sid=parts[int(obj)]['source'];selected=t['object']==obj
   xyz=q[selected,:,:3].reshape(-1,3)
   points=shapely.points(xyz[:,:2]);distance=shapely.distance(points,polygons[sid])
   maximum_component_outside_m=max(maximum_component_outside_m,float(distance.max()))
   assert distance.max()<=.081,'Assembly exceeds80mm declared sill/trim projection plus1mm float32/angled-corner allowance'
   if int(t['material'][selected][0]) in {58,60,62,64,66}:
    maximum_wall_outside_m=max(maximum_wall_outside_m,float(distance.max()))
    assert distance.max()<.00015,'Wall plane outside source footprint'
   excess=float(xyz[:,2].max())-roof_max[sid]
   maximum_roof_height_excess_m=max(maximum_roof_height_excess_m,excess)
   assert excess<.00015,'Roof/assembly exceeds source upper envelope'

 assert not f.read(1)
assert total_read==total==new['triangles']
print('NORMAL_DIAGNOSTIC',json.dumps(normal_worst),flush=True)
assert normal_error<1e-6
assert all(counts[k]==p['triangles'] for k,p in parts.items())
assert sum(b['retained_roof_edge_segments'] for b in new['buildings'])>2000
assert all('non-service' in b['frontage'][0]['method'] for b in new['buildings'] if b['frontage'])
report={'passed':True,'target_sha256':hashlib.sha256(mesh.read_bytes()).hexdigest(),'source_buildings_exact':True,'source_floor_counts_exact':True,'replaced_source_wall_components_exact':True,'source_building_count':len(new['buildings']),'maximum_serialized_wall_outside_source_plan_m':maximum_wall_outside_m,'maximum_serialized_component_projection_outside_source_plan_m':maximum_component_outside_m,'maximum_height_excess_above_serialized_source_roof_m':maximum_roof_height_excess_m,'triangles':total,'unique_objects':len(parts),'minimum_serialized_triangle_area_m2':minarea,'maximum_saved_vs_recomputed_normal_vector_error':normal_error,'finite_positions_normals_uv_colors':True,'nondegenerate_uvs':True,'native_material_range':[57,71],'source_receipt_sha256':hashlib.sha256((out/'FACADE_RECEIPT.json').read_bytes()).hexdigest(),'limits':'Checks identity, serialized topology/attributes and numerical health. Closed member and opposed reveal normals are independently checked in test_iv_facade_assemblies.py; the whole building mesh is not a watertight interior solid.'}
(out/'SERIALIZED_GEOMETRY_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
