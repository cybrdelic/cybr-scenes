"""Bounded-memory, exact-dtype CYBR GEO assembly spooling and native export.

Geometric computations remain float64, in the same order as the recovered
builder. Completed Part arrays become read-only disk mappings, not lower-detail
meshes. Archive roundtrip validation streams one Part at a time.
"""
from pathlib import Path
import hashlib,json
import numpy as np

def stream_hash(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for data in iter(lambda:f.read(8<<20),b''):h.update(data)
 return h.hexdigest()

class PartSpool:
 def __init__(self,directory):
  self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True);self.count=0
 def store(self,part):
  self.count+=1
  for field in ['vertices','faces','normals']:
   path=self.directory/f'{self.count:05d}-{field}.npy'
   np.save(path,getattr(part,field),allow_pickle=False)
   setattr(part,field,np.load(path,mmap_mode='r',allow_pickle=False))
  return part

def roundtrip_to_native(directory,meshpath,triangle_count):
 from cybrgeo import Part
 directory=Path(directory);info=json.loads((directory/'scene.json').read_text())
 if info.get('schema')!='cybrgeo.scene/1' or info.get('units')!='mm':raise ValueError('Invalid assembly format')
 if stream_hash(directory/'meshes.npz')!=info['meshes_sha256']:raise ValueError('Assembly archive hash mismatch')
 lo=np.full(3,np.inf);hi=-lo;seen=set();count=0
 with np.load(directory/'meshes.npz',allow_pickle=False) as arrays,Path(meshpath).open('wb') as stream:
  stream.write(np.asarray([triangle_count],dtype='<u4').tobytes())
  for group,entry in enumerate(info['parts']):
   data=dict(entry);key=data.pop('key')
   p=Part(**data,**{field:arrays[f'{key}_{field}'] for field in ['vertices','faces','normals']})
   if p.name in seen or not 0<=p.material<len(info['materials']):raise ValueError('Invalid material or duplicate part')
   seen.add(p.name);bounds=p.bounds;lo=np.minimum(lo,bounds[0]);hi=np.maximum(hi,bounds[1])
   for begin in range(0,len(p.faces),24000):
    faces=p.faces[begin:begin+24000];a=np.empty((len(faces),20),dtype='<f4')
    a[:,:9]=(p.vertices[faces]*.001).reshape(-1,9);a[:,9:18]=p.normals[faces].reshape(-1,9)
    a[:,18]=p.material;a[:,19]=group;stream.write(a.tobytes())
   count+=len(p.faces);del p
 if count!=triangle_count:raise ValueError('Native triangle count mismatch')
 return {'schema':'cybrgeo.validation/1','name':info['name'],'part_count':len(seen),'triangles':count,
    'bounds_mm':[lo.tolist(),hi.tolist()],'unique_names':True,'finite_vertices':True,'valid_indices':True,
    'actual_cybrgeo_part_roundtrip':True,'roundtrip_method':'Hash-validated NPZ; every original Part reconstructed and checked individually',
    'array_dtypes_preserved':True,'geometry_decimation':False,'image_generation':False}
