#!/usr/bin/env python3
"""OBSIDIAN REACH IV: shared geometry and material authoring utilities.

Fictional, art-directed volcanic terrain. Thermal emission uses CYBR ELEMENTS
optics; geometry/validation uses CYBR GEO; native transport uses CYBR LIGHT.
This is not a conservation-law lava solver or a survey of a real eruption.
"""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import sys,json,struct,time
from pathlib import Path
import numpy as np
import trimesh
from scipy.ndimage import map_coordinates,spline_filter,gaussian_filter
from scipy.spatial import cKDTree
from PIL import Image
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
from cybrgeo import Part,Assembly,Material
from cybrelements.lava_optics import radiance,material_attributes
A=ROOT/'assets';A.mkdir(exist_ok=True)
rng=np.random.default_rng(202609214)
t0=time.monotonic();parts=[];uvs=[];palette=[];mats=[]

def material(name,color,rough=.65,spec=.045,kind=0,temp=0):
    emission=radiance(temp)*28 if temp else np.zeros(3)
    palette.append(Material(name=name,color=tuple(color),metal=0,rough=rough,ior=1.52,
        microfinish='optical volcanic finish',material_source='PROVENANCE.json'))
    mats.append((*color,*emission,rough,spec,kind));return len(mats)-1
rockm=[material(f'Basalt_clinker_{i}',(v*.93,v,v*1.04),.68+.02*i,spec=.036) for i,v in enumerate([.027,.034,.041,.050,.061,.074])]
groundmat=material('Old_basalt_flow',(.043,.047,.052),.77,.037,kind=3)
crustmat=material('Fragmented_levee_crust',(.020,.023,.026),.60,.047,kind=4)
scanm=[material('Boulder_01_native_UV',(.40,.42,.45),.70,kind=-1),material('Namaqualand_03_native_UV',(.31,.33,.36),.73,kind=-2)]
flankmat=material('Cooled_lava_flank',(.035,.037,.038),.67,.047,kind=5)
heatmat=material('Partly_cooled_lava_skin',(.03,.033,.037),.36,.045,kind=10000,temp=1465)
# Smooth, repeatable geometric fields: no photograph generation involved.
lattices=[spline_filter(rng.random((512,512)).astype(np.float32),order=3,mode='wrap') for _ in range(7)]
def field(x,z,scale=.1,octaves=4):
    x,z=np.broadcast_arrays(x,z);out=np.zeros(x.shape,np.float32);total=0
    for i in range(octaves):
        s=scale*2**i;a=.49**i
        coords=np.stack(((z*s+173).ravel()%507,(x*s+179).ravel()%507))
        out+=a*map_coordinates(lattices[i],coords,order=3,mode='wrap',prefilter=False).reshape(x.shape);total+=a
    return out/total

def srgb(a):return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
gd=srgb(np.asarray(Image.open(A/'brown_mud_rocks_01_diff_2k.jpg').convert('RGB').resize((1024,1024)),np.float32)/255)
glum=gd@np.array([.2126,.7152,.0722]);glum=np.clip((glum/np.mean(glum))**.55,.45,1.9)
gheight=np.asarray(Image.open(A/'brown_mud_rocks_01_disp_2k.jpg').convert('L').resize((1024,1024)),np.float32)/255
grough=np.asarray(Image.open(A/'brown_mud_rocks_01_rough_2k.jpg').convert('L').resize((1024,1024)),np.float32)/255
with (A/'rock_texture.bin').open('wb') as f:
    f.write(struct.pack('<II',1024,1024));f.write(np.stack([glum,gheight,grough,np.ones_like(glum)],-1).astype('<f4').tobytes())
def ground_height(x,z):
    x,z=np.broadcast_arrays(x,z)
    return map_coordinates(gheight,np.stack([((z*.723)%1*1023).ravel(),((x*.723)%1*1023).ravel()]),order=1,mode='wrap').reshape(x.shape)

def center(z):
    return 3.7*np.sin(z*.090)+1.10*np.sin(z*.153+.7)
def width(z):
    return 4.18+.45*np.sin(z*.113+.8)+.20*np.sin(z*.337)+.09*np.sin(z*1.47)
def level(z):
    # Slow incline plus two eroded steps: a perched, locally compressing reach.
    return .55+.035*(z+22)+.55*(1+np.tanh((z-11)/2.4))+.85*(1+np.tanh((z-39)/3.1))
def terrain(x,z):
    x,z=np.broadcast_arrays(x,z)
    edge=np.abs(x-center(z))-width(z)
    bank=np.maximum(edge,0)
    micro=field(x,z,3.8,3)
    meso=field(x,z,.72,4)
    macro=field(x,z,.13,4)
    lip=(.24+.68*meso)*np.exp(-((bank-1.3)/1.75)**2)
    hill=6.8*np.exp(-((x+14)/8)**2-((z-30)/31)**2)
    hill+=8.2*np.exp(-((x-18)/11)**2-((z-60)/30)**2)
    hill+=.90*np.exp(-((x-10)/7)**2-((z+6)/14)**2)
    old=.38+.14*bank+lip+hill
    old+=(macro-.5)*3.2+(meso-.5)*1.25+(micro-.5)*.27
    # Fracture-scale ridges instead of a smooth dirt surface.
    old+=.4*np.abs(field(x+22,z-111,1.65,3)-.50)
    h=level(z)-.30+old
    blend=np.clip((edge+.30)/1.35,0,1);blend=blend*blend*(3-2*blend)
    bed=level(z)-.90+.15*(meso-.5)
    return bed*(1-blend)+h*blend

def add(name,v,f,mat,group='landscape',uv=None,smooth=True,normals=None):
    v=np.asarray(v,np.float64);f=np.asarray(f,np.int64)
    if not len(f):return
    native=v.astype(np.float32).astype(np.float64)
    tri=native[f]
    good=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)>2e-12
    f=f[good]
    if not len(f):return
    used,inv=np.unique(f,return_inverse=True);v=v[used];f=inv.reshape(-1,3)
    if uv is not None:uv=np.asarray(uv)[used]
    if normals is not None:normals=np.asarray(normals)[used]
    if not smooth:
        v=v[f].reshape(-1,3)
        if uv is not None:uv=uv[f].reshape(-1,2)
        f=np.arange(len(v)).reshape(-1,3);normals=None
    n=np.asarray(trimesh.Trimesh(v,f,process=False).vertex_normals) if normals is None else normals
    pv=v[:,[0,2,1]]*np.array([1000,-1000,1000]);pn=n[:,[0,2,1]]*np.array([1,-1,1])
    parts.append(Part(name,pv,f,pn,material=mat,group=group,role='Explicit authored metre-scale environment',metadata={'authored_units':'m','smooth':smooth,'uv_preserved':uv is not None}))
    uvs.append(uv)

def gridfaces(nz,nx):
    ids=np.arange(nz*nx).reshape(nz,nx);a=ids[:-1,:-1].ravel();b=ids[1:,:-1].ravel();c=ids[1:,1:].ravel();d=ids[:-1,1:].ravel()
    return np.concatenate([np.stack((a,b,d),1),np.stack((b,c,d),1)])

