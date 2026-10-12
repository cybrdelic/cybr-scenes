"""AS original sparse centimetre/decimetre rock tier, physical metres.

This does not resize an approved R5D particle. New bounded solids are cut by
physical oblique planes, then narrowly weathered at true dihedral edges.
Regional reference was used for visible hierarchy only, never as a texture,
scan, shape reconstruction or a calibrated size distribution.
"""
from dataclasses import dataclass
import math
import numpy as np
from scipy.spatial import ConvexHull, HalfspaceIntersection

PALETTE=np.array([[.56,.53,.45],[.39,.315,.225],[.265,.205,.135],[.145,.163,.154],[.49,.385,.26],[.165,.108,.062],[.34,.34,.31]])
@dataclass(frozen=True)
class Fragment:
    vertices:np.ndarray
    faces:np.ndarray
    mineral:int
    color:np.ndarray
    roughness:np.ndarray
    nominal_length_m:float
    weathering_width_m:float
    family:str

def build_fragment(index,seed=2610100905):
    rng=np.random.default_rng(np.random.SeedSequence([seed,index]))
    # New authored dimensional spectrum; mostly small fragments, sparse larger
    # blocks. Every bank body already has its final dimensions, never scaled by
    # the allocator or by distance from the camera.
    family=('slab','block','splinter','broken_lump')[index%4]
    length=float(np.exp(rng.uniform(np.log(.035),np.log(.225))))
    if family=='slab': aspect=rng.uniform(.54,.96);height=length*rng.uniform(.19,.37)
    elif family=='splinter':aspect=rng.uniform(.22,.43);height=length*rng.uniform(.23,.52)
    elif family=='block':aspect=rng.uniform(.60,.98);height=length*rng.uniform(.48,.73)
    else:aspect=rng.uniform(.42,.84);height=length*rng.uniform(.35,.65)
    scale=np.array([length,length*aspect,height])*.5
    planes=[];n=int(rng.integers(7,11));phase=rng.uniform(0,math.tau)
    for i in range(n):
        a=phase+i*math.tau/n+rng.uniform(-.18,.18)
        normal=np.array([np.cos(a),np.sin(a),rng.uniform(-.38,.38)])/scale
        normal/=np.linalg.norm(normal)
        support=float(np.linalg.norm(normal*scale)*rng.uniform(.70,.98))
        planes.append([*normal,-support])
    for sign in (1,-1):
        for _ in range(int(rng.integers(3,6))):
            a=rng.uniform(0,math.tau);tilt=rng.uniform(.18,.70)
            normal=np.array([tilt*np.cos(a),tilt*np.sin(a),sign])/scale
            normal/=np.linalg.norm(normal)
            support=float(np.linalg.norm(normal*scale)*rng.uniform(.60,.93))
            planes.append([*normal,-support])
    planes=np.array(planes);points=HalfspaceIntersection(planes,np.zeros(3)).intersections;h=ConvexHull(points)
    bevel=float(min(rng.uniform(.00055,.0018),height*.065));extra=[];seen=set()
    for fi,face in enumerate(h.simplices):
        for ni in h.neighbors[fi]:
            key=tuple(sorted((fi,int(ni))))
            if key in seen:continue
            seen.add(key);a=h.equations[fi,:3];b=h.equations[ni,:3]
            if np.dot(a,b)>.995:continue
            edge=list(set(face).intersection(h.simplices[ni]))
            if len(edge)!=2:continue
            q=points[edge].mean(0);normal=a+b;normal/=np.linalg.norm(normal)
            cut=bevel*rng.uniform(.45,1.0)
            # A deeply weathered tiny corner can fail to retain the origin;
            # bound each physical plane to the retained interior witness.
            support=float(normal@q-cut)
            if support>height*.06:extra.append([*normal,-support])
    if extra:points=HalfspaceIntersection(np.vstack([planes,extra]),np.zeros(3)).intersections
    h=ConvexHull(points);faces=h.simplices.copy();center=points.mean(0)
    for i,f in enumerate(faces):
        if np.dot(np.cross(points[f[1]]-points[f[0]],points[f[2]]-points[f[0]]),points[f].mean(0)-center)<0:faces[i,[1,2]]=faces[i,[2,1]]
    points[:,:2]-=(points[:,:2].min(0)+points[:,:2].max(0))*.5;points[:,2]-=points[:,2].min()
    mineral=int(rng.choice(7,p=[.17,.24,.19,.12,.11,.07,.10]));base=PALETTE[mineral]*rng.uniform(.84,1.08);dust=np.array([.29,.231,.16]);t=points[:,2]/points[:,2].max();coat=rng.uniform(.03,.12)+.24*(1-t)**2
    color=np.c_[base[None]*(1-coat[:,None])+dust*coat[:,None],np.ones(len(points))];rough=np.clip((.58 if mineral in(0,4) else .72)+coat*.16+rng.uniform(-.03,.03),.45,.9)
    return Fragment(points,faces,mineral,color,rough,length,bevel,family)

def audit_fragment(f):
    edges=np.sort(np.concatenate([f.faces[:,[0,1]],f.faces[:,[1,2]],f.faces[:,[2,0]]]),axis=1);_,counts=np.unique(edges,axis=0,return_counts=True)
    tri=f.vertices[f.faces];signed=float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6)
    assert np.all(counts==2) and signed>0
    assert np.isfinite(f.vertices).all() and np.isfinite(f.color).all() and f.vertices[:,2].min()==0
    assert .015<float(np.ptp(f.vertices,axis=0)[:2].max())<.24
    assert 0<f.weathering_width_m<=.0018
    return dict(family=f.family,vertices=len(f.vertices),triangles=len(f.faces),dimensions_m=np.ptp(f.vertices,axis=0).tolist(),solid_volume_m3=signed,narrow_edge_weathering_m=f.weathering_width_m,mineral_index=f.mineral)
