"""Insert preserved detailed 6503 as one georeferenced neighborhood component."""
from pathlib import Path
import importlib.util,sys,json,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime',r/'work/cybr-geo/src']:sys.path.insert(0,str(p))
from cybr_light import Scene,Meshlets
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
# cybr_ucsb is loaded from the explicitly retained full-IV working source.
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
geo=r/'work/cybr-geo/examples/del_playa_6503';m=module('full_iv_house',geo/'recipe.py');i=module('full_iv_house_i',geo/'facade_structure_i.py');b=m.Builder(m.HouseConfig());m._architecture(b);m._decks_and_rails(b);m._fence_and_patio_objects(b)
old=json.loads((r/'evidence/candidate-e/part_geometry_digests.json').read_text());matched=0
for p in b.parts:
 h=hashlib.sha256(np.asarray(p.vertices,dtype='<f8').tobytes()+np.asarray(p.faces,dtype='<i8').tobytes()).hexdigest();assert old[p.name]==h;matched+=1
b.parts=[p for p in b.parts if not p.name.startswith('neighbor_') and not i.excludes_base(p.name)];i.add(b,m)
# Reuse exact authored patio dimensions, without transplanting old invented
# terrain, the previous small context strip, or an arbitrary ocean height.
b.box('main_patioslab',(12900,4800,90),(550,-2450,-55),m.CONCRETE,'site','Observed ocean-side patio; dimensions estimated')
b.box('east_patioslab',(3900,7300,90),(6900,550,-65),m.CONCRETE,'site','Observed side patio; dimensions estimated')
config=json.loads((geo/'site_constraints.json').read_text());basis=np.array([config['local_x_east_north'],config['local_y_east_north']]);scale=np.array([config['longitude_scale_m_per_degree'],config['latitude_scale_m_per_degree']]);offset=np.array([config['origin_x_offset_m'],0]);origin=np.array(config['origin_wgs84'])
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame)
def xy_world(v):
 ll=((np.asarray(v)-offset)@basis)/scale+origin;x,y=sector.frame.local(ll[:,0],ll[:,1]);return np.c_[x,y]
originxy=xy_world([[0,0]])[0];jac=(xy_world([[1,0],[0,1]])-originxy).T;J=np.eye(3);J[:2,:2]=jac
footprint=m.footprint_mm()*.001;worldpoly=xy_world(footprint);datum=float(np.median(dem.sample(worldpoly[:,0],worldpoly[:,1])))
out=r/'evidence/full-iv-house-component';out.mkdir(exist_ok=True)
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inverse=np.linalg.inv(M)
def control(c):return np.maximum(0,(np.array(c)*white)@inverse.T)
s=Scene();s.materials=20;mapping={}
for mid in sorted({p.material for p in b.parts}):
 mat=m.MATERIALS[mid];name=mat.name.lower()
 if 'window glass' in name:idx=s.material('thindielectric',(1,1,1),.05,ior=1.515)
 elif 'woven curtain' in name:
  a=s.material('diffuse',control(mat.color),float(mat.rough));t=s.material('difftrans',control((.35,.35,.33)),1);idx=s.material('blendbsdf');s.emit('nested',idx,a,t,.20)
 elif mat.metal>=.45 and 'frame' not in name:idx=s.material('metal',control(mat.color),.48,eta=(1.75,1.93,2.04),k=(3.4,3.24,3.08))
 else:idx=s.material('plastic',control(mat.color),max(.26,float(mat.rough)),ior=1.44)
 mapping[mid]=idx
with Meshlets(out/'house.clm') as writer:
 for j,p in enumerate(b.parts):
  v=np.asarray(p.vertices)*.001;world=np.c_[xy_world(v[:,:2]),v[:,2]+datum];normals=np.asarray(p.normals)@np.linalg.inv(J);normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
  for begin in range(0,len(p.faces),24000):
   f=p.faces[begin:begin+24000];a=np.zeros((len(f),36),'<f4');a[:,:9]=world[f].reshape(-1,9);a[:,9:18]=normals[f].reshape(-1,9);a[:,18]=mapping[p.material];a[:,19]=1000000+j;a[:,20:26]=v[f,:2].reshape(-1,6);a[:,26:35]=1;writer.add(a)
s.save(out/'materials.cys')
layout=json.loads((r/'evidence/full-iv-roofs/glb-part-layout.json').read_text());replacement=[p['component'] for batch in layout.values() for p in batch['parts'] if p['part'].startswith('osm_way_42753197_')]
assert len(replacement)>=2
report={'parts':len(b.parts),'triangles':writer.triangles,'base_parts_verified_byte_exact_before_transform':matched,'new_native_object_id_start':1000000,'replace_sector_components':sorted(replacement),'source_feature_id':'osm:way:42753197','estimated_foundation_datum_from_DEM_m':datum,'plan_transform':'Invert retained house local tangent projection to WGS84, then forward into full-scene UTM11N local metres','normal_transform':'Inverse transpose of local projection Jacobian','material_scope':'Retained estimated base palette, roughness, glass, metal and curtain reflection/transmission. Microtexture shader parity is not asserted in this lower-detail neighborhood component.','geometry_scope':'Preserved architecture/deck/fence source with I fence/cord additions. Old authored terrain and nearby context proxies are excluded.','source_recipe_sha256':hashlib.sha256((geo/'recipe.py').read_bytes()).hexdigest(),'I_source_sha256':hashlib.sha256((geo/'facade_structure_i.py').read_bytes()).hexdigest()}
(out/'COMPONENT_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
