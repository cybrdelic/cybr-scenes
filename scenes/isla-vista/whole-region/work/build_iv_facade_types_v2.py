"""Illustrative, reference-informed opening systems on mapped IV footprints.

These are typed architectural estimates, not recovered observations of each
facade. Footprints and supplied story counts remain source anchors. Openings,
room-side backing, trim and finishes are consistently authored per type.
"""
from pathlib import Path
import hashlib, struct, re, collections
import sys,json,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from shapely.geometry import shape,Point,LineString
from shapely.geometry.polygon import orient
from shapely.ops import transform
from shapely.strtree import STRtree
from cybr_ucsb.ingest import ingest,polygons
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.geometry import triangulate_polygon,optical_atlas
from cybr_terrain.materials import write_pfm
from cybr_light import Scene
from iv_mesh_parts import Parts
from iv_facade_assemblies import FacadeFrame, family
out=r/'evidence/full-iv-facades-v2';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs';sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);d=ingest(r/'data/full-iv-20261011',sector)
boundary=json.loads((r/'evidence/whole-iv-coverage/isla_vista_cdp.geojson').read_text());cdp=transform(lambda x,y,z=None:sector.frame.local(x,y),shape(boundary['features'][0]['geometry']))
layout=json.loads((base/'glb-part-layout.json').read_text());wall_ids={p['part']:p['component'] for b in layout.values() for p in b['parts'] if p['part'].endswith('_walls')};roof_rows={}
for x in json.loads((base/'TAGGED_ROOFS.json').read_text())['details']:roof_rows.setdefault(x['source_id'],[]).append(x)
all_roads=[f for f in d.selected('road') if f.geometry.geom_type in {'LineString','MultiLineString'} and f.geometry.length>2]
# Prefer actual through-streets, retaining unnamed streets; access lanes remain
# source geometry but do not automatically determine the primary elevation.
roads=[f for f in all_roads if f.properties.get('highway') not in {'service','track','path','footway','cycleway','steps','pedestrian'} and not f.properties.get('service')]
assert roads
road_tree=STRtree([f.geometry for f in roads])
all_buildings=d.selected('building');building_tree=STRtree([f.geometry for f in all_buildings])
roof_objects={}
stems={f.id.replace(':','_')+'_':f.id for f in all_buildings}
for batch in layout.values():
 for part in batch['parts']:
  if part['part'].endswith('_roof') or '_roof_tagged_' in part['part']:
   source=next((sid for stem,sid in stems.items() if part['part'].startswith(stem)),None)
   if source:roof_objects[part['component']]=source
roof_faces=collections.defaultdict(list)
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
with (base/'sector.clm').open('rb') as stream:
 magic,total,packets=struct.unpack('<4sQI',stream.read(16));assert magic==b'CLM1'
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',stream.read(4));v=np.frombuffer(stream.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(stream.read(nt*11),dtype)
  for obj in np.unique(t['object']):
   if int(obj) in roof_objects:
    roof_faces[roof_objects[int(obj)]].extend(v[t['indices'][t['object']==obj],:3].astype(float))
 assert not stream.read(1)
print('RETAINED_ROOF_BOUNDARIES',len(roof_faces),flush=True)
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inverse=np.linalg.inv(M)
def native(rgb):
 c=(np.array(rgb)*white)@inverse.T
 if np.min(c)<-1e-6:raise ValueError('Unrepresentable facade optical control')
 return np.maximum(0,c)
prior=json.loads((r/'evidence/full-iv-pardall/PARDALL_RECEIPT.json').read_text());offset=prior['material_offset']+prior['material_count'];s=Scene();s.materials=offset
# Reuse the exact existing CYBR optical fields and native material slots.
# Geometry is the independent variable in the first matched test.
prior_materials=r/'evidence/full-iv-facades/materials.cys'
s.lines=[re.sub(r'"([^"]+)"',lambda m:json.dumps(str((prior_materials.parent/m[1]).resolve())),line) for line in prior_materials.read_text().splitlines() if line and not line.startswith('#')]
s.materials=72
walls={'house':58,'apartment':60,'commercial':62,'institution':64,'unspecified':66}
frame,trim,glass,inside,door=67,68,69,70,71
parts=Parts(out/'facades.clm',5000000);skip=[];records=[]
class Buffer:
 def __init__(self):self.groups={};self.window_count=0;self.roof_edge_count=0;self.blocked_wall_count=0
 def quad(self,v,mat,uv):
  v=np.asarray(v,dtype='<f4').astype(float).tolist() # Normals computed from actual exported coordinates.
  g=self.groups.setdefault(mat,{'v':[],'f':[],'uv':[]});j=len(g['v']);g['v'].extend(v);g['f'].extend([[j,j+1,j+2],[j,j+2,j+3]]);g['uv'].extend(uv)
 def emit(self,prefix,source):
  for mat,g in self.groups.items():parts.mesh(prefix+'_'+str(mat),g['v'],g['f'],mat,source,'Reusable closed facade construction; family, dimensions and unseen elevations are authored estimates',uv=g['uv'])
