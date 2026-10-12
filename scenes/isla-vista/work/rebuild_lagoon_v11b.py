"""Source-bound San Nicolas restoration reconstruction after workspace recovery.

GIS footprints and dataset elevations are retained. The small freshwater basin,
floor sections, species distribution and weather are explicitly authored from
CCBER's photograph and restoration history, not a survey or current inventory.
"""
from pathlib import Path
import argparse,hashlib,json,math,os,sys
R=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(R/'work'))
import numpy as np
import shapely
from shapely.geometry import Point,Polygon,box,mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.affinity import scale,rotate
from scipy.spatial import Delaunay
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM,layer_rows,arcgis_geometry,polygons
from cybr_ucsb.geometry import triangulate_polygon,stable_seed
from cybrlight.scene_compat import Scene,render
from cybrlight.scene_compat.runtime import read_pfm
from scene_io import write_pfm
from iv_mesh_parts import Parts,leaf_mesh
from iv_polygon_tin import polygon_tin_masks,LocalPolygonClipper
from architecture_helpers import Buffer,Facade

OUT=R/'evidence/lagoon-restoration-v11b';OUT.mkdir(exist_ok=True)
FRAME=Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame
DEM0=DEM(R/'data/full-iv-20261011/dem.tif',FRAME)
DEM1=DEM(R/'data/lagoon-extension-20261011/dem.tif',FRAME)
DOMAIN=unary_union([box(-1295,-995,1295,1295),box(1295,-995,1790,140)])
CAMERA=np.array([1388.,-489.,10.])
TARGET=np.array([1347.,-444.,6.4])
BASIN=rotate(scale(Point(1372,-473).buffer(1,quad_segs=48),14,5.5),-8)
BASIN_LEVEL=5.5
BASIN_WATER=BASIN.buffer(-.9)
DAY=json.loads((R/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
M=np.array(DAY['native_basis_to_linear_rgb']);WHITE=M@np.ones(3)
def native(c):return np.maximum(0,(np.asarray(c)*WHITE)@np.linalg.inv(M).T)
def source_height(p):
 p=np.asarray(p,float);x,y=p.T;use=(x>1200)&(y<145);z=np.empty(len(p));z[use]=DEM1.sample(x[use],y[use]);z[~use]=DEM0.sample(x[~use],y[~use]);return z
def designed_height(p):
 p=np.asarray(p,float);z=source_height(p)
 # Continuous bounded grade for a photo-supported wetland omitted by GIS.
 # Its center/outline/level are explicit estimates. Outside 4 m nothing moves.
 points=shapely.points(p);distance=shapely.distance(points,BASIN);inside=shapely.contains_xy(BASIN,p[:,0],p[:,1]);inner=shapely.distance(points,BASIN.boundary)
 w=np.maximum(0,1-distance/4);w=w*w*(3-2*w);t=np.minimum(inner/3.8,1);bed=BASIN_LEVEL+.09-.65*t*t*(3-2*t)
 desired=np.where(inside,bed,BASIN_LEVEL+.09+distance*.23)
 change=w*(desired-z);return z+change
def digest(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def features():
 records={}
 for folder in ['full-iv-20261011','lagoon-extension-20261011']:
  for kind in ['buildings','bike-paths','footpaths','driving-surfaces','lawns','trees']:
   for row in layer_rows(R/'data'/folder,kind):
    props=row['attributes'];oid=next((props[k] for k in ['OBJECTID','OBJECTID_1','objectid','FID'] if k in props),None)
    g=FRAME.project_geometry(arcgis_geometry(row['geometry']));sid=f'ucsb:{kind}:{oid}'
    if g.intersects(DOMAIN):records[sid]={'source':sid,'category':kind,'geometry':g,'props':props}
 return list(records.values())

def make_materials():
 print('V11 material construction admitted',flush=True)
 import subprocess
 for script in ['bake_coastal_microbed.py','bake_iv_street_finishes.py']:
  subprocess.run([sys.executable,str(R/'work'/script)],check=True)
 sys.path.insert(0,str(R/'original/cybr-material-concrete'))
 from mineral_construction_bounded import construction
 spec=json.loads((R/'original/cybr-material-concrete/sidewalk_recipe.json').read_text());fields,report=construction(spec,512)
 rgb=fields['BaseColor'];lin=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4);lin*=np.array([.36,.355,.325])/lin.mean((0,1))
 for name,a in [('concrete_color',native(lin)),('concrete_height',np.repeat(((fields['Height']-.5)*spec['height_scale_m'])[:,:,None],3,2)),('concrete_roughness',np.repeat(fields['Roughness'][:,:,None],3,2))]:write_pfm(OUT/(name+'.pfm'),a)
 s=Scene();ids={}
 def field(name,color,height,roughness,tile):
  b=s.material('plastic',(1,1,1),.8,ior=1.45,texture=color);s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+f' {1.25/tile} {1.25/tile} 1';s.emit('roughness_texture',b,json.dumps(str(roughness)),1.25/tile,1.25/tile,1)
  m=s.material('bumpmap',texture=height);s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+f' {1.25/tile} {1.25/tile} 1';s.emit('nested',m,b,-1,.5);s.emit('metric_bump',m);ids[name]=m
 field('soil',R/'evidence/full-iv-materials/coastal_soil_color_native.pfm',R/'evidence/full-iv-materials/coastal_soil_height_metres.pfm',R/'evidence/full-iv-materials/coastal_soil_roughness.pfm',.18)
 field('path',OUT/'concrete_color.pfm',OUT/'concrete_height.pfm',OUT/'concrete_roughness.pfm',.32)
 for name,mean in [('wall',(.66,.66,.625)),('tanwall',(.46,.40,.33))]:
  a=read_pfm(R/'evidence/full-iv-street-finishes/6574_cream_stucco_native.pfm');a*=native(mean)/a.mean((0,1));write_pfm(OUT/(name+'.pfm'),a)
  field(name,OUT/(name+'.pfm'),R/'evidence/full-iv-street-finishes/lime_height_metres.pfm',R/'evidence/full-iv-street-finishes/lime_roughness.pfm',.65)
 for name,c,rough in [('trim',(.61,.62,.60),.46),('roof',(.24,.24,.22),.82),('bark',(.16,.13,.095),.92),('dry',(.27,.225,.15),.88),('litter',(.20,.17,.115),.96),('mineral',(.43,.42,.37),.87),('gold',(.75,.51,.026),.6),('disk',(.11,.065,.022),.8),('cloth',(.51,.49,.43),.9),('asphalt',(.055,.058,.057),.87),('lawn',(.10,.14,.045),.88)]:ids[name]=s.material('plastic',native(c),rough,ior=1.45)
 for name,c in [('sage',(.24,.285,.205)),('sunflower',(.15,.215,.09)),('rhus',(.065,.115,.042)),('sedge',(.085,.16,.047)),('tree',(.105,.155,.073))]:
  a=s.material('plastic',native(c),.72,ior=1.44);b=s.material('difftrans',native(np.asarray(c)*.8));m=s.material('blendbsdf');s.emit('nested',m,a,b,.14);ids[name]=m
 n=512;x,y=np.meshgrid((np.arange(n)+.5)/n,(np.arange(n)+.5)/n);hh=.0009*np.sin(2*np.pi*(4*x+2*y))+.0004*np.sin(2*np.pi*(7*x-5*y)+.7)+.0002*np.sin(2*np.pi*(13*x+9*y)+2)
 write_pfm(OUT/'ripple_metres.pfm',np.repeat(hh[:,:,None],3,2))
 for name,c in [('lagoon',(.015,.031,.022)),('basin',(.032,.043,.017))]:
  a=s.material('plastic',native(c),.075,ior=1.333);m=s.material('bumpmap',texture=OUT/'ripple_metres.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' .625 .625 1';s.emit('nested',m,a,-1,.5);s.emit('metric_bump',m);ids[name]=m
 while s.materials<69:s.material('diffuse',(.2,.2,.2))
 assert s.materials==69;s.material('thindielectric',(.98,.98,.98),.02,ior=1.52);s.material('diffuse',native((.08,.085,.075)))
 s.save(OUT/'materials.cys');(OUT/'MATERIAL_IDS.json').write_text(json.dumps(ids,indent=2))
 from correct_lagoon_daylight_v11 import corrected_light
 corrected_light()
 print('V11 materials complete',len(ids),flush=True)

def build():
 ids=json.loads((OUT/'MATERIAL_IDS.json').read_text());fs=features();sources=[]
 for row in json.loads((R/'data/full-iv-20261011/water-000.json').read_text())['features']:
  sources.append((row['attributes'],FRAME.project_geometry(arcgis_geometry(row['geometry']))))
 lagoon=next(g for p,g in sources if p.get('Name')=='UCSB Lagoon');allwater=unary_union([g for p,g in sources]).intersection(DOMAIN)
 buildings=[f for f in fs if f['category']=='buildings'];bu=unary_union([f['geometry'] for f in buildings])
 def union(kind):return unary_union([f['geometry'].buffer(1.2) if 'LineString' in f['geometry'].geom_type else f['geometry'] for f in fs if f['category'] in kind]).intersection(DOMAIN)
 paths=union(['footpaths','bike-paths']).difference(allwater).difference(bu);rawpaved=union(['driving-surfaces']).difference(allwater).difference(bu);overlap=paths.intersection(rawpaved).area;paved=rawpaved.difference(paths)
 assert BASIN.intersection(paths.union(paved)).area<1e-6
 lawn=union(['lawns']).difference(unary_union([paths,paved,allwater,bu,BASIN.buffer(4)]))
 land=DOMAIN.difference(allwater).difference(BASIN_WATER);soil=land.difference(unary_union([paths,paved,lawn,bu]))
 # One multiresolution Delaunay TIN. Fine vertices near the intended bank;
 # all classes clip this same TIN and use its barycentric support heights.
 clouds=[]
 for bounds,step in [(DOMAIN.bounds,12),((850,-900,1680,-180),4),((1280,-560,1460,-380),1.),((1340,-500,1405,-450),.5)]:
  a,b,c,d=bounds;x,y=np.meshgrid(np.arange(a,c+1e-7,step),np.arange(b,d+1e-7,step));clouds.append(np.c_[x.ravel(),y.ravel()])
 # Exact rectangular outer boundary ensures complete supplied ground extent.
 a,b,c,d=DOMAIN.bounds;xx=np.r_[np.arange(a,c,12),c];yy=np.r_[np.arange(b,d,12),d];clouds += [np.c_[xx,np.full(len(xx),b)],np.c_[xx,np.full(len(xx),d)],np.c_[np.full(len(yy),a),yy],np.c_[np.full(len(yy),c),yy]]
 clouds.append(np.asarray(DOMAIN.exterior.coords));xy=np.unique(np.concatenate(clouds).astype('<f4'),axis=0);xy=xy[shapely.intersects_xy(DOMAIN,xy[:,0],xy[:,1])];tin=Delaunay(xy);ff=tin.simplices;z=designed_height(xy).astype('<f4');vv=np.c_[xy,z]
 triangles=shapely.polygons(xy[ff]);tree=shapely.STRtree(triangles);centers=xy[ff].mean(1)
 def sample(p):
  p=np.asarray(p);k=tin.find_simplex(p,tol=1e-7);assert np.all(k>=0);t=tin.transform[k];bc=np.einsum('nij,nj->ni',t[:,:2],p-t[:,2]);weight=np.c_[bc,1-bc.sum(1)];return (weight*z[ff[k]]).sum(1)
 valid_ground=shapely.intersects_xy(DOMAIN,centers[:,0],centers[:,1]);normal_faces=ff[valid_ground];cross=np.cross(vv[normal_faces[:,1]]-vv[normal_faces[:,0]],vv[normal_faces[:,2]]-vv[normal_faces[:,0]]);vertex_normals=np.zeros_like(vv,dtype=float)
 for corner in range(3):np.add.at(vertex_normals,normal_faces[:,corner],cross)
 norm=np.linalg.norm(vertex_normals,axis=1);vertex_normals[norm==0]=[0,0,1];vertex_normals/=np.linalg.norm(vertex_normals,axis=1)[:,None]
 def normals(p):
  p=np.asarray(p);k=tin.find_simplex(p,tol=1e-7);assert np.all(k>=0);t=tin.transform[k];bc=np.einsum('nij,nj->ni',t[:,:2],p-t[:,2]);weights=np.c_[bc,1-bc.sum(1)];n=(weights[:,:,None]*vertex_normals[ff[k]]).sum(1);return n/np.linalg.norm(n,axis=1)[:,None]
 parts=Parts(OUT/'ground.clm',10000000);audits=[]
 def surface(name,area,mat,height=sample,normal=True):
  area=area.intersection(DOMAIN)
  if area.is_empty:return
  inside,touch=polygon_tin_masks(area,triangles,tree,centers);clip=LocalPolygonClipper(area,padding=20);batch=[];total=0;maxerr=0
  def write(p,f):
   nonlocal total,maxerr
   if not len(f):return
   zz=height(p);v=np.c_[p,zz];nm=normals(p) if normal else np.tile([0,0,1.],(len(p),1));parts.mesh(name,v,f,mat,name,'One shared support TIN; clipped elevations are interpolated in that parent surface',normals=nm,uv_period=(.144 if mat==ids['soil'] else .256 if mat==ids['path'] else 1.6),drop_zero_projected_area=True);total+=len(f)
   if height is sample:maxerr=max(maxerr,float(np.max(abs(v[:,2].astype('f4')-sample(p)))))
  # Retain source geographic triangle orientation, no shifted duplicate tops.
  write(xy,ff[inside])
  for k in np.flatnonzero(touch):
   for poly in polygons(clip.intersection(triangles[k]) if max(np.ptp(xy[ff[k]],axis=0))<=40 else area.intersection(triangles[k])):
    if poly.area<1e-8:continue
    p,f=triangulate_polygon(poly);batch.append(p[f])
   if len(batch)>=150:
    p=np.concatenate(batch).reshape(-1,2);write(p,np.arange(len(p)).reshape(-1,3));batch=[]
  if batch:p=np.concatenate(batch).reshape(-1,2);write(p,np.arange(len(p)).reshape(-1,3))
  audits.append({'name':name,'area_m2':area.area,'triangles':total,'serialized_support_error_m':maxerr});print('V11 surface',name,total,flush=True)
 surface('mineral_ground',soil,ids['soil']);surface('concrete_paths',paths,ids['path']);surface('driving_surfaces_partitioned',paved,ids['asphalt']);surface('managed_lawn',lawn,ids['lawn'])
 surface('lagoon',lagoon,ids['lagoon'],lambda p:2.74+.004*np.sin(np.asarray(p)[:,0]*.7+np.asarray(p)[:,1]*.5),False)
 surface('restoration_basin_estimate',BASIN_WATER,ids['basin'],lambda p:np.full(len(p),BASIN_LEVEL),False)
 surface('other_water_context',allwater.difference(lagoon),ids['lagoon'],lambda p:np.full(len(p),.11),False)
 groundreport=parts.close();np.savez_compressed(OUT/'support.npz',xy=xy,z=z,faces=ff)
 (OUT/'SURFACES.json').write_text(json.dumps({'mapped_path_paving_overlap_m2':overlap,'partition_priority':['building','water','paths','driving','lawn','soil'],'surfaces':audits,'basin':mapping(BASIN),'basin_water':mapping(BASIN_WATER),'basin_level_m':BASIN_LEVEL,'basin_status':'Photo/official-history anchored shape, position, level and below-water grade estimates; not surveyed. Exact placement chosen within mapped terrestrial bank and outside hardscape.','basin_source':'https://ccber.ucsb.edu/restoration-area-campus-lagoon','domain_local_m':DOMAIN.bounds,'shared_surface':True,'no_layer_offsets':True},indent=2))
 print('V11 ground complete',groundreport['triangles'],flush=True)
 build_architecture(buildings,ids,sample)
 build_plants(fs,soil,lagoon,ids,sample)
 (OUT/'SOURCE_PIN.json').write_text(json.dumps({'generator_sha256':digest(__file__),'source_checkpoint':'Preserved original CYBR all-Isla-Vista scene lineage; public source closure recorded in SCENE_SOURCE.json','last_image_sha256':'1a0f2e8bcba7cce1a077eedba1c74305cc10892ee983f2130cd289dfdd2d8b74','artifacts':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.suffix in ['.clm','.cys','.npz']},'original_sources_retained':True},indent=2))

def build_architecture(buildings,ids,height):
 parts=Parts(OUT/'architecture.clm',11000000);records=[]
 for feature in buildings:
  poly=feature['geometry'].intersection(DOMAIN);sid=feature['source'];oid=feature['props'].get('OBJECTID');close=poly.distance(Point(*CAMERA[:2]))<350;story=int(feature['props'].get('FLOORCOUNT') or 2);story=min(10,max(1,story))
  if oid in [318,327]:story=8
  pieces=[(poly,story)]
  if oid==327:
   tall_area=unary_union([box(1320,-433.3,1378.6,-380),box(1365,-437,1381.7,-420),box(1390,-422.8,1406.1,-380)])
   pieces=[(poly.intersection(tall_area),8),(poly.difference(tall_area),1)]
  b=Buffer(sid);window_count=0
  for component,levels in pieces:
   for pp in polygons(component):
    if pp.area<1:continue
    pp=orient(pp,1);coords=np.array(pp.exterior.coords);datum=float(np.median(source_height(coords)));h=levels*3.1 if levels>1 else 4.0;v,faces=triangulate_polygon(pp);b.mesh(np.c_[v,np.full(len(v),datum+h)],faces,ids['roof'],v/1.25)
    for a,c in zip(coords[:-1],coords[1:]):
     length=np.linalg.norm(c-a)
     if length<.08:continue
     facade=Facade(b,a,c,datum);opens=[]
     core=oid==327 and 1378<a[0]<1382 and abs(c[0]-a[0])<1 and length>7
     if close and length>2.0:
      pitch=2.35 if levels>=8 else 4.2;count=max(1,int(length/pitch))
      for floor in range(levels):
       for k in range(count):
        center=length*(k+.5)/count;width=min(1.25 if levels>=8 else 2.10,length/count-.45);lo=floor*3.1+.88;hi=floor*3.1+2.44;opens.append((center-width/2,center+width/2,lo,hi,'window'))
     if core:opens=[(.5,min(length-.5,3.9),floor*3.1+.12,floor*3.1+2.98,'window') for floor in range(levels)]
     material=ids['wall'] if abs(facade.n[0])>.6 or core else ids['tanwall']
     foundation_bottom=min(-.35,float(source_height(np.asarray([a,c])).min())-datum-.15);facade.wall(opens,h,material,ids['trim'],floor=foundation_bottom);window_count+=len(opens)
     for j,(x0,x1,z0,z1,_) in enumerate(opens):
      if (j+int(oid or 0))%5==0:continue
      # Real folded half-curtains with small gaps, behind the glass plane.
      for side in [0,1]:
       left=x0+side*(x1-x0)*.62;right=left+(x1-x0)*.38
       xs=np.linspace(left,right,7)
       for aa,bb in zip(xs[:-1],xs[1:]):
        ya=-.30+.024*np.sin((aa-left)*80);yb=-.30+.024*np.sin((bb-left)*80)
        b.quad([facade.world(aa,ya,z0+.025),facade.world(bb,yb,z0+.025),facade.world(bb,yb,z1-.04),facade.world(aa,ya,z1-.04)],ids['cloth'])
     if levels>=8:
      facade.box((length/2,.045,h-.05),(length,.17,.14),ids['trim'])
      for xx in np.arange(2.35,length,2.35):facade.box((xx,.015,h/2),(.12,.045,h),ids['wall'])
     if oid==327 and levels==1 and facade.n[1]<-.7:
      facade.box((length/2,.5,h-.1),(length+ .12,1.10,.24),ids['trim'])
    records.append({'source':sid,'footprint_component_m2':pp.area,'floors':levels,'height_m':h,'footprint_retained':True,'height_and_section_split':'Photo-guided estimate; official eight-story description overrides unqualified GIS10 for dorms.'})
  b.finish(parts)
 report=parts.close();report.update(buildings=records);(OUT/'ARCHITECTURE.json').write_text(json.dumps(report,indent=2));print('V11 architecture complete',report['triangles'],flush=True)

def build_plants(fs,soil,lagoon,ids,height):
 parts=Parts(OUT/'plants.clm',12000000);rng=np.random.default_rng(2026101204);counts={};leafarea={}
 def leaves(name,c,a,l,w,mat,roll=None):
  if not len(c):return
  v,f=leaf_mesh(c,a,l,w,folded=False,rolls=roll);parts.mesh(name,v,f,mat,name,'Botanically differentiated foliage: sage uses narrow subpixel compound-foliage groups at this view distance; other leaves at SI scale. Individual plants and seasonal state estimated');leafarea[name]=leafarea.get(name,0)+float(np.sum(np.asarray(l)*np.asarray(w)*.5))
 # Bank restoration community: overlapping species cohorts. Explicit spatial
 # support excludes hardscape and water; no nearest-N truncation creates holes.
 bank=soil.intersection(box(1280,-550,1450,-440));x,y=np.meshgrid(np.arange(1280,1450,1.3),np.arange(-550,-440,1.3));p=np.c_[x.ravel(),y.ravel()]+rng.uniform(-.49,.49,(x.size,2));p=p[shapely.contains_xy(bank,p[:,0],p[:,1])];p=p[np.linalg.norm(p-CAMERA[:2],axis=1)<150]
 for j,q in enumerate(p):
  dist=np.linalg.norm(q-CAMERA[:2]);signal=np.sin(q[0]*.26+q[1]*.13)+.65*np.cos(q[0]*.071-q[1]*.19)
  if rng.random()<(.12 if dist<70 else .38):continue
  kind='sage' if signal<.65 else 'sunflower' if signal<1.32 else 'rhus';counts[kind]=counts.get(kind,0)+1
  root=np.r_[q,height(q[None])[0]+.008];h=rng.uniform(.52,.98) if kind=='sage' else rng.uniform(.7,1.3) if kind=='sunflower' else rng.uniform(.95,1.7);rad=h*(.70 if kind=='sage' else .55);stems=7 if dist<60 else 4
  cc=[];aa=[];ll=[];ww=[];petal_c=[];petal_a=[];petal_l=[];petal_w=[]
  for branch in range(stems):
   az=branch*2.399963+rng.uniform(-.25,.25);direction=np.array([np.cos(az),np.sin(az),0]);tip=root+direction*rad*rng.uniform(.45,1)+[0,0,h*rng.uniform(.65,1)]
   parts.tube('shrub_stem',root,tip,.008,.002,ids['bark'],kind,'Connected branching shrub structure',segments=4)
   for shoot in range(5 if dist<70 else 3):
    t=.32+shoot*.125;start=root+(tip-root)*t;phi=az+(-1 if shoot%2 else 1)*1.4;end=start+np.array([np.cos(phi)*rad*.48,np.sin(phi)*rad*.48,h*.35]);parts.tube('lateral_shoot',start,end,.003,.001,ids['bark'],kind,'Leaves attach to actual lateral shoot',segments=3)
    for node in range(17 if kind=='sage' and dist<60 else 11):
     tt=(node+.7)/18 if kind=='sage' and dist<60 else (node+.7)/12;center=start+(end-start)*tt
     for sign in [-1,1]:
      direction=np.array([np.cos(phi+sign*1.12),np.sin(phi+sign*1.12),rng.uniform(.1,.65)]);direction/=np.linalg.norm(direction);length=rng.uniform(.082,.14) if kind=='sage' else rng.uniform(.105,.165) if kind=='sunflower' else rng.uniform(.065,.10);width=length*(rng.uniform(.24,.34) if kind=='sage' else .60 if kind=='sunflower' else .48)
      cc.append(center+direction*length*.45);aa.append(direction);ll.append(length);ww.append(width)
    if kind=='sunflower' and shoot%2==0:
     head=end+[0,0,.12];parts.tube('flower_peduncle',end,head,.0018,.001,ids['bark'],kind,'Authored flowering season',segments=3)
     for k in range(11):
      angle=k*2*np.pi/11;ax=np.array([np.cos(angle),np.sin(angle),.12]);petal_c.append(head+ax*.02);petal_a.append(ax);petal_l.append(.035);petal_w.append(.012)
     parts.tube('flower_disk',head-[0,0,.002],head+[0,0,.003],.009,.009,ids['disk'],kind,'Finite central floral disk',segments=7)
  leaves(kind+'_fine_foliage_groups' if kind=='sage' else kind,cc,aa,ll,ww,ids[kind],rng.uniform(-1.1,1.1,len(cc)));leaves('yellow_flowerheads',petal_c,petal_a,petal_l,petal_w,ids['gold'])
  if j%500==0:print('V11 shrubs',j,'triangles',parts.writer.triangles,flush=True)
 # Basin fringe and connected understory with tall narrow, curving leaves.
 fringe=BASIN.buffer(2.0).difference(BASIN.buffer(-.22));under=bank.difference(BASIN.buffer(1.5));x,y=np.meshgrid(np.arange(1280,1450,.48),np.arange(-550,-440,.48));pp=np.c_[x.ravel(),y.ravel()]+rng.uniform(-.18,.18,(x.size,2));pp=pp[shapely.contains_xy(bank,pp[:,0],pp[:,1])];cc=[];aa=[];ll=[];ww=[];dryc=[];drya=[];dryl=[];dryw=[]
 for q in pp:
  near=Point(q).distance(BASIN)<2.0;dist=np.linalg.norm(q-CAMERA[:2])
  if dist>100 or (not near and rng.random()<.42):continue
  z=float(height(q[None])[0]);h=rng.uniform(.60,1.05) if near else rng.uniform(.16,.40)
  for k in range(50 if near else 42):
   az=rng.uniform(0,2*np.pi);axis=np.array([np.cos(az)*.35,np.sin(az)*.35,1]);axis/=np.linalg.norm(axis);length=h*rng.uniform(.65,1.1);center=np.r_[q+rng.normal(0,.035,2),z]+axis*length*.47
   target=(cc,aa,ll,ww) if near or rng.random()<.55 else (dryc,drya,dryl,dryw)
   for buf,item in zip(target,[center,axis,length,rng.uniform(.006,.012)]):buf.append(item)
 leaves('sedge_and_understory',cc,aa,ll,ww,ids['sedge'],rng.uniform(-1,1,len(cc)));leaves('dry_understory',dryc,drya,dryl,dryw,ids['dry'],rng.uniform(-1,1,len(dryc)))
 # Source-polygon background habitat maintains the lagoon's opposite bank,
 # with a distance tier of narrow leaf groups and dry understory. No new
 # geographic cover polygons or exact tree identities are inferred.
 from shapely.geometry import shape
 source_cover=json.loads((R/'evidence/full-iv-lagoon-habitat-extension/SOURCE_COVERAGE.geojson').read_text())
 habitat=unary_union([shape(f['geometry']) for f in source_cover['features'] if f['properties']['class'] in ['scrub','woodland']]).intersection(soil).difference(bank)
 bounds=habitat.bounds;gx,gy=np.meshgrid(np.arange(bounds[0],bounds[2],3.3),np.arange(bounds[1],bounds[3],3.3));pp=np.c_[gx.ravel(),gy.ravel()]+rng.uniform(-1.2,1.2,(gx.size,2));pp=pp[shapely.contains_xy(habitat,pp[:,0],pp[:,1])];pp=pp[np.linalg.norm(pp-CAMERA[:2],axis=1)<600]
 for j,q in enumerate(pp):
  root=np.r_[q,height(q[None])[0]];h=rng.uniform(.55,1.35);cc=[];aa=[];ll=[];ww=[]
  for shoot in range(6):
   az=shoot*2.399963;tip=root+[np.cos(az)*h*.6,np.sin(az)*h*.6,h*.7];parts.tube('source_habitat_stem',root,tip,.01,.002,ids['bark'],'mapped_scrub_or_woodland','Authored shrubs within preserved geographic class polygons',segments=3)
   for leaf in range(40):
    cc.append(tip+rng.normal(size=3)*[h*.23,h*.23,h*.22]);ax=rng.normal(size=3);aa.append(ax);ll.append(rng.uniform(.14,.26));ww.append(rng.uniform(.025,.075))
  leaves('regional_habitat_leaf_groups',cc,aa,ll,ww,ids['sage'] if j%3 else ids['sunflower'],rng.uniform(-1,1,len(cc)))
 # Leaf litter and small angular stones anchor plant bases to metric soil.
 for j in range(8000):
  q=rng.uniform([1310,-515],[1425,-443]);dist=np.linalg.norm(q-CAMERA[:2])
  if dist>85 or not bank.contains(Point(q)) or BASIN.buffer(.4).contains(Point(q)):continue
  z=float(height(q[None])[0]);scale_=rng.uniform(.007,.035);v=np.array([[q[0]-scale_,q[1],z],[q[0]+scale_,q[1],z+.002],[q[0],q[1]+scale_*.8,z+scale_*.45],[q[0],q[1]-scale_*.7,z+.001]]);v[:,2]=height(v[:,:2])+np.array([0,.002,scale_*.45,.001]);parts.mesh('mineral_grit',v,[[0,1,2],[0,3,1],[0,2,3],[1,3,2]],ids['mineral'],'authored bank mineral fraction','Discrete millimetre/centimetre contacts, estimated abundance; source mineral microbed retained beneath')
 # Mapped trees keep source roots. Nearby broadleaf crowns use thin botanical
 # leaves across full-depth secondary branches; distant trees use a smaller
 # branch-supported foliage tier, never a closed faceted crown hull.
 treerecords=[]
 for feature in fs:
  if feature['category']!='trees' or feature['geometry'].geom_type!='Point':continue
  q=np.array(feature['geometry'].coords[0]);distance=np.linalg.norm(q-CAMERA[:2])
  if distance>550 or not DOMAIN.buffer(-2).contains(feature['geometry']):continue
  genus=str(feature['props'].get('genus') or 'unclassified').strip();sid=feature['source'];local=np.random.default_rng(stable_seed(sid));palms={'Syagrus','Phoenix','Washingtonia','Howea','Butia','Chamaerops','Archontophoenix'};known={'Eucalyptus','Corymbia','Pinus','Platanus','Ficus','Jacaranda','Quercus','Schinus','Liquidambar','Olea','Pyrus','Alnus','Tipuana','Pittosporum','Acacia','Podocarpus','Cedrus','Cupressus','Sequoia','Lophostemon','Metrosideros'}
  if genus not in known|palms:continue
  h=(2.6 if genus=='Chamaerops' else 11 if genus in palms else 14 if genus in ['Eucalyptus','Corymbia','Pinus'] else 8)*local.uniform(.85,1.1);root=np.r_[q,height(q[None])[0]];radius=h*.29
  if lagoon.contains(Point(q)) or BASIN.contains(Point(q)):continue
  parts.tube('mapped_tree_trunk',root,root+[0,0,h*.7],h*.016,.07,ids['bark'],sid,'Mapped root; source genus, explicitly estimated height',segments=7)
  cc=[];aa=[];ll=[];ww=[]
  if genus in palms:
   crown=root+[0,0,h*.72];reach=min(3.8,h*.28)
   for j in range(22):
    az=j*2.399963;radial=np.array([np.cos(az),np.sin(az),0]);side=np.array([-radial[1],radial[0],0]);points=[]
    for t in np.linspace(0,1,11):points.append(crown+radial*reach*t+[0,0,reach*(.52*np.sin(np.pi*t)-.45*t*t)])
    for a,b in zip(points[:-1],points[1:]):parts.tube('palm_rachis',a,b,.014,.008,ids['bark'],sid,'Curved pinnate frond support',segments=4)
    for t in np.linspace(.10,.99,35 if distance<110 else 16):
     origin=crown+radial*reach*t+[0,0,reach*(.52*np.sin(np.pi*t)-.45*t*t)];length=.88*np.sin(np.pi*t)**.55+.10
     for sign in [-1,1]:
      axis=side*sign+radial*.45+[0,0,-.3-.65*t];axis/=np.linalg.norm(axis);cc.append(origin+axis*length*.46);aa.append(axis);ll.append(length);ww.append(.035 if distance<110 else .065)
   leaves('palm_leaflets',cc,aa,ll,ww,ids['tree'],local.uniform(-.35,.35,len(cc)));treerecords.append({'source':sid,'root_m':root.tolist(),'genus':genus,'estimated_height_m':h,'distance_m':distance,'representation':'Curved fronds and separate narrow leaflets; species scale estimated.'});continue
  for j in range(16):
   phi=j*2.399963;branch=root+[np.cos(phi)*radius*local.uniform(.5,1),np.sin(phi)*radius*local.uniform(.5,1),h*(.55+.4*local.random())];parts.tube('mapped_tree_branch',root+[0,0,h*.4],branch,.055,.009,ids['bark'],sid,'Branch-supported full-depth crown',segments=5)
   count=2200 if distance<70 else 800 if distance<150 else 72
   # Leaves distributed around secondary shoot volumes rather than umbrella.
   offsets=local.normal(size=(count,3))*[radius*.23,radius*.23,h*.105];centers=branch+offsets;axes=local.normal(size=(count,3));axes[:,2]*=.55;length=local.uniform(.09,.18,count) if distance<70 else local.uniform(.18,.30,count) if distance<150 else local.uniform(.4,.7,count);width=length*(.22 if genus in ['Eucalyptus','Corymbia'] else .44)
   cc.extend(centers);aa.extend(axes);ll.extend(length);ww.extend(width)
  leaves('mapped_tree_foliage',cc,aa,ll,ww,ids['tree'],local.uniform(-np.pi,np.pi,len(cc)));treerecords.append({'source':sid,'root_m':root.tolist(),'genus':genus,'estimated_height_m':h,'distance_m':distance,'representation':'Resolved small leaves within70m; narrow foliage groups70–150m and reduced branch-supported groups farther out. Source roots retained.'})
 report=parts.close();report.update(species_counts=counts,leaf_area_m2=leafarea,trees=treerecords,season='Authored mixed active/flowering restoration state informed by CCBER photograph, not capture date or current inventory.');(OUT/'BOTANY.json').write_text(json.dumps(report,indent=2));print('V11 plants complete',report['triangles'],counts,flush=True)

def capture(width,spp,view="basin"):
 views={"basin":(CAMERA,TARGET,49.),"lagoon-context":(np.array([1400.,-498.,11.]),np.array([1328.,-454.,6.8]),55.)}
 origin,target,fov=views[view]
 light=json.loads((OUT/'LIGHT.json').read_text());s=Scene();s.lines=(OUT/'materials.cys').read_text().splitlines()
 # Resolve preserved material references in the generated component directory.
 import re
 s.lines=[re.sub(r'"([^\"]+)"',lambda m:json.dumps(str((OUT/m[1]).resolve())),line) for line in s.lines]
 s.settings(width,round(width*.7),spp,8,2,6,20261012,1.05);s.camera(origin,target,(0,0,1),fov)
 s.emit('observer',json.dumps(str(R/'work/cybr-light/data/CIE_xyz_1931_2deg.csv')));s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str(OUT/'coastal_diffuse_sky.pfm')),0);s.emit('environment_sun',DAY['sun_direction'],light['native_sun'],DAY['solar_radius_radians'])
 for name in ['ground','architecture','plants']:s.mesh(OUT/(name+'.clm'))
 stem=OUT/(f'view_{width}_{spp}' if view=='basin' else f'{view}_{width}_{spp}');s.save(stem.with_suffix('.cys'))
 import subprocess
 subprocess.run([sys.executable,str(R/'work/audit_scene_metric_uv.py'),str(stem.with_suffix('.cys'))],check=True)
 print('V11 tracing admitted',width,spp,flush=True)
 report=render(s,stem,metadata={'scope':'Geographic full lagoon and visible/reflected context of Isla Vista, source v10 reconstruction with original CYBR materials and procedural components.','source_image':'https://ccber.ucsb.edu/sites/default/files/images/2023-12/SN3_postrest.JPG','camera':'Virtual lower restoration-bank overlook chosen from mapped footprint projection; not a recovered source-photo pose or surveyed viewpoint.','new_estimates':['Small freshwater basin position/outline/level and microtopography','Photo-informed architectural sections/openings','Mixed species growth/flowering state','Diffuse coastal sky mixture'],'rendering':'Actual native CYBR LIGHT CPU transport. No image-generation or photograph textures.','display':'Retained centre-hit guided atrous, ACES fitted curve and sRGB, exposure1.05.'});print('V11 complete',json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['materials','build','capture']);p.add_argument('--width',type=int,default=1000);p.add_argument('--spp',type=int,default=32);p.add_argument('--view',choices=['basin','lagoon-context'],default='basin');a=p.parse_args()
 if a.action=='materials':make_materials()
 elif a.action=='build':build()
 else:capture(a.width,a.spp,a.view)
