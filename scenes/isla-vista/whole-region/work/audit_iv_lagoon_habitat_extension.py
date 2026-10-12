"""Recover complete retained OSM habitat polygons across the old tile boundary."""
from pathlib import Path
import hashlib,json,sys
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/cybr-iv-full/src')]
import shapely
from shapely.geometry import Polygon,LineString,Point,box,mapping
from shapely.ops import polygonize,unary_union,nearest_points
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import load_osm,arcgis_geometry,layer_rows,DEM
out=r/'evidence/full-iv-lagoon-habitat-extension';out.mkdir(exist_ok=True)
print('LAGOON_HABITAT_AUDIT admitted',flush=True)
frame=Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame
elements,nodes,conflicts=load_osm(r/'data/full-iv-20261011')
source=json.loads((r/'evidence/full-iv-coastal-classes/COASTAL_CLASSES_RECEIPT.json').read_text())
lag=json.loads((r/'evidence/full-iv-lagoon-context/LAGOON_CONTEXT_RECEIPT.json').read_text());extent=box(*lag['extension_bounds_m'])
result=[];rejected=[]
for kind in ['beach','scrub','woodland','natural_grass']:
 for record in source['source_records'][kind]:
  prefix,typ,identifier=record['id'].split(':');element=elements.get((typ,identifier))
  try:
   if typ=='way':
    refs=[n.get('ref') for n in element.findall('nd')];assert refs[0]==refs[-1];geom=Polygon([nodes[q] for q in refs])
   else:
    outer=[];inner=[]
    for member in element.findall('member'):
     if member.get('type')!='way':continue
     way=elements[('way',member.get('ref'))];refs=[n.get('ref') for n in way.findall('nd')];(inner if member.get('role')=='inner' else outer).append(LineString([nodes[q] for q in refs]))
    geom=unary_union(list(polygonize(unary_union(outer)))).difference(unary_union(list(polygonize(unary_union(inner)))))
   geom=shapely.make_valid(frame.project_geometry(geom))
   if not geom.intersects(extent):continue
   clipped=geom.intersection(extent)
   if clipped.area<1:continue
   result.append({'type':'Feature','id':record['id'],'properties':{'class':kind,'source_properties':record['properties'],'full_source_area_m2':geom.area,'extension_area_m2':clipped.area},'geometry':mapping(geom)})
  except (KeyError,AssertionError,AttributeError) as e:rejected.append({'source':record['id'],'reason':type(e).__name__})
(out/'SOURCE_COVERAGE.geojson').write_text(json.dumps({'type':'FeatureCollection','features':result})+'\n')
# Choose the closest point of a retained actual mapped path to the proposed
# western-bank camera. Polygon interiors are retained, not guessed roads.
near=[];probe=Point(990,-380)
for row in layer_rows(r/'data/lagoon-extension-20261011','footpaths'):
 geom=frame.project_geometry(arcgis_geometry(row['geometry']));distance=geom.distance(probe)
 if distance<30:
  p=nearest_points(geom,probe)[0];near.append({'attributes':row['attributes'],'distance_m':distance,'nearest_xy_m':list(p.coords[0]),'geometry':mapping(geom)})
dem=DEM(r/'data/lagoon-extension-20261011/dem.tif',frame)
for p in near:p['dataset_ground_m']=float(dem.sample(*p['nearest_xy_m']))
report={'source':'Full retained OSM feature rings, recovered before original tile clipping; no new polygon invention.','extension_bounds_m':lag['extension_bounds_m'],'features':[{k:v for k,v in f.items() if k!='geometry'} for f in result],'rejected':rejected,'near_proposed_western_bank_paths':sorted(near,key=lambda x:x['distance_m']),'coverage_file_sha256':hashlib.file_digest((out/'SOURCE_COVERAGE.geojson').open('rb'),'sha256').hexdigest()}
(out/'SOURCE_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'features':[(f['id'],f['properties']['class'],f['properties']['extension_area_m2']) for f in result],'rejected':rejected,'near_paths':[{k:v for k,v in x.items() if k!='geometry'} for x in sorted(near,key=lambda x:x['distance_m'])[:5]]}),flush=True)
