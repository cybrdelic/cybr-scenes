"""Three reference-authored buildings with metric catalogue plaster and folded linen.

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
from iv_mesh_parts import Parts,leaf_mesh
out=r/'evidence/full-iv-del-playa-finish-v2';out.mkdir(exist_ok=True);(out/'textures').mkdir(exist_ok=True)
features={f['id']:f for f in json.loads((r/'evidence/full-iv-roofs/normalized.geojson').read_text())['features']};sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame);road=shape(features['osm:way:50978848']['geometry'])
old=json.loads((r/'evidence/full-iv-facades/FACADE_RECEIPT.json').read_text());layout=json.loads((r/'evidence/full-iv-roofs/glb-part-layout.json').read_text());day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inv=np.linalg.inv(M)
def native(rgb):return np.maximum(0,(np.asarray(rgb)*white)@inv.T)
s=Scene();s.materials=172
# Reuse the existing original CYBR procedural plaster relief and roughness,
# authored color controls are photo-informed estimates, not measured spectra.
finish=r/'evidence/full-iv-street-finishes'
finish_receipt=json.loads((finish/'FINISH_RECEIPT.json').read_text())
def plaster(name,rgb):
 a=s.material('plastic',(1,1,1),.76,ior=1.48,texture=finish/(name+'_native.pfm'))
 s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 1.923076923076923 1.923076923076923 1'
 s.emit('roughness_texture',a,json.dumps(str((finish/'lime_roughness.pfm').resolve())),1.25/.65,1.25/.65,1)
 b=s.material('bumpmap',texture=finish/'lime_height_metres.pfm')
 s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 1.923076923076923 1.923076923076923 1'
 s.emit('nested',b,a,-1,.5);s.emit('metric_bump',b);return b
wallm={6570:plaster('6570_tan_stucco',(.47,.405,.31)),6574:plaster('6574_cream_stucco',(.52,.47,.38)),6584:plaster('6584_gray_stucco',(.34,.355,.335))};infill=plaster('6574_panel_infill',(.56,.40,.31));whitepaint=s.material('plastic',native((.72,.725,.70)),.52,ior=1.48);graypaint=s.material('plastic',native((.20,.225,.22)),.65,ior=1.48);roofmat=s.material('plastic',native((.065,.055,.04)),.83,ior=1.48);concrete=s.material('plastic',native((.40,.39,.345)),.90,ior=1.45);soffit=s.material('plastic',native((.44,.43,.385)),.84,ior=1.45)
parts=Parts(out/'architecture.clm',12000000);records=[];skip_base=[];skip_facades=[]
cloth=Scene();cloth.materials=282
linen=finish_receipt['linen'];cloth_r=cloth.material('diffuse',linen['native_reflectance_controls'],linen['mean_roughness'])
cloth_t=cloth.material('difftrans',linen['native_reflectance_controls'],linen['mean_roughness'])
cloth_blend=cloth.material('blendbsdf');cloth.emit('nested',cloth_blend,cloth_r,cloth_t,.18)
cloth_mask=cloth.material('mask');cloth.emit('nested',cloth_mask,cloth_blend,-1,.5);cloth.emit('coverage',cloth_mask,linen['source_mean_coverage'])
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

 def tube(self,a,b,radius,mat,sides=5):
  a=np.asarray(a,float);b=np.asarray(b,float);axis=(b-a)/np.linalg.norm(b-a);ref=np.array([0.,0.,1.]) if abs(axis[2])<.95 else np.array([1.,0.,0.]);u=np.cross(axis,ref);u/=np.linalg.norm(u);v=np.cross(axis,u);angles=np.arange(sides)*2*np.pi/sides;ring=np.cos(angles)[:,None]*u+np.sin(angles)[:,None]*v
  vertices=np.vstack([a+radius*ring,b+radius*ring]);faces=[]
  for k in range(sides):j=(k+1)%sides;faces.extend([[k,j,sides+j],[k,sides+j,sides+k]])
  self.mesh(vertices,faces,mat)
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
   # Two source-compatible linen panels behind real glass, with a central
   # gap and 0.11 m authored pleat spacing. Interiors are unobserved estimates.
   width=right-left
   for q0,q1 in [(left+.045,left+width*.41),(left+width*.59,right-.045)]:
    count=max(8,int((q1-q0)/.022));xx=np.linspace(q0,q1,count)
    for j in range(count-1):
     xa,xb=xx[j:j+2];ya=-.23+.026*np.cos(2*np.pi*(xa-left)/.11);yb=-.23+.026*np.cos(2*np.pi*(xb-left)/.11)
     z0=lo+.06;z1=hi-.035
     b.quad([world(xa,ya,z0),world(xb,yb,z0),world(xb,yb,z1),world(xa,ya,z1)],cloth_mask,[[xa/1.25,z0/1.25],[xb/1.25,z0/1.25],[xb/1.25,z1/1.25],[xa/1.25,z1/1.25]])
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
   # The labeled manager photograph shows a low chain-link front boundary
   # and substantial garden shrubs. Their dimensions/positions are estimates.
   fence_y=5.5;fence_h=1.0;gate=(length*.45,length*.45+1.05)
   def ground(x,y):
    q=np.asarray(world(x,y,0));q[2]=float(dem.sample(q[0],q[1]))+.015;return q
   for xx in sorted(set([.18,length-.18,*gate,*np.arange(.18,length-.18,2.1)])):
    a0=ground(xx,fence_y);b.tube(a0,a0+[0,0,fence_h+.045],.023,graypaint,7)
   for lo_,hi_ in [(.18,gate[0]),(gate[1],length-.18)]:
    a0=ground(lo_,fence_y);a1=ground(hi_,fence_y);b.tube(a0+[0,0,fence_h],a1+[0,0,fence_h],.017,graypaint,7)
    # Actual 58 mm diamond pitch and 1.8 mm wire; no enlarged wire texture.
    for direction in [-1,1]:
     for intercept in np.arange(lo_-fence_h,hi_+fence_h,.058):
      points=[]
      for z_ in [0,fence_h]:
       x_=intercept+direction*z_
       if lo_<=x_<=hi_:points.append((x_,z_))
      for x_ in [lo_,hi_]:
       z_=(x_-intercept)/direction
       if 0<=z_<=fence_h:points.append((x_,z_))
      if len(points)>=2:
       aa,bb=points[0],points[-1]
       if np.linalg.norm(np.array(aa)-bb)>1e-6:b.tube(ground(aa[0],fence_y)+[0,0,aa[1]],ground(bb[0],fence_y)+[0,0,bb[1]],.0009,graypaint,4)
   rng=np.random.default_rng(6574);centers=[];axes=[];lengths=[];widths=[]
   for j,x_ in enumerate(np.linspace(.65,length-.65,14)):
    if gate[0]-.3<x_<gate[1]+.3:continue
    root=ground(x_,4.0+rng.uniform(-.3,.3));height=rng.uniform(.65,1.05)
    for branch in range(9):
     az=branch*2.399963;tip=root+[np.cos(az)*.30,np.sin(az)*.30,height*(.5+.05*branch)];b.tube(root,tip,.008,39,4)
     for k in range(22):
      fraction=(k+.5)/22;center=root*(1-fraction)+tip*fraction+rng.normal(size=3)*[.11,.11,.07];axis=rng.normal(size=3);axis[2]*=.3;axis/=np.linalg.norm(axis);centers.append(center);axes.append(axis);lengths.append(rng.uniform(.055,.095));widths.append(rng.uniform(.027,.046))
   vv,ff=leaf_mesh(centers,axes,lengths,widths,rolls=rng.uniform(-1,1,len(centers)));b.mesh(vv,ff,42)

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
report=parts.close();s.save(out/'materials.cys');cloth.save(out/'cloth_materials.cys');report.update(finish_receipt='evidence/full-iv-street-finishes/FINISH_RECEIPT.json',cloth_material_offset=282,cloth_material_count=cloth.materials-282,estimated_cloth_folds=True,frontage_reference='6574 manager photo: low chain-link and garden shrubs; local dimensions and individual plants authored',material_offset=172,material_count=s.materials-172,exclude_prior_facade_objects=skip_facades,replace_sector_components=skip_base,buildings=records,reference_manifest='references/del-playa-corridor/REFERENCE_MANIFEST.json',limits='Observed building forms are interpreted from identified external photos, not surveyed. Roof pitch, balcony depth, rail section, opening dimensions, optics and unobserved details are estimated. No photos are textures. Original OSM floor conflict remains in input and is explicitly overridden only for6574.')
(out/'ARCHITECTURE_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'triangles':report['triangles'],'parts':len(report['parts']),'materials':report['material_count'],'buildings':records}),flush=True)
