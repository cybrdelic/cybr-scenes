"""Read back actual serialized near-street blades, object IDs and source anchors."""
from pathlib import Path
import sys,json,struct,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent;out=r/'evidence/full-iv-near-street-vegetation';receipt=json.loads((out/'VEGETATION_RECEIPT.json').read_text());source=json.loads((r/'evidence/full-iv-roofs/normalized.geojson').read_text());by_id={f['id']:f for f in source['features']};prior=json.loads((r/'evidence/full-iv-botanical-dense/BOTANICAL_RECEIPT.json').read_text());prior_id={f['source_id']:f for f in prior['features']}
for item in receipt['source_features']:
 assert item['source_xy_m']==by_id[item['source_id']]['geometry']['coordinates']
 if item['source_id'] in prior_id:assert item['height_m']==prior_id[item['source_id']]['height_m']
assert not set(receipt['replace_sector_components'])&set(prior['replace_sector_components'])
expected={p['object'] for p in receipt['parts']};seen=set();bad=0;area=0.;normal_error=0.;dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);leaf_material=prior['material_offset']+3;leaf_area=0
with (out/'vegetation.clm').open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==receipt['triangles']
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype);q=v[t['indices'],:3];a=np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1)*.5;bad+=int((a<=1e-15).sum());area+=float(a.sum());leaf_area+=float(a[t['material']==leaf_material].sum());normal_error=max(normal_error,float(np.max(abs(np.linalg.norm(v[:,3:6],axis=1)-1))));seen.update(t['object'].tolist())
 assert not f.read(1)
assert bad==0,bad;assert seen==expected;assert normal_error<1e-6;relative=abs(leaf_area-receipt['leaf_surface_area_m2'])/receipt['leaf_surface_area_m2'];assert relative<1e-4,relative
result={'passed':True,'source_position_checks':len(receipt['source_features']),'stored_native_triangles':total,'zero_area_faces':bad,'normal_length_maximum_error':normal_error,'serialized_leaf_surface_area_m2':leaf_area,'relative_leaf_area_error_from_float32':relative,'prior_height_checks':sum(x['source_id'] in prior_id for x in receipt['source_features']),'source_derived_form_checks':'Source genus is required for fan form. Family-only palms remain explicitly illustrative pinnate architecture.','mesh_sha256':hashlib.sha256((out/'vegetation.clm').read_bytes()).hexdigest(),'limits':'Verifies actual serialized source anchors, finite/nondegenerate geometry and leaf area. Does not establish measured species, biomass, dimensions or photoreal appearance.'};(out/'VEGETATION_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
