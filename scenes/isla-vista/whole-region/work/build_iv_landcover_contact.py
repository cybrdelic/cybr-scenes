"""Drape sourced landcover and beach polygons on the exact visible TERRAIN TIN.

This repairs geometric intersections. Existing optical proxy materials are
retained so the result is a topology/contact comparison, not a color grade.
"""
from pathlib import Path
import sys,json,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import shapely
from shapely.ops import unary_union
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import ingest,polygons
from cybr_ucsb.geometry import area_geometry,ocean_from_coastline,triangulate_polygon
from iv_mesh_parts import Parts
from iv_shared_ground import SharedGround
out=r/'evidence/full-iv-landcover-contact';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs'
ground=SharedGround(base/'measured-terrain-state.npz');sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dataset=ingest(r/'data/full-iv-20261011',sector)
features=[f for f in dataset.selected('landcover') if f.geometry.geom_type in {'Polygon','MultiPolygon'}]
beaches=[f for f in features if f.properties.get('natural') in {'beach','sand'}]
buildings=unary_union([f.geometry for f in dataset.selected('building')]);water=unary_union([ocean_from_coastline(dataset),*[f.geometry for f in dataset.selected('water') if f.geometry.geom_type in {'Polygon','MultiPolygon'}]])
widths=[];paving=unary_union([area_geometry(f,widths) for c in ['road','pavement','parking','path'] for f in dataset.selected(c)])
excluded=unary_union([buildings,water,paving]);sand=unary_union([f.geometry for f in beaches]).intersection(sector.clip).difference(excluded)
cover=unary_union([f.geometry for f in features]).intersection(sector.clip).difference(excluded).difference(sand)
areas={'mapped_landcover':(cover,7),'mapped_sand':(sand,13)}
(out/'coverage.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'category':k},'geometry':shapely.geometry.mapping(v[0])} for k,v in areas.items()]}))
if '--footprints-only' in sys.argv:
 print('PRESERVED_SOURCE_FOOTPRINTS',flush=True);raise SystemExit(0)
triangles=shapely.polygons(ground.xy[ground.faces]);parts=Parts(out/'landcover.clm',6000000);rows=[];raise_m=.018
for category,(area,material) in areas.items():
 shapely.prepare(area);inside=shapely.contains_properly(area,triangles);touch=shapely.intersects(area,triangles)&~inside
 vv=ground.vertices.copy();vv[:,2]+=raise_m;parts.mesh(category+'_interior',vv,ground.faces[inside],material,category,'Same retained terrain triangles; 18 mm optical-cover separation estimate',drop_zero_projected_area=True)
 pending=[];batch=0
 def flush():
  global pending,batch
  if not pending:return
  t=np.concatenate(pending);v=t.reshape(-1,3);parts.mesh(category+f'_boundary_{batch}',v,np.arange(len(v)).reshape(-1,3),material,category,'Exact source footprint clipped against retained TIN; 18 mm separation estimate',drop_zero_projected_area=True);pending=[];batch+=1
 for idx in np.flatnonzero(touch):
  for polygon in polygons(triangles[idx].intersection(area)):
   if polygon.area<1e-8:continue
   p,f=triangulate_polygon(polygon);v=np.c_[p,ground.height(p)+raise_m];pending.append(v[f])
  if len(pending)>400:flush()
 flush();rows.append({'category':category,'source_area_m2':area.area,'whole_TIN_triangles':int(inside.sum()),'boundary_TIN_triangles':int(touch.sum()),'material_retained':material,'top_above_same_terrain_m':raise_m});print('GROUNDED',category,parts.writer.triangles,flush=True)
report=parts.close();layout=json.loads((base/'glb-part-layout.json').read_text());skip=[p['component'] for b in layout.values() for p in b['parts'] if p['part'].startswith(('mapped_landcover_','mapped_sand_'))]
report.update(replace_sector_components=skip,construction=rows,source_features=[f.id for f in features],source_state_sha256=hashlib.sha256((base/'measured-terrain-state.npz').read_bytes()).hexdigest(),preserved='Original mapped polygon coverage, DEM and TERRAIN realization, material IDs, daylight and cameras. Sand takes priority over the general landcover union; building/water/paving areas are excluded.',limits='18 mm is an estimated geometric separation, not measured soil/lawn thickness. This repairs contact; grass/shrub structure and surface materials remain optical proxies. No new vegetation distribution or terrain geography invented.')
(out/'LANDCOVER_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');(out/'materials.cys').write_text('# Retains existing landcover7 and sand13 optical material IDs.\n');print('DONE_LANDCOVER',report['triangles'],len(skip),flush=True)
