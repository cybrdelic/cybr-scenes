"""Measured seafloor and one connected dielectric ocean identity.

The measured heights are sampled onto the retained ocean triangulation. No
vertical registration to the OSM shoreline or authored tide is silently applied.
"""
from pathlib import Path
import json,struct,hashlib,numpy as np
from iv_coastal_life import r,Bathymetry,state
from cybr_light import Meshlets
out=r/'evidence/full-iv-coastal-life';bathy=Bathymetry()
old=r/'evidence/full-iv-coastal-water/water.clm'
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
water=Meshlets(out/'ocean_transport.clm');bottom=Meshlets(out/'bottom.clm')
positions=hashlib.sha256();old_positions=hashlib.sha256();area=0.;emerged_area=0.;heights=[];ocean_objects=set()
with old.open('rb') as stream:
 magic,total,packets=struct.unpack('<4sQI',stream.read(16));assert magic==b'CLM1'
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',stream.read(4));v=np.frombuffer(stream.read(nv*44),'<f4').reshape(nv,11);tri=np.frombuffer(stream.read(nt*11),dtype);mask=tri['material']==state['material_offset']
  if not np.any(mask):continue
  tri=tri[mask];p=v[tri['indices']].copy();ocean_objects.update(map(int,tri['object']));records=np.zeros((len(tri),36),'<f4');records[:,:9]=p[:,:,:3].reshape(-1,9);records[:,9:18]=p[:,:,3:6].reshape(-1,9);records[:,18]=190;records[:,19]=14000000;records[:,20:26]=p[:,:,6:8].reshape(-1,6);records[:,26:35]=p[:,:,8:11].reshape(-1,9)
  old_positions.update(p[:,:,:3].tobytes());positions.update(records[:,:9].reshape(-1,3,3).tobytes());water.add(records)
  q=p[:,:,:3].astype(float);z=bathy.sample(q[:,:,:2].reshape(-1,2)).reshape(-1,3);heights.extend(z.ravel().tolist());cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);projected=abs(cross[:,2])*.5;area+=projected.sum();emerged_area+=projected[np.mean(z-q[:,:,2],axis=1)>0].sum();q[:,:,2]=z;cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);length=np.linalg.norm(cross,axis=1);keep=length>2e-15;normal=cross[keep]/length[keep,None];assert np.all(normal[:,2]>0)
  records=records[keep].copy();records[:,:9]=q[keep].reshape(-1,9);records[:,9:18]=np.repeat(normal[:,None,:],3,axis=1).reshape(-1,9);records[:,18]=189;records[:,19]=14000001;bottom.add(records)
 assert not stream.read(1)
water.__exit__(None,None,None);bottom.__exit__(None,None,None)
assert positions.hexdigest()==old_positions.hexdigest()
record={'passed':True,'water_triangles':water.triangles,'bottom_triangles':bottom.triangles,'water_geometry_unchanged':True,'ordered_ocean_position_sha256':positions.hexdigest(),'ocean_projected_area_m2':float(area),'bottom_above_authored_water_centroid_area_m2':float(emerged_area),'bottom_elevation_percentiles_m':np.percentile(heights,[0,1,10,50,90,99,100]).tolist(),'replace_old_ocean_objects':sorted(ocean_objects),'water_object':14000000,'bottom_object':14000001,'water_material':190,'bottom_material':189,'source_raster_sha256':hashlib.sha256((r/'data/coastal-coned-20261011/coned_native_1m_iv_subset.tif').read_bytes()).hexdigest(),'datum':'CoNED NAVD88 metres retained; horizontal NAD83/WGS84 operation reported accuracy4m. Existing OSM shore and authored mean water0.11m are not a surveyed tidal registration.','resolution':'Bilinear native1m heights sampled on retained approximately5.08m ocean triangles. Flat triangle normals derive from the actual sampled mesh.','limits':'Bottom reflectance is estimated homogeneous mineral sediment; source does not classify underwater substrate. Exposed portions are retained measured elevations, not forced below the authored water. One water object identity ensures that native dielectric medium entry and exit match across meshlet batches.'}
(out/'BOTTOM_RECEIPT.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