for f in d.selected('building'):
 if f.id in {'osm:way:42753197','ucsb:buildings:549'} or not cdp.intersects(f.geometry):continue
 p={**f.properties.get('osm_match',{}).get('tags',{}),**f.properties};tag=str(p.get('building','')).lower();use=str(p.get('BLDGTYPE','')).lower()
 if tag in {'garage','garages','shed','roof','carport','greenhouse','kiosk','service'}:continue
 kind='apartment' if tag in {'apartments','dormitory','hotel'} else 'house' if tag in {'house','detached','semidetached_house','terrace','residential'} else 'commercial' if tag in {'retail','commercial','office'} else 'institution' if tag in {'university','school','church','civic'} or 'acad' in use else 'unspecified'
 value=p.get('building:levels',p.get('FLOORCOUNT'));story_source='source floor count'
 try:levels=int(float(value));assert 1<=levels<=8
 except (ValueError,TypeError,AssertionError):levels=max(1,min(5,round(float(p['height_m'])/3.3)));story_source='estimated from retained massing height'
 nearest=roads[int(road_tree.nearest(f.geometry.centroid))];buffer=Buffer();feature_skips=[];opening_count=0;fronts=[];style=family(f.id,kind)
 for index,polygon in enumerate(polygons(f.geometry)):
  if polygon.area<35:continue
  name=f.id.replace(':','_')+f'_{index}_walls'
  # Tagged roofs add a component suffix; keep the original per-part mapping.
  matching=[(n,i) for n,i in wall_ids.items() if n==name or n==f.id.replace(':','_')+f'_roofcomponent_{index}_0_walls']
  if not matching:continue
  xy,ff=triangulate_polygon(polygon);datum=float(np.median(d.dem.sample(xy[:,0],xy[:,1])));eave=datum+float(p['height_m'])
  if f.id in roof_rows and index<len(roof_rows[f.id]):eave=roof_rows[f.id][index]['eave_z_m']
  floor_height=(eave-datum)/levels
  if floor_height<2.2:continue
  polygon=orient(polygon,sign=1.0);coords=np.asarray(polygon.exterior.coords);candidates=[]
  for j,(aa,bb) in enumerate(zip(coords[:-1],coords[1:])):
   if np.linalg.norm(bb-aa)>2.4:candidates.append((Point((aa+bb)*.5).distance(nearest.geometry),j))
  front=min(candidates)[1] if candidates else -1;fronts.append({'polygon':index,'edge':front,'nearest_road':nearest.id,'road_name':nearest.properties.get('name'),'method':'nearest eligible exterior edge to non-service mapped through-street; authored frontage estimate'})
  feature_skips.extend(i for _,i in matching)
  for ring_no,ring in enumerate([polygon.exterior,*polygon.interiors]):
   c=np.asarray(ring.coords)[:,:2]
   for edge,(a,b) in enumerate(zip(c[:-1],c[1:])):
    length=float(np.linalg.norm(b-a))
    if length<.02:continue
    tangent=(b-a)/length;outward=np.array([tangent[1],-tangent[0]]);bottom=min(datum-.25,float(d.dem.sample(*a))-.1,float(d.dem.sample(*b))-.1)
    def quad(label,x0,x1,z0,z1,mat,depth=0):
     if x1-x0<1e-5 or z1-z0<1e-5:return
     v=[[* (a+tangent*x0-outward*depth),z0],[*(a+tangent*x1-outward*depth),z0],[*(a+tangent*x1-outward*depth),z1],[*(a+tangent*x0-outward*depth),z1]];uv=[[x0/1.25,z0/1.25],[x1/1.25,z0/1.25],[x1/1.25,z1/1.25],[x0/1.25,z1/1.25]];buffer.quad(v,mat,uv)
    assembly=FacadeFrame(buffer,a,b)
    is_front=ring_no==0 and edge==front
    bay_pitch=style['pitch'] if is_front else style['pitch']*1.15
    bays=max(1,int(length/bay_pitch));pitch=length/bays;active=length>=2.4
    for floor in range(levels):
     lo=datum+floor*floor_height;hi=datum+(floor+1)*floor_height
     for bay in range(bays):
      x0=bay*pitch;x1=(bay+1)*pitch;lower=bottom if floor==0 else lo
      if not active:quad('plain',x0,x1,lower,hi,walls[kind]);continue
      entry=is_front and floor==0 and bay==bays//2;shop=is_front and floor==0 and kind=='commercial'
      width=min(pitch-.60,2.0 if shop else style['width']*(1 if is_front else .86));left=(x0+x1-width)/2;right=left+width;wl=lo+(.10 if entry or shop else style['sill']);wh=min(hi-.48,wl+(2.16 if entry or shop else style['height']))
      if wh<=wl or width<.50:quad('plain',x0,x1,lower,hi,walls[kind]);continue
      # Test the full proposed opening span, not only the wall midpoint.
      span=LineString([a+tangent*left+outward*.08,a+tangent*right+outward*.08])
      nearby=building_tree.query(span.buffer(.40))
      blocked=any(all_buildings[int(j)].id!=f.id and all_buildings[int(j)].geometry.distance(span)<.30 for j in nearby)
      if blocked:
       quad('party_wall',x0,x1,lower,hi,walls[kind]);buffer.blocked_wall_count+=1;continue
      opening_count+=1
      quad('pier_l',x0,left,lower,hi,walls[kind]);quad('pier_r',right,x1,lower,hi,walls[kind]);quad('sill_wall',left,right,lower,wl,walls[kind]);quad('head_wall',left,right,wh,hi,walls[kind])
      assembly.opening(left,right,wl,wh,walls[kind],trim if style['light_frame'] else frame,
                       door if entry and kind=='house' else glass,inside,trim,
                       depth=style['reveal'],panes=style['panes'],door=entry,
                       curtains=(not entry and (floor+bay+index)%4==1))
      buffer.window_count+=1
    # Closed understated floor course; no generic balcony/gallery invention.
    if kind in {'apartment','commercial','institution'} and levels>1:
     for level in range(1,levels):
      z=datum+level*floor_height
      assembly.box(0,length,-.025,.025,z-.07,z-.025,trim)
  # Derive the perimeter from actual serialized roof triangles. Interior
  # diagonals/ridges cancel; keep only mapped exterior/interior boundaries.
  edge_counts=collections.Counter()
  for triangle in roof_faces.get(f.id,[]):
   for aa,bb in zip(triangle,np.roll(triangle,-1,axis=0)):
    key=tuple(sorted((tuple(aa),tuple(bb))))
    edge_counts[key]+=1
  for (aa,bb),count in edge_counts.items():
   if count!=1:continue
   aa=np.array(aa);bb=np.array(bb);mid=(aa[:2]+bb[:2])*.5
   if polygon.boundary.distance(Point(mid))>.002:continue
   length=float(np.linalg.norm(bb[:2]-aa[:2]))
   if length<.08:continue
   t=(bb[:2]-aa[:2])/length;n=np.array([t[1],-t[0]])
   if polygon.covers(Point(mid+n*.08)):aa,bb=bb,aa;n=-n
   span=LineString([aa[:2]+n*.05,bb[:2]+n*.05]);nearby=building_tree.query(span.buffer(.18))
   if any(all_buildings[int(j)].id!=f.id and all_buildings[int(j)].geometry.distance(span)<.12 for j in nearby):continue
   FacadeFrame(buffer,aa[:2],bb[:2]).roof_edge(length,aa[2],bb[2],trim,abs(aa[2]-bb[2])<.002)
   buffer.roof_edge_count+=1
 if feature_skips:
  buffer.emit(f.id.replace(':','_'),f.id)
  skip.extend(feature_skips);records.append({'source_id':f.id,'type':kind,'source_building_tag':tag,'stories':levels,'story_count_basis':story_source,'opening_count':opening_count,'frontage':fronts,'replaced_wall_objects':feature_skips,'family':style,'closed_window_assemblies':buffer.window_count,'retained_roof_edge_segments':buffer.roof_edge_count,'near_abutting_bays_without_openings':buffer.blocked_wall_count,'status':'Illustrative reusable construction, not an observation of this specific building'})
 if len(records) and len(records)%100==0:print('FACADES',len(records),parts.writer.triangles,flush=True)
