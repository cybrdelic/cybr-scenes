"""Deterministic non-neural A-trous filtering using renderer normals, albedo,
material/depth and Monte Carlo variance; raw scene-linear buffers never changed.
"""
from pathlib import Path
import argparse,json,struct,os
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, median_filter
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import cv2

def read_pfm(p):
    with open(p,'rb') as f:
        assert f.readline().strip()==b'PF'
        w,h=map(int,f.readline().split());scale=float(f.readline())
        a=np.frombuffer(f.read(),'<f4' if scale<0 else '>f4').reshape(h,w,3)
        return a[::-1].copy()

def display(a,white,exposure):
    a=np.maximum(a/np.asarray(white)*exposure,0)
    # Same fitted filmic curve used by the uploaded photographic renderer.
    a=np.clip((a*(2.51*a+.03))/(a*(2.43*a+.59)+.14),0,1)
    a=np.where(a<=.0031308,a*12.92,1.055*a**(1/2.4)-.055)
    return np.uint8(np.clip(a,0,1)*255+.5)

def filter_image(rgb,g,iterations=4,outlier_control=True):
    normal=g[:,:,:3];albedo=np.maximum(g[:,:,3:6],0);depth=g[:,:,6];var=np.maximum(g[:,:,7],0);mat=g[:,:,8]
    # Viewing-only, variance-gated firefly compression. It prevents a single
    # high-energy path from spreading into a large bright blotch during the
    # wavelet pass. This is a biased preview regularizer, NOT a correction to
    # the native radiance estimate. Preserve the original rgb and guide arrays.
    controlled=0
    if outlier_control:
        luminance=np.maximum(rgb@[.2126,.7152,.0722],1e-8)
        peak=np.maximum(rgb,0).max(axis=-1)
        local_peak=median_filter(peak,size=5,mode='reflect')
        ceiling=np.maximum(local_peak*8,local_peak+.20)
        unreliable=var>.30*luminance*luminance
        bad=unreliable&(peak>ceiling)
        factor=np.where(bad,ceiling/np.maximum(peak,1e-15),1).astype(np.float32)
        rgb=rgb*factor[:,:,None]
        var=var*factor*factor
        controlled=int(np.count_nonzero(bad))
    # Divide out the true texture/albedo only partially: this preserves photo
    # microdetail without imposing the albedo on reflected sky or fog.
    alb_lum=albedo.mean(-1)
    lum=np.maximum(rgb@[.2126,.7152,.0722],0)
    relief=np.clip(albedo+.13,.13,.85)
    data=rgb/relief
    kernel=np.array([1,4,6,4,1],np.float32)
    hh,ww=depth.shape
    variance=gaussian_filter(var,1.1)
    valid=depth>0
    for it in range(iterations):
        step=2**it
        pad=2*step
        color=np.maximum(data,0)
        # Log luminance has a finite scale in deep cavern shadows.
        l=np.log1p((color*relief).mean(-1)*3)
        sigma=.15+2.5*np.sqrt(variance)/(1+lum)
        features=[color,normal,depth,mat,albedo,l,sigma,relief]
        p=[np.pad(v,((pad,pad),(pad,pad))+((0,0),)*(v.ndim-2),mode='edge') for v in features]
        total=np.zeros_like(color);weights=np.zeros((hh,ww),np.float32)
        for ky in range(-2,3):
          for kx in range(-2,3):
            sl=(slice(pad+ky*step,pad+ky*step+hh),slice(pad+kx*step,pad+kx*step+ww))
            c,n,d,m,a,ls,ss,r=[v[sl] for v in p]
            wn=np.exp(-np.maximum(0,1-np.sum(normal*n,axis=-1))*10)
            wd=np.exp(-np.abs(depth-d)/(.25+.025*depth*step))
            wa=np.exp(-np.mean(np.abs(albedo-a),axis=-1)*2)
            wl=np.exp(-np.abs(l-ls)/np.maximum(.10,sigma+ss))
            wm=np.where((mat==m)|((mat>=0)&(m>=0)&(mat<6)&(m<6)),1.,.07)
            w=(kernel[ky+2]*kernel[kx+2])*wn*wd*wa*wl*wm
            total+=c*w[:,:,None];weights+=w
        data=total/np.maximum(weights[:,:,None],1e-15)
    return np.maximum(data*relief,0), {'enabled':outlier_control,'affected_pixels':controlled,'median_window':5,'peak_ratio_limit':8,'variance_gate':.30,'raw_modified':False,'biased_viewing_regularization':True}

def main():
    a=argparse.ArgumentParser();a.add_argument('stem',type=Path);a.add_argument('--exposure',type=float);a.add_argument('--iterations',type=int,default=4);a.add_argument('--disable-outlier-control',action='store_true');v=a.parse_args()
    stem=v.stem;meta=json.loads(stem.with_suffix('.json').read_text())
    if stem.with_suffix('.pfm').exists():
        rgb=read_pfm(stem.with_suffix('.pfm'))
    else:
        image=cv2.imread(str(stem)+'_raw.exr',cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(f'Neither native PFM nor raw EXR exists for {stem}')
        rgb=image[:,:,::-1].copy()
    if stem.with_suffix('.guides').exists():
        with stem.with_suffix('.guides').open('rb') as f:
            w,h=struct.unpack('<II',f.read(8));g=np.frombuffer(f.read(),'<f4').reshape(h,w,9).copy()
    else:
        with np.load(str(stem)+'_guides.npz') as z:
            g=np.concatenate([z['normal'],z['albedo'],z['depth'][:,:,None],z['variance'][:,:,None],z['material'][:,:,None]],axis=2)
    if rgb.shape[:2]!=g.shape[:2] or not np.isfinite(rgb).all():
        raise ValueError('Inconsistent guide dimensions or non-finite raw framebuffer')
    white=meta['film_white_rgb'];exposure=meta['exposure'] if v.exposure is None else v.exposure
    raw=display(rgb,white,exposure);Image.fromarray(raw).save(str(stem)+'_unfiltered.png')
    out,regularization=filter_image(rgb,g,v.iterations,not v.disable_outlier_control)
    Image.fromarray(display(out,white,exposure)).save(str(stem)+'.png')
    ok=cv2.imwrite(str(stem)+'_raw.exr',rgb[:,:,::-1]);assert ok
    np.savez_compressed(str(stem)+'_guides.npz',normal=g[:,:,:3],albedo=g[:,:,3:6],depth=g[:,:,6],variance=g[:,:,7],material=g[:,:,8])
    meta['finishing']={'method':'non-neural variance/normal/depth/albedo guided A-trous filter','iterations':v.iterations,'exposure':exposure,'display_transform':'ACES fitted curve then exact sRGB OETF','raw_preserved':True,'image_generation':False,'neural_denoising':False,'viewing_outlier_control':regularization}
    meta['finite_raw']=bool(np.isfinite(rgb).all());meta['raw_statistics']={'mean':np.mean(rgb,axis=(0,1)).tolist(),'p99':np.percentile(rgb,99).item()}
    stem.with_suffix('.json').write_text(json.dumps(meta,indent=2))
    print('Finished',stem,flush=True)
if __name__=='__main__':main()
