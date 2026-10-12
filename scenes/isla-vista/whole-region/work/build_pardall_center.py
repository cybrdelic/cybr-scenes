"""Reference-authored Pardall Center at its retained UCSB footprint.

The 2025 official exterior is the visual reference. Dimensions above ground,
openings and material controls are estimates. Only observed faces are detailed;
unseen interior/back construction stays explicitly simplified.
"""
from pathlib import Path
import sys,json,numpy as np,hashlib
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Scene
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-pardall';out.mkdir(exist_ok=True)
base=r/'evidence/full-iv-roofs';fs=json.loads((base/'normalized.geojson').read_text())['features'];feature=next(x for x in fs if x['id']=='ucsb:buildings:549');source=feature['id'];ring=np.array(feature['geometry']['coordinates'][0]);origin=ring[0];u=(ring[-2]-origin);u/=np.linalg.norm(u);v=np.array([-u[1],u[0]])
# The southern edge of the sourced main rectangle faces Pardall Road.
assert u[0]>.98 and v[1]>.98
W=float(np.linalg.norm(ring[-2]-origin));D=float((ring[-3]-ring[-2])@v)
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame);datum=float(np.median(dem.sample(ring[:,0],ring[:,1])))
def world(a):
 a=np.asarray(a);return np.c_[origin+a[:,:1]*u+a[:,1:2]*v,a[:,2]+datum]
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inv=np.linalg.inv(M)
def c(rgb):return np.maximum(0,(np.array(rgb)*white)@inv.T)
botpath=next(r/'evidence'/name/'BOTANICAL_RECEIPT.json' for name in ['full-iv-botanical-dense','full-iv-botanical-tiered','full-iv-botanical'] if (r/'evidence'/name/'BOTANICAL_RECEIPT.json').is_file())
bot=json.loads(botpath.read_text());offset=bot['material_offset']+bot['material_count'];s=Scene();s.materials=offset
blue=[s.material('plastic',c(np.array([.165,.205,.235])*k),.83,ior=1.44) for k in [.92,.96,1,1.04,1.08]]
plaster=s.material('plastic',c((.47,.445,.38)),.86,ior=1.45);trim=s.material('plastic',c((.45,.48,.46)),.68,ior=1.47);dark=s.material('plastic',c((.018,.025,.034)),.62,ior=1.46);glass=s.material('thindielectric',(1,1,1),.035,ior=1.515);concrete=s.material('plastic',c((.27,.255,.22)),.91,ior=1.45);sign=s.material('plastic',c((.57,.57,.51)),.7,ior=1.44);letter=s.material('plastic',c((.012,.020,.053)),.67,ior=1.44);post=s.material('plastic',c((.16,.045,.022)),.7,ior=1.45)
parts=Parts(out/'pardall.clm',3000000);estimate='Official 2025 exterior reference; above-ground dimensions and optical controls estimated'
def box(name,size,center,mat):parts.box(name,size,center,mat,source,estimate,world)
def quad(name,a,mat):parts.mesh(name,world(a),[[0,1,2],[0,2,3]],mat,source,estimate)
def wall(name,axis,fixed,length,z0,z1,openings,mat,boards=False):
 # Split every opening out of the wall, rather than laying glass on an opaque
 # box. Clapboard rows have an actual tiny lip and retain the same openings.
 xs=sorted(set([0,length]+[max(0,min(length,x)) for h in openings for x in h[:2]]));zs=sorted(set([z0,z1]+[max(z0,min(z1,z)) for h in openings for z in h[2:]]))
 if boards:zs=sorted(set(zs+[min(z1,z0+j*.17) for j in range(1,int((z1-z0)/.17)+1)]))
 for ix,(a,b) in enumerate(zip(xs[:-1],xs[1:])):
  for iz,(lo,hi) in enumerate(zip(zs[:-1],zs[1:])):
   x=(a+b)/2;z=(lo+hi)/2
   if any(h[0]<x<h[1] and h[2]<z<h[3] for h in openings):continue
   q=[[a,fixed,lo],[b,fixed,lo],[b,fixed,hi],[a,fixed,hi]] if axis=='x' else [[fixed,a,lo],[fixed,b,lo],[fixed,b,hi],[fixed,a,hi]]
   if boards:
    off=-.004 if fixed<1.6 else .004
    for k in [0,1]:q[k][1 if axis=='x' else 0]+=off
   quad(name+f'_{ix}_{iz}',q,blue[(iz*7+ix*3)%len(blue)] if boards else mat)
 for j,(a,b,lo,hi) in enumerate(openings):
  fixedglass=fixed+(.04 if fixed<1.6 else -.04)
  q=[[a,fixedglass,lo],[b,fixedglass,lo],[b,fixedglass,hi],[a,fixedglass,hi]] if axis=='x' else [[fixedglass,a,lo],[fixedglass,b,lo],[fixedglass,b,hi],[fixedglass,a,hi]];quad(name+f'_glass{j}',q,glass)
  for edge in [a,b,(a+b)/2]:
   box(name+f'_frame{j}_{edge}',(.055,.095,hi-lo+.09) if axis=='x' else (.095,.055,hi-lo+.09),(edge,fixed,(lo+hi)/2) if axis=='x' else (fixed,edge,(lo+hi)/2),trim)
  for z in [lo,hi]:box(name+f'_lintel{j}_{z}',(b-a+.12,.10,.065) if axis=='x' else (.10,b-a+.12,.065),((a+b)/2,fixed,z) if axis=='x' else (fixed,(a+b)/2,z),trim)
