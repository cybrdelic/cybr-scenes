#!/usr/bin/env python3
"""World-space, topology-preserving R2 surface upgrades for recovered native meshes.

This edits real triangle vertices and transforms their normals by the exact
inverse-transpose deformation Jacobian. It never reads a reference/beauty image.
Water geometry, UVs, materials, primitive order, and component IDs are preserved.
Processing is streamed so 10+ million-triangle scenes need little extra RAM.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, struct, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''): h.update(block)
    return h.hexdigest()


def layout(path: Path, scene: str):
    with path.open('rb') as f:
        head=f.read(16)
        if scene=='obsidian-reach':
            magic,nm,count,stride=struct.unpack('<4I',head)
            if magic!=0x3253424f or stride!=104: raise ValueError('Not OBS2/104')
            f.seek(16); materials=f.read(nm*36)
            kinds=np.frombuffer(materials,dtype='<i4').reshape(nm,9)[:,8].copy()
            return 16+nm*36,count,26,kinds
        if scene=='drowned-geode':
            if head[:4]!=b'CVR2': raise ValueError('Not CVR2')
            return 8,struct.unpack('<I',head[4:8])[0],36,None
        return 4,struct.unpack('<I',head[:4])[0],20,None


def wave(p, amplitude, frequency, phase):
    """Scalar displacement and analytic gradient, both in world coordinates."""
    q=p*np.asarray(frequency,np.float32)+np.asarray(phase,np.float32)
    sn=np.sin(q);cs=np.cos(q)
    h=amplitude*sn[:,0]*sn[:,1]*sn[:,2]
    grad=np.column_stack((cs[:,0]*sn[:,1]*sn[:,2],sn[:,0]*cs[:,1]*sn[:,2],sn[:,0]*sn[:,1]*cs[:,2]))
    grad*=amplitude*np.asarray(frequency,np.float32)
    return h,grad


def deform(p,n,h,gradient,direction):
    """F(p)=p+e*h(p); normal'=J^-T normal (Sherman-Morrison)."""
    e=np.asarray(direction,np.float32)
    jacobian_determinant=1+np.sum(gradient*e,axis=-1)
    if np.min(jacobian_determinant)<=.40:
        raise ValueError('Unsafe/inverting geometry deformation')
    transformed=n-gradient*(np.sum(n*e,axis=-1)/jacobian_determinant)[:,None]
    length=np.linalg.norm(transformed,axis=1)
    good=length>1e-12
    transformed[good]/=length[good,None]
    transformed[~good]=n[~good]
    return p+e*h[:,None],transformed,float(np.min(jacobian_determinant))


def mineral_deform(p,n,scene):
    configs={
      'sandstone-passage':(0,[(.035,(1.1,.75,4.4),(1.7,.3,.8)),(.0075,(12.,8.,17.),(.1,1.1,2.))]),
      'basalt-tide':(0,[(.016,(4.3,3.7,2.2),(.4,1.7,.8)),(.0045,(18.,14.,22.),(.9,.3,1.3))]),
      'fernwater':(2,[(.010,(4.,3.3,3.4),(.8,1.2,.4)),(.002,(24.,21.,18.),(1.9,.7,1.))]),
      'desert-hot-springs':(2,[(.012,(2.6,3.2,4.1),(1.4,.7,.5)),(.003,(20.,16.,18.),(.2,1.1,1.5))]),
      'drowned-geode':(0,[(.025,(3.8,2.5,1.8),(.4,1.8,.7)),(.006,(14.,17.,11.),(1.2,.8,.2))]),
      # Obsidian uses Y-up, unlike the other five scenes. The warm skin's
      # topology and XZ temperature coordinates stay unchanged.
      'obsidian-reach':(1,[(.020,(3.1,1.2,5.4),(.1,1.3,.7)),(.005,(14.,4.,19.),(.9,.7,1.))]),
    }
    axis,terms=configs[scene];h=np.zeros(len(p),np.float32);g=np.zeros_like(p)
    for amplitude,freq,phase in terms:
        dh,dg=wave(p,amplitude,freq,phase);h+=dh;g+=dg
    e=np.zeros(3,np.float32);e[axis]=1
    return (*deform(p,n,h,g,e),float(np.max(np.abs(h))))


def curl_litter(p,n,f):
    q=p-f[:,:3];d=f[:,3:6];s=f[:,6:9];e=f[:,9:12]
    length=np.maximum(f[:,12],.001);width=np.maximum(f[:,13],.001)
    u=np.sum(q*d,axis=1)/length;v=np.sum(q*s,axis=1)*2/width
    # Small, independent edge curling; petiole and endpoints remain fixed.
    a=np.minimum(length*.055,.009)*(.75+.25*np.sin(f[:,15]*1.37))
    h=a*np.sin(np.pi*u)*(v*v-.20)
    du=a*np.pi*np.cos(np.pi*u)*(v*v-.20)
    dv=a*np.sin(np.pi*u)*2*v
    g=d*(du/length)[:,None]+s*(dv*2/width)[:,None]
    return (*deform(p,n,h,g,e),float(np.max(np.abs(h))))


