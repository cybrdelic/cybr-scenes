#!/usr/bin/env python3
"""Render-only finishing: AOV-guided reflected-light denoising and filmic display.
No image synthesis, learned reconstruction, upscaling, or generated textures.
"""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.ndimage import gaussian_filter,median_filter
from PIL import Image
from finish import pfm
from finish_v2 import filter_lighting

def filmic(rgb,exposure=3.0):
    v=np.maximum(rgb,0).astype(np.float32)*exposure
    # Modest optical halo, in linear light. No glow is drawn into the scene.
    h=np.maximum(v-1.2,0)
    scale=v.shape[1]/2400
    v+=gaussian_filter(h,(1.5*scale,1.5*scale,0))*.045
    v+=gaussian_filter(h,(9*scale,9*scale,0))*.014
    # Fitted filmic transform with cross-channel highlight compression.
    # This is a display fit, not a claim of an ACES reference-transform output.
    im=np.array([[.59719,.35458,.04823],[.076,.90834,.01566],[.02840,.13383,.83777]],np.float32)
    om=np.array([[1.60475,-.53108,-.07367],[-.10208,1.10813,-.00605],[-.00327,-.07276,1.07602]],np.float32)
    v=v@im.T
    v=(v*(v+.0245786)-.000090537)/(v*(.983729*v+.4329510)+.238081)
    v=np.clip(v@om.T,0,1)
    # A mild lens falloff, not a painted lighting pass.
    hh,ww=v.shape[:2];y,x=np.mgrid[0:hh,0:ww]
    falloff=1-.075*((x/(ww-1)-.5)**2+(y/(hh-1)-.5)**2)*2
    v*=falloff[...,None]
    v=np.where(v<=.0031308,12.92*v,1.055*np.power(v,1/2.4)-.055)
    return np.uint8(np.clip(v,0,1)*255+.5)

def main():
    p=argparse.ArgumentParser();p.add_argument('prefix');p.add_argument('--exposure',type=float,default=5.5);p.add_argument('--passes',type=int,default=3);a=p.parse_args();b=str(a.prefix)
    raw=pfm(b+'.pfm');normal=pfm(b+'_normal.pfm');albedo=pfm(b+'_albedo.pfm');depth=pfm(b+'_depth.pfm')[...,0];var=pfm(b+'_variance.pfm');em=pfm(b+'_emission.pfm')
    out=filter_lighting(raw,normal,depth,albedo,var,em,a.passes)
    np.save(b+'_denoised.npy',out)
    Image.fromarray(filmic(out,a.exposure)).save(b+'.png')
    Image.fromarray(filmic(raw,a.exposure)).save(b+'_raw.png')
    print(json.dumps({'width':raw.shape[1],'height':raw.shape[0],'finite_raw':bool(np.isfinite(raw).all()),'raw_min':float(raw.min()),'raw_max':float(raw.max()),'exposure':a.exposure,'denoising':'non-neural variance/normal/depth/albedo-guided reflected light; visible emission retained separately','passes':a.passes,'display':'filmic cross-channel highlight compression and restrained linear-light bloom','upscaling':False,'image_generation':False},indent=2))
if __name__=='__main__':main()
