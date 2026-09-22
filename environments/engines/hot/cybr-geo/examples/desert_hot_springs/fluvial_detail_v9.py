"""Drainage-correlated geometric incision, not a validated landscape simulator."""
from __future__ import annotations
import numpy as np
from numba import njit
from scipy.ndimage import gaussian_filter

@njit(cache=True)
def drainage(height,dx,dy):
    ny,nx=height.shape
    downstream=np.full(ny*nx,-1,np.int64)
    slope=np.zeros(ny*nx,np.float64)
    for y in range(1,ny-1):
        for x in range(1,nx-1):
            j=y*nx+x;z=height[y,x];best=0.;target=-1
            for v in range(-1,2):
                for u in range(-1,2):
                    if u==0 and v==0:continue
                    distance=np.sqrt(u*u*dx*dx+v*v*dy*dy)
                    descent=(z-height[y+v,x+u])/distance
                    if descent>best:best=descent;target=(y+v)*nx+x+u
            downstream[j]=target;slope[j]=best
    order=np.argsort(height.ravel())
    area=np.ones(ny*nx,np.float64)
    for k in range(len(order)-1,-1,-1):
        i=order[k];target=downstream[i]
        if target>=0:area[target]+=area[i]
    return area.reshape(ny,nx),slope.reshape(ny,nx)

def incise(z,dx,dy,passes=12):
    """Shape tributaries using contributing area, retaining the broad ridge.

    Incision is deliberately bounded per pass and spatially widened. No claim
    is made for geological time, sediment mass balance, rainfall, or rock strength.
    """
    original=z.copy();out=z.copy()
    for _ in range(passes):
        area,slope=drainage(out,dx,dy)
        cut=np.minimum(.22*np.sqrt(area)*np.sqrt(slope),2.8)
        cut*=np.clip((original-30)/150,0,1)
        cut=.35*cut+.65*gaussian_filter(cut,1.1)
        out-=cut
    return out
