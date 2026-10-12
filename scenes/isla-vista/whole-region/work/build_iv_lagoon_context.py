"""Full sourced lagoon outline, compatible elevation and bounded eastern GIS.

Water surface follows the export's hydroflattened level, not bathymetry or a
current water observation. Brackish optics, ripples and marsh plants are an
explicit authored state. The original native scene and geographic inputs stay
unchanged; this component lists the exact source objects it supersedes.
"""
from pathlib import Path
import hashlib,json,math,struct,sys,tempfile
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/iv-component-runtime'),str(r/'work/cybr-iv-full/src'),str(r/'whole-iv-vendor')]
import numpy as np
import shapely
from shapely.geometry import Point,box,mapping
from shapely.ops import unary_union
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM,arcgis_geometry,layer_rows,polygons,metres
from cybr_ucsb.geometry import triangulate_polygon,stable_seed
from cybr_terrain.materials import write_pfm
from cybr_light import Scene
from cybr_light.runtime import read_pfm,publish
from iv_mesh_parts import Parts,leaf_mesh
from iv_shared_ground import SharedGround
from iv_polygon_tin import polygon_tin_masks,LocalPolygonClipper
out=r/'evidence/full-iv-lagoon-context';out.mkdir(exist_ok=True)
print('LAGOON_PHASE admitted: source and water-level audit',flush=True)
data=r/'data/lagoon-extension-20261011';frame=Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame
dem=DEM(data/'dem.tif',frame);old=SharedGround(r/'evidence/full-iv-roofs/measured-terrain-state.npz')
water_rows=json.loads((r/'data/full-iv-20261011/water-000.json').read_text())['features']
water_features=[(row,frame.project_geometry(arcgis_geometry(row['geometry']))) for row in water_rows]
lagoon=next(geom for row,geom in water_features if row['attributes'].get('Name')=='UCSB Lagoon')
full_water=unary_union([g for _,g in water_features])
level_samples=[];lagoon_interior=lagoon.buffer(-8)
for x in np.arange(980,1590,12):
 for y in np.arange(-770,-215,12):
  if lagoon_interior.contains(Point(x,y)):level_samples.append(dem.sample(x,y))
level=float(np.median(level_samples));assert abs(level-2.74)<.01
boundary=lagoon.boundary
extent=box(1300,-1300+60*old.dx,1795,-1300+284*old.dx)
acquired=box(801,-997,1798,148)
def ground(xy):
 xy=np.asarray(xy,float);z=dem.sample(xy[:,0],xy[:,1]);western=xy[:,0]<=1300
 z[western]=old.height(xy[western])
 # The old TERRAIN display grid includes millimetric relief. Blend only that
 # boundary discrepancy across 10 m, preserving exact shared seam heights.
 eastern=~western
 if eastern.any():
  p=xy[eastern];seam=np.c_[np.full(len(p),1300.),p[:,1]];delta=old.height(seam)-dem.sample(seam[:,0],seam[:,1]);z[eastern]+=delta*np.maximum(0,1-(p[:,0]-1300)/10)
 return z
features=[]
for category in ['buildings','footpaths','bike-paths','driving-surfaces','lawns','trees']:
 for row in layer_rows(data,category):
  props=row['attributes'];oid=next(props[k] for k in ['OBJECTID','OBJECTID_1','objectid','FID'] if props.get(k) is not None)
  geom=frame.project_geometry(arcgis_geometry(row['geometry']))
  features.append({'source_id':f'ucsb:{category}:{oid}','category':category,'geometry':geom,'properties':props})