floor=2.78;eave=5.82;ridge=7.38;upperfront=1.34
box('foundation',(W,D,.25),(W/2,D/2,-.03),concrete);box('upper_floor',(W,D-upperfront,.18),(W/2,(D+upperfront)/2,floor),concrete)
wall('lower_front','x',0,W,0,floor,[(.8,3.4,1.0,2.32),(5.6,7.45,.10,2.36),(7.65,9.10,.40,2.36)],plaster)
wall('lower_east','y',W,D,0,floor,[(1.0,3.7,.75,2.25)],plaster)
wall('lower_west','y',0,D,0,floor,[],plaster);wall('lower_back','x',D,W,0,floor,[],plaster)
wall('upper_front','x',upperfront,W,floor,eave,[(1.15,3.65,floor+.13,floor+2.21),(5.90,8.35,floor+.13,floor+2.21)],blue[2],True)
wall('upper_east','y',W,D,floor,eave,[(2.0,4.1,floor+1.0,floor+2.33),(7.2,8.1,floor+1.0,floor+2.25),(10.2,12.1,floor+1.0,floor+2.25)],blue[2],True)
wall('upper_west','y',0,D,floor,eave,[],blue[2],True);wall('upper_back','x',D,W,floor,eave,[],blue[2],True)
# Fill the gable in horizontal courses and include the observed louver.
for side,y in [('front',upperfront),('back',D)]:
 for j,z in enumerate(np.arange(eave,ridge,.17)):
  top=min(z+.17,ridge);a=(z-eave)/(ridge-eave)*W*.5;b=W-a;aa=(top-eave)/(ridge-eave)*W*.5;bb=W-aa
  quad(side+f'_gable_{j}',[[a,y,z],[b,y,z],[bb,y,top],[aa,y,top]],blue[j%5])
for j in range(6):box('gable_louver'+str(j),(1.0,.12,.05),(W*.5,upperfront-.065,6.25+j*.105),dark)
for x in [W*.5-.57,W*.5+.57]:box('louver_frame'+str(x),(.055,.13,.70),(x,upperfront-.07,6.55),trim)
# Continuous gabled roof geometry, with actual fascia and modest overhangs.
roof_y0=upperfront-.42;roof_y1=D+.40
for side,(a,b,za,zb) in enumerate([(-.42,W/2,eave,ridge),(W/2,W+.42,ridge,eave)]):
 quad('roof'+str(side),[[a,roof_y0,za],[b,roof_y0,zb],[b,roof_y1,zb],[a,roof_y1,za]],9)
 for y in [roof_y0,roof_y1]:
  direction=np.array([b-a,0,zb-za]);length=np.linalg.norm(direction);t=np.linspace(0,1,30)
  for j,(lo,hi) in enumerate(zip(t[:-1],t[1:])):
   p=np.array([a,y,za])+direction*(lo+hi)/2;box(f'fascia{side}_{y}_{j}',(abs(b-a)*(hi-lo)+.015,.13,.14),p,trim)
box('roof_eave_east',(.11,roof_y1-roof_y0,.16),(W+.42,(roof_y0+roof_y1)/2,eave),trim);box('roof_eave_west',(.11,roof_y1-roof_y0,.16),(-.42,(roof_y0+roof_y1)/2,eave),trim)
# Front balcony, including actual gaps between the observed vertical pickets.
box('balcony_deck',(W+.10,1.55,.17),(W*.5,.57,floor),blue[2])
for y in [-.18,1.28]:
 for z in [floor+.22,floor+1.02]:box('balcony_rail'+str((y,z)),(W+.12,.085,.10),(W*.5,y,z),trim)
 for j,x in enumerate(np.arange(0,W+.01,.155)):box('balcony_picket'+str((y,j)),(.038,.044,.82),(x,y,floor+.60),blue[j%5])
for x in [0,W]:
 for z in [floor+.22,floor+1.02]:box('balcony_side_rail'+str((x,z)),(.085,1.5,.10),(x,.55,z),trim)
 for j,y in enumerate(np.arange(-.15,1.31,.155)):box('balcony_side_picket'+str((x,j)),(.044,.038,.82),(x,y,floor+.60),blue[j%5])
