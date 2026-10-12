"""Mapped ocean surface with resolved long waves and residual slope response.

This is an authored static surface state. There is no measured wind, bathymetry,
fluid solver or underwater volume. A low diffuse term represents unresolved
water-column return; the actual surface reflection uses native dielectric Fresnel.
"""
from pathlib import Path
import sys,json,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import shapely
from shapely.ops import unary_union
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import ingest,polygons
from cybr_ucsb.geometry import ocean_from_coastline,triangulate_polygon
from cybr_light import Scene
from iv_shared_ground import SharedGround
from iv_polygon_tin import polygon_tin_masks,LocalPolygonClipper
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-coastal-water';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs';sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dataset=ingest(r/'data/full-iv-20261011',sector);grid=SharedGround(base/'measured-terrain-state.npz')
ocean=ocean_from_coastline(dataset);water=unary_union([ocean,*[f.geometry for f in dataset.selected('water') if f.geometry.geom_type in {'Polygon','MultiPolygon'}]]);inland=water.difference(ocean)
segments=[]
for feature in dataset.selected('coastline'):
 for line in (feature.geometry.geoms if hasattr(feature.geometry,'geoms') else [feature.geometry]):
  if line.geom_type!='LineString':continue
  p=np.asarray(line.coords)[:,:2];segments.extend(np.stack([p[:-1],p[1:]],axis=1))
shore=shapely.STRtree(shapely.linestrings(np.asarray(segments)))
def shore_distance(p):
 index,d=shore.query_nearest(shapely.points(p),all_matches=False,return_distance=True);result=np.empty(len(p));result[index[0]]=d;return result
waves=[{'wavelength_m':80.,'amplitude_m':.16,'direction_deg':35.,'phase':.4},{'wavelength_m':53.,'amplitude_m':.09,'direction_deg':62.,'phase':1.7},{'wavelength_m':34.,'amplitude_m':.043,'direction_deg':-5.,'phase':2.9}]
def height(p):
 p=np.asarray(p);d=shore_distance(p);t=1-np.exp(-(d/18)**2);h=np.zeros(len(p))
 for w in waves:
  direction=np.array([np.cos(np.deg2rad(w['direction_deg'])),np.sin(np.deg2rad(w['direction_deg']))]);h+=w['amplitude_m']*np.sin((p@direction)*2*np.pi/w['wavelength_m']+w['phase'])
 return .11+h*t
def normals(p):
 epsilon=.02;gx=(height(p+[epsilon,0])-height(p-[epsilon,0]))/(2*epsilon);gy=(height(p+[0,epsilon])-height(p-[0,epsilon]))/(2*epsilon);return np.c_[-gx,-gy,np.ones(len(p))]
long_variance=sum(.5*(2*np.pi*w['amplitude_m']/w['wavelength_m'])**2 for w in waves);wind=3.;total_variance=.003+.00512*wind;residual=max(.001,total_variance-long_variance)
# Match the central half-height width of an isotropic Gaussian slope model.
# GGX has heavier tails and no finite equal variance: this is explicitly a
# central-lobe transport approximation, not an exact Cox–Munk BRDF implementation.
alpha=np.sqrt(residual*np.log(2)/(np.sqrt(2)-1));rough=np.sqrt(alpha)
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);rgb=np.array([.003,.016,.027]);native=(rgb*(M@np.ones(3)))@np.linalg.inv(M).T
classes=json.loads((r/'evidence/full-iv-coastal-classes/COASTAL_CLASSES_RECEIPT.json').read_text());offset=classes['material_offset']+classes['material_count'];s=Scene();s.materials=offset;material=s.material('plastic',native,rough=rough,ior=1.333);s.save(out/'materials.cys')
triangles=shapely.polygons(grid.xy[grid.faces]);tree=shapely.STRtree(triangles);centroids=grid.xy[grid.faces].mean(1);parts=Parts(out/'water.clm',8000000);rows=[]
for label,area,mid in [('ocean',ocean,material),('retained_inland_water',inland,15)]:
 inside,touch=polygon_tin_masks(area,triangles,tree,centroids);clipper=LocalPolygonClipper(area);v=np.c_[grid.xy,height(grid.xy) if label=='ocean' else np.full(len(grid.xy),.11)];nn=normals(grid.xy) if label=='ocean' else np.tile([0.,0,1.],(len(grid.xy),1));parts.mesh(label+'_interior',v,grid.faces[inside],mid,label,'Mapped water boundary; authored static long-wave ocean and preserved inland level',normals=nn,drop_zero_projected_area=True);pending=[];batch=0
 def flush():
  global pending,batch
  if not pending:return
  p=np.concatenate(pending).reshape(-1,2);v=np.c_[p,height(p) if label=='ocean' else np.full(len(p),.11)];nn=normals(p) if label=='ocean' else np.tile([0.,0,1.],(len(p),1));parts.mesh(label+f'_boundary_{batch}',v,np.arange(len(v)).reshape(-1,3),mid,label,'Exact source shoreline; wave amplitude fades over an estimated18m coastal band',normals=nn,drop_zero_projected_area=True);pending=[];batch+=1
 for idx in np.flatnonzero(touch):
  for polygon in polygons(clipper.intersection(triangles[idx])):
   if polygon.area<1e-8:continue
   p,f=triangulate_polygon(polygon);pending.append(p[f])
  if len(pending)>400:flush()
 flush();rows.append({'category':label,'area_m2':area.area,'material':mid});print('WATER_COMPONENT',label,parts.writer.triangles,flush=True)
report=parts.close();layout=json.loads((base/'glb-part-layout.json').read_text());skip=[p['component'] for b in layout.values() for p in b['parts'] if p['part'].startswith('source_water_')]
report.update(material_offset=offset,material_count=1,replace_sector_components=skip,source_features=[f.id for f in dataset.selected('water')+dataset.selected('coastline')],coverage=rows,authored_mean_level_m=.11,waves=waves,geometry_spacing_m=grid.dx,estimated_coast_fade_m=18.,authored_wind_speed_at12_5m_mps=wind,long_wave_mean_square_slope=long_variance,reference_total_mean_square_slope=total_variance,residual_slope_model_value=residual,native_GGX_alpha=alpha,native_roughness_parameter=rough,unresolved_linear_rgb_return=rgb.tolist(),normal_contract='Geometry and smooth normals derive from the same physical height function, including coastal amplitude taper. Existing micro-bump is removed from the ocean. Long-wave mean slope power is subtracted before fitting the residual central reflection lobe; no double relief.',references=[{'url':'https://opg.optica.org/josa/abstract.cfm?URI=josa-44-11-838','title':'Cox and Munk1954, Measurement of the Roughness of the Sea Surface from Photographs of the Sun’s Glitter','use':'Wind-dependent mean-square-slope reference; authored3m/s state.'}],limits='Static analytic waves and a native Fresnel surface approximation. GGX central-width fit is not full Cox–Munk statistical transport. No measured wind/tide, bathymetry, underwater radiative transfer, breaking waves, foam or fluid simulation. The low diffuse term is an explicit water-column return proxy. Inland water retains its prior optical treatment.')
(out/'WATER_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('DONE_COASTAL_WATER',report['triangles'],flush=True)
