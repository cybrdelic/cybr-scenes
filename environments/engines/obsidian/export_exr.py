#!/usr/bin/env python3
"""Write a little-endian, uncompressed RGB float32 scanline OpenEXR from a PFM.
The export preserves the stored float32 values; it applies no display transform.
"""
from __future__ import annotations
import argparse,struct
from pathlib import Path
import numpy as np
from finish import pfm

def write_exr(path: str | Path, rgb: np.ndarray) -> None:
    image=np.asarray(rgb,dtype='<f4')
    if image.ndim!=3 or image.shape[2]!=3 or not np.isfinite(image).all():
        raise ValueError('A finite H x W x 3 float image is required.')
    h,w=image.shape[:2]
    if h<1 or w<1:raise ValueError('The image is empty.')
    def attr(name: str,kind: str,value: bytes) -> bytes:
        return name.encode()+b'\0'+kind.encode()+b'\0'+struct.pack('<I',len(value))+value
    channels=b''.join(name+b'\0'+struct.pack('<iB3xii',2,0,1,1) for name in [b'B',b'G',b'R'])+b'\0'
    box=struct.pack('<4i',0,0,w-1,h-1)
    header=struct.pack('<II',20000630,2)
    header+=attr('channels','chlist',channels)
    header+=attr('compression','compression',b'\0')
    header+=attr('dataWindow','box2i',box)+attr('displayWindow','box2i',box)
    header+=attr('lineOrder','lineOrder',b'\0')
    header+=attr('pixelAspectRatio','float',struct.pack('<f',1.))
    header+=attr('screenWindowCenter','v2f',struct.pack('<2f',0.,0.))
    header+=attr('screenWindowWidth','float',struct.pack('<f',1.))
    header+=attr('chromaticities','chromaticities',struct.pack('<8f',.64,.33,.30,.60,.15,.06,.3127,.3290))
    header+=b'\0'
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    first=len(header)+8*h;rowbytes=12*w
    with path.open('wb') as out:
        out.write(header)
        for y in range(h):out.write(struct.pack('<Q',first+y*(8+rowbytes)))
        for y in range(h):
            out.write(struct.pack('<ii',y,rowbytes))
            out.write(np.ascontiguousarray(image[y,:,::-1].T,dtype='<f4').tobytes())

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pfm',type=Path);p.add_argument('exr',type=Path);a=p.parse_args()
    write_exr(a.exr,pfm(a.pfm));print(a.exr)
if __name__=='__main__':main()
