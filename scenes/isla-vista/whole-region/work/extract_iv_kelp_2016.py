"""Bounded polygon extraction from the original public CDFW shapefile.

Read standard SHP/DBF fields directly; preserve multipart rings and holes.
This selects classified geographic canopy extent, not individual fronds.
"""
from pathlib import Path
import sys,struct,zipfile,json,hashlib,collections
import numpy as np
r=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(r/'geo-deps'))
from pyproj import CRS,Transformer
import shapely
from shapely.geometry import Polygon,box,mapping
from shapely.ops import unary_union,transform
folder=r/'data/coastal-kelp-2016';archive=folder/'BIO_CA_Kelp2016.zip';scene=json.loads((r/'data/full-iv-20261011/manifest.json').read_text())['sector'];origin=np.array(scene['local_origin_utm_m']);bounds=scene['utm_bounds'];to_source=Transformer.from_crs(32611,3310,always_xy=True);to_scene=Transformer.from_crs(3310,32611,always_xy=True);roi_source=box(*to_source.transform_bounds(*bounds,densify_pts=21));roi_local=box(-1300,-1300,1300,1300)
features=[];records_checked=0;source_rows=[];ring_repairs=[]
with zipfile.ZipFile(archive) as z:
 dbf=z.read('BIO_CA_Kelp2016.dbf');n,h,w=struct.unpack_from('<IHH',dbf,4);fields=[]
 for offset in range(32,h-1,32):q=dbf[offset:offset+32];fields.append((q[:11].split(b'\0')[0].decode(),chr(q[11]),q[16]))
 def attributes(index):
  row=dbf[h+index*w:h+(index+1)*w];assert len(row)==w and row[0]!=42;pos=1;values={}
  for name,kind,length in fields:
   value=row[pos:pos+length].decode().strip();pos+=length;values[name]=float(value) if kind in {'N','F'} and value else value
  return values
 with z.open('BIO_CA_Kelp2016.shp') as s:
  header=s.read(100);assert struct.unpack_from('>i',header,0)[0]==9994;assert struct.unpack_from('<ii',header,28)==(1000,5)
  while head:=s.read(8):
   number,length=struct.unpack('>ii',head);length*=2;q=s.read(44);kind=struct.unpack_from('<i',q)[0];assert kind==5;bb=struct.unpack_from('<4d',q,4);np_,nv=struct.unpack_from('<ii',q,36);remaining=length-44;records_checked+=1
   if not box(*bb).intersects(roi_source):
    while remaining:chunk=s.read(min(remaining,1_048_576));assert chunk;remaining-=len(chunk)
    continue
   b=s.read(remaining);assert len(b)==remaining;starts=np.frombuffer(b,dtype='<i4',count=np_);xy=np.frombuffer(b,dtype='<f8',count=nv*2,offset=np_*4).reshape(nv,2);ends=np.r_[starts[1:],nv];outer=[];holes=[];signed_area=0.;kept=0
   for start,end in zip(starts,ends):
    ring=xy[start:end];a=float(np.sum(ring[:-1,0]*ring[1:,1]-ring[1:,0]*ring[:-1,1])*.5);signed_area+=a
    if ring[:,0].max()<roi_source.bounds[0] or ring[:,0].min()>roi_source.bounds[2] or ring[:,1].max()<roi_source.bounds[1] or ring[:,1].min()>roi_source.bounds[3]:continue
    p=Polygon(ring)
    if not p.is_valid:
     reason=shapely.is_valid_reason(p);p=shapely.make_valid(p);delta=p.area-abs(a);assert abs(delta)<max(1e-5,abs(a)*1e-7)
     ring_repairs.append({'record':number,'ring_start':int(start),'reason':reason,'signed_ring_area_m2':a,'repaired_area_m2':p.area,'area_change_m2':delta,'method':'OGC make_valid resolves source self-touching ring topology; polygon area must remain equal within numerical tolerance.'})
    # ESRI exterior rings run clockwise; holes run counterclockwise.
    (outer if a<0 else holes).append(p);kept+=1
   if not outer:continue
   # Even/odd ring fill preserves canopy islands nested inside source holes.
   # A global union(shells)-union(holes) would incorrectly erase such islands.
   area=shapely.symmetric_difference_all(outer+holes).intersection(roi_source);attrs=attributes(number-1);full_area=-signed_area;assert abs(full_area-attrs['Shape_Area'])<max(.05,attrs['Shape_Area']*2e-6)
   local=transform(lambda x,y,z=None:(np.asarray(to_scene.transform(x,y)[0])-origin[0],np.asarray(to_scene.transform(x,y)[1])-origin[1]),area).intersection(roi_local)
   if local.is_empty:continue
   assert local.is_valid
   row={'source_record_number':number,'source_dbf_attributes':attrs,'original_record_ring_count':int(np_),'retained_intersecting_rings':kept,'original_record_area_m2':full_area,'subset_area_m2':local.area,'source_id':f'cdfw:kelp2016:record:{number}','survey_interval':'2016-09-03/2016-09-25','classification_grid_spacing_m':2,'individual_blades_sourced':False};source_rows.append(row);features.append({'type':'Feature','id':row['source_id'],'properties':row,'geometry':mapping(local)})
 assert records_checked==n
payload={'type':'FeatureCollection','coordinate_contract':scene,'features':features,'provenance':'CDFW/Sandoval & Associates September2016 classified canopy polygons, clipped and reprojected into the current scene. Original archive and source metadata retained.'};target=folder/'iv_kelp_2016_local.geojson';target.write_text(json.dumps(payload,separators=(',',':'))+'\n')
report={'passed':True,'source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'source_records_checked':records_checked,'subset_features':len(features),'classes':dict(collections.Counter(f['properties']['source_dbf_attributes']['Class_Name'] for f in features)),'class_area_m2':{c:sum(f['properties']['subset_area_m2'] for f in features if f['properties']['source_dbf_attributes']['Class_Name']==c) for c in {f['properties']['source_dbf_attributes']['Class_Name'] for f in features}},'source_ring_topology_repairs':ring_repairs,'subset_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'subset_bytes':target.stat().st_size,'horizontal_transform':to_scene.description,'horizontal_transform_accuracy_m':to_scene.accuracy,'survey_interval':'2016-09-03/2016-09-25','classification_grid_spacing_m':2,'attribution':'California Department of Fish and Wildlife (contract/database management), Sandoval & Associates LLC (collection/processing).','limitations':'Dated classified extents, not a present-day canopy map. Surface and subsurface classes remain distinct. The survey does not provide individual fronds, depth of the subsurface canopy, densities, blade dimensions, physiological state or present-day water conditions.'};(folder/'SUBSET_VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='source_ring_topology_repairs'}),flush=True)