for x in np.linspace(0,W,7):box('balcony_post'+str(x),(.09,.09,1.15),(x,-.18,floor+.55),trim)
# One-story western annex follows the corresponding retained footprint strip.
local_ring=(ring-origin)@np.column_stack([u,v]);annex_width=-float(local_ring[2,0]);ay0=float(local_ring[2,1]);ay1=float(local_ring[3,1]);ax=-annex_width
box('annex_roof',(annex_width+.10,ay1-ay0,.14),(-annex_width/2,(ay0+ay1)/2,2.68),concrete)
for j,(a,b,lo,hi) in enumerate([(ax,0,0,.6),(ax,0,2.3,2.62),(ax,ax+.25,.6,2.3),(-.25,0,.6,2.3)]):quad('annex_front'+str(j),[[a,ay0,lo],[b,ay0,lo],[b,ay0,hi],[a,ay0,hi]],plaster)
quad('annex_front_glass',[[ax+.25,ay0+.04,.6],[-.25,ay0+.04,.6],[-.25,ay0+.04,2.3],[ax+.25,ay0+.04,2.3]],glass)
quad('annex_west',[[ax,ay0,0],[ax,ay1,0],[ax,ay1,2.62],[ax,ay0,2.62]],plaster)
quad('annex_back',[[ax,ay1,0],[0,ay1,0],[0,ay1,2.62],[ax,ay1,2.62]],plaster)
box('annex_floor',(annex_width,ay1-ay0,.15),(-annex_width/2,(ay0+ay1)/2,.01),concrete)
for x in [1.05,4.65,6.9,9.65]:box('painted_bollard'+str(x),(.085,.085,1.04),(x,-1.45,.52),post)
box('sign_post',(.14,.14,3.20),(6.75,-1.12,1.60),blue[2])
# Original vector lettering, not a photo texture. Geometry is readable at
# pedestrian scale while the full-region image naturally reduces it.
segments={'P':[(0,0,0,1),(0,1,.6,1),(.6,1,.6,.55),(.6,.55,0,.55)],'A':[(0,0,.3,1),(.3,1,.6,0),(.12,.43,.48,.43)],'R':[(0,0,0,1),(0,1,.6,1),(.6,1,.6,.55),(.6,.55,0,.55),(.25,.55,.65,0)],'D':[(0,0,0,1),(0,1,.5,.85),(.5,.85,.5,.15),(.5,.15,0,0)],'L':[(0,1,0,0),(0,0,.6,0)],'C':[(.6,1,0,1),(0,1,0,0),(0,0,.6,0)],'E':[(.6,1,0,1),(0,1,0,0),(0,0,.6,0),(0,.5,.48,.5)],'N':[(0,0,0,1),(0,1,.6,0),(.6,0,.6,1)],'T':[(0,1,.6,1),(.3,1,.3,0)]}
sx=6.75;sy=-1.23;sz=2.30;sw=1.90;sh=1.33
box('sign_board',(sw,.08,sh),(sx,sy,sz),sign)
for row,word in enumerate(['PARDALL','CENTER']):
 height=.37;advance=sw*.86/len(word);left=sx-sw*.43;bottom=sz+.17-row*.46
 for j,ch in enumerate(word):
  for k,(a,b,cx,d) in enumerate(segments[ch]):
   p=np.array([left+j*advance+a*advance,bottom+b*height]);q=np.array([left+j*advance+cx*advance,bottom+d*height]);normal=np.array([-(q-p)[1],(q-p)[0]]);normal=normal/np.linalg.norm(normal)*.014;vv=np.array([p-normal,q-normal,q+normal,p+normal]);quad(f'letter_{row}_{j}_{k}',[[x,sy-.046,z] for x,z in vv],letter)
report=parts.close();s.save(out/'materials.cys');layout=json.loads((base/'glb-part-layout.json').read_text());skip=[p['component'] for b in layout.values() for p in b['parts'] if p['part'].startswith('ucsb_buildings_549_')]
report.update(material_offset=offset,material_count=s.materials-offset,replace_sector_components=skip,source_id=source,footprint=feature,local_frame={'origin_utm_local':origin.tolist(),'x':u.tolist(),'y':v.tolist(),'main_width_m':W,'main_depth_m':D,'foundation_datum_m':datum},reference_urls=['https://pardallcenter.as.ucsb.edu/about/','https://pardallcenter.as.ucsb.edu/files/2025/09/PXL_20250521_193852434-scaled.jpg','https://pardallcenter.as.ucsb.edu/files/2021/09/pardall-center.jpg'],limits='UCSB footprint and two floors are sourced. Vertical dimensions, facade openings, balcony dimensions, material reflectance and optical finish are photo-estimated. Hidden back/interior and annex construction are simplified. Photos are inspection references only and are not textures or included in source delivery. No scans or generated-image rendering.')
(out/'PARDALL_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('PARDALL_DONE',json.dumps({'parts':len(report['parts']),'triangles':report['triangles'],'replaced_objects':skip,'frame':report['local_frame']}),flush=True)
