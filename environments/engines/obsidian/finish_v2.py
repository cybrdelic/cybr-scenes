#!/usr/bin/env python3
"""Non-neural, AOV-guided variance filtering. No external/image-generation model.
Denoise reflected light separately, preserve directly visible thermal emission.
"""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.ndimage import gaussian_filter,median_filter
from PIL import Image
from finish import pfm,display

def filter_lighting(rgb,normal,depth,albedo,variance,emission,passes=3):
    surf=np.linalg.norm(normal,axis=-1)>.05
    mod=np.where(surf[...,None],np.maximum(albedo,.008)+.035,1.)
    image=np.maximum(rgb-emission,0)/mod
    var=np.maximum(np.mean(variance/mod**2,axis=-1),1e-8)
    norms=np.linalg.norm(normal,axis=-1,keepdims=True)
    normal=normal/np.maximum(norms,1e-6)
    lum=np.array([.2126,.7152,.0722],np.float32)
    H,W=depth.shape
    for step in [1,2,4,8][:passes]:
        out=np.zeros_like(image);ws=np.zeros((H,W),np.float32)
        y=image@lum
        for dy in range(-2,3):
            for dx in range(-2,3):
                if dx*dx+dy*dy>5:continue
                sx=dx*step;sy=dy*step
                other=np.roll(image,(sy,sx),(0,1));n=np.roll(normal,(sy,sx),(0,1))
                d=np.roll(depth,(sy,sx),(0,1));a=np.roll(albedo,(sy,sx),(0,1))
                nd=np.sum(normal*n,axis=-1)
                nw=np.where(surf,np.maximum(nd,0)**16,1.)
                dw=np.exp(-np.abs(depth-d)/(np.maximum(depth,1)*.015*step+.025))
                aw=np.exp(-np.sum((albedo-a)**2,axis=-1)/.016)
                sigma=.035+4*np.sqrt(var+np.roll(var,(sy,sx),(0,1)))
                cw=np.exp(-np.abs(y-other@lum)/sigma)
                w=np.exp(-(dx*dx+dy*dy)/2.5)*nw*dw*aw*cw
                if sy>0:w[:sy]=0
                elif sy<0:w[sy:]=0
                if sx>0:w[:,:sx]=0
                elif sx<0:w[:,sx:]=0
                out+=other*w[...,None];ws+=w
        image=out/np.maximum(ws[...,None],1e-8)
    return np.maximum(image*mod+emission,0)

def main():
    p=argparse.ArgumentParser();p.add_argument('prefix');p.add_argument('--exposure',type=float,default=1.5);p.add_argument('--passes',type=int,default=3)
    a=p.parse_args();b=str(a.prefix)
    raw=pfm(b+'.pfm');normal=pfm(b+'_normal.pfm');albedo=pfm(b+'_albedo.pfm');depth=pfm(b+'_depth.pfm')[...,0];var=pfm(b+'_variance.pfm');em=pfm(b+'_emission.pfm')
    out=filter_lighting(raw,normal,depth,albedo,var,em,a.passes)
    for e in [a.exposure]:
        Image.fromarray(display(out,e)).save(b+'.png')
        Image.fromarray(display(raw,e)).save(b+'_raw.png')
    np.save(b+'_denoised.npy',out)
    print(json.dumps({'finite_raw':bool(np.isfinite(raw).all()),'raw_min':float(raw.min()),'raw_max':float(raw.max()),'exposure':a.exposure,'denoising':'non-neural variance-guided demodulated a-trous; direct emission preserved','passes':a.passes,'dimensions':[raw.shape[1],raw.shape[0]],'raw_luma_percentiles':np.percentile(raw@np.array([.2126,.7152,.0722]),[0,10,50,90,99,100]).tolist()},indent=2))
if __name__=='__main__':main()
