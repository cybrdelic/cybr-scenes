"""Source-anchored close street camera for a genuinely changed generic facade."""
from pathlib import Path
import argparse,hashlib,json,re,shlex,sys
import numpy as np
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/'geo-deps'),str(R/'work'),str(R/'whole-iv-vendor')]
from shapely.geometry import shape,Point
from shapely.geometry.polygon import orient
from iv_shared_ground import SharedGround
from cybr_light import Scene,render
p=argparse.ArgumentParser();p.add_argument('--spp',type=int,default=32);p.add_argument('--variant',choices=['v2','original'],default='v2');p.add_argument('--prepare-only',action='store_true');a=p.parse_args();assert a.spp in [16,32,64]
source_id='osm:way:42753147'
features=json.loads((R/'evidence/full-iv-roofs/normalized.geojson').read_text())['features'];byid={x['id']:x for x in features}
receipt=json.loads((R/'evidence/full-iv-facades-v2/FACADE_RECEIPT.json').read_text());row=next(x for x in receipt['buildings'] if x['source_id']==source_id)
assert row['stories']==2 and row['family']['name']=='paired_slider'
polygon=orient(shape(byid[source_id]['geometry']),sign=1.)
front=row['frontage'][0];coords=np.asarray(polygon.exterior.coords);pa,pb=coords[front['edge']:front['edge']+2];t=(pb-pa)/np.linalg.norm(pb-pa);n=np.array([t[1],-t[0]]);mid=(pa+pb)/2
xy=mid+n*10.+t*3.5
assert not polygon.contains(Point(xy))
assert shape(byid[front['nearest_road']]['geometry']).distance(Point(xy))<7
assert not any(shape(x['geometry']).contains(Point(xy)) for x in features if x['properties']['category']=='building')
ground=SharedGround(R/'evidence/full-iv-roofs/measured-terrain-state.npz')
origin=np.r_[xy,ground.height(xy[None])[0]+1.70]
target=np.r_[mid,ground.height(mid[None])[0]+3.05]
source=R/('evidence/facades-v2-native/sabado_facades_v2_600_32.cys' if a.variant=='v2' else 'evidence/sabado-profile-matched-v2/sabado_profile_600_32.cys')
s=Scene();lines=[]
for line in source.read_text().splitlines():
 if not line or line.startswith('#'):continue
 line=re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line);q=shlex.split(line)
 if q[0]=='camera':continue
 if q[0]=='settings':q[1:4]=['700','490',str(a.spp)];line=' '.join(q)
 lines.append(line)
s.lines=lines;s.camera(origin,target,(0,0,1),48.)
out=R/'evidence/facades-v2-native';stem=out/f'generic_6538_{a.variant}_700_{a.spp}';s.save(stem.with_suffix('.cys'))
meta={'purpose':'Actual native close street view of an active generic building; facade detail is illustrative, not a surveyed reconstruction','source_id':source_id,'source_address':'6538 Sabado Tarde Road','source_url':'https://www.openstreetmap.org/way/42753147','source_floor_count':2,'source_frontage_road':front['nearest_road'],'source_frontage_road_name':front['road_name'],'estimated_camera_origin_m':origin.tolist(),'estimated_camera_target_m':target.tolist(),'camera_rule':'Front-edge midpoint plus10m outward and3.5m along edge; eye1.70m above retained ground;48degree vertical field of view','camera_outside_mapped_buildings':True,'variant':a.variant,'family':row['family'],'scope':'Same light/material/dedicated meshes as matched Sabado. Only camera and700x490 film change from its selected original/v2 geometry variant. Source ID/address anchor the footprint only; window layout and finish remain authored estimates.','baseline_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'normal_serialization_gate':json.loads((R/'evidence/full-iv-facades-v2/SERIALIZED_GEOMETRY_VERIFICATION.json').read_text())['target_sha256']}
(stem.with_name(stem.name+'_CAMERA_CONTRACT.json')).write_text(json.dumps(meta,indent=2)+'\n')
if a.prepare_only:print(json.dumps(meta));raise SystemExit()
report=render(s,stem,metadata=meta);print(json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
