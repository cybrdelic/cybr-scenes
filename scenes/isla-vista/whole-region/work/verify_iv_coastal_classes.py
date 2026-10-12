"""Validate class provenance, retained footprint and serialized ground contact."""
from pathlib import Path
import sys,json,struct,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'whole-iv-vendor']:sys.path.insert(0,str(p))
import shapely
from iv_shared_ground import SharedGround
out=r/'evidence/full-iv-coastal-classes';receipt=json.loads((out/'COASTAL_CLASSES_RECEIPT.json').read_text());ground=SharedGround(r/'evidence/full-iv-roofs/measured-terrain-state.npz')
actual=json.loads((out/'class_coverage.geojson').read_text());prior=json.loads((r/'evidence/full-iv-landcover-contact/coverage.geojson').read_text());aa=[shapely.geometry.shape(f['geometry']) for f in actual['features']];bb=[shapely.geometry.shape(f['geometry']) for f in prior['features']]
changed=shapely.union_all(aa).symmetric_difference(shapely.union_all(bb)).area;assert changed<.001,changed
overlap=sum(x.area for x in aa)-shapely.union_all(aa).area;assert abs(overlap)<.001,overlap
objects={p['object'] for p in receipt['parts'] if p['name'].endswith('_support') or '_boundary_' in p['name']}
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);maximum=0.;tested=0;zero_area=0;zero_area_by_object={}
with (out/'coastal.clm').open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==receipt['triangles']
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype);mask=np.isin(t['object'],list(objects));q=v[t['indices'],:3];degenerate=np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1)*.5<=1e-15;zero_area+=int(degenerate.sum())
  for ob in t['object'][degenerate]:zero_area_by_object[int(ob)]=zero_area_by_object.get(int(ob),0)+1
  if not np.any(mask):continue
  q=v[np.unique(t['indices'][mask])];maximum=max(maximum,float(np.max(abs(q[:,2]-ground.height(q[:,:2])-.018))));tested+=len(q)
 assert not f.read(1)
assert maximum<.0001,maximum
counts={row['class']:row['source_feature_count'] for row in receipt['classes']};assert counts=={'beach':6,'scrub':48,'woodland':30,'natural_grass':21,'lawn':1002,'park_or_garden':175},counts
names={p['object']:p['name'] for p in receipt['parts']};assert all(names[o].startswith('natural_grass_tufts') for o in zero_area_by_object)
record={'passed':True,'source_class_counts':counts,'changed_source_coverage_m2':changed,'overlapping_class_area_m2':overlap,'ground_contact_vertices_checked':tested,'maximum_float32_error_from18mm_TIN_support_m':maximum,'stored_geometry_triangles':total,'native_nonzero_area_triangles':total-zero_area,'native_culled_zero_area_grass_tip_faces':zero_area,'precision_limit':'Thin taper tips can collapse in world-coordinate float32 positions. The native loader discards those zero-area faces; the remaining true-scale blades and aggregate canopy response are retained. This regional tier does not resolve individual blade tips at the overview camera.','limits':'Validates source classification/coverage and support contact. Does not validate authored plant species, density, season, reflectance or photoreal appearance.'}
(out/'CLASS_VALIDATION.json').write_text(json.dumps(record,indent=2)+'\n');print('COASTAL_CLASS_VALIDATION',json.dumps(record),flush=True)
