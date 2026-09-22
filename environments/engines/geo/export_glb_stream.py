#!/usr/bin/env python3
"""Export full CYBR GEO assemblies to inspection GLB with bounded working memory.

The mesh and native camera are preserved. Ordinary glTF palette materials are an
inspection approximation, not the native procedural/spectral shaders. No image
textures, simplification or generated geometry are introduced.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, struct, zipfile
from pathlib import Path
from typing import BinaryIO
import numpy as np


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def header(stream: BinaryIO) -> tuple[tuple[int,...],np.dtype]:
    major,minor=np.lib.format.read_magic(stream)
    if major==1:shape,fortran,dtype=np.lib.format.read_array_header_1_0(stream)
    elif major==2:shape,fortran,dtype=np.lib.format.read_array_header_2_0(stream)
    else:raise ValueError(f'Unsupported NPY version {(major,minor)}')
    if fortran or dtype.hasobject:raise ValueError('Numeric C-order arrays are required')
    if len(shape)!=2 or shape[1]!=3:raise ValueError(f'Expected an (N,3) array, got {shape}')
    return shape,dtype


def camera_matrix(config: dict) -> list[float]:
    origin=np.array(config['camera'],float);target=np.array(config['target'],float)
    forward=target-origin;forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0.,0.,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    m=np.eye(4);m[:3,0]=right;m[:3,1]=up;m[:3,2]=-forward;m[:3,3]=origin
    return m.ravel(order='F').tolist()


def export(scene: Path,destination: Path) -> dict:
    assembly=scene/'assembly';description=json.loads((assembly/'scene.json').read_text())
    if description.get('schema')!='cybrgeo.scene/1' or description.get('units')!='mm':
        raise ValueError('Expected a CYBR GEO schema-1 assembly in millimetres')
    expected=json.loads((scene/'geometry.json').read_text())
    config=json.loads((scene/'camera.json').read_text())
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.bin.partial');pending=destination.with_suffix('.glb.partial')
    gltf={'asset':{'version':'2.0','generator':'CYBR GEO R4 streaming assembly exporter'},
          'scene':0,'scenes':[{'name':description['name'],'nodes':[0]}],
          'nodes':[{'name':'Z-up to glTF Y-up','matrix':[1,0,0,0,0,0,-1,0,0,1,0,0,0,0,0,1],'children':[]}],
          'meshes':[],'materials':[],'buffers':[{'byteLength':0}],'bufferViews':[],'accessors':[],
          'extras':{'native_materials_included':False,'scope':'Full actual geometry and camera; basic inspection palette only','source_mesh_sha256':expected['mesh_sha256']}}
    for i,m in enumerate(description['materials']):
        item={'name':m['name'],'doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':m['color']+[1.],'metallicFactor':m['metal'],'roughnessFactor':m['rough']}}
        if i in (6,7):
            item['alphaMode']='BLEND';item['pbrMetallicRoughness']['baseColorFactor'][3]=.38
        gltf['materials'].append(item)
    triangles=0;total_vertices=0;all_normals_finite=True;offset=0
    try:
        with zipfile.ZipFile(assembly/'meshes.npz') as npz,temporary.open('wb') as body:
            for part in description['parts']:
                names={};vertex_count=0
                for kind,target,dtype in [('vertices',34962,np.dtype('<f4')),('normals',34962,np.dtype('<f4')),('faces',34963,np.dtype('<u4'))]:
                    with npz.open(part['key']+'_'+kind+'.npy') as stream:
                        shape,oldtype=header(stream);count=shape[0]
                        if kind=='vertices':vertex_count=count;total_vertices+=count
                        if kind=='normals' and count!=vertex_count:raise ValueError('Position/normal count mismatch')
                        start=offset;lo=np.full(3,np.inf);hi=np.full(3,-np.inf)
                        for row in range(0,count,65536):
                            n=min(65536,count-row);raw=stream.read(n*3*oldtype.itemsize)
                            if len(raw)!=n*3*oldtype.itemsize:raise ValueError('Truncated NPY array')
                            arr=np.frombuffer(raw,dtype=oldtype).reshape(n,3)
                            if kind=='vertices':
                                out=(arr.astype(np.float64)*.001).astype(dtype)
                                if not np.isfinite(out).all():raise ValueError('Nonfinite positions')
                                lo=np.minimum(lo,out.min(axis=0));hi=np.maximum(hi,out.max(axis=0))
                            elif kind=='faces':
                                if arr.size and (arr.min()<0 or arr.max()>=vertex_count):raise ValueError('Invalid triangle indices')
                                out=arr.astype(dtype)
                            else:
                                out=arr.astype(dtype)
                                if not np.isfinite(out).all():raise ValueError('Nonfinite normals')
                            data=out.tobytes(order='C');body.write(data);offset+=len(data)
                        if stream.read(1):raise ValueError('Trailing NPY array data')
                    view={'buffer':0,'byteOffset':start,'byteLength':offset-start,'target':target}
                    gltf['bufferViews'].append(view)
                    accessor={'bufferView':len(gltf['bufferViews'])-1,'byteOffset':0,'componentType':5125 if kind=='faces' else 5126,'count':count*3 if kind=='faces' else count,'type':'SCALAR' if kind=='faces' else 'VEC3'}
                    if kind=='vertices':accessor.update({'min':lo.tolist(),'max':hi.tolist()})
                    gltf['accessors'].append(accessor);names[kind]=len(gltf['accessors'])-1
                    if kind=='faces':triangles+=count
                mesh={'name':part['name'],'primitives':[{'attributes':{'POSITION':names['vertices'],'NORMAL':names['normals']},'indices':names['faces'],'material':part['material'],'mode':4}], 'extras':{'group':part.get('group'),'components':part.get('metadata',{}).get('components')}}
                gltf['meshes'].append(mesh);gltf['nodes'].append({'name':part['name'],'mesh':len(gltf['meshes'])-1});gltf['nodes'][0]['children'].append(len(gltf['nodes'])-1)
        if triangles!=expected['triangles']:raise RuntimeError('Geometry count differs from actual native render')
        gltf['buffers'][0]['byteLength']=offset
        gltf['cameras']=[{'type':'perspective','name':'Native render camera','perspective':{'aspectRatio':1.5,'yfov':2*math.atan(math.tan(math.radians(config['fov'])/2)/1.5),'znear':.01,'zfar':20000.}}]
        gltf['nodes'].append({'name':'Native render camera','camera':0,'matrix':camera_matrix(config)});gltf['nodes'][0]['children'].append(len(gltf['nodes'])-1)
        encoded=json.dumps(gltf,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
        pad=(-offset)%4;total=12+8+len(encoded)+8+offset+pad
        if total>=2**32:raise ValueError('GLB exceeds unsigned-32-bit file-length limit')
        with pending.open('wb') as out,temporary.open('rb') as body:
            out.write(struct.pack('<III',0x46546C67,2,total));out.write(struct.pack('<II',len(encoded),0x4E4F534A));out.write(encoded)
            out.write(struct.pack('<II',offset+pad,0x004E4942))
            for block in iter(lambda:body.read(4*1024*1024),b''):out.write(block)
            out.write(b'\0'*pad)
        if pending.stat().st_size!=total:raise RuntimeError('GLB byte-length mismatch')
        pending.replace(destination)
        report={'scope':__doc__,'scene':expected['scene'],'triangles':triangles,'vertices':total_vertices,'parts':len(description['parts']),'actual_triangle_count_matches':True,'image_generation':False,'native_mesh_sha256':expected['mesh_sha256'],'source_assembly_npz_sha256':sha(assembly/'meshes.npz'),'glb_sha256':sha(destination),'bytes':destination.stat().st_size,'path':str(destination),'native_procedural_materials_replaced_by_basic_palette_for_inspection':True}
        destination.with_suffix('.glb.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2));return report
    finally:
        temporary.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene_directory',type=Path,help='Contains assembly/, geometry.json and camera.json')
    parser.add_argument('output',type=Path)
    a=parser.parse_args();export(a.scene_directory,a.output)
if __name__=='__main__':main()
