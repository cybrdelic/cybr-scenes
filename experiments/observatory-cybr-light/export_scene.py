#!/usr/bin/env python3
"""Export Observatory IV into native CYBR LIGHT scene files without modifying it.

Requires CYBR LIGHT's generic CYBM importer and shared-texture loader. Geometry
is not simplified; materials use documented native-model translations. No
rendering algorithm is implemented here.
"""
from __future__ import annotations
import argparse, hashlib, json, math, struct
from pathlib import Path
import numpy as np
from scipy.optimize import nnls

CAMERAS = {
    'hero': ((-.95,-3.28,2.38),(-.20,.43,1.51),62),
    'instrument': ((-1.52,-1.64,1.98),(-.39,.15,1.52),42),
    'workbench': ((1.86,-1.79,2.19),(-.29,.06,1.40),55),
}

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def rotate(v):
    v=np.asarray(v)
    return np.stack((v[...,0],v[...,2],-v[...,1]),axis=-1)

def write_pfm(path: Path, a: np.ndarray) -> None:
    a=np.asarray(a,dtype='<f4')
    if a.ndim!=3 or a.shape[2]!=3 or not np.isfinite(a).all():raise ValueError('Invalid PFM array')
    with path.open('wb') as f:
        f.write(f'PF\n{a.shape[1]} {a.shape[0]}\n-1.0\n'.encode())
        f.write(a[::-1].tobytes())

def controls(nm):
    w=np.exp(-.5*((np.asarray(nm)[:,None]-[610,545,450])/[43,34,27])**2)
    return w/np.maximum(w.sum(axis=1,keepdims=True),1e-30)

def anchors(c,nm):
    b=np.clip((nm-465)/90,0,1);b=b*b*(3-2*b)
    r=np.clip((nm-550)/95,0,1);r=r*r*(3-2*r)
    return np.clip(c[2]*(1-b)+c[1]*b*(1-r)+c[0]*r,0,.985)

def planck(nm,temperature):
    w=np.asarray(nm)*1e-9
    return 1/(w**5*np.expm1(.01438776877/(w*temperature)))

def cie_y(nm):
    def g(m,l,r):return np.exp(-.5*((nm-m)*np.where(nm<m,l,r))**2)
    return .821*g(568.8,.0213,.0247)+.286*g(530.9,.0613,.0322)

def quartz(nm):
    l2=(np.asarray(nm)*.001)**2
    return np.sqrt(1.28604141+1.07044083*l2/(l2-.0100585997)+1.10202242*l2/(l2-100))

