"""Metric full-surface object-space normal contract for procedural flat coupons.

These normals already include the complete height slope. They must not be
applied as a tangent-space residual on an independently displaced base.
For curved/reparameterized arbitrary meshes, use a separate qualified adapter.
"""
import numpy as np

def height_normals(height, *, tile_m, height_scale_m, periodic=True):
    h=np.asarray(height,dtype=np.float64)
    if h.ndim!=2 or min(h.shape)<3 or not np.isfinite(h).all():
        raise ValueError('Height must be a finite two-dimensional field of at least 3x3')
    if not np.isfinite(tile_m) or tile_m<=0 or not np.isfinite(height_scale_m) or height_scale_m<=0:
        raise ValueError('Physical tile and height scales must be positive and finite')
    py,px=tile_m/h.shape[0],tile_m/h.shape[1]
    if periodic:
        dx=(np.roll(h,-1,1)-np.roll(h,1,1))*height_scale_m/(2*px)
        dy=(np.roll(h,-1,0)-np.roll(h,1,0))*height_scale_m/(2*py)
    else:
        dy,dx=np.gradient(h*height_scale_m,py,px,edge_order=2)
    # Arrays are top-down; UV V and object Y point up.
    n=np.stack((-dx,dy,np.ones_like(h)),axis=-1)
    return n/np.linalg.norm(n,axis=-1,keepdims=True)

def encode16(normals):
    n=np.asarray(normals,dtype=np.float64)
    if not np.isfinite(n).all() or n.shape[-1]!=3:raise ValueError('Invalid normal field')
    return np.rint(np.clip(n*.5+.5,0,1)*65535).astype(np.uint16)
