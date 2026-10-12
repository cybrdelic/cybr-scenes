"""Connected bank understory and contact litter, all dimensions in metres.

The geographic bank and shared support are unchanged. Plant density, seasonal
state and organic accumulation are authored source-photo interpretations, not a
current ecological inventory or a hydrology simulation.
"""
from rebuild_lagoon_v11b import *
from scipy.ndimage import gaussian_filter,map_coordinates
import struct
BASE=OUT
OUT=R/'evidence/lagoon-restoration-v12';OUT.mkdir(exist_ok=True)

def region():
 fs=features();buildings=unary_union([x['geometry'] for x in fs if x['category']=='buildings'])
 excluded=[]
 for x in fs:
  if x['category'] not in ['footpaths','bike-paths','driving-surfaces','lawns']:continue
  g=x['geometry'];excluded.append(g.buffer(1.2) if 'LineString' in g.geom_type else g)
 water=unary_union([FRAME.project_geometry(arcgis_geometry(x['geometry'])) for x in json.loads((R/'data/full-iv-20261011/water-000.json').read_text())['features']])
 bank=box(1290,-545,1445,-440).difference(unary_union([buildings,water,BASIN_WATER,*excluded]))
 cache=np.load(BASE/'support.npz');xy=cache['xy'];z=cache['z'];tin=Delaunay(xy);ff=tin.simplices
 def height(p):
  p=np.asarray(p);k=tin.find_simplex(p,tol=1e-7);assert np.all(k>=0);t=tin.transform[k];bc=np.einsum('nij,nj->ni',t[:,:2],p-t[:,2]);return(np.c_[bc,1-bc.sum(1)]*z[ff[k]]).sum(1)
 return bank,height

class PatchField:
 """Metre-scale correlated plant occupancy, not independently random pixels."""
 def __init__(self):
  self.origin=np.array([1280.,-550.]);self.step=.25;g=np.random.default_rng(2026101212);a=g.normal(size=(481,721));self.a=gaussian_filter(a,6/.25,mode='reflect');self.a/=self.a.std();b=gaussian_filter(g.normal(size=a.shape),1.5/.25,mode='reflect');self.a+=b/b.std()*.28
 def __call__(self,p):
  q=(np.asarray(p)-self.origin)/self.step;return map_coordinates(self.a,[q[:,1],q[:,0]],order=1,mode='nearest')

