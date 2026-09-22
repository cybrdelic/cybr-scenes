"""Structural and optical-data regression checks; no fluid-physics claim."""
from pathlib import Path
import json,struct,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'vendor'))
from cybrelements.lava_optics import radiance,material_attributes
p=ROOT/'assets/scene.bin'
with p.open('rb') as f:
    magic,nm,nt,stride=struct.unpack('<4sIII',f.read(16))
    assert magic==b'OBS2' and stride==104
    mats=np.array([struct.unpack('<8fi',f.read(36)) for _ in range(nm)])
assert np.isfinite(mats).all() and (mats[:,:6]>=0).all()
assert (mats[:,6]>0).all() and (mats[:,6]<=1).all()
assert p.stat().st_size==16+36*nm+104*nt
report=json.loads((ROOT/'assets/geometry_validation.json').read_text())
assert report['triangles']==nt
assert report['unique_names'] and report['finite_vertices'] and report['valid_indices']
dtype=np.dtype([('v','<f4',(6,3)),('uv','<f4',(3,2)),('mat','<i4'),('obj','<i4')])
a=np.memmap(p,dtype=dtype,mode='r',offset=16+36*nm,shape=(nt,))
minimum_area=float('inf');bad=0;uvtri=0
for start in range(0,nt,50000):
    q=a[start:start+50000]
    assert np.isfinite(q['v']).all() and np.isfinite(q['uv']).all()
    assert (q['mat']>=0).all() and (q['mat']<nm).all()
    v=q['v'][:,:3].astype(np.float64)
    area=np.linalg.norm(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),axis=1)*.5
    minimum_area=min(minimum_area,float(area.min()));bad+=int((area<=1e-14).sum())
    uvtri+=int((mats[q['mat'],8]<0).sum())
assert bad==0,('degenerate triangles',bad)
with (ROOT/'assets/lava_skin.bin').open('rb') as f:
    w,h,*bounds=struct.unpack('<II4f',f.read(24))
    skin=np.memmap(ROOT/'assets/lava_skin.bin',dtype='<f4',offset=24,mode='r',shape=(h,w,8))
    assert np.isfinite(skin).all()
    assert skin[:,:,2].min()>400 and skin[:,:,2].max()<1900
    assert skin[:,:,3].min()>0 and skin[:,:,3].max()<1
v=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
a=material_attributes(v,v.copy(),np.array([[0,1,2]]));assert np.isfinite(a['reference_dx']).all()
assert radiance(1600)[0]>radiance(1400)[0]>radiance(1200)[0]>0
result={'status':'PASS','materials':nm,'triangles':nt,'uv_textured_scan_triangles':uvtri,'minimum_triangle_area_m2':minimum_area,'degenerate_triangles':bad,'lava_temperature_min_K':float(skin[:,:,2].min()),'lava_temperature_max_K':float(skin[:,:,2].max()),'checks':['OBS2 binary size and schema','all vertex, normal and UV values finite','material indices and values','no zero-area triangles','CYBR GEO report count','heat map finite and bounded','ELEMENTS Jacobian','Planck source monotonicity']}
(ROOT/'tests/scene_check.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
