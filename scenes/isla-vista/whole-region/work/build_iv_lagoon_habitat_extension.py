"""Continue retained mapped habitat polygons over the old tile edge.

The eastern patch uses the same terrain triangles and class material response.
Plants are an explicitly authored distant tier; only polygon extents are sourced.
"""
from pathlib import Path
import hashlib,json,sys
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/iv-component-runtime'),str(r/'work/cybr-iv-full/src'),str(r/'whole-iv-vendor')]
import numpy as np
import shapely
from shapely.geometry import shape,box,Point
from shapely.ops import unary_union
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM,arcgis_geometry,layer_rows,polygons
from cybr_ucsb.geometry import triangulate_polygon
from iv_shared_ground import SharedGround
from iv_mesh_parts import Parts,leaf_mesh
from iv_polygon_tin import polygon_tin_masks,LocalPolygonClipper
out=r/'evidence/full-iv-lagoon-habitat-extension';print('LAGOON_HABITAT_BUILD admitted',flush=True)
source=json.loads((out/'SOURCE_COVERAGE.geojson').read_text());lag=json.loads((r/'evidence/full-iv-lagoon-context/LAGOON_CONTEXT_RECEIPT.json').read_text());extent=box(*lag['extension_bounds_m'])
frame=Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame;data=r/'data/lagoon-extension-20261011';dem=DEM(data/'dem.tif',frame);old=SharedGround(r/'evidence/full-iv-roofs/measured-terrain-state.npz')
def ground(xy):
 xy=np.asarray(xy,float);z=dem.sample(xy[:,0],xy[:,1]);western=xy[:,0]<=1300;z[western]=old.height(xy[western]);eastern=~western
 if eastern.any():
  p=xy[eastern];seam=np.c_[np.full(len(p),1300.),p[:,1]];delta=old.height(seam)-dem.sample(seam[:,0],seam[:,1]);z[eastern]+=delta*np.maximum(0,1-(p[:,0]-1300)/10)
 return z
exclusions=[]
for kind in ['buildings','footpaths','bike-paths','driving-surfaces','lawns']:
 for row in layer_rows(data,kind):
  g=frame.project_geometry(arcgis_geometry(row['geometry']))
  if g.geom_type in ['LineString','MultiLineString']:g=g.buffer(1.2)
  exclusions.append(g)
for row in json.loads((r/'data/full-iv-20261011/water-000.json').read_text())['features']:exclusions.append(frame.project_geometry(arcgis_geometry(row['geometry'])))
excluded=unary_union(exclusions);classes=['beach','scrub','woodland','natural_grass'];materials={'beach':13,'scrub':76,'woodland':77,'natural_grass':75};areas={};occupied=shapely.Polygon()
for kind in classes:
 areas[kind]=unary_union([shape(f['geometry']) for f in source['features'] if f['properties']['class']==kind]).intersection(extent).difference(excluded).difference(occupied);occupied=unary_union([occupied,areas[kind]])
