"""Close paved surfaces against the existing terrain with common triangulation.

The road/path footprints retain their source-derived widths. Curb heights,
construction thickness and transition profiles are explicit presentation
estimates, because the elevation source does not measure individual curbs.
"""
from pathlib import Path
import sys,json,numpy as np,hashlib
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from scipy.ndimage import gaussian_filter
import shapely
from shapely.ops import unary_union
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import ingest,polygons
from cybr_ucsb.geometry import area_geometry,ocean_from_coastline,triangulate_polygon
from cybr_terrain.geometry import grid_faces
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-contact';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs'
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dataset=ingest(r/'data/full-iv-20261011',sector)
state=np.load(base/'measured-terrain-state.npz');metadata=json.loads(str(state['metadata']));n=metadata['config']['grid'];extent=metadata['config']['extent'];dx=extent/(n-1);z=state['foundation']+state['thickness'].sum(axis=0)
assert np.max(state['water'])==0 and np.max(state['loose'])==0 and len(metadata['layers'])==1
rng=np.random.default_rng(metadata['config']['seed']+19);fields=[]
for sigma in [.75,2.2,6]:
 a=gaussian_filter(rng.normal(size=(n,n)),sigma);a/=max(a.std(),1e-9);fields.append(a)
rough,medium,coarse=fields;amplitude=min(max(metadata['layers'][0]['grain_scale']*.30,.008),dx*.20);display=z+(.54*rough+.30*medium+.16*coarse-.14*np.maximum(rough,0)**2)*amplitude
axis=np.linspace(-extent/2,extent/2,n);x,y=np.meshgrid(axis,axis);xy=np.c_[x.ravel(),y.ravel()];faces=grid_faces(n);grid=np.c_[xy,display.ravel()]
def terrain(points):
 p=np.asarray(points);q=np.clip((p+extent/2)/dx,0,n-1-1e-9);ix=np.floor(q[:,0]).astype(int);iy=np.floor(q[:,1]).astype(int);tx=q[:,0]-ix;ty=q[:,1]-iy
 a=display[iy,ix];b=display[iy,ix+1];c=display[iy+1,ix+1];d=display[iy+1,ix]
 return np.where(ty<=tx,(1-tx)*a+(tx-ty)*b+ty*c,(1-ty)*a+tx*c+(ty-tx)*d)
assert np.max(abs(terrain(xy[::17])-grid[::17,2]))<1e-7
buildings=unary_union([f.geometry for f in dataset.selected('building')]);water=unary_union([ocean_from_coastline(dataset),*[f.geometry for f in dataset.selected('water') if f.geometry.geom_type in {'Polygon','MultiPolygon'}]])
widths=[];areas={};ids={}
for category in ['road','pavement','parking','path']:
 fs=dataset.selected(category);areas[category]=unary_union([area_geometry(f,widths) for f in fs]).intersection(sector.clip).difference(buildings).difference(water);ids[category]=[f.id for f in fs]
road=areas['road'];occupied=shapely.Polygon()
# Query individual boundary segments: distance to the complete union for every
# vertex scales poorly with all distant street edges. This is the same nearest
# boundary distance for path points outside the clipped road footprint.
segments=[]
for polygon in polygons(road):
 for ring in [polygon.exterior,*polygon.interiors]:
  a=np.asarray(ring.coords)[:,:2];segments.extend(np.stack([a[:-1],a[1:]],axis=1))
road_boundary_tree=shapely.STRtree(shapely.linestrings(np.asarray(segments)))
for category in ['road','pavement','parking','path']:
 areas[category]=areas[category].difference(occupied);occupied=unary_union([occupied,areas[category]])
shapely.prepare(road)
triangles=shapely.polygons(xy[faces]);parts=Parts(out/'contact.clm',4000000);construction=[]
def offset(category,points):
 if category!='path':return np.full(len(points),.018)
 pp=shapely.points(points);index,distance=road_boundary_tree.query_nearest(pp,all_matches=False,return_distance=True);dist=np.empty(len(points));dist[index[0]]=distance;dist[shapely.contains(road,pp)]=0;t=np.clip(dist/1.2,0,1)
 return .018+.122*t*t*(3-2*t)
