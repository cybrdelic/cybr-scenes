"""Check geometry/contact invariants for the additive bank revision."""
from pathlib import Path
import hashlib,json,struct
import numpy as np
from scipy.spatial import Delaunay
R=Path(__file__).resolve().parents[1];BASE=R/'evidence/lagoon-restoration-v11b';OUT=R/'evidence/lagoon-restoration-v12'
def packets(path):
 with path.open('rb') as f:
  head=f.read(16);magic,total,count=struct.unpack('<4sQI',head);assert magic==b'CLM1'
  for _ in range(count):
   header=f.read(4);nv,nt=struct.unpack('<HH',header);raw=f.read(nv*44);idx=f.read(nt*11);yield header,raw,idx
  assert not f.read(1)
vertices=0;changed=0;minimum=np.ones(3);maximum=np.ones(3)
for a,b in zip(packets(BASE/'ground.clm'),packets(OUT/'ground.clm'),strict=True):
 assert a[0]==b[0] and a[2]==b[2]
 x=np.frombuffer(a[1],'<f4').reshape(-1,11);y=np.frombuffer(b[1],'<f4').reshape(-1,11)
 assert np.array_equal(x[:,:8],y[:,:8]);assert np.isfinite(y).all();ratio=y[:,8:]/x[:,8:];minimum=np.minimum(minimum,ratio.min(0));maximum=np.maximum(maximum,ratio.max(0));vertices+=len(x);changed+=int(np.any(x[:,8:]!=y[:,8:],axis=1).sum())
assert np.all(minimum>=np.array([.82,.85,.80])-1e-6) and np.all(maximum<=1+1e-6)
cache=np.load(BASE/'support.npz');xy=cache['xy'];z=cache['z'];tin=Delaunay(xy);ff=tin.simplices
assert np.array_equal(ff,cache['faces'])
minimum_support=1e9;maximum_support=-1e9;plant_vertices=0
for _,raw,_ in packets(OUT/'understory.clm'):
 p=np.frombuffer(raw,'<f4').reshape(-1,11)[:,:3];assert np.isfinite(p).all();k=tin.find_simplex(p[:,:2],tol=1e-7);assert np.all(k>=0);t=tin.transform[k];bc=np.einsum('nij,nj->ni',t[:,:2],p[:,:2]-t[:,2]);height=(np.c_[bc,1-bc.sum(1)]*z[ff[k]]).sum(1);offset=p[:,2]-height;minimum_support=min(minimum_support,float(offset.min()));maximum_support=max(maximum_support,float(offset.max()));plant_vertices+=len(p)
assert minimum_support>=0, (minimum_support, "Serialized understory penetrates its support")
result={'passed':True,'ground_vertices_checked':vertices,'tinted_vertices':changed,'positions_normals_uv_indices_and_packet_headers_identical':True,'minimum_tint_ratio':minimum.tolist(),'maximum_tint_ratio':maximum.tolist(),'understory_vertices_checked':plant_vertices,'minimum_serialized_support_offset_m':minimum_support,'maximum_serialized_support_offset_m':maximum_support,'support_sha256':hashlib.sha256((BASE/'support.npz').read_bytes()).hexdigest(),'qualification':'Deterministic mesh/contact validation; not an ecological inventory or visual realism certification.'}
(OUT/'GEOMETRY_CONTRACTS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
