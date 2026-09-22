from pathlib import Path
import argparse, json
import numpy as np
from scipy.ndimage import gaussian_filter
from PIL import Image

def pfm(path):
    with open(path,'rb') as f:
        assert f.readline().strip()==b'PF';w,h=map(int,f.readline().split());scale=float(f.readline());a=np.frombuffer(f.read(),'<f4' if scale<0 else '>f4').reshape(h,w,3)[::-1].copy()
    return a

def atrous(rgb,normal,depth,albedo,variance,passes=3):
    image=rgb.copy();H,W=image.shape[:2];lum=np.array([.2126,.7152,.0722]);var=np.maximum(variance@lum,1e-8)
    for step in [1,2,4][:passes]:
        output=np.zeros_like(image);weights=np.zeros((H,W),np.float32)
        y0=image@lum
        for dy in range(-2,3):
            for dx in range(-2,3):
                if dx*dx+dy*dy>5:continue
                sx=dx*step;sy=dy*step
                other=np.roll(image,(sy,sx),(0,1));n=np.roll(normal,(sy,sx),(0,1));d=np.roll(depth,(sy,sx),(0,1));a=np.roll(albedo,(sy,sx),(0,1))
                nd=np.sum(normal*n,axis=-1);surface=np.linalg.norm(normal,axis=-1)>.1
                nw=np.where(surface,np.maximum(nd,0)**48,1)
                dw=np.exp(-np.abs(depth-d)/(np.maximum(depth,1)*.012*step+.025))
                aw=np.exp(-np.sum((albedo-a)**2,axis=-1)/.004)
                color_sigma=.025+3.5*np.sqrt(var+np.roll(var,(sy,sx),(0,1)))
                cw=np.exp(-np.abs(y0-other@lum)/color_sigma)
                weight=np.exp(-(dx*dx+dy*dy)/2.5)*nw*dw*aw*cw
                if sy>0:weight[:sy]=0
                elif sy<0:weight[sy:]=0
                if sx>0:weight[:,:sx]=0
                elif sx<0:weight[:,sx:]=0
                output+=other*weight[:,:,None];weights+=weight
        image=output/np.maximum(weights[:,:,None],1e-9)
    return image

def display(rgb,exposure=2.0):
    rgb=np.maximum(rgb*exposure,0)
    # Restrained lens bloom from highlights, no generated detail.
    highlights=np.maximum(rgb-1,0)
    rgb=rgb+gaussian_filter(highlights,(2,2,0))*.07+gaussian_filter(highlights,(11,11,0))*.018
    rgb=np.clip((rgb*(2.51*rgb+.03))/(rgb*(2.43*rgb+.59)+.14),0,1)
    rgb=np.where(rgb<=.0031308,12.92*rgb,1.055*np.power(rgb,1/2.4)-.055)
    return (np.clip(rgb,0,1)*255+.5).astype('uint8')

def main():
    p=argparse.ArgumentParser();p.add_argument('prefix');p.add_argument('--exposure',type=float,default=2);p.add_argument('--passes',type=int,default=3);a=p.parse_args();prefix=Path(a.prefix)
    image=pfm(str(prefix)+'.pfm');n=pfm(str(prefix)+'_normal.pfm');d=pfm(str(prefix)+'_depth.pfm')[...,0];al=pfm(str(prefix)+'_albedo.pfm');v=pfm(str(prefix)+'_variance.pfm')
    clean=atrous(image,n,d,al,v,a.passes)
    Image.fromarray(display(image,a.exposure)).save(str(prefix)+'_raw.png');Image.fromarray(display(clean,a.exposure)).save(str(prefix)+'.png')
    print('linear percentiles',np.percentile(image,[0,25,50,90,99,100]),'range',clean.min(),clean.max(),flush=True)
if __name__=='__main__':main()