def top(category,points):return terrain(points)+offset(category,points)
for category,area in areas.items():
 material=11 if category=='path' else 9;estimate='Source footprint; common terrain contact; curb and crossing-transition dimensions estimated';source='mapped_'+category
 shapely.prepare(area);inside=shapely.contains_properly(area,triangles);touch=shapely.intersects(area,triangles)&~inside
 vv=grid.copy();vv[:,2]+=offset(category,xy);parts.mesh(source+'_interior',vv,faces[inside],material,source,estimate,uv_period=.2 if material==9 else None,drop_zero_projected_area=True)
 pending=[];batch=0
 def flush():
  global pending,batch
  if not pending:return
  t=np.concatenate(pending);v=t.reshape(-1,3);parts.mesh(source+f'_boundary_{batch}',v,np.arange(len(v)).reshape(-1,3),material,source,estimate,uv_period=.2 if material==9 else None,drop_zero_projected_area=True);pending=[];batch+=1
 for idx in np.flatnonzero(touch):
  intersection=triangles[idx].intersection(area)
  for polygon in polygons(intersection):
   if polygon.area<1e-8:continue
   p,f=triangulate_polygon(polygon,max_edge=1.2 if category=='path' else None);v=np.c_[p,top(category,p)];pending.append(v[f])
  if len(pending)>400:flush()
 flush()
 # Closed construction edges terminate below the common terrain, so a raised
 # sidewalk casts a curb shadow instead of exposing an unsupported air gap.
 edge_v=[];edge_f=[];edge_uv=[];arc=0.
 for polygon in polygons(shapely.segmentize(area,1.2)):
  for ring in [polygon.exterior,*polygon.interiors]:
   p=np.asarray(ring.coords)[:,:2];zz=top(category,p);bottom=terrain(p)-.04
   for j in range(len(p)-1):
    k=len(edge_v);quad=np.array([[*p[j],bottom[j]],[*p[j+1],bottom[j+1]],[*p[j+1],zz[j+1]],[*p[j],zz[j]]]);quantized=quad.astype('<f4');length=float(np.linalg.norm(quantized[1,:2].astype(float)-quantized[0,:2].astype(float)));edge_v.extend(quad);edge_uv.extend(np.c_[[arc,arc+length,arc+length,arc],quantized[:,2].astype(float)]/1.25);edge_f.extend([[k,k+1,k+2],[k,k+2,k+3]]);arc+=length
 if edge_f:parts.mesh(source+'_closed_edges',edge_v,edge_f,material,source,estimate,uv=edge_uv,uv_period=.2 if material==9 else None)
 construction.append({'category':category,'footprint_area_m2':area.area,'full_terrain_triangles':int(inside.sum()),'intersected_terrain_triangles':int(touch.sum()),'top_above_common_terrain_m':.14 if category=='path' else .018,'curb_bottom_below_common_terrain_m':.04,'sourced_widths_preserved':True})
 print('CONTACT',category,'triangles',parts.writer.triangles,flush=True)
report=parts.close();layout=json.loads((base/'glb-part-layout.json').read_text());skip=[p['component'] for b in layout.values() for p in b['parts'] if p['part'].startswith(('mapped_road_','mapped_pavement_','mapped_parking_','mapped_path_'))]
report.update(replace_sector_components=sorted(skip),construction=construction,widths=widths,source_features=ids,terrain_grid=metadata['config'],terrain_height_method='Exact retained TERRAIN display-grid reconstruction and its two-triangle cell interpolation. Same DEM and render-only millimetric realization; no new terrain geography.',overlap_policy='Road, pavement and parking take precedence; raised paths are clipped at those surfaces. The path transition falls to road grade within1.2m of a road boundary.',limits='Curbs, slab thickness and local transitions are authored estimates, not surveyed curb ramps or accessibility verification. Material microrelief is added only in shading. This closes contact geometry; it does not constitute a road engineering design.',source_state_sha256=hashlib.sha256((base/'measured-terrain-state.npz').read_bytes()).hexdigest())
(out/'CONTACT_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');(out/'materials.cys').write_text('# Reuses established native asphalt9 and concrete11 material IDs.\n');print('DONE_CONTACT',report['triangles'],len(skip),flush=True)
