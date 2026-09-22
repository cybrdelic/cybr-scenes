"""Two-sided foliage-only spatial estimator for non-neural display filtering.

Native finite radiance and primary geometry guides only. Leaf normals may have
opposite orientation within a pixel footprint; the opaque normal^28 rejection
starves this thin, unresolved geometry of neighbours. This display filter uses
soft absolute normal alignment, material equality, albedo and relative depth.
It is biased, never modifies raw radiance, and does not invent extra samples.
"""
from __future__ import annotations
import numpy as np
from numba import njit,prange

@njit(parallel=True,cache=True)
def leaf_pass(rgb,normal,albedo,depth,variance,material,step):
    h,w,_=rgb.shape;out=rgb.copy()
    weights=np.array([1.,4.,6.,4.,1.],np.float32)
    for y in prange(h):
        for x in range(w):
            mid=material[y,x]
            if mid!=9 and mid!=3:continue
            acc=rgb[y,x].copy()*36.;total=36.
            for dy in range(-2,3):
                yy=y+dy*step
                if yy<0 or yy>=h:continue
                for dx in range(-2,3):
                    xx=x+dx*step
                    if xx<0 or xx>=w or (dx==0 and dy==0):continue
                    if material[yy,xx]!=mid:continue
                    dot=0.;da=0.;n1=0.;n2=0.
                    for c in range(3):
                        dot+=normal[y,x,c]*normal[yy,xx,c]
                        n1+=normal[y,x,c]*normal[y,x,c]
                        n2+=normal[yy,xx,c]*normal[yy,xx,c]
                        d=albedo[y,x,c]-albedo[yy,xx,c];da+=d*d
                    cosine=min(1.,abs(dot)/np.sqrt(max(n1*n2,1.e-12)))
                    dw=abs(depth[y,x]-depth[yy,xx])/(.10+.10*max(0.,min(depth[y,x],depth[yy,xx])))
                    wt=weights[dx+2]*weights[dy+2]*(.35+.65*cosine)*np.exp(-da/.01-dw*dw)
                    # Do not use noisy current-pixel luminance to reject its own
                    # neighbours: a zero-sun-sample leaf otherwise stays black.
                    total+=wt
                    for c in range(3):acc[c]+=wt*rgb[yy,xx,c]
            for c in range(3):out[y,x,c]=acc[c]/total
    return out
