"""Non-neural, component-separated spectral render reconstruction.

No pixel clipping, isolated-peak replacement, AI denoising, image generation,
upscaling, or painted corrections. Raw floating-point radiance is untouched.
"""
from __future__ import annotations
import argparse,json,os,struct,time,hashlib
from pathlib import Path
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter
LUMA=np.array([.2126,.7152,.0722],np.float32)

def read_pfm(p):
    with open(p,'rb') as f:
        if f.readline().strip()!=b'PF':raise ValueError('Not RGB PFM')
        w,h=map(int,f.readline().split());scale=float(f.readline())
        a=np.frombuffer(f.read(),'<f4' if scale<0 else '>f4').reshape(h,w,3)[::-1].copy()
    return a

def read_guides(p):
    with open(p,'rb') as f:
        w,h=struct.unpack('<II',f.read(8));a=np.frombuffer(f.read(),'<f4').reshape(h,w,9).copy()
    return a

def write_exr(p,a):
    if not cv2.imwrite(str(p),np.ascontiguousarray(a[:,:,::-1],dtype=np.float32)):raise RuntimeError('Cannot write '+str(p))

def display(a,white,exposure):
    a=np.maximum(a/np.array(white,np.float32)*exposure,0)
    a=(a*(2.51*a+.03))/(a*(2.43*a+.59)+.14)
    a=np.clip(a,0,1)
    a=np.where(a<=.0031308,a*12.92,1.055*np.power(a,1/2.4)-.055)
    return np.uint8(np.clip(a,0,1)*255+.5)

