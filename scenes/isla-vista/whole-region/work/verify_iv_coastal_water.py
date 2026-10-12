"""Check the actual serialized ocean surface and smooth normal correspondence."""
from pathlib import Path
import json,struct,numpy as np
r=Path(__file__).resolve().parent.parent;out=r/'evidence/full-iv-coastal-water';receipt=json.loads((out/'WATER_RECEIPT.json').read_text());mid=receipt['material_offset'];dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);area=0.;lowest=1e9;highest=-1e9;min_dot=1.;normal_error=0.;count=0;degenerate=0
with (out/'water.clm').open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1' and total==receipt['triangles']
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(f.read(nt*11),dtype);q=v[t['indices']];e=q[:,1,:3]-q[:,0,:3];g=q[:,2,:3]-q[:,0,:3];cross=np.cross(e,g);length=np.linalg.norm(cross,axis=1);area+=float(np.abs(cross[:,2]).sum()*.5);degenerate+=int((length<=2e-15).sum());mask=(t['material']==mid)&(length>2e-15)
  if not np.any(mask):continue
  qq=q[mask];nn=qq[:,:,3:6];normal_error=max(normal_error,float(abs(np.linalg.norm(nn,axis=2)-1).max()));gn=cross[mask]/length[mask,None];min_dot=min(min_dot,float(np.sum(gn[:,None,:]*nn,axis=2).min()));lowest=min(lowest,float(qq[:,:,2].min()));highest=max(highest,float(qq[:,:,2].max()));count+=int(mask.sum())
 assert not f.read(1)
expected=sum(row['area_m2'] for row in receipt['coverage']);assert abs(area-expected)<1.;assert normal_error<1e-6 and min_dot>.97
amplitude=sum(w['amplitude_m'] for w in receipt['waves']);assert lowest>=.11-amplitude-.0001 and highest<=.11+amplitude+.0001
record={'passed':True,'total_stored_triangles':total,'ocean_faces_checked':count,'native_culled_zero_area_faces':degenerate,'projected_area_m2':area,'difference_from_source_water_union_area_m2':area-expected,'ocean_height_range_m':[lowest,highest],'normal_length_max_error':normal_error,'minimum_smooth_normal_geometric_normal_dot':min_dot,'maximum_normal_deviation_degrees':float(np.degrees(np.arccos(min_dot))),'interpretation':'Smooth normals remain close to the corresponding resolved wave triangles; no unrelated broad terrain normals. Source water footprint area is preserved within float32 coordinate precision.','limits':'This does not validate observed sea state, bathymetry, breaking-wave dynamics or exact ocean reflectance.'}
(out/'WATER_VALIDATION.json').write_text(json.dumps(record,indent=2)+'\n');print('WATER_VALIDATION',json.dumps(record),flush=True)
