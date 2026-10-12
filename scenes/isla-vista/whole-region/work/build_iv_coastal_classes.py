"""Source-class coastal cover with explicit authored late-dry-season appearance.

The map determines habitat polygons. It does not determine species, irrigation,
plant positions, season, reflectance, or vegetation height. Those presentation
choices are recorded separately. All support uses the retained visible TIN.
"""
from pathlib import Path
import sys,json,hashlib,time,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import shapely
from shapely.ops import unary_union
from scipy.ndimage import gaussian_filter
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import ingest,polygons
from cybr_ucsb.geometry import area_geometry,ocean_from_coastline,triangulate_polygon
from cybr_terrain.materials import write_pfm
from cybr_light import Scene
from iv_mesh_parts import Parts,leaf_mesh
from iv_shared_ground import SharedGround
from iv_polygon_tin import polygon_tin_masks,LocalPolygonClipper
out=r/'evidence/full-iv-coastal-classes';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs'
ground=SharedGround(base/'measured-terrain-state.npz');sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dataset=ingest(r/'data/full-iv-20261011',sector)
features=[f for f in dataset.selected('landcover') if f.geometry.geom_type in {'Polygon','MultiPolygon'}]
def category(f):
 p=f.properties
 if p.get('natural') in {'beach','sand'}:return 'beach'
 if p.get('natural')=='scrub':return 'scrub'
 if p.get('natural')=='wood' or p.get('landuse')=='forest':return 'woodland'
 if p.get('natural')=='grassland' or p.get('landuse')=='meadow':return 'natural_grass'
 if p.get('landuse')=='grass' or 'lawns' in str(p.get('_source','')).lower() or 'lawns' in str(getattr(f,'source','')).lower():return 'lawn'
 return 'park_or_garden'
classes=['beach','scrub','woodland','natural_grass','lawn','park_or_garden']
groups={k:[f for f in features if category(f)==k] for k in classes}
# The ingestion source category also identifies UCSB's mapped lawn polygons.
for f in list(groups['park_or_garden']):
 if 'lawn' in f.id.lower():groups['park_or_garden'].remove(f);groups['lawn'].append(f)
buildings=unary_union([f.geometry for f in dataset.selected('building')]);water=unary_union([ocean_from_coastline(dataset),*[f.geometry for f in dataset.selected('water') if f.geometry.geom_type in {'Polygon','MultiPolygon'}]])
widths=[];paving=unary_union([area_geometry(f,widths) for c in ['road','pavement','parking','path'] for f in dataset.selected(c)])
excluded=unary_union([buildings,water,paving]);occupied=shapely.Polygon();areas={}
for k in classes:
 areas[k]=unary_union([f.geometry for f in groups[k]]).intersection(sector.clip).difference(excluded).difference(occupied);occupied=unary_union([occupied,areas[k]])