def wavelet(a,g,iterations,demodulate,volume=False):
    normal=g[:,:,:3];alb=np.clip(g[:,:,3:6],.02,.94);dep=np.maximum(g[:,:,6],0);mat=g[:,:,8]
    isdiff=np.isin(mat,[0,1,2,6,7,9,10,11,12]);isglass=mat==8;ismetal=np.isin(mat,[3,4,5])
    relief=alb if demodulate else np.ones_like(alb)
    if demodulate:relief=np.where(isdiff[:,:,None],alb+.025,1).astype(np.float32)
    data=a/relief
    var=gaussian_filter(np.maximum(g[:,:,7],0),.7)
    kernel=np.array([1,4,6,4,1],np.float32);hh,ww=dep.shape
    for it in range(iterations):
        step=1<<it;pad=2*step
        lum=np.maximum(np.sum(data*relief*LUMA,axis=-1),0);ll=np.log1p(lum*3)
        arr=[data,normal,dep,mat,var,ll,alb]
        pp=[np.pad(v,((pad,pad),(pad,pad))+((0,0),)*(v.ndim-2),mode='edge') for v in arr]
        total=np.zeros_like(data);weights=np.zeros((hh,ww),np.float32);vsum=np.zeros_like(var)
        for j in range(-2,3):
            for i in range(-2,3):
                sl=(slice(pad+j*step,pad+j*step+hh),slice(pad+i*step,pad+i*step+ww))
                c,n,d,m,v,logl,al=(x[sl] for x in pp)
                nd=np.maximum(0,1-np.sum(n*normal,axis=-1))
                if volume:
                    wn=1;wd=np.exp(-np.abs(dep-d)/(.30+.04*np.maximum(dep,d)*step));wm=np.where((mat<0)==(m<0),1,.05)
                    wl=np.exp(-np.abs(ll-logl)/(.14+3.5*np.sqrt(var+v)*3/(1+3*lum)))
                else:
                    wn=np.exp(-nd*np.where(ismetal|isglass,160.,40.))
                    wd=np.exp(-np.abs(dep-d)/(.008+.002*np.maximum(dep,d)*step))
                    wm=np.where(mat==m,1.,.001)
                    sigma=.026+4.5*np.sqrt(np.maximum(var+v,0))*3/(1+3*lum)
                    wl=np.exp(-np.abs(ll-logl)/np.maximum(.04,sigma))
                # Spatial texture is restored through demodulation, rather than
                # reintroducing a noisy percentage of the original radiance.
                wa=np.exp(-np.mean(np.abs(alb-al),-1)*5) if demodulate else 1
                w=kernel[i+2]*kernel[j+2]*wn*wd*wm*wl*wa
                total+=w[:,:,None]*c;weights+=w;vsum+=w*w*v
        den=np.maximum(weights,1e-20);data=total/den[:,:,None];var=np.maximum(vsum/den**2,var*.10)
    return data*relief

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stem',type=Path);ap.add_argument('--exposure',type=float);ap.add_argument('--preview',action='store_true');ap.add_argument('--no-filter',action='store_true');args=ap.parse_args();t0=time.time();s=args.stem
    meta=json.loads(s.with_suffix('.json').read_text());raw=read_pfm(str(s)+'.pfm');g=read_guides(str(s)+'.guides')
    if not np.isfinite(raw).all():raise ValueError('Nonfinite radiance')
    exp=args.exposure or meta['exposure'];white=meta['film_white_rgb']
    transmitted_path=Path(str(s)+'_transmitted.guides')
    shading_guides=g.copy()
    if transmitted_path.exists():
        tg=read_guides(transmitted_path)
        if tg.shape != g.shape or not np.isfinite(tg).all():raise ValueError('Invalid transmitted geometry guides')
        glass=g[:,:,8]==8
        shading_guides[:,:,:3]=np.where(glass[:,:,None],tg[:,:,:3],g[:,:,:3])
        shading_guides[:,:,6]=np.where(glass,tg[:,:,6],g[:,:,6])

    Image.fromarray(display(raw,white,exp)).save(str(s)+'_unfiltered.png')
    direct=read_pfm(str(s)+'_direct.pfm');indirect=read_pfm(str(s)+'_indirect.pfm');volume=read_pfm(str(s)+'_volume.pfm')
    if args.no_filter:finished=raw
    else:
        # Keep directly sampled diffuse detail; reconstruct the less-converged
        # indirect light independently. Metallic/glass pixels receive a larger
        # reflection filter restricted by their surface normal and depth.
        d=wavelet(direct,g,2,True)
        reflection=wavelet(direct,shading_guides,3,False)
        spec=np.isin(g[:,:,8],[3,4,5,8]);d=np.where(spec[:,:,None],reflection,d)
        ind_diffuse=wavelet(indirect,shading_guides,6,True)
        ind_specular=wavelet(indirect,shading_guides,3,False)
        ind=np.where(spec[:,:,None],ind_specular,ind_diffuse)
        vol=wavelet(volume,g,5,False,True)
        finished=d+ind+vol
    Image.fromarray(display(finished,white,exp)).save(str(s)+'.png')
    if not args.preview:
        write_exr(str(s)+'_raw.exr',raw);write_exr(str(s)+'_finished.exr',finished)
        for name,a in [('direct_raw',direct),('indirect_raw',indirect),('volume_raw',volume)]:write_exr(str(s)+'_'+name+'.exr',a)
        np.savez_compressed(str(s)+'_guides.npz',guides=g)
    with Path(str(s)+'.samples').open('rb') as cf:
        cw,ch=struct.unpack('<II',cf.read(8));counts=np.frombuffer(cf.read(),'<u4').reshape(ch,cw)
    meta['sampling']={'minimum_spp':int(counts.min()),'mean_spp':float(counts.mean()),'maximum_spp':int(counts.max()),'camera_samples':int(counts.sum()),'allocation':'fixed primary-material allocation, not noisy adaptive stopping','histogram':{str(int(v)):int(n) for v,n in zip(*np.unique(counts,return_counts=True))}}
    meta['requested_base_spp']=meta.pop('spp',meta.get('requested_base_spp',0))
    meta['finishing']={'method':'Direct / indirect / volume separation with normal-depth-material-variance-guided a-trous reconstruction','neural':False,'generative':False,'outlier_replacement':False,'path_radiance_clamping':False,'upscaling':False,'raw_changed':False,'dominant_transmitted_geometry_guides':transmitted_path.exists(),'iterations':{'direct_diffuse':2,'direct_glossy':3,'indirect_diffuse':6,'indirect_glossy':3,'volume':5},'display':'ACES fitted shoulder followed by exact sRGB transfer','exposure':exp,'seconds':time.time()-t0}
    meta['aov_sum_max_abs_error']=float(np.max(np.abs(raw-direct-indirect-volume)))
    meta['raw_rgb_negative_component_fraction']=float(np.mean(raw<0))
    meta['png_sha256']=hashlib.sha256(Path(str(s)+'.png').read_bytes()).hexdigest();s.with_suffix('.json').write_text(json.dumps(meta,indent=2));print(str(s)+'.png',time.time()-t0,flush=True)
if __name__=='__main__':main()
