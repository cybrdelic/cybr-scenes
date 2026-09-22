"""Closed non-convex rock solids from clipped bedrock and localized erosion.

The field is evaluated on a 3D lattice and meshed with marching cubes. This is
procedural CSG geometry, not photogrammetry or a calibrated weathering model.
Unlike the inherited radial rock parameterization it can represent undercuts,
concave spalls and bounded cavities. Dimensions are normalized before placement.
"""
from __future__ import annotations
import numpy as np
from skimage.measure import marching_cubes
from build_scene_v4 import noise, mesh_normals


def implicit_rock(seed: int, resolution: int = 112):
    if resolution<32 or resolution>192:raise ValueError('Unsupported rock resolution')
    rng=np.random.default_rng(seed)
    axes=np.linspace(-1.1,1.1,resolution)
    x,y,z=np.meshgrid(axes,axes,axes,indexing='ij')
    # A coarse bedrock mass is cut by unequal structural joint planes.
    d=np.sqrt((x/1.04)**2+(y/.96)**2+(z/1.02)**2)-.86
    normals=rng.normal(size=(8,3));normals/=np.linalg.norm(normals,axis=1)[:,None]
    normals[:3,2]=np.abs(normals[:3,2])
    for n,dist in zip(normals,rng.uniform(.61,.85,len(normals))):
        d=np.maximum(d,x*n[0]+y*n[1]+z*n[2]-dist)
    # Grain-scale irregularity is kept distinct from the main structural faces.
    offset=rng.uniform(-40,40,3)
    d+=.022*noise(x*6.2+offset[0],y*6.4+offset[1],z*7.1+offset[2])
    d+=.007*noise(x*19+offset[0],y*21+offset[1],z*17+offset[2])
    # Sparse deep spalls have bounded footprints; they are not grooves engraved
    # around the entire rock. Subtractive solids create genuine concave walls.
    for _ in range(13):
        direction=rng.normal(size=3);direction[2]=rng.uniform(-.20,1.15)
        direction/=np.linalg.norm(direction)
        c=direction*rng.uniform(.70,.91)
        radius=rng.uniform(.028,.075)
        ratio=rng.uniform(.75,1.25,3)
        cavity=(np.abs((x-c[0])/ratio[0])**2.6+np.abs((y-c[1])/ratio[1])**2.6+np.abs((z-c[2])/ratio[2])**2.6)**(1/2.6)-radius
        cavity+=.010*noise(x*19+seed*.1,y*17,z*21)
        d=np.maximum(d,-cavity)
    for _ in range(2):
        n=rng.normal(size=3);n/=np.linalg.norm(n)
        c=rng.normal(size=3);c[2]=abs(c[2]);c=c/max(np.linalg.norm(c),1e-12)*.63
        plane=np.abs((x-c[0])*n[0]+(y-c[1])*n[1]+(z-c[2])*n[2])-.017
        support=np.sqrt((x-c[0])**2+(y-c[1])**2+(z-c[2])**2)-rng.uniform(.24,.36)
        support+=.020*noise(x*13+seed*.3,y*15,z*11)
        cut=np.maximum(plane,support)
        d=np.maximum(d,-cut)
    pitch=float(axes[1]-axes[0])
    v,f,_,_=marching_cubes(d.astype(np.float32),level=0,spacing=(pitch,)*3,allow_degenerate=False,gradient_direction='ascent')
    v+=axes[0]
    # Winding is checked explicitly rather than assumed from a library default.
    signed=np.einsum('ij,ij->i',v[f[:,0]],np.cross(v[f[:,1]],v[f[:,2]])).sum()/6
    if signed<0:f=f[:,[0,2,1]]
    return v,f,mesh_normals(v,f)