buildings=[f for f in features if f['category']=='buildings' and f['geometry'].intersects(extent)]
for f in buildings:f['geometry']=f['geometry'].intersection(acquired)
building_union=unary_union([f['geometry'] for f in buildings])
paths=unary_union([f['geometry'] if f['geometry'].geom_type in ['Polygon','MultiPolygon'] else f['geometry'].buffer(1.2) for f in features if f['category'] in ['footpaths','bike-paths']]).intersection(extent).difference(full_water).difference(building_union)
paved=unary_union([f['geometry'] for f in features if f['category']=='driving-surfaces']).intersection(extent).difference(full_water).difference(building_union)
lawns=unary_union([f['geometry'] for f in features if f['category']=='lawns']).intersection(extent).difference(unary_union([full_water,paths,paved,building_union]))
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.asarray(day['native_basis_to_linear_rgb']);white=M@np.ones(3)
def native(rgb):return np.maximum(0,(np.asarray(rgb)*white)@np.linalg.inv(M).T)
s=Scene();s.materials=320
water_mat=s.material('plastic',native((.013,.024,.013)),.16,ior=1.333)
n=512;x,y=np.meshgrid((np.arange(n)+.5)/n,(np.arange(n)+.5)/n);micro=np.zeros((n,n))
for kx,ky,amplitude,phase in [(3,1,.0015,.4),(7,3,.0007,1.5),(11,-4,.0003,2.2)]:micro+=amplitude*np.sin(2*np.pi*(kx*x+ky*y)+phase)
write_pfm(out/'lagoon_metric_ripple.pfm',np.repeat(micro[:,:,None],3,axis=2))
water_bump=s.material('bumpmap',texture=out/'lagoon_metric_ripple.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' .5 .5 1';s.emit('nested',water_bump,water_mat,-1,.5);s.emit('metric_bump',water_bump)
wet=s.material('plastic',native((.075,.068,.043)),.64,ior=1.45)
wet_bump=s.material('bumpmap',texture=r/'evidence/full-iv-materials/coastal_soil_height_metres.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 6.944444444444445 6.944444444444445 1';s.emit('nested',wet_bump,wet,-1,.5);s.emit('metric_bump',wet_bump)
green=s.material('plastic',native((.070,.116,.043)),.77,ior=1.44);trans=s.material('difftrans',native((.10,.15,.035)));marsh_leaf=s.material('blendbsdf');s.emit('nested',marsh_leaf,green,trans,.12)
dry=s.material('plastic',native((.23,.18,.087)),.89,ior=1.44)
wall=s.material('plastic',(1,1,1),.76,ior=1.48,texture=r/'evidence/full-iv-street-finishes/6574_cream_stucco_native.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 1.923076923076923 1.923076923076923 1'
wall_bump=s.material('bumpmap',texture=r/'evidence/full-iv-street-finishes/lime_height_metres.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 1.923076923076923 1.923076923076923 1';s.emit('nested',wall_bump,wall,-1,.5);s.emit('metric_bump',wall_bump)
roof=s.material('plastic',native((.30,.295,.27)),.82,ior=1.48)
s.save(out/'materials.cys');parts=Parts(out/'lagoon_context.clm',16200000);rows=[]
def grid(bounds,step):
 a,b,c,d=bounds;xx=np.r_[np.arange(a,c,step),c];yy=np.r_[np.arange(b,d,step),d];x,y=np.meshgrid(xx,yy);xy=np.c_[x.ravel(),y.ravel()];i=np.arange((len(xx)-1)*(len(yy)-1));ix=i%(len(xx)-1);iy=i//(len(xx)-1);v=iy*len(xx)+ix;faces=np.r_[np.c_[v,v+1,v+len(xx)+1],np.c_[v,v+len(xx)+1,v+len(xx)]];tri=shapely.polygons(xy[faces]);return xy,faces,tri,shapely.STRtree(tri),xy[faces].mean(axis=1)
extension_grid=grid(extent.bounds,old.dx);water_grid=grid((955,-795,1615,-195),old.dx/2)
def water_height(xy):
 xy=np.asarray(xy);distance=shapely.distance(shapely.points(xy),boundary);fade=1-np.exp(-(distance/2)**2);return level+fade*(.005*np.sin((xy[:,0]*.8+xy[:,1]*.6)*2*np.pi/12)+.002*np.sin((xy[:,0]*-.3+xy[:,1]*.9539)*2*np.pi/8+1))
def surface(name,area,material,gg,height,source,offset=0):
 if area.is_empty:return
 xy,faces,tri,tree,centroids=gg;inside,touch=polygon_tin_masks(area,tri,tree,centroids);clipper=LocalPolygonClipper(area);v=np.c_[xy,height(xy)+offset]
 parts.mesh(name+'_interior',v,faces[inside],material,source,'Mapped boundary on source-elevation TIN; component-specific authored optics',drop_zero_projected_area=True)
 pending=[];batch=0
 def flush():
  nonlocal pending,batch
  if not pending:return
  p=np.concatenate(pending).reshape(-1,2);v=np.c_[p,height(p)+offset];parts.mesh(name+f'_boundary_{batch}',v,np.arange(len(v)).reshape(-1,3),material,source,'Exact polygon/TIN clipping',drop_zero_projected_area=True);pending=[];batch+=1
 for k in np.flatnonzero(touch):
  for geom in polygons(clipper.intersection(tri[k])):
   if geom.area<1e-8:continue
   p,f=triangulate_polygon(geom);pending.append(p[f])
  if len(pending)>300:flush()
 flush();rows.append({'name':name,'source_area_m2':area.area,'material':material});print('LAGOON_SURFACE',name,parts.writer.triangles,flush=True)
surface('full_lagoon',lagoon,water_bump,water_grid,water_height,'ucsb:water:1')
surface('eastern_land',extent.difference(full_water),1,extension_grid,ground,'USGS3DEP_export_extension')
surface('eastern_paths',paths,186,extension_grid,ground,'UCSB_mapped_footpaths_and_bikepaths',.018)
surface('eastern_paving',paved,9,extension_grid,ground,'UCSB_mapped_driving_surfaces',.018)
classes=json.loads((r/'evidence/full-iv-coastal-classes/COASTAL_CLASSES_RECEIPT.json').read_text());lawn_mat=next(x['ground_material_id'] for x in classes['classes'] if x['class']=='lawn')
surface('eastern_managed_lawns',lawns,lawn_mat,extension_grid,ground,'UCSB_mapped_lawns',.018)
# Maritime water beyond the original tile receives the existing authored
# surface return only. It is explicitly distant context, not new bathymetry.
ocean=next(g for row,g in water_features if row['attributes'].get('Name')=='Pacific Ocean').intersection(extent)
surface('eastern_ocean_context',ocean,85,extension_grid,lambda p:np.full(len(p),.11),'UCSB_Pacific_Ocean_outline')
building_records=[]
for f in buildings:
 source=f['source_id'];props=f['properties'];height=max(3.5,min(45,float(props.get('FLOORCOUNT') or 2)*3.6));start=parts.object
 for j,poly in enumerate(polygons(f['geometry'])):
  if poly.area<2:continue
  xy,ff=triangulate_polygon(poly);base=float(np.median(ground(xy)));top=base+height;parts.mesh(source+f'_roof_{j}',np.c_[xy,np.full(len(xy),top)],ff,roof,source,'Source plan retained; FLOORCOUNT times estimated3.6m; illustrative low-slope roof')
  for ring in [poly.exterior,*poly.interiors]:
   coords=np.array(ring.coords);travel=0
   for a,b in zip(coords[:-1],coords[1:]):
    length=np.linalg.norm(b-a)
    if length<.01:continue
    bottom=min(base-.25,float(ground(np.array([a,b])).min())-.1);v=np.array([[*a,bottom],[*b,bottom],[*b,top],[*a,top]])
    parts.mesh(source+'_wall',v,[[0,1,2],[0,2,3]],wall_bump,source,'Distant source footprint massing; unsourced facade detail omitted',uv=[[travel/1.25,bottom/1.25],[(travel+length)/1.25,bottom/1.25],[(travel+length)/1.25,top/1.25],[travel/1.25,top/1.25]]);travel+=length
 building_records.append({'source_id':source,'source_floor_count':props.get('FLOORCOUNT'),'height_m':height,'height_estimated':True,'uninterpreted_raw_height':props.get('BLDGHEIGHT'),'footprint_area_m2':f['geometry'].area,'objects':list(range(start,parts.object))})
print('LAGOON_PHASE source buildings complete',len(buildings),flush=True)
known={'Eucalyptus','Corymbia','Pinus','Platanus','Ficus','Jacaranda','Quercus','Schinus','Liquidambar','Olea','Pyrus','Alnus','Tipuana','Pittosporum','Acacia','Podocarpus','Cedrus','Cupressus','Sequoia','Lophostemon','Metrosideros'}
palms={'Syagrus','Phoenix','Washingtonia','Howea','Butia','Chamaerops','Archontophoenix'}
tree_records=[]
for item in features:
 if item['category']!='trees' or item['geometry'].geom_type!='Point' or not extent.contains(item['geometry']) or building_union.contains(item['geometry']) or full_water.contains(item['geometry']):continue
 genus=str(item['properties'].get('genus','')).strip()
 if genus not in known|palms:continue
 source=item['source_id'];xy=np.asarray(item['geometry'].coords[0]);rng=np.random.default_rng(stable_seed(source));tag=metres(item['properties'].get('height'));height=tag or (11 if genus in palms else 14 if genus in {'Pinus','Eucalyptus','Corymbia'} else 7.5)*rng.uniform(.8,1.15);base=np.r_[xy,ground(xy[None])[0]];root=parts.object
 parts.tube(source+'_trunk',base,base+[0,0,height*.72],max(.10,height*.018),.065,39,source,'Mapped source root/genus; supplied height if present, otherwise explicit botanical estimate',segments=6)
 if genus in palms:
  vertices=[];faces=[]
  for j in range(18):
   phi=j*2.399963;radial=np.array([np.cos(phi),np.sin(phi),0]);side=np.array([-radial[1],radial[0],0]);reach=height*.28;start=len(vertices)
   for k,t in enumerate(np.linspace(0,1,7)):
    center=base+[0,0,height*.9]+radial*(reach*t)+[0,0,reach*.35*np.sin(np.pi*t)-reach*.7*t*t];width=max(.005,.60*np.sin(np.pi*t));vertices.extend([center-side*width,center+[0,0,width*.07],center+side*width])
    if k:
     a=start+(k-1)*3;b=start+k*3;faces.extend([[a,a+1,b+1],[a,b+1,b],[a+1,a+2,b+2],[a+1,b+2,b+1]])
  parts.mesh(source+'_aggregate_fronds',vertices,faces,42,source,'Distant reduced-frond coverage at mapped palm root; unresolved leaflet groups, not enlarged individual leaves')
 else:
  centers=[];axes=[];lengths=[];widths=[]
  for j in range(8):
   phi=j*2.399963;zz=-.5+j/7;tip=base+[np.cos(phi)*height*.20,np.sin(phi)*height*.20,height*(.65+zz*.24)]
   parts.tube(source+'_branch',base+[0,0,height*.43],tip,.045,.013,39,source,'Authored branch-supported aggregate foliage',segments=4)
   for k in range(12):
    axis=rng.normal(size=3);axis/=np.linalg.norm(axis);centers.append(tip+rng.normal(size=3)*[height*.085,height*.085,height*.065]);axes.append(axis);lengths.append(height*.12);widths.append(height*.06)
  v,f=leaf_mesh(centers,axes,lengths,widths,rolls=rng.uniform(-1,1,len(centers)));parts.mesh(source+'_aggregate_crown',v,f,42,source,'Porous branch-supported groups of unresolved leaves for distant eastern context')
 tree_records.append({'source_id':source,'source_xy_m':xy.tolist(),'source_genus':genus,'source_height_tag_m':tag,'authored_height_m':height,'objects':list(range(root,parts.object))})
print('LAGOON_PHASE distant source trees',len(tree_records),flush=True)

# Authored saltgrass/rush-like foliage only on actual low terrestrial banks.
# The restoration reference supports the habitat, not these individual plants.
rng=np.random.default_rng(202610113);centers=[];axes=[];lengths=[];widths=[];clumps=[]
for arclength in np.arange(0,boundary.length,1.4):
 point=boundary.interpolate(arclength);next_=boundary.interpolate(min(boundary.length,arclength+.1));t=np.array(next_.coords[0])-np.array(point.coords[0]);t/=max(np.linalg.norm(t),1e-8)
 for sign in [-1,1]:
  xy=np.array(point.coords[0])+sign*np.array([-t[1],t[0]])*rng.uniform(.25,1.5)
  if lagoon.contains(Point(xy)) or not acquired.contains(Point(xy)):continue
  z=float(ground(xy[None])[0])
  if not level+.025<z<level+.75:continue
  if rng.random()>.72:continue
  clumps.append([*xy,z]);height=rng.uniform(.18,.52)
  for k in range(22):
   az=rng.uniform(0,2*np.pi);axis=np.array([np.cos(az)*.65,np.sin(az)*.65,1.]);axis/=np.linalg.norm(axis);length=height*rng.uniform(.65,1.15);centers.append([*xy,z]+axis*length*.49+rng.normal(size=3)*[.045,.045,0]);axes.append(axis);lengths.append(length);widths.append(rng.uniform(.006,.014))
if centers:
 v,f=leaf_mesh(centers,axes,lengths,widths,rolls=rng.uniform(-.5,.5,len(centers)));parts.mesh('estimated_lagoon_fringe',v,f,marsh_leaf,'authored_lagoon_low_bank_habitat','Ground-supported sparse saltgrass-like clumps; habitat supported by CCBER, individual plants and seasonal state authored')
print('LAGOON_PHASE marsh geometry',len(clumps),flush=True)
report=parts.close();report.update(material_offset=320,material_count=s.materials-320,full_lagoon_area_m2=lagoon.area,full_lagoon_bounds_m=list(lagoon.bounds),prior_clipped_area_m2=lagoon.intersection(box(-1300,-1300,1300,1300)).area,
 water_level_m=level,level_basis='Median hydroflattened USGS3DEP export samples in the sourced lagoon polygon; dataset surface level, not observed current water or bathymetry.',sample_quantiles_m=np.quantile(level_samples,[0,.05,.5,.95,1]).tolist(),extension_bounds_m=list(extent.bounds),terrain_seam='Same old-grid Y vertices at x1300; actual retained TERRAIN surface height matched, discrepancy blended over10m.',surfaces=rows,buildings=building_records,trees=tree_records,marsh_clump_positions_m=clumps,
 full_lagoon_polygon=mapping(lagoon),optics='Native Fresnel dielectric/plastic surface with estimated homogeneous brackish diffuse return, static millimetric metric ripples and resolved long ripples. No volume/bathymetry/current-flow claim.',
 sources=['data/full-iv-20261011/water-000.json','data/lagoon-extension-20261011/manifest.json','https://ccber.ucsb.edu/restoration-area-campus-lagoon','https://ccber.ucsb.edu/sites/default/files/Cheadle_docs/Lagoon_Tour_2012.pdf'],
 limitations='A bounded full-lagoon context extension, not a complete campus reconstruction. GIS epochs differ. New buildings retain mapped plan and floor count but have estimated heights and simple distant envelopes. The official restoration reference supports brackish lagoon and saltmarsh habitat, not exact individual plants. Ripples, pigment and current seasonal state are authored. Historical tide/ocean optics are not reused for lagoon level.')
(out/'LAGOON_CONTEXT_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'triangles':report['triangles'],'parts':len(report['parts']),'material_count':report['material_count'],'water_level_m':level,'full_lagoon_area_m2':lagoon.area}),flush=True)