a,b,c,d=extent.bounds;xx=np.r_[np.arange(a,c,old.dx),c];yy=np.r_[np.arange(b,d,old.dx),d];x,y=np.meshgrid(xx,yy);xy=np.c_[x.ravel(),y.ravel()];i=np.arange((len(xx)-1)*(len(yy)-1));v=(i//(len(xx)-1))*len(xx)+i%(len(xx)-1);faces=np.r_[np.c_[v,v+1,v+len(xx)+1],np.c_[v,v+len(xx)+1,v+len(xx)]];tri=shapely.polygons(xy[faces]);tree=shapely.STRtree(tri);centroids=xy[faces].mean(1)
parts=Parts(out/'habitat_extension.clm',16400000);rows=[]
for kind,area in areas.items():
 if area.is_empty:continue
 inside,touch=polygon_tin_masks(area,tri,tree,centroids);clipper=LocalPolygonClipper(area);v=np.c_[xy,ground(xy)+.018];parts.mesh(kind+'_support',v,faces[inside],materials[kind],kind,'Complete retained source polygon, same class response and exact shared terrain support',drop_zero_projected_area=True)
 pending=[];batch=0
 def flush():
  global pending,batch
  if not pending:return
  p=np.concatenate(pending).reshape(-1,2);parts.mesh(kind+'_boundary_'+str(batch),np.c_[p,ground(p)+.018],np.arange(len(p)).reshape(-1,3),materials[kind],kind,'Exact mapped polygon/TIN clipping',drop_zero_projected_area=True);pending=[];batch+=1
 for k in np.flatnonzero(touch):
  for g in polygons(clipper.intersection(tri[k])):
   if g.area<1e-8:continue
   p,f=triangulate_polygon(g);pending.append(p[f])
  if len(pending)>300:flush()
 flush();rows.append({'class':kind,'area_m2':area.area,'material':materials[kind],'source_ids':[f['id'] for f in source['features'] if f['properties']['class']==kind]})
# Sparse distant shrub structure supplements the retained integrated material.
# This is a view-independent bounded regional tier, not giant individual leaves.
plant_counts={};rng=np.random.default_rng(202610114)
for kind,spacing in [('scrub',4.8),('woodland',7.5)]:
 area=areas[kind]
 if area.is_empty:continue
 a,b,c,d=area.bounds;gx=np.arange(np.floor(a/spacing)*spacing,c,spacing);gy=np.arange(np.floor(b/spacing)*spacing,d,spacing);x,y=np.meshgrid(gx,gy);p=np.c_[x.ravel(),y.ravel()]+rng.uniform(-.38,.38,(x.size,2))*spacing;core=area.buffer(-1);p=p[shapely.contains_xy(core,p[:,0],p[:,1])];plant_counts[kind]=len(p);vv=[];ff=[];offset=0
 for j,q in enumerate(p):
  h=rng.uniform(.55,1.3);radius=rng.uniform(.45,.85);root=np.r_[q,ground(q[None])[0]+.018];parts.tube(kind+'_stem_'+str(j),root,root+[0,0,h*.60],.017,.007,84,kind,'Authored support stem for bounded distant habitat shrub',segments=4)
  for lobe in range(3):
   phi=lobe*2.399963+rng.uniform(-.2,.2);center=root+[np.cos(phi)*radius*.28,np.sin(phi)*radius*.28,h*.60]
   for level in range(3):
    rr=radius*np.sin(np.pi*(.14+.36*level))
    for k in range(6):
     angle=k*np.pi/3+.23*level;vv.append(center+[np.cos(angle)*rr,np.sin(angle)*rr,(level-1)*h*.28])
   for level in range(2):
    for k in range(6):
     if rng.random()<.15:continue
     aa=offset+level*6+k;bb=offset+level*6+(k+1)%6;ff.extend([[aa,bb,bb+6],[aa,bb+6,aa+6]])
   offset+=18
  if len(vv)>9000:
   parts.mesh(kind+'_porous_groups_'+str(j),vv,ff,83 if kind=='scrub' else 81,kind,'Authored porous aggregate canopy lobes for distant extension, not resolved individual leaves');vv=[];ff=[];offset=0
 if vv:parts.mesh(kind+'_porous_groups_final',vv,ff,83 if kind=='scrub' else 81,kind,'Authored distant canopy groups')
# Retained source-tagged compacted trail near the selected camera. The
# shallow cap follows the existing authored path top; it does not infer a
# surveyed trail width or replace the larger legacy GIS path union.
normalized=json.loads((r/'evidence/full-iv-roofs/normalized.geojson').read_text())['features']
trail=next(f for f in normalized if f['id']=='osm:way:196222525')
assert trail['properties']['source_properties']['surface']=='compacted'
trail_area=shape(trail['geometry']).intersection(box(975,-420,1030,-325)).buffer(.9,cap_style='flat').difference(shape(lag['full_lagoon_polygon']))
old_tri_xy=old.xy[old.faces];centers=old_tri_xy.mean(1);bounds=trail_area.bounds
selected=(centers[:,0]>bounds[0]-old.dx)&(centers[:,0]<bounds[2]+old.dx)&(centers[:,1]>bounds[1]-old.dx)&(centers[:,1]<bounds[3]+old.dx)
trail_vertices=[];trail_faces=[];offset=0
for tri_xy in old_tri_xy[selected]:
 for g in polygons(shapely.Polygon(tri_xy).intersection(trail_area)):
  if g.area<1e-8:continue
  xy0,f=triangulate_polygon(g);v0=np.c_[xy0,old.height(xy0)+.142];trail_vertices.extend(v0);trail_faces.extend(f+offset);offset+=len(v0)
parts.mesh('mapped_compacted_trail_finish',trail_vertices,trail_faces,1,'osm:way:196222525','Source surface=compacted; original coastal soil fields; estimated1.8m width on retained authored path top+.002m',drop_zero_projected_area=True)
trail_receipt={'source_id':trail['id'],'source_properties':trail['properties']['source_properties'],'estimated_width_m':1.8,'height_above_retained_terrain_m':.142,'prior_path_top_m':.14,'cap_separation_m':.002,'native_material':1,'limits':'Local source-tagged finish cap. Legacy UCSB parallel path records remain outside this1.8m strip and may disagree with the newer OSM centerline. No surveyed path section claim.'}
report=parts.close();report.update(source_tagged_compacted_trail=trail_receipt,source_coverage_sha256=hashlib.file_digest((out/'SOURCE_COVERAGE.geojson').open('rb'),'sha256').hexdigest(),source_polygons=rows,plant_counts=plant_counts,terrain_support_offset_m=.018,terrain_seam_max_error_m=float(np.max(abs(ground(np.c_[np.full(len(yy),1300.),yy])-old.height(np.c_[np.full(len(yy),1300.),yy])))),limits='No source polygon invented. Source classes continue over the old tile edge using the same prior authored late-dry-season reflectance. Distant shrub positions/shape/coverage are procedural estimates; no exact plant or current season claim. Underlying terrain, existing mapped trees and buildings remain unchanged.')
(out/'HABITAT_EXTENSION_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['triangles','plant_counts','terrain_seam_max_error_m']}),flush=True)

import subprocess
subprocess.run([sys.executable,str(r/'work/verify_iv_lagoon_habitat_extension.py')],check=True)