def enhance(scene: str, source: Path, target: Path, chunk: int=24000) -> dict:
    if source.resolve()==target.resolve():raise ValueError('Never overwrite recovered originals')
    source=source.resolve();target=target.resolve()
    start=time.monotonic();offset,count,stride,kinds=layout(source,scene)
    if source.stat().st_size!=offset+count*stride*4:raise ValueError('Mesh length/count mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    report_path=target.parent/'geometry-upgrade.json'
    input_sha=sha(source);tool_sha=sha(Path(__file__))
    if target.exists() and report_path.exists():
        old=json.loads(report_path.read_text())
        if old.get('source_sha256')==input_sha and old.get('tool_sha256')==tool_sha and sha(target)==old.get('result_sha256'):
            return old
    tmp=target.with_suffix(target.suffix+'.partial')
    frames=None;frame_path=source.parent/'surface_frames.bin'
    if frame_path.exists():
        with frame_path.open('rb') as f:
            if f.read(4)!=b'FRM6':raise ValueError('Invalid frames')
            nf=struct.unpack('<I',f.read(4))[0]
        frames=np.memmap(frame_path,mode='r',offset=8,dtype='<f4',shape=(nf,16))
    original=np.memmap(source,mode='r',offset=offset,dtype='<f4',shape=(count,stride))
    touched=0;curled=0;max_displacement=0.;min_det=1.;water_unchanged=True
    bounds_min=np.full(3,np.inf);bounds_max=np.full(3,-np.inf)
    with source.open('rb') as src,tmp.open('wb') as dst:
        dst.write(src.read(offset))
        for first in range(0,count,chunk):
            a=np.array(original[first:first+chunk],copy=True)
            if scene=='obsidian-reach':
                ids=a[:,24].view('<i4');mat=kinds[ids];select=(mat==6)|(mat==7)|(mat==3)|(mat<0)
            else:
                mat=a[:,18].astype(np.int32)
                if scene=='sandstone-passage':select=np.isin(mat,[1,2])
                elif scene=='basalt-tide':select=np.isin(mat,[1,2,13])
                elif scene=='fernwater':select=np.isin(mat,[1,2,5])
                elif scene=='desert-hot-springs':select=np.isin(mat,[1,2])
                else:select=np.isin(mat,[0,1,2])
            if np.any(select):
                p=a[select,:9].reshape(-1,3);n=a[select,9:18].reshape(-1,3)
                pp,nn,det,disp=mineral_deform(p,n,scene)
                a[select,:9]=pp.reshape(-1,9);a[select,9:18]=nn.reshape(-1,9)
                touched+=int(select.sum())*3;max_displacement=max(max_displacement,disp);min_det=min(min_det,det)
            if frames is not None and scene=='fernwater':
                group=a[:,19].astype(np.int32)
                leaf=np.isin(mat,[11,13])&(group>0)&(group<len(frames))
                if leaf.any():
                    f=np.repeat(np.asarray(frames[group[leaf]]),3,axis=0)
                    pp,nn,det,disp=curl_litter(a[leaf,:9].reshape(-1,3),a[leaf,9:18].reshape(-1,3),f)
                    a[leaf,:9]=pp.reshape(-1,9);a[leaf,9:18]=nn.reshape(-1,9)
                    touched+=int(leaf.sum())*3;curled+=int(leaf.sum());max_displacement=max(max_displacement,disp);min_det=min(min_det,det)
            if not np.isfinite(a[:,:18]).all():raise ValueError('Non-finite position/normal')
            if scene!='obsidian-reach':
                water=np.isin(mat,[6,7]);water_unchanged &= bool(np.array_equal(a[water],original[first:first+len(a)][water]))
            coords=a[:,:9].reshape(-1,3);bounds_min=np.minimum(bounds_min,coords.min(0));bounds_max=np.maximum(bounds_max,coords.max(0))
            dst.write(a.astype('<f4',copy=False).tobytes())
            if first%(chunk*40)==0:print(f'{scene}: {first}/{count} triangles',flush=True)
    os.replace(tmp,target)
    # Frame and photographic-texture sidecars are preserved exactly.
    for name in ['surface_frames.bin','textures']:
        item=source.parent/name;out=target.parent/name
        if item.exists() and not out.exists():
            if item.is_dir():shutil.copytree(item,out)
            else:shutil.copy2(item,out)
    report={'scene':scene,'source_sha256':input_sha,'result_sha256':sha(target),'tool_sha256':tool_sha,
       'triangles':count,'changed_vertex_records':touched,'curled_litter_triangles':curled,
       'max_displacement_m':max_displacement,'minimum_jacobian_determinant':min_det,
       'water_records_unchanged':water_unchanged,'bounds_min':bounds_min.tolist(),'bounds_max':bounds_max.tolist(),
       'primitive_order_preserved':True,'material_ids_and_uvs_preserved':True,'finite':True,
       'new_normal_method':'Exact inverse-transpose of continuous deformation Jacobian; normalized',
       'source':str(source.relative_to(ROOT)),'result':str(target.relative_to(ROOT)),
       'seconds':time.monotonic()-start,'image_generation':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True);return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('scene');ap.add_argument('source',type=Path);ap.add_argument('target',type=Path)
    a=ap.parse_args();enhance(a.scene,a.source,a.target)