def export(source: Path, out: Path, width=900,height=600,spp=48,bands=8,view='hero',aperture=.004,threads=5):
    source=source.resolve();out=out.resolve()
    if out==source or source in out.parents:raise ValueError('Output must be separate from the preserved scene')
    out.mkdir(parents=True,exist_ok=True)
    (out/'textures').mkdir(exist_ok=True);(out/'spectra').mkdir(exist_ok=True)
    meshpath=source/'scene/observatory.cvr2'
    with meshpath.open('rb') as f:
        if f.read(4)!=b'CVR2':raise ValueError('Expected CVR2 input')
        count=struct.unpack('<I',f.read(4))[0]
    if meshpath.stat().st_size!=8+144*count:raise ValueError('Invalid CVR2 size')
    a=np.memmap(meshpath,dtype='<f4',mode='r',offset=8,shape=(count,36))
    if not np.isfinite(a).all():raise ValueError('Nonfinite source mesh')
    # Apply the same mathematical rule. FMA rounding differs for near-zero faces.
    cross=np.cross(a[:,3:6]-a[:,:3],a[:,6:9]-a[:,:3])
    keep=np.einsum('ij,ij->i',cross,cross)>np.float32(1e-22)
    if not np.array_equal(a[:,26:29],a[:,29:32]) or not np.array_equal(a[:,26:29],a[:,32:35]):
        raise ValueError('This adapter requires the source scene\'s constant per-triangle tint')
    keys=np.c_[a[:,18],a[:,35],a[:,26:29]]
    unique,inverse=np.unique(keys,axis=0,return_inverse=True)
    textures={};lines=[];material_count=0;mapping=[]
    nm=np.arange(360.,831.)
    texture_records=[]
    for tex in sorted(set(int(k[1]) for k in unique if k[1]>=0)):
        path=source/'scene/textures'/f'{tex}.cvtex'
        with path.open('rb') as f:w,h,ch=struct.unpack('<III',f.read(12))
        if ch!=7 or path.stat().st_size!=12+w*h*28:raise ValueError('Invalid source texture')
        data=np.memmap(path,dtype='<f4',mode='r',offset=12,shape=(h,w,7))
        color=np.asarray(data[:,:,:3]);normal=np.asarray(data[:,:,3:6])
        # Native normalmap input is linear [0,1], not display-encoded color.
        write_pfm(out/'textures'/f'{tex}_color.pfm',color)
        write_pfm(out/'textures'/f'{tex}_normal.pfm',normal*.5+.5)
        textures[tex]={'roughness':float(np.mean(data[:,:,6])),'mean_color':np.mean(color,axis=(0,1))}
        texture_records.append({'index':tex,'width':w,'height':h,'source_sha256':sha256(path),
                                'color_sha256':sha256(out/'textures'/f'{tex}_color.pfm'),
                                'normal_sha256':sha256(out/'textures'/f'{tex}_normal.pfm')})
    qn=quartz(nm);qa,qb=np.linalg.lstsq(np.c_[np.ones(len(nm)),1/(nm*.001)**2],qn,rcond=None)[0]
    qfit=qa+qb/(nm*.001)**2
    np.savetxt(out/'spectra/quartz_absorption.spd',np.c_[nm,.009+.018*np.exp(-.5*((nm-430)/90)**2)],fmt='%.12g')
    def material(kind,color=(1,1,1),rough=.5,ior_a=1.48,ior_b=0,eta=(1,1,1),k=(1,1,1),emission=0,kelvin=6500):
        nonlocal material_count
        i=material_count;material_count+=1
        nums=[*color,rough,ior_a,ior_b,*eta,*k,0,0,0,emission,kelvin]
        lines.append('material '+kind+' '+' '.join(f'{x:.12g}' for x in nums))
        return i
    for kind_,tex_,*tint_ in unique:
        kind,tex=int(kind_),int(tex_);tint=np.asarray(tint_,float)
        rough=textures[tex]['roughness'] if tex>=0 else .6
        if kind in (3,4,5):
            rough=(.21 if kind==3 else .30) if tex<0 else rough
            if kind==3:rough=np.clip(rough+.072,.19,.42)
            color=textures[tex]['mean_color']*tint if tex>=0 else tint
            if kind==3:color*=np.array([.91,.93,.97])
            f0=anchors(np.clip(color,0,.94),nm)
            kval=2*np.sqrt(f0/np.maximum(1-f0,1e-6))
            i=material('metal',rough=rough)
            np.savetxt(out/'spectra'/f'metal_{i}.spd',np.c_[nm,kval],fmt='%.12g')
            lines.append(f'spectrum {i} k "spectra/metal_{i}.spd"')
            slope=rough*rough;aspect=math.sqrt(1-.8*.40)
            lines.append(f'anisotropy {i} {slope/aspect:.12g} {slope*aspect:.12g}')
        elif kind==8:
            i=material('glass',ior_a=qa,ior_b=qb)
            lines.append(f'spectrum {i} absorption "spectra/quartz_absorption.spd"')
        elif kind==12:
            r=material('diffuse',tint,rough)
            t=material('difftrans',tint,rough)
            if tex>=0:
                lines.extend(f'texture {j} "textures/{tex}_color.pfm" 1 1 1' for j in (r,t))
            i=material('blendbsdf',rough=rough)
            lines.append(f'nested {i} {r} {t} 0.58')
        else:
            if kind==10:tint=np.array([.022,.017,.009]);rough=.7
            i=material('plastic',np.clip(tint,0,1.06),rough)
            if tex>=0:lines.append(f'texture {i} "textures/{tex}_color.pfm" 1 1 1')
        # Preserve all normal maps. CYBR LIGHT uses its own tangent-frame convention.
        if tex>=0 and kind!=8:
            wrapper=material('normalmap')
            lines.extend([f'nested {wrapper} {i} -1 0',f'texture {wrapper} "textures/{tex}_normal.pfm" 1 1 1'])
            i=wrapper
        mapping.append(i)
    pos,target,hfov=CAMERAS[view];pos=rotate(pos);target=rotate(target)
    vfov=math.degrees(2*math.atan(math.tan(math.radians(hfov/2))/(width/height)))
    focus=float(np.linalg.norm(target-pos))
    cfg=[f'settings {width} {height} {spp} {bands} 12 5 {threads} 71833 1.7 0 0 -1 1 1',
         'camera '+' '.join(f'{x:.12g}' for x in [*pos,*target,0,1,0,vfov,aperture,focus,0,0,0,4]),
         'render_options volpath 1 box 1','film_format openexr']
    # Fit only the existing sky spectral controls; do not introduce fill lights.
    wl=380+(np.arange(16)+.5)*25;Y=cie_y(wl);Y/=Y.sum()
    def normalized_bb(w,T):return planck(w,T)/np.dot(planck(wl,T),Y)
    blue=normalized_bb(nm,7200)*(550/nm)**.25
    blue/=np.dot(normalized_bb(wl,7200)*(550/wl)**.25,Y)
    horizon=normalized_bb(nm,6300)
    weights=controls(nm);bc=nnls(weights,blue)[0];hc=nnls(weights,horizon)[0]
    H,W=256,512;el=np.clip(np.cos((np.arange(H)+.5)*np.pi/H),0,1)
    rgb=(.7+.3*el)[:,None]*bc+(.34*(1-el)**3)[:,None]*hc
    sky=np.broadcast_to(rgb[:,None,:],(H,W,3)).copy()
    write_pfm(out/'textures/sky.pfm',sky)
    # Distant disk preserves the source sun's angular radius and radiance scale.
    sun=np.array([.52,.81,.335]);sun/=np.linalg.norm(sun);sun=rotate(sun)
    solid=2*math.pi*(1-math.cos(.043));radiance_scale=float(normalized_bb(560,4900)*2/solid)
    light=material('emitter',emission=radiance_scale,kelvin=4900)
    lights=['environment 1 1 1 1',
            'environment_portal 1.35 2.195 -3.17 0.85 0 0 0 1.325 0',
            'environment_portal -1.78 2.35 3.81 0.79 0 0 0 1.27 0','envmap "textures/sky.pfm" 0',
            'disk '+str(light)+' 2000000000 '+' '.join(f'{x:.12g}' for x in [*(sun*1e7),*(-sun),1e7*math.tan(.043),0,0,0]),
            'volume 0 -3.6 0 -2.77 3.6 5 3.6 0.006 0.006 0.006 0.98 0.98 0.98 0.36 1 1']
    # Stream to disk: binary layout stores exact source float32 values after a
    # signed permutation. No lossy decimal conversion or mesh decimation.
    record=np.dtype([('p','<f4',(9,)),('n','<f4',(9,)),('uv','<f4',(6,)),('material','<u4'),('object','<u4')])
    assert record.itemsize==104
    vertex_hash=hashlib.sha256();normal_hash=hashlib.sha256();uv_hash=hashlib.sha256()
    with (out/'geometry.cybm').open('wb') as f:
        f.write(b'CYBM'+struct.pack('<I',int(keep.sum())))
        for first in range(0,count,32768):
            end=min(count,first+32768);b=a[first:end][keep[first:end]]
            batch=np.zeros(len(b),record)
            batch['p']=rotate(b[:,:9].reshape(-1,3,3)).reshape(-1,9)
            batch['n']=rotate(b[:,9:18].reshape(-1,3,3)).reshape(-1,9)
            batch['uv']=b[:,20:26];batch['object']=b[:,19].astype(np.uint32)
            batch['material']=np.asarray(mapping,np.uint32)[inverse[first:end][keep[first:end]]]
            for key,h in [('p',vertex_hash),('n',normal_hash),('uv',uv_hash)]:h.update(np.ascontiguousarray(batch[key]).tobytes())
            f.write(batch.tobytes())
    (out/'scene.cys').write_text('\n'.join(cfg+lines+['mesh_binary "geometry.cybm"']+lights)+'\n')
    meta={'source_scene':'Observatory IV','source_mesh_sha256':sha256(meshpath),'source_triangles':count,
          'accepted_triangles':int(keep.sum()),'rejected_degenerate_triangles':int((~keep).sum()),
          'source_filter':'float32 squared cross product > 1e-22, same mathematical rule; FMA rounding can retain extra near-degenerate faces in the baseline',
          'binary_mesh_sha256':sha256(out/'geometry.cybm'),'position_sha256':vertex_hash.hexdigest(),
          'normal_sha256':normal_hash.hexdigest(),'uv_sha256':uv_hash.hexdigest(),
          'source_objects':int(len(np.unique(a[:,19]))),'native_materials':material_count,
          'material_key_count':len(unique),'textures':texture_records,'coordinate_transform':'[x,z,-y], proper rotation; no rescaling',
          'camera':{'view':view,'origin':pos.tolist(),'target':target.tolist(),'horizontal_fov':hfov,'vertical_fov':vfov,'aperture_radius_m':aperture,'focus_distance_m':focus},
          'settings':{'width':width,'height':height,'spp_packets':spp,'wavelengths_per_packet':bands},
          'quartz_cauchy':{'a':qa,'b_um2':qb,'max_ior_error_360_830_nm':float(np.max(np.abs(qn-qfit)))},
          'native_light_source':'cybrdelic/cybr-light, stock native executable plus generic mesh I/O, shared texture cache, and environment-portal importance sampling',
          'mapping_differences':['Smoothstep RGB spectral controls become native Gaussian spectral controls.',
            'Mean roughness per source material replaces its spatial roughness map.',
            'Metal complex IOR is fitted to mean source normal-incidence reflectance, not measured optical data.',
            'Native UV-aligned anisotropy replaces group-axis-aligned machining tangents.',
            'Native normal-map tangent handedness differs on mirrored source UV faces.',
            'Cauchy fit replaces the source quartz Sellmeier expression; fit error is recorded.',
            'Native bilinear map lookup has no source ray-cone mip selection.',
            'A distant physical emitter disk approximates the original uniform directional cone.',
            'Native engine uses a 90/10 portal/global environment MIS proposal rather than the baseline portal-only proposal.'],
          'no_image_generation':True,'no_geometry_simplification':True,'baseline_modified':False}
    (out/'export.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps({k:meta[k] for k in ['accepted_triangles','source_objects','native_materials','camera','quartz_cauchy']},indent=2),flush=True)
    return meta

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--width',type=int,default=900);p.add_argument('--height',type=int,default=600);p.add_argument('--spp',type=int,default=48);p.add_argument('--bands',type=int,default=8)
    p.add_argument('--view',choices=CAMERAS,default='hero');p.add_argument('--aperture',type=float,default=.004);p.add_argument('--threads',type=int,default=5)
    a=p.parse_args()
    if min(a.width,a.height,a.spp,a.bands,a.threads)<1 or a.bands>128 or a.aperture<0: p.error('Invalid render configuration')
    export(a.source,a.out,a.width,a.height,a.spp,a.bands,a.view,a.aperture,a.threads)
if __name__=='__main__':main()
