"""Audit serialized render geometry; open cave/floor meshes are intentional."""
from pathlib import Path
import json,struct,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'assets/built_v3/scene.meshbin'
with p.open('rb') as f:
    magic=f.read(4);count=struct.unpack('<I',f.read(4))[0]
assert magic==b'CVR2' and p.stat().st_size==8+count*144
m=np.memmap(p,dtype='<f4',offset=8,mode='r',shape=(count,36))
finite=all(np.isfinite(m[i:i+100000]).all() for i in range(0,count,100000))
items=[]
for mat in [6,8,9]:
    groups=np.unique(m[m[:,18]==mat,19])
    for group in groups:
        xyz=np.array(m[(m[:,18]==mat)&(m[:,19]==group),:9],dtype=np.float64).reshape(-1,3,3)
        vertices,faces=np.unique(xyz.reshape(-1,3),axis=0,return_inverse=True);faces=faces.reshape(-1,3)
        edges=np.sort(np.r_[faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]],axis=1)
        _,ec=np.unique(edges,axis=0,return_counts=True)
        centered=xyz-xyz.reshape(-1,3).mean(0)
        volume=np.einsum('ij,ij->i',centered[:,0],np.cross(centered[:,1],centered[:,2])).sum()/6
        xyz32=xyz.astype('f4');native_cross=np.cross(xyz32[:,1]-xyz32[:,0],xyz32[:,2]-xyz32[:,0]);native_ok=bool(np.all(np.sum(native_cross*native_cross,axis=1)>1e-20))
        area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)*.5
        items.append(dict(group=int(group),material=mat,triangles=len(xyz),boundary_edges=int(np.sum(ec==1)),nonmanifold_edges=int(np.sum(ec>2)),signed_volume_m3=float(volume),min_triangle_area_m2=float(area.min()),closed_outward=bool(np.all(ec==2) and volume>0 and native_ok),native_float32_faces_survive=native_ok))
sha=hashlib.sha256()
with p.open('rb') as f:
    while b:=f.read(8*1024*1024):sha.update(b)
result=dict(triangles=count,mesh_finite=finite,mesh_sha256=sha.hexdigest(),dielectric_objects=len(items),dielectrics_all_closed_outward=all(x['closed_outward'] for x in items),details=items,open_cave_and_basin_are_intentional=True,scope='Topology/finiteness audit only; does not certify photorealism or unbiased transport')
(ROOT/'verification_v3/geometry.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2))
if not finite or not result['dielectrics_all_closed_outward']:raise SystemExit(1)
