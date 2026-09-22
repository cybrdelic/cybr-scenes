"""Authored, porous carbonate shelves with real overhanging 3D geometry.

Marching cubes extracts a metre-native signed field. This creates geometry;
it is not a mineral-growth simulation, texture-generation model, or backplate.
Tile boundaries share the exact same field and sample lattice.
"""
from __future__ import annotations
import numpy as np
from skimage.measure import marching_cubes
from build_scene_v4 import noise, fbm, mesh_normals, join


def carbonate_shelves(pools, poolq):
    pieces=[]
    for i,(cx,cy,rx,ry,level,depth) in enumerate(pools):
        step=.006
        tile=step*256
        lo=np.floor(np.array([cx-rx*1.47,cy-ry*1.47])/tile)*tile
        hi=np.ceil(np.array([cx+rx*1.47,cy+ry*1.47])/tile)*tile
        zz=np.linspace(level-.012,level+.118,34)
        for x0 in np.arange(lo[0],hi[0]-.01,tile):
            for y0 in np.arange(lo[1],hi[1]-.01,tile):
                xs=x0+np.arange(257)*step;ys=y0+np.arange(257)*step
                xx,yy=np.meshgrid(xs,ys,indexing='ij')
                d=(poolq(xx,yy,i)-1)*rx
                if np.min(d)>.42 or np.max(d)<-.23:continue
                lower=-.09-.055*noise(xx*4.1,yy*4.1)
                upper=.23+.067*noise(xx*5.7,yy*5.7)
                radial=np.maximum(lower-d,d-upper)
                center=level+.038+.012*fbm(xx*4.3,yy*4.7,4)
                thick=.021+.007*noise(xx*12.1,yy*12.1)
                X=xx[:,:,None];Y=yy[:,:,None];Z=zz[None,None,:]
                f=np.maximum(np.abs(Z-center[:,:,None])-thick[:,:,None],radial[:,:,None]*.45)
                f+=.0065*noise(X*39.7,Y*39.7,Z*39.7)
                f+=.0033*noise(X*81.2,Y*81.2,Z*81.2)
                # Cavities intersect the thin shelf rather than being painted
                # dark dots: their interior shadow is solved by the renderer.
                f+=.021*np.maximum(noise(X*47.1+23,Y*47.1-16,Z*47.1+4)-.12,0)**1.2
                if f.min()>=0 or f.max()<=0:continue
                v,faces,_,_=marching_cubes(np.asarray(f,dtype=np.float32),0,
                    spacing=(step,step,float(zz[1]-zz[0])),gradient_direction='ascent',
                    allow_degenerate=False)
                v+=np.array([x0,y0,zz[0]])
                pieces.append((v,faces,mesh_normals(v,faces)))
    if not pieces:raise RuntimeError('No carbonate shelf surface was extracted')
    return join(pieces)
