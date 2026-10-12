"""Illustrative, reference-informed opening systems on mapped IV footprints.

These are typed architectural estimates, not recovered observations of each
facade. Footprints and supplied story counts remain source anchors. Openings,
room-side backing, trim and finishes are consistently authored per type.
"""
from pathlib import Path
import sys,json,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from shapely.geometry import shape,Point
from shapely.geometry.polygon import orient
from shapely.ops import transform
from shapely.strtree import STRtree
from cybr_ucsb.ingest import ingest,polygons
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.geometry import triangulate_polygon,optical_atlas
from cybr_terrain.materials import write_pfm
from cybr_light import Scene
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-facades';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs';sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);d=ingest(r/'data/full-iv-20261011',sector)
boundary=json.loads((r/'evidence/whole-iv-coverage/isla_vista_cdp.geojson').read_text());cdp=transform(lambda x,y,z=None:sector.frame.local(x,y),shape(boundary['features'][0]['geometry']))
layout=json.loads((base/'glb-part-layout.json').read_text());wall_ids={p['part']:p['component'] for b in layout.values() for p in b['parts'] if p['part'].endswith('_walls')};roof_rows={}
for x in json.loads((base/'TAGGED_ROOFS.json').read_text())['details']:roof_rows.setdefault(x['source_id'],[]).append(x)
roads=[f for f in d.selected('road') if f.geometry.geom_type in {'LineString','MultiLineString'} and f.geometry.length>2];road_tree=STRtree([f.geometry for f in roads])
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inverse=np.linalg.inv(M)
def native(rgb):
 c=(np.array(rgb)*white)@inverse.T
 if np.min(c)<-1e-6:raise ValueError('Unrepresentable facade optical control')
 return np.maximum(0,c)
prior=json.loads((r/'evidence/full-iv-pardall/PARDALL_RECEIPT.json').read_text());offset=prior['material_offset']+prior['material_count'];s=Scene();s.materials=offset
palette={'house':(.39,.365,.30),'apartment':(.47,.455,.415),'commercial':(.44,.43,.39),'institution':(.50,.495,.47),'unspecified':(.42,.41,.375)};walls={}
for kind,color in palette.items():
 atlas=optical_atlas('iv-'+kind+'-plaster',color,.84,.00045,out/'textures',256);color_path=out/'textures'/('iv-'+kind+'-native.pfm');height_path=out/'textures'/('iv-'+kind+'-height.pfm');write_pfm(color_path,native(atlas.albedo));write_pfm(height_path,np.repeat(atlas.height[:,:,None],3,axis=2));a=s.material('plastic',(1,1,1),.84,ior=1.45,texture=color_path);s.emit('roughness_texture',a,json.dumps(str(atlas.roughness_pfm.resolve())),1,1,1);b=s.material('bumpmap',texture=height_path);s.emit('nested',b,a,-1,.5);s.emit('metric_bump',b);walls[kind]=b
frame=s.material('plastic',native((.045,.052,.056)),.40,ior=1.48);trim=s.material('plastic',native((.47,.47,.425)),.64,ior=1.46);glass=s.material('thindielectric',(1,1,1),.035,ior=1.515);inside=s.material('diffuse',native((.022,.025,.023)),1);door=s.material('plastic',native((.11,.078,.045)),.76,ior=1.44)
parts=Parts(out/'facades.clm',5000000);skip=[];records=[]
class Buffer:
 def __init__(self):self.groups={}
 def quad(self,v,mat,uv):
  g=self.groups.setdefault(mat,{'v':[],'f':[],'uv':[]});j=len(g['v']);g['v'].extend(v);g['f'].extend([[j,j+1,j+2],[j,j+2,j+3]]);g['uv'].extend(uv)
 def emit(self,prefix,source):
  for mat,g in self.groups.items():parts.mesh(prefix+'_'+str(mat),g['v'],g['f'],mat,source,'Illustrative typed facade; openings, finish and unseen backing estimated, not surveyed',uv=g['uv'])