source_records={k:[{'id':f.id,'properties':f.properties} for f in groups[k]] for k in classes}
(out/'class_coverage.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'class':k,'source_ids':[f.id for f in groups[k]]},'geometry':shapely.geometry.mapping(areas[k])} for k in classes]}))
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inverse=np.linalg.inv(M)
def native(rgb):return np.maximum(0,(np.asarray(rgb)*white)@inverse.T)
s=Scene();s.materials=74;material_offset=74;materials={};field_reports={};rng=np.random.default_rng(20261011)
# Area-integrated low-detail appearance: green/dry plant and exposed litter
# fractions. Values are authored linear reflectances, not measurements.
palette={
 'lawn':((.064,.145,.034),(.23,.181,.09),.14,.10,.84),
 'natural_grass':((.095,.153,.046),(.235,.188,.112),.78,.19,.93),
 'scrub':((.089,.12,.066),(.165,.139,.101),.66,.23,.91),
 'woodland':((.065,.09,.037),(.094,.073,.043),.72,.18,.96),
 'park_or_garden':((.073,.137,.046),(.18,.143,.083),.33,.20,.88)}
for k,(green,dry,fraction,variation,roughness) in palette.items():
 field=gaussian_filter(rng.normal(size=(256,256)),12,mode='wrap');field/=max(field.std(),1e-9);fraction_map=np.clip(fraction+variation*field*.45,0,1)
 color=np.asarray(green)*(1-fraction_map[...,None])+np.asarray(dry)*fraction_map[...,None]
 path=out/(k+'_canopy_response_native.pfm');write_pfm(path,native(color).astype('f4'))
 mid=s.material('plastic',(1,1,1),roughness,ior=1.44);s.emit('texture',mid,json.dumps(str(path.resolve())),1.25/32,1.25/32,1);materials[k]=mid
 field_reports[k]={'authored_live_linear_rgb':green,'authored_dry_or_litter_linear_rgb':dry,'mean_dry_fraction':float(fraction_map.mean()),'roughness':roughness,'low_detail_response_tile_m':32,'interpretation':'Area-integrated unresolved canopy/litter response; no enlarged individual leaf or measured spectral claim.'}
leaf_r=s.material('plastic',native((.082,.127,.049)),.76,ior=1.44);leaf_t=s.material('difftrans',native((.11,.17,.04)),1);leaf=s.material('blendbsdf');s.emit('nested',leaf,leaf_r,leaf_t,.14)
dry_leaf=s.material('plastic',native((.245,.191,.10)),.91,ior=1.44)
gray_leaf=s.material('plastic',native((.142,.17,.118)),.86,ior=1.44)
stem=s.material('plastic',native((.12,.095,.056)),.94,ior=1.45)
materials['beach']=13;s.save(out/'materials.cys')
triangles=shapely.polygons(ground.xy[ground.faces]);tree=shapely.STRtree(triangles);centroids=ground.xy[ground.faces].mean(1);parts=Parts(out/'coastal.clm',7000000);rows=[]
for k,area in areas.items():
 started=time.monotonic();inside,touch=polygon_tin_masks(area,triangles,tree,centroids);clipper=LocalPolygonClipper(area);vv=ground.vertices.copy();vv[:,2]+=.018
 parts.mesh(k+'_support',vv,ground.faces[inside],materials[k],k,'Mapped class; retained TIN support with18mm separation; authored seasonal optical response',drop_zero_projected_area=True)
 pending=[];batch=0
 def flush():
  global pending,batch
  if not pending:return
  t=np.concatenate(pending);v=t.reshape(-1,3);parts.mesh(k+f'_boundary_{batch}',v,np.arange(len(v)).reshape(-1,3),materials[k],k,'Exact mapped polygon/TIN clipping',drop_zero_projected_area=True);pending=[];batch+=1
 for idx in np.flatnonzero(touch):
  for polygon in polygons(clipper.intersection(triangles[idx])):
   if polygon.area<1e-8:continue
   p,f=triangulate_polygon(polygon);v=np.c_[p,ground.height(p)+.018];pending.append(v[f])
  if len(pending)>400:flush()
 flush();rows.append({'class':k,'source_feature_count':len(groups[k]),'nonoverlapping_area_m2':area.area,'ground_material_id':materials[k]});print('CLASS_SUPPORT',k,parts.writer.triangles,round(time.monotonic()-started,2),flush=True)
# Seeded placement is restricted to the classified polygons, excluded footprint
# holes, and ground support. The map has no individual shrub locations here.
plant_counts={};plant_records=[]
def sample(area,spacing,seed,margin):
 if area.is_empty:return np.empty((0,2))
 rr=np.random.default_rng(seed);minx,miny,maxx,maxy=area.bounds;x=np.arange(minx,maxx,spacing);y=np.arange(miny,maxy,spacing);xx,yy=np.meshgrid(x,y);p=np.c_[xx.ravel(),yy.ravel()]+rr.uniform(-.43,.43,(xx.size,2))*spacing
 core=area.buffer(-margin);shapely.prepare(core);return p[shapely.contains_xy(core,p[:,0],p[:,1])]
for k,spacing,height_range,radius_range in [('scrub',3.2,(.65,1.65),(.45,1.1)),('woodland',7.5,(.35,.8),(.3,.7)),('park_or_garden',10.,(.25,.7),(.3,.65))]:
 pp=sample(areas[k],spacing,912+classes.index(k),max(radius_range)*1.05);plant_counts[k]=len(pp);rng=np.random.default_rng(812+classes.index(k));v_all=[];f_all=[];baseidx=0;stem_v=[];stem_f=[]
 for index,p in enumerate(pp):
  h=rng.uniform(*height_range);radius=rng.uniform(*radius_range);origin=np.r_[p,ground.height(p[None])[0]+.018]
  # Grounded woody stem joins the coarse canopy; no hovering crown shell.
  angles=np.arange(5)*np.pi*2/5;ring=np.c_[np.cos(angles),np.sin(angles),np.zeros(5)]*h*.018;vv=np.vstack([origin+ring,origin+[0,0,h*.73]+ring*.42]);ff=[]
  for q in range(5):
   b=(q+1)%5;ff.extend([[q,b,b+5],[q,b+5,q+5]])
  stem_v.append(vv);stem_f.append(np.asarray(ff)+(len(stem_v)-1)*10)
  # Bounded overview tier: connected irregular canopy lobes with real holes.
  # These are aggregate leaf clusters, explicitly not metre-wide leaf blades.
  for lobe in range(4):
   a=lobe*2.39996323+rng.uniform(-.3,.3);center=origin+np.array([np.cos(a)*radius*.35,np.sin(a)*radius*.35,h*(.52+.10*rng.random())]);rad=radius*rng.uniform(.47,.68);v=[]
   for j in range(4):
    t=j/3;rr=rad*np.sin(np.pi*(.10+.80*t))
    for q in range(7):
     theta=q*np.pi*2/7+j*.24;v.append(center+[np.cos(theta)*rr,np.sin(theta)*rr,(t-.5)*h*.8])
   v=np.asarray(v);ff=[]
   for j in range(3):
    for q in range(7):
     if rng.random()<.18:continue
     a0=j*7+q;b0=j*7+(q+1)%7;ff.extend([[a0,b0,b0+7],[a0,b0+7,a0+7]])
   v_all.append(v);f_all.append(np.asarray(ff)+baseidx);baseidx+=len(v)
  if len(v_all)>=800:
   parts.mesh(k+'_canopy_batch'+str(index),np.concatenate(v_all),np.concatenate(f_all),gray_leaf if k=='scrub' else leaf,k,'Authored planted positions/heights; coarse porous canopy lobes for region-scale LOD');v_all=[];f_all=[];baseidx=0
 if v_all:parts.mesh(k+'_canopy_final',np.concatenate(v_all),np.concatenate(f_all),gray_leaf if k=='scrub' else leaf,k,'Authored low-detail canopy; mapped habitat polygon bounds')
 if stem_v:parts.mesh(k+'_grounded_stems',np.concatenate(stem_v),np.concatenate(stem_f),stem,k,'Estimated woody support connecting each authored canopy to the retained terrain')
 plant_records.append({'class':k,'count':len(pp),'height_range_m':height_range,'canopy_radius_m':radius_range,'spacing_m':spacing,'placement':'Seeded illustrative positions inside mapped polygon after full-radius setback; existing sourced tree points retained.'});print('CLASS_CANOPIES',k,len(pp),parts.writer.triangles,flush=True)
# Original CYBR MATERIALS grass construction: continuous quadratic bend, tapered
# ribbon, true metre dimensions. Sparse regional tufts supplement the integrated
# response; they do not pretend to resolve every individual blade at2m/pixel.
pp=sample(areas['natural_grass'],5.2,271,.30);rng=np.random.default_rng(272);v_all=[];f_all=[];offset=0
for i,p in enumerate(pp):
 z=ground.height(p[None])[0]+.018
 for blade in range(8):
  angle=rng.uniform(0,2*np.pi);h=rng.uniform(.13,.34);width=rng.uniform(.0018,.004);bend=rng.uniform(.15,.65)*h;root=p+rng.uniform(-.055,.055,2);z=ground.height(root[None])[0]+.018
  v=[]
  for j in range(4):
   t=j/3;center=np.r_[root+np.array([np.cos(angle),np.sin(angle)])*bend*t*t,z+h*t];side=np.array([-np.sin(angle),np.cos(angle),0])*width*.5*(1-.99*t);v.extend([center-side,center+side])
  v_all.extend(v);f_all.extend([[offset+j*2,offset+j*2+1,offset+j*2+3] for j in range(3)]);f_all.extend([[offset+j*2,offset+j*2+3,offset+j*2+2] for j in range(3)]);offset+=8
 if i%700==699:
  parts.mesh('natural_grass_tufts_'+str(i),v_all,f_all,dry_leaf,'natural_grass','Original MATERIALS quadratic tapered-blade construction; authored dry bunchgrass dimensions and sparse regional detail tier');v_all=[];f_all=[];offset=0
if v_all:parts.mesh('natural_grass_tufts_final',v_all,f_all,dry_leaf,'natural_grass','Authored dry bunchgrass regional tier')
plant_counts['natural_grass_tufts']=len(pp)
report=parts.close();layout=json.loads((base/'glb-part-layout.json').read_text());skip=[p['component'] for b in layout.values() for p in b['parts'] if p['part'].startswith(('mapped_landcover_','mapped_sand_'))]
report.update(material_offset=material_offset,material_count=s.materials-material_offset,replace_sector_components=skip,classes=rows,source_records=source_records,field_reports=field_reports,plant_counts=plant_counts,plant_records=plant_records,season='Authored late dry-season coastal presentation. Managed-lawn hydration and natural grass senescence are estimates; this is not a measured October2026 vegetation state.',overlap_priority=classes,terrain_support_offset_m=.018,ground_state_sha256=hashlib.sha256((base/'measured-terrain-state.npz').read_bytes()).hexdigest(),materials_reuse={'repository':'cybrdelic/cybr-material','commit':'12848c82f60bc58fa88640545868009b90298b32','geometry_blob':'bfbfe69374c90b17e3dbacf75883294457463996','recipe':'27_grass','adaptation':'Original quadratic-bent tapered blade construction translated from Blender to native meshlets. Authored longer bunchgrass dimensions; reduced regional segment/density tier. No selected-sample optical parity claim.'},references=[{'url':'https://ivparks.org/isla-vista-district-parks/natural-open-spaces/del-sol-vernal-pool-reserve/','basis':'Mapped Del Sol includes native reserve/vernal-pool habitats, not uniformly managed lawn.'},{'url':'https://www.ncos.ccber.ucsb.edu/native-plant-habitats/grassland','basis':'Coastal perennial bunchgrass community structure; annual/dry seasonal components.'},{'url':'https://www.ncos.ccber.ucsb.edu/native-plant-habitats/coastal-sage-scrub','basis':'Variable gray-green, drought-deciduous coastal shrub forms, generally around1–2m; not exact species identification in each polygon.'}],limits='Polygon classes and existing mapped trees are source data. Plant density, positions, height, physiology, spectra and seasonal state are authored approximations. Porous canopy lobes are low-detail cluster geometry; fine foliage and thatch are integrated appearance at this overview scale. No dynamic LOD, vegetation growth simulation, aerial-photo texture, photoreal or survey claim.')
(out/'COASTAL_CLASSES_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('DONE_COASTAL_CLASSES',report['triangles'],plant_counts,flush=True)
