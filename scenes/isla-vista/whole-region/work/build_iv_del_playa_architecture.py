"""Three individually reference-authored buildings in the retained IV corridor.

Footprints are original OSM geometry. The6574 story override is supported by
its manager's explicit description and exterior image; dimensional/material
values and unobserved rear elevations remain authored estimates.
"""
from pathlib import Path
import json,sys,hashlib
import numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from shapely.geometry import shape,Point,Polygon,box
from shapely.geometry.polygon import orient
from shapely.affinity import affine_transform
from cybr_ucsb.geometry import triangulate_polygon
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
from cybr_light import Scene
from cybr_light.runtime import read_pfm
from cybr_terrain.materials import write_pfm
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-del-playa-architecture';out.mkdir(exist_ok=True);(out/'textures').mkdir(exist_ok=True)
features={f['id']:f for f in json.loads((r/'evidence/full-iv-roofs/normalized.geojson').read_text())['features']};sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame);road=shape(features['osm:way:50978848']['geometry'])
old=json.loads((r/'evidence/full-iv-facades/FACADE_RECEIPT.json').read_text());layout=json.loads((r/'evidence/full-iv-roofs/glb-part-layout.json').read_text());day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inv=np.linalg.inv(M)
def native(rgb):return np.maximum(0,(np.asarray(rgb)*white)@inv.T)
s=Scene();s.materials=172
# Reuse the existing original CYBR procedural plaster relief and roughness,
# authored color controls are photo-informed estimates, not measured spectra.
oldcolor=read_pfm(r/'evidence/full-iv-facades/textures/iv-unspecified-plaster_color.pfm');variation=oldcolor/np.maximum(np.mean(oldcolor,axis=(0,1)),1e-6)
def plaster(name,rgb):
 p=out/'textures'/f'{name}_native.pfm';write_pfm(p,native(variation*np.asarray(rgb)));a=s.material('plastic',(1,1,1),.84,ior=1.45,texture=p);s.emit('roughness_texture',a,json.dumps(str((r/'evidence/full-iv-facades/textures/iv-unspecified-plaster_roughness.pfm').resolve())),1,1,1);b=s.material('bumpmap',texture=r/'evidence/full-iv-facades/textures/iv-unspecified-height.pfm');s.emit('nested',b,a,-1,.5);s.emit('metric_bump',b);return b
wallm={6570:plaster('6570_tan_stucco',(.47,.405,.31)),6574:plaster('6574_cream_stucco',(.52,.47,.38)),6584:plaster('6584_gray_stucco',(.34,.355,.335))};infill=plaster('6574_panel_infill',(.56,.40,.31));whitepaint=s.material('plastic',native((.72,.725,.70)),.52,ior=1.48);graypaint=s.material('plastic',native((.20,.225,.22)),.65,ior=1.48);roofmat=s.material('plastic',native((.065,.055,.04)),.83,ior=1.48);concrete=s.material('plastic',native((.40,.39,.345)),.90,ior=1.45);soffit=s.material('plastic',native((.44,.43,.385)),.84,ior=1.45)
parts=Parts(out/'architecture.clm',12000000);records=[];skip_base=[];skip_facades=[]
class Buffer:
 def __init__(self,source):self.source=source;self.groups={}
 def mesh(self,v,f,mat,uv=None):
  v=np.asarray(v,float);f=np.asarray(f,int);g=self.groups.setdefault(mat,{'v':[],'f':[],'uv':[]});j=len(g['v']);g['v'].extend(v.tolist());g['f'].extend((f+j).tolist());g['uv'].extend((v[:,:2]/1.25 if uv is None else np.asarray(uv)).tolist())
 def quad(self,v,mat,uv=None):self.mesh(v,[[0,1,2],[0,2,3]],mat,uv)
 def box(self,center,size,mat,frame=None):
  c=np.asarray(center);h=np.asarray(size)/2;v=np.array([[x,y,z] for z in [-1,1] for y in [-1,1] for x in [-1,1]])*h+c
  if frame is not None:v=frame(v)
  quads=[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]
  for ids in quads:
   q=v[ids]
   #The local (edge tangent,outward,z) frame has negative determinant.
   if frame is not None:q=q[::-1]
   u=np.linalg.norm(q[1]-q[0])/1.25;w=np.linalg.norm(q[3]-q[0])/1.25
   self.quad(q,mat,[[0,0],[u,0],[u,w],[0,w]])

 def finish(self):
  for mat,g in self.groups.items():parts.mesh(self.source.replace(':','_')+'_'+str(mat),g['v'],g['f'],mat,self.source,'Visible architectural form from identified exterior reference; dimensions, pigment and unseen elevations estimated',uv=g['uv'])