for f in d.selected('building'):
 if f.id in {'osm:way:42753197','ucsb:buildings:549'} or not cdp.intersects(f.geometry):continue
 p={**f.properties.get('osm_match',{}).get('tags',{}),**f.properties};tag=str(p.get('building','')).lower();use=str(p.get('BLDGTYPE','')).lower()
 if tag in {'garage','garages','shed','roof','carport','greenhouse','kiosk','service'}:continue
 kind='apartment' if tag in {'apartments','dormitory','hotel'} else 'house' if tag in {'house','detached','semidetached_house','terrace','residential'} else 'commercial' if tag in {'retail','commercial','office'} else 'institution' if tag in {'university','school','church','civic'} or 'acad' in use else 'unspecified'
 value=p.get('building:levels',p.get('FLOORCOUNT'));story_source='source floor count'
 try:levels=int(float(value));assert 1<=levels<=8
 except (ValueError,TypeError,AssertionError):levels=max(1,min(5,round(float(p['height_m'])/3.3)));story_source='estimated from retained massing height'
 nearest=roads[int(road_tree.nearest(f.geometry.centroid))];buffer=Buffer();feature_skips=[];opening_count=0;fronts=[]
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
  front=min(candidates)[1] if candidates else -1;fronts.append({'polygon':index,'edge':front,'nearest_road':nearest.id,'road_name':nearest.properties.get('name'),'method':'nearest eligible exterior edge to sourced road; frontage estimate'})
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
    bays=max(1,int(length/(3.25 if kind=='commercial' else 2.9 if kind=='apartment' else 3.1)));pitch=length/bays;active=length>=2.4;is_front=ring_no==0 and edge==front
    for floor in range(levels):
     lo=datum+floor*floor_height;hi=datum+(floor+1)*floor_height
     for bay in range(bays):
      x0=bay*pitch;x1=(bay+1)*pitch;lower=bottom if floor==0 else lo
      if not active:quad('plain',x0,x1,lower,hi,walls[kind]);continue
      entry=is_front and floor==0 and bay==bays//2;shop=is_front and floor==0 and kind=='commercial'
      width=min(pitch-.50,2.0 if shop else 1.55 if kind=='apartment' else 1.25);left=(x0+x1-width)/2;right=left+width;wl=lo+(.10 if entry or shop else .93);wh=min(hi-.48,wl+(2.16 if entry or shop else 1.32))
      if wh<=wl or width<.50:quad('plain',x0,x1,lower,hi,walls[kind]);continue
      opening_count+=1
      quad('pier_l',x0,left,lower,hi,walls[kind]);quad('pier_r',right,x1,lower,hi,walls[kind]);quad('sill_wall',left,right,lower,wl,walls[kind]);quad('head_wall',left,right,wh,hi,walls[kind])
      # Real opening reveal and separate interior-facing backing, rather than
      # a dark rectangle painted on the front of the original wall.
      for xx in [left,right]:
       aa=a+tangent*xx;bb=aa-outward*.16;buffer.quad([[*aa,wl],[*bb,wl],[*bb,wh],[*aa,wh]],walls[kind],[[0,wl/1.25],[.16/1.25,wl/1.25],[.16/1.25,wh/1.25],[0,wh/1.25]])
      for zz in [wl,wh]:
       aa=a+tangent*left;bb=a+tangent*right;buffer.quad([[*aa,zz],[*bb,zz],[*(bb-outward*.16),zz],[*(aa-outward*.16),zz]],walls[kind],[[left/1.25,0],[right/1.25,0],[right/1.25,.16/1.25],[left/1.25,.16/1.25]])
      quad('backing',left,right,wl,wh,inside,.32);quad('pane',left,right,wl,wh,door if entry and kind=='house' else glass,.105)
      for xx in [left,right,(left+right)/2]:quad('frame',xx-.024,xx+.024,wl-.03,wh+.03,frame,.085)
      for zz in [wl,wh]:quad('frame',left-.03,right+.03,zz-.027,zz+.027,frame,.085)
      quad('flashing',left-.05,right+.05,wl-.035,wl+.005,trim,-.045)
     # A repeated floor/cornice course ties the whole elevation together.
     if kind in {'apartment','commercial','institution'} or floor==levels-1:quad('course',0,length,hi-.14,hi-.045,trim,-.018)
 if feature_skips:
  buffer.emit(f.id.replace(':','_'),f.id)
  skip.extend(feature_skips);records.append({'source_id':f.id,'type':kind,'source_building_tag':tag,'stories':levels,'story_count_basis':story_source,'opening_count':opening_count,'frontage':fronts,'replaced_wall_objects':feature_skips,'status':'illustrative facade detail, not an observation of this specific building'})
 if len(records) and len(records)%100==0:print('FACADES',len(records),parts.writer.triangles,flush=True)
report=parts.close();s.save(out/'materials.cys');report.update(material_offset=offset,material_count=s.materials-offset,replace_sector_components=sorted(skip),buildings=records,reference_basis=['Retained 6503 Del Playa exterior reference and authored reconstruction for local residential proportions/material families','Official Pardall Center exterior reference for coherent street-facing openings, horizontal courses and trim'],limits='Mapped footprints and supplied floor counts anchor the system. Opening layout, facade type when unspecified, frontage selection, optical finish and room-side backing are illustrative estimates. The two individually authored landmarks retain their own components. This is not a building-by-building photographic reconstruction.')
(out/'FACADE_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('DONE_FACADES',len(records),report['triangles'],flush=True)