report=parts.close();s.save(out/'materials.cys');report.update(material_offset=offset,material_count=s.materials-offset,replace_sector_components=sorted(skip),buildings=records,reference_basis=['references/residential-street-v2/REFERENCE_MANIFEST.json','references/del-playa-corridor/REFERENCE_MANIFEST.json'],source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),r/'work/iv_facade_assemblies.py',base/'normalized.geojson',base/'sector.clm',prior_materials]},geometry_contract={'mapped_wall_footprints_and_eave_heights':'unchanged','roof_boundary_basis':'serialized original roof triangles, unchanged slope and upper height; no new roof type','maximum_authored_roof_edge_projection_m':.042,'maximum_authored_window_sill_projection_m':.080,'party_wall_rule':'each full proposed opening span at80mm exterior is tested against other sourced footprints within300mm; geographic mapping quality limits this heuristic','normal_export':'coordinates quantized to float32 before computing face normals','reveals':'opposed correct winding, 0.16 to 0.21 m','glazing':'behind closed frame members, separate dark backing','curtains':'bounded estimated side panels, 0.075 m fold pitch and0.012 m depth','materials':'byte-identical retained fields and slots, no extra grain or photographic textures'},limits='Mapped footprints and supplied floor counts anchor the system. Opening layout, facade type when unspecified, frontage selection, optical finish and room-side backing are illustrative estimates. The two individually authored landmarks retain their own components. This is not a building-by-building photographic reconstruction.')
(out/'FACADE_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('DONE_FACADES_V2',len(records),report['triangles'],flush=True)