for address,oid in [(6570,42753859),(6574,42753857),(6584,42753856)]:
 source=f'osm:way:{oid}';f=features[source];poly=orient(shape(f['geometry']),sign=1.0);c=np.array(poly.exterior.coords)[:,:2];xy,ff=triangulate_polygon(poly);datum=float(np.median(dem.sample(xy[:,0],xy[:,1])));level=1 if address==6574 else 2;maxheight=3.70 if address==6574 else 6.60;eave=3.05 if address==6574 else 5.8;floorheight=2.9;wall=wallm[address];b=Buffer(source);fronts=[];edge_info=[]
 for i,(a,z) in enumerate(zip(c[:-1],c[1:])):
  length=np.linalg.norm(z-a);t=(z-a)/length;n=np.array([t[1],-t[0]]);mid=(a+z)/2;target=np.array(road.interpolate(road.project(Point(mid))).coords[0]);facing=np.dot(n,target-mid)>0;dist=Point(mid).distance(road);edge_info.append((i,a,z,length,t,n,dist,facing))
 minfront=min(e[6] for e in edge_info if e[7] and e[3]>3)
 #6570 has offset street-facing wings; source roof/facade system applies to
 #each sufficiently broad south-facing wing, including recessed courtyard.
 for i,a,z,length,t,n,dist,facing in edge_info:
  front=facing and length>3 and (dist<minfront+5 or address==6570 and n[1]<-.7);fronts.append(i) if front else None
  def world(x,y,zz):return [*(a+t*x+n*y),datum+zz]
  def frame(v):return np.array([world(*q) for q in v])
  def panel(x0,x1,z0,z1,mat,depth=0):
   if x1-x0<=1e-5 or z1-z0<=1e-5:return
   b.quad([world(x0,depth,z0),world(x1,depth,z0),world(x1,depth,z1),world(x0,depth,z1)],mat,[[x0/1.25,z0/1.25],[x1/1.25,z0/1.25],[x1/1.25,z1/1.25],[x0/1.25,z1/1.25]])
  openings=[]
  if front and address==6584:
   for floor in range(2):
    for center in [.26,.74]:openings.append((length*center-1.38,length*center+1.38,floor*floorheight+.22,floor*floorheight+2.30,'slider'))
  elif front and address==6574:
   for left,right,lo,hi in [(.12,.245,1.13,2.13),(.33,.415,1.0,2.15),(.535,.68,1.50,2.12),(.80,.955,1.13,2.14)]:openings.append((length*left,length*right,lo,hi,'window'))
  elif front and address==6570:
   bays=max(1,round(length/4.6))
   for floor in range(2):
    for k in range(bays):center=length*(k+.5)/bays;ww=min(2.75,length/bays-.75);openings.append((center-ww/2,center+ww/2,floor*floorheight+.12,floor*floorheight+2.27,'slider'))
  elif length>3.5:
   #Unseen side/rear windows remain a coherent estimate, differentiated from
   #the observed front; do not claim their exact layout.
   bays=max(1,int(length/5.1))
   for floor in range(level):
    for k in range(bays):center=length*(k+.5)/bays;openings.append((center-.67,center+.67,floor*floorheight+1.00,min(eave-.38,floor*floorheight+2.05),'window'))
  #Wall cells exactly subtract rectangular openings; glazing is actually
  #recessed, with reveals and a separate unobserved dark interior backing.
  xs=sorted(set([0.,length]+[q for op in openings for q in op[:2]]));zs=sorted(set([-.30,eave]+[q for op in openings for q in op[2:4]]))
  for x0,x1 in zip(xs[:-1],xs[1:]):
   for z0,z1 in zip(zs[:-1],zs[1:]):
    mx=(x0+x1)/2;mz=(z0+z1)/2
    if any(o[0]<mx<o[1] and o[2]<mz<o[3] for o in openings):continue
    mat=infill if address==6574 and front and 1.02<=mz<2.18 else wall;panel(x0,x1,z0,z1,mat)
  for left,right,lo,hi,kind in openings:
   for xx in [left,right]:b.quad([world(xx,0,lo),world(xx,-.16,lo),world(xx,-.16,hi),world(xx,0,hi)],wall,[[0,lo],[.16,lo],[.16,hi],[0,hi]])
   for zz in [lo,hi]:b.quad([world(left,0,zz),world(right,0,zz),world(right,-.16,zz),world(left,-.16,zz)],wall,[[left,0],[right,0],[right,.16],[left,.16]])
   panel(left,right,lo,hi,70,-.45);panel(left,right,lo,hi,69,-.095)
   for xx in [left,right,(left+right)/2]:b.box((xx,-.065,(lo+hi)/2),(.052,.05,hi-lo+.08),whitepaint,frame)
   for zz in [lo,hi]:b.box(((left+right)/2,-.065,zz),(right-left+.08,.05,.055),whitepaint,frame)
   b.box(((left+right)/2,.045,lo-.055),(right-left+.14,.19,.065),whitepaint,frame)
  if front and address in (6570,6584):
   x0=.18;x1=length-.18;deckdepth=1.35 if address==6570 else 1.05;rail=whitepaint if address==6570 else graypaint
   b.box(((x0+x1)/2,deckdepth/2,floorheight-.10),(x1-x0,deckdepth,.20),concrete,frame)
   b.box(((x0+x1)/2,deckdepth,floorheight-.12),(x1-x0+.10,.12,.28),rail,frame)
   for xx in np.linspace(x0,x1,max(2,int((x1-x0)/.145)+1)):
    b.box((xx,deckdepth,floorheight+.54),(.038,.044,.98),rail,frame)
   for zz in [floorheight+.09,floorheight+1.08]:b.box(((x0+x1)/2,deckdepth,zz),(x1-x0+.10,.08,.085),rail,frame)
   for xx in [x0,x1]:
    b.box((xx,deckdepth/2,floorheight+1.08),(.08,deckdepth,.085),rail,frame)
    for yy in np.arange(.12,deckdepth,.145):b.box((xx,yy,floorheight+.54),(.044,.038,.98),rail,frame)
   if address==6570:
    for xx in [x0+.12,x1-.12]:b.box((xx,deckdepth-.12,(floorheight-.22)/2),(.18,.18,floorheight-.22),wall,frame)
    #Street-facing mansard roof band and soffit read as a continuous system.
   else:
    #Reference-visible enclosed front court and side gate volume. Heights
    #and setback inferred from the picture; original footprint unchanged.
    courtdepth=3.0;courtheight=1.72;gatewidth=1.10
    b.box(((length-gatewidth)/2,courtdepth,courtheight/2),(length-gatewidth,.17,courtheight),wall,frame)
    b.box((.06,courtdepth/2,courtheight/2),(.17,courtdepth,courtheight),wall,frame)
    b.box((length-.06,courtdepth/2,courtheight/2),(.17,courtdepth,courtheight),wall,frame)
    b.box((length-gatewidth/2,courtdepth,.83),(gatewidth-.12,.075,1.66),graypaint,frame)
  if address==6574 and front:
   #Sparse exposed roof outriggers seen beneath the broad overhang.
   for xx in np.linspace(.2,length-.2,8):b.box((xx,.31,eave-.05),(.095,.70,.12),whitepaint,frame)
  b.box((length/2,.07,.18),(length,.12,.32),wall,frame)
 #Roof layer: geometric overhang and closed fascia. Contour bands retain
 #the mapped plan, with estimate of observed pitch/fascia shape.
 outer=poly.buffer(.62 if address==6574 else .42,join_style=2);inset=poly.buffer(-(.75 if address==6570 else 2.5),join_style=2)
 if inset.is_empty:inset=poly.buffer(-.35,join_style=2)
 shell=outer.difference(inset)
 def roof_mesh(area,inner=False):
  for geom in (area.geoms if hasattr(area,'geoms') else [area]):
   if geom.is_empty or geom.area<1e-5:continue
   vx,faces=triangulate_polygon(geom)
   if inner:zz=np.full(len(vx),datum+maxheight)
   else:
    zz=np.array([datum+(maxheight if Point(q).distance(inset.boundary)<1e-5 else eave) for q in vx])
   b.mesh(np.c_[vx,zz],faces,roofmat,vx/1.25)
 roof_mesh(shell);roof_mesh(inset,True)
 #A thin horizontal soffit covers only the overhang, not the roof void.
 ox,of=triangulate_polygon(outer.difference(poly));b.mesh(np.c_[ox,np.full(len(ox),datum+eave-.06)],of[:,::-1],soffit,ox/1.25)
 for aa,bb in zip(np.array(outer.exterior.coords)[:-1],np.array(outer.exterior.coords)[1:]):b.quad([[*aa,datum+eave-.10],[*bb,datum+eave-.10],[*bb,datum+eave+.045],[*aa,datum+eave+.045]],whitepaint if address==6574 else graypaint)
 b.finish()
 excludes=[p['object'] for p in old['parts'] if p['source']==source];skip_facades.extend(excludes)
 roofs=[p['component'] for group in layout.values() for p in group['parts'] if p['part'].startswith(source.replace(':','_')+'_') and p['part'].endswith('_roof')];skip_base.extend(roofs)
 records.append({'address':str(address)+' Del Playa Drive','source_id':source,'footprint':f['geometry'],'footprint_retained_exactly':True,'source_OSM_floor_count':2,'authored_floor_count':level,'height_basis':'6574 single-story manager description and photo override; other total heights retain source2×estimated3.3m','estimated_eave_height_m':eave,'estimated_max_roof_height_m':maxheight,'estimated_floor_height_m':floorheight if level==2 else None,'foundation_datum_m':datum,'street_facing_edges':fronts,'frontage_source_road':'osm:way:50978848','excluded_prior_facade_objects':excludes,'excluded_base_roof_objects':roofs,'unseen_side_rear_openings_estimated':True})
report=parts.close();s.save(out/'materials.cys');report.update(material_offset=172,material_count=s.materials-172,exclude_prior_facade_objects=skip_facades,replace_sector_components=skip_base,buildings=records,reference_manifest='references/del-playa-corridor/REFERENCE_MANIFEST.json',limits='Observed building forms are interpreted from identified external photos, not surveyed. Roof pitch, balcony depth, rail section, opening dimensions, optics and unobserved details are estimated. No photos are textures. Original OSM floor conflict remains in input and is explicitly overridden only for6574.')
(out/'ARCHITECTURE_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'triangles':report['triangles'],'parts':len(report['parts']),'materials':report['material_count'],'buildings':records}),flush=True)
