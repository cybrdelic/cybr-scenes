#!/usr/bin/env python3
"""Allocate an independent final pass from pilot luminance variance.

Only the *sample budget* is resized; final radiance is always traced at native
output resolution. The final pass uses a separate fixed randomization key.
"""
from pathlib import Path
import argparse,json,struct
import numpy as np
from scipy.ndimage import gaussian_filter,maximum_filter
from PIL import Image
from finish import pfm

def allocate(prefix:Path,output:Path,width:int,height:int,pilot_spp:int=20,maximum:int=192,minimum:int=48):
    rgb=pfm(str(prefix)+'.pfm');variance=pfm(str(prefix)+'_variance.pfm');depth=pfm(str(prefix)+'_depth.pfm')[...,0]
    w=np.array([.2126,.7152,.0722]);luminance=rgb@w;v=variance@(w*w)
    required=pilot_spp*gaussian_filter(v,.8)/((.035*gaussian_filter(luminance,.8)+.0007)**2)
    budget=np.clip(np.ceil(required/8)*8,minimum,maximum)
    budget[depth>2000]=12;budget[(depth>130)&(depth<=2000)]=min(32,maximum)
    budget=maximum_filter(budget,size=3)
    scaled=Image.fromarray(budget.astype(np.float32)).resize((width,height),Image.Resampling.BILINEAR)
    arr=np.minimum(np.ceil(np.asarray(scaled)/8)*8,maximum).astype('<u2')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('wb') as f:f.write(struct.pack('<II',width,height));f.write(arr.tobytes())
    record={'minimum_spp':int(arr.min()),'maximum_spp':int(arr.max()),'mean_spp':float(arr.mean()),'total_camera_paths':int(arr.sum()),'dimensions':[width,height],
      'method':'Fixed independent final-pass allocation from pilot luminance variance; no sample-dependent stopping','radiance_upscaling':False}
    output.with_suffix('.json').write_text(json.dumps(record,indent=2))
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pilot',type=Path);p.add_argument('output',type=Path);p.add_argument('--width',type=int,default=2560);p.add_argument('--height',type=int,default=1120);p.add_argument('--pilot-spp',type=int,default=20);p.add_argument('--maximum',type=int,default=192);p.add_argument('--minimum',type=int,default=48);a=p.parse_args()
    if min(a.width,a.height,a.pilot_spp,a.minimum)<1 or not a.minimum<=a.maximum<=65535:p.error('Invalid resolution or sample bounds')
    print(json.dumps(allocate(a.pilot,a.output,a.width,a.height,a.pilot_spp,a.maximum,a.minimum),indent=2))
if __name__=='__main__':main()
