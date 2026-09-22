#!/usr/bin/env python3
"""Build the shared material atlas from the recovered CC0 surface photographs."""
from __future__ import annotations
import hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def build(size:int=1024)->Path:
 source=ROOT/'engines/geode/assets/inputs/cybr-geo/examples/desert_hot_springs_v2/assets'
 paths={k:source/f'rock_boulder_dry_{k}_4k.jpg' for k in ('diff','disp','rough')}
 rgb=np.asarray(Image.open(paths['diff']).convert('RGB').resize((size,size),Image.Resampling.LANCZOS),dtype=np.float32)/255
 linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
 # Normalize per channel to retain the scene's calibrated mineral albedo rather
 # than accidentally importing the illumination or colour of another material.
 ratio=np.clip(linear/np.maximum(linear.mean((0,1)),.001),.28,2.8)
 h=np.asarray(Image.open(paths['disp']).convert('L').resize((size,size),Image.Resampling.LANCZOS),dtype=np.float32)/255
 rough=np.asarray(Image.open(paths['rough']).convert('L').resize((size,size),Image.Resampling.LANCZOS),dtype=np.float32)/255
 gx=(np.roll(h,-1,1)-np.roll(h,1,1))*(size*.5*.018)
 gy=(np.roll(h,-1,0)-np.roll(h,1,0))*(size*.5*.018)
 # Gradient samples live in metres per texture-coordinate unit. The native
 # world-space sampler applies the texture density and minification footprint.
 a=np.dstack([ratio,rough,gx,gy,gx*gx+gy*gy,h]).astype('<f4')
 assert a.shape==(size,size,8) and np.isfinite(a).all()
 out=ROOT/'assets/mineral_detail.cdt';out.parent.mkdir(exist_ok=True)
 with out.open('wb') as f:f.write(b'CDT2'+struct.pack('<II',size,8));f.write(a.tobytes())
 record={'input_files':{str(p.relative_to(ROOT)):sha(p) for p in paths.values()},'output_sha256':sha(out),'size':size,'channels':['linear_R_ratio','linear_G_ratio','linear_B_ratio','roughness','height_dU_m','height_dV_m','squared_gradient','height'],'height_amplitude_m':.018,'beauty_image_input':False,'image_generation':False,'source':'Recovered rock_boulder_dry CC0 maps; see original download manifests and notices.'}
 (ROOT/'provenance/material-atlas.json').write_text(json.dumps(record,indent=2)+'\n');return out
if __name__=='__main__':print(build())
