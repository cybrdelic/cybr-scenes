"""Pixel-exact 16-bit PNG crop for texture inspection, no resizing or grading."""
from pathlib import Path
import argparse,subprocess,json,hashlib,struct
import numpy as np
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--box',type=int,nargs=4,required=True,metavar=('X','Y','W','H'));a=p.parse_args();x,y,w,h=a.box
raw=a.source.read_bytes();W,H,bits,color=struct.unpack('>IIBB',raw[16:26]);assert bits==16 and color==2 and 0<=x<W and 0<=y<H and x+w<=W and y+h<=H
subprocess.run(['convert',str(a.source),'-crop',f'{w}x{h}+{x}+{y}','+repage','-depth','16',str(a.output)],check=True)
def pixels(path,shape):
 b=subprocess.run(['convert',str(path),'-depth','16','-endian','MSB','RGB:-'],stdout=subprocess.PIPE,check=True).stdout
 return np.frombuffer(b,dtype='>u2').reshape(shape)
full=pixels(a.source,(H,W,3));crop=pixels(a.output,(h,w,3));assert np.array_equal(full[y:y+h,x:x+w],crop)
b=a.output.read_bytes();ww,hh,depth,ct=struct.unpack('>IIBB',b[16:26]);assert (ww,hh,depth,ct)==(w,h,16,2)
r=dict(source_name=a.source.name,source_sha256=hashlib.sha256(raw).hexdigest(),source_dimensions=[W,H],crop_box_xywh=a.box,output_sha256=hashlib.sha256(b).hexdigest(),output_dimensions=[w,h],channels='16-bit RGB',native_pixel_equality=True,resampling=False,grading=False);a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
