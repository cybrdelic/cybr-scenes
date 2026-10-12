"""Rechart the retained Pardall surfaces and bind the original CYBR finish.

Serialized positions, normals, object IDs and triangle order stay unchanged.
No facade geometry or source geography is added by this material adapter.
"""
from pathlib import Path
import hashlib,json,struct,sys
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'work/iv-component-runtime'),str(r/'whole-iv-vendor')]
import numpy as np
from cybr_light import Scene,Meshlets
from cybr_light.runtime import read_pfm
from cybr_terrain.materials import write_pfm
out=r/'evidence/full-iv-pardall-metric-finish';out.mkdir(exist_ok=True);source=r/'evidence/full-iv-pardall/pardall.clm'
print('PARDALL_FINISH_PHASE admitted',flush=True)
s=Scene();s.materials=331;fields=r/'evidence/full-iv-street-finishes'
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.asarray(day['native_basis_to_linear_rgb']);white=M@np.ones(3);old=read_pfm(fields/'6574_cream_stucco_native.pfm');linear=(old@M.T)/white;linear*=np.array([.47,.445,.38])/np.array([.52,.47,.38]);adapted=np.maximum(0,(linear*white)@np.linalg.inv(M).T);write_pfm(out/'pardall_lime_native.pfm',adapted)
base=s.material('plastic',(1,1,1),.76,ior=1.48,texture=out/'pardall_lime_native.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 1.923076923076923 1.923076923076923 1';s.emit('roughness_texture',base,json.dumps(str((fields/'lime_roughness.pfm').resolve())),1.25/.65,1.25/.65,1)
bump=s.material('bumpmap',texture=fields/'lime_height_metres.pfm');s.lines[-1]=s.lines[-1].rsplit(' ',3)[0]+' 1.923076923076923 1.923076923076923 1';s.emit('nested',bump,base,-1,.5);s.emit('metric_bump',bump);s.save(out/'materials.cys')
dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);before=hashlib.sha256();after=hashlib.sha256();changed=0;bad_before=0;min_after=1e99;count=0
with Meshlets(out/'pardall.clm') as writer,source.open('rb') as f:
 magic,total,n=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
 for _ in range(n):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(f.read(nt*11),dtype);q=v[t['indices']];p=q[:,:,:3].astype(float);nn=q[:,:,3:6]
  cross=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);normal=cross/np.linalg.norm(cross,axis=1,keepdims=True);tangent=np.cross(np.tile([0.,0.,1.],(nt,1)),normal);horizontal=np.linalg.norm(tangent,axis=1)<.2;tangent[horizontal]=[1,0,0];tangent/=np.linalg.norm(tangent,axis=1,keepdims=True);canonical=np.argmax(abs(tangent),axis=1);negative=tangent[np.arange(nt),canonical]<0;tangent[negative]*=-1;bitangent=np.cross(normal,tangent);bitangent/=np.linalg.norm(bitangent,axis=1,keepdims=True)
  uv=np.stack([(p*tangent[:,None]).sum(axis=2),(p*bitangent[:,None]).sum(axis=2)],axis=2)/1.25
  def determinants(tex):
   a=tex[:,1]-tex[:,0];b=tex[:,2]-tex[:,0];return a[:,0]*b[:,1]-a[:,1]*b[:,0]
  bad_before+=int((abs(determinants(q[:,:,6:8]))<1e-12).sum());min_after=min(min_after,float(abs(determinants(uv.astype('f4').astype(float))).min()))
  a=np.zeros((nt,36),'<f4');a[:,:9]=q[:,:,:3].reshape(nt,9);a[:,9:18]=nn.reshape(nt,9);a[:,18]=t['material'];a[:,19]=t['object'];a[:,20:26]=uv.reshape(nt,6);a[:,26:35]=q[:,:,8:11].reshape(nt,9)
  chosen=t['material']==49;a[chosen,18]=bump;changed+=int(chosen.sum());a[t['material']==53,18]=186
  before.update(q[:,:,:6].tobytes());after.update(np.concatenate([a[:,:9].reshape(nt,3,3),a[:,9:18].reshape(nt,3,3)],axis=2).tobytes());writer.add(a);count+=nt
assert before.hexdigest()==after.hexdigest() and count==total and min_after>1e-12
receipt={'passed':True,'source_mesh_sha256':hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),'candidate_mesh_sha256':hashlib.file_digest((out/'pardall.clm').open('rb'),'sha256').hexdigest(),'triangles':count,'geometry_position_and_normal_payload_byte_exact':True,'source_object_ids_and_primitive_order_retained':True,'old_degenerate_UV_triangles':bad_before,'new_minimum_abs_float32_UV_determinant':min_after,'plaster_triangles_rebound':changed,'material_offset':331,'material_count':2,'plaster_source':'Pinned CYBR lime-plaster function, .65m tile; prior Pardall mean pigment is retained through the native spectral basis. It remains an estimated finish, not measured local reflectance.','concrete_source':'Existing original CYBR brushed-concrete material186, .32m tile.','UV_contract':'Orthonormal physical face charts,1.25m per UV unit, including vertical faces. Geometry and shading-normal bytes are exact.','scope':'Material/chart repair of the retained source-referenced Pardall building. No ground reconstruction, geometry expansion or photographed texture.'}
(out/'METRIC_FINISH_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