def build():
 bank,height=region();field=PatchField();rng=np.random.default_rng(2026101213);ids=json.loads((BASE/'MATERIAL_IDS.json').read_text());parts=Parts(OUT/'understory.clm',16500000)
 xx,yy=np.meshgrid(np.arange(1300,1435,.38),np.arange(-535,-441,.38));p=np.c_[xx.ravel(),yy.ravel()]+rng.uniform(-.16,.16,(xx.size,2));p=p[shapely.contains_xy(bank,p[:,0],p[:,1])];distance=np.linalg.norm(p-np.array([1394,-493]),axis=1);p=p[distance<70]
 signal=field(p);wetdistance=shapely.distance(shapely.points(p),BASIN);fraction=1/(1+np.exp(-(signal-.20)*2.1));fraction=np.maximum(fraction,.6*np.exp(-wetdistance/4));keep=rng.random(len(p))<fraction*.90;p=p[keep];signal=signal[keep]
 # Spatial coherence is explicit; retaining bare patches preserves the source
 # restoration mosaic. Continuous stems run from the common support surface.
 roots=np.c_[p,height(p)];blade_count=0;wet_clumps=0
 for start in range(0,len(p),100):
  v=[];f=[];m=[]
  for root,sig in zip(roots[start:start+100],signal[start:start+100]):
   wet=Point(root[:2]).distance(BASIN)<2.2;wet_clumps+=int(wet);h=rng.uniform(.22,.48)*(1+.20*np.clip(sig,-1,1));h*=1.25 if wet else 1
   for j in range(24):
    az=rng.uniform(0,2*np.pi);radial=np.array([np.cos(az),np.sin(az),0]);side=np.array([-radial[1],radial[0],0]);length=h*rng.uniform(.65,1.25);reach=length*rng.uniform(.30,.75);width=rng.uniform(.012,.030);base=root.copy();base[:2]+=rng.normal(0,.025,2);base[2]=height(base[None,:2])[0]+.001
    offset=len(v)
    for t in [0,.34,.70,1.]:
     center=base+radial*reach*t*t+[0,0,length*(1.35*t-.55*t*t)];w=width*np.sin(np.pi*t)**.7/2
     v.extend([center-side*w,center+side*w])
    f.extend([[offset,offset+2,offset+3],[offset+2,offset+4,offset+5],[offset+2,offset+5,offset+3],[offset+4,offset+6,offset+5]])
    blade_count+=1
  v=np.asarray(v);v[:,2]=np.maximum(v[:,2],height(v[:,:2])+.001)
  parts.mesh('connected_curved_understory',v,f,ids['sedge'],'authored_restoration_mosaic','Fine curved grass/forb blade groups rooted in the unchanged shared bank TIN;6m coherent patches and1.5m edge breakup, authored density and seasonal state')
 # Fallen leaves conform to the support at each corner instead of floating on
 # a flat horizontal quad. A low fold adds thickness/contact silhouette only.
 q=rng.uniform([1310,-535],[1430,-440],(120000,2));q=q[shapely.contains_xy(bank,q[:,0],q[:,1])];q=q[np.linalg.norm(q-np.array([1394,-493]),axis=1)<65];q=q[rng.random(len(q))<(.22+.55/(1+np.exp(-field(q))))]
 for start in range(0,len(q),3000):
  p=q[start:start+3000];n=len(p);az=rng.uniform(0,2*np.pi,n);axes=np.c_[np.cos(az),np.sin(az),np.zeros(n)];length=rng.uniform(.025,.085,n);width=length*rng.uniform(.22,.6,n);c=np.c_[p,height(p)+.002];v,f=leaf_mesh(c,axes,length,width,folded=True,rolls=np.zeros(n));v[:,2]=height(v[:,:2])+np.tile([.001,.001,.001,.001,.003],n)
  parts.mesh('contact_leaf_litter',v,f,ids['litter'],'authored_fallen_organic_material','Millimetre-contact dry organic leaves; correlated with same coherent understory patches; abundance not measured')
 report=parts.close();report.pop('parts',None);report.update({'clumps':len(roots),'curved_blades':blade_count,'wet_clumps':wet_clumps,'contact_litter_leaves':len(q),'patch_correlation_m':[6,1.5],'bank_area_m2':bank.area,'existing_support_unchanged':True,'source_support_sha256':digest(BASE/'support.npz'),'source_base_mesh_sha256':digest(BASE/'ground.clm'),'max_litter_corner_support_offset_m':.001,'litter_fold_height_m':.003,'authoring_limit':'Patch occupancy and organics are authored ecological appearance estimates. Geographic polygons, DEM, all base mesh positions and lagoon surface are unchanged. No exact present-day plant inventory, moisture solver or generated-image texture.'})
 # Correlated organic-contact pigment modulation uses the same plant field.
 # This changes only vertex reflectance tint; metric soil height/roughness and
 # every position, normal, UV and source polygon remain bit-identical.
 dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);tinted=0
 with (BASE/'ground.clm').open('rb') as src,(OUT/'ground.clm').open('wb') as dst:
  header=src.read(16);dst.write(header);magic,total,packets=struct.unpack('<4sQI',header);assert magic==b'CLM1'
  for packet in range(packets):
   hdr=src.read(4);nv,nt=struct.unpack('<HH',hdr);raw=src.read(nv*44);indices=src.read(nt*11);verts=np.frombuffer(raw,dtype='<f4').reshape(nv,11).copy();tri=np.frombuffer(indices,dtype=dtype);chosen=tri['material']==ids['soil']
   if chosen.any():
    used=np.unique(tri['indices'][chosen]);q=verts[used,:2];selected=shapely.contains_xy(bank,q[:,0],q[:,1]);hit=used[selected];q=q[selected]
    if len(q):
     fraction=1/(1+np.exp(-(field(q)-.20)*2.1));verts[hit,8:11]*=1-fraction[:,None]*np.array([.18,.15,.20]);tinted+=len(hit)
   assert np.array_equal(verts[:,:8],np.frombuffer(raw,dtype='<f4').reshape(nv,11)[:,:8]);dst.write(hdr);dst.write(verts.tobytes());dst.write(indices)
  assert not src.read(1)
 report.update(tinted_ground_vertices=tinted,ground_tint_limit=[.82,.85,.80],tint_contract='Authored organic-contact reflectance variation correlated with same understory patches. Original metric microbed relief, roughness, all geometric support and UVs unchanged.')
 (OUT/'UNDERSTORY.json').write_text(json.dumps(report,indent=2)+'\n');print('CONNECTED_UNDERSTORY',json.dumps(report),flush=True)

if __name__=='__main__':build()
