"""Check whether retained nested OSM roof tags cover the matched UCSB footprint."""
from pathlib import Path
import sys,json,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src']:sys.path.insert(0,str(p))
import shapely
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import load_osm
base=r/'evidence/full-iv-roofs';features=json.loads((base/'normalized.geojson').read_text())['features'];sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);elements,nodes,conflicts=load_osm(r/'data/full-iv-20261011');rows=[]
for feature in features:
 if feature['properties']['category']!='building':continue
 props=feature['properties']['source_properties'];match=props.get('osm_match',{});tags=match.get('tags',{});kind=tags.get('roof:shape','').lower()
 if kind not in {'gabled','hipped','pyramidal','skillion'}:continue
 source_id=match['id'];_,type_,id_=source_id.split(':');row={'target_id':feature['id'],'source_id':source_id,'roof_shape':kind,'retained_roof_tags':{k:v for k,v in tags.items() if k.startswith('roof:')},'name':props.get('name',props.get('BUILDINGID'))}
 if type_!='way':row.update(accepted=False,reason='Relation geometry requires a separate full multipolygon audit.');rows.append(row);continue
 element=elements[(type_,id_)];refs=[n.get('ref') for n in element.findall('nd')]
 if refs[0]!=refs[-1] or any(q not in nodes for q in refs):row.update(accepted=False,reason='Incomplete or open source footprint.');rows.append(row);continue
 source=shapely.make_valid(sector.frame.project_geometry(shapely.Polygon([nodes[q] for q in refs]))).intersection(sector.clip);target=shapely.geometry.shape(feature['geometry']);intersection=source.intersection(target).area;source_fraction=intersection/source.area;target_fraction=intersection/target.area;iou=intersection/source.union(target).area;accepted=min(source_fraction,target_fraction)>=.90
 row.update(source_version=element.get('version'),source_timestamp=element.get('timestamp'),source_area_m2=source.area,target_area_m2=target.area,source_overlap_fraction=source_fraction,target_overlap_fraction=target_fraction,intersection_over_union=iou,accepted=accepted,reason='Both footprints overlap at least90%; roof tag is a whole-building candidate, with ridge/pitch still estimated.' if accepted else 'Mismatch may represent only a subbuilding or different footprint; do not transfer roof form to the full UCSB polygon.')
 rows.append(row)
out=r/'evidence/full-iv-roof-provenance';out.mkdir(exist_ok=True);report={'candidate_count':len(rows),'accepted_count':sum(row['accepted'] for row in rows),'criterion':'At least90% of each independent footprint lies in their intersection. This checks coverage, not exact ridge topology, current roof condition, height, pitch or finish.','rows':rows};(out/'NESTED_ROOF_MATCH_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'candidate_count':report['candidate_count'],'accepted_count':report['accepted_count'],'accepted_shapes':{k:sum(x['accepted'] and x['roof_shape']==k for x in rows) for k in ['gabled','hipped','pyramidal','skillion']},'rejected':[{k:x[k] for k in ['target_id','source_id','name','reason']} for x in rows if not x['accepted']]}),flush=True)
