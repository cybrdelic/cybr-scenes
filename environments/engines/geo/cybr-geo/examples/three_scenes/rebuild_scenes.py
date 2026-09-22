"""CYBR GEO three-environment rebuild, revision R3 (recovered complete pipeline).

All visible surfaces are authored triangle geometry. Assembly/Part serialization,
SAH BVH and the supplied fixed-band spectral transport remain the native path.
This is an art-directed formation model, not a geophysical or botanical simulation.
Dimensions in this file are metres; CYBR GEO's saved assemblies are millimetres.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial import Voronoi
import trimesh

import build_scenes as base
from build_scenes import (Builder, Water, unit, smooth, n3, fractal, rock_mesh,
                          scatter_rocks, parameter_mesh, grid_faces, vertex_normals,
                          sha, HERE, REPO, PALETTE)
from cybrgeo import Material

# Material slots intentionally separate geological and biological formation classes.
# Water remains slots 6 and 7 for compatibility with the native integrator.
if len(PALETTE) == 13:
    PALETTE.extend([
        Material('Hard_layer_or_senescent_fern',(.27,.16,.085),0,.84),
        Material('Dust_or_shell_encrustation_or_pale_bark',(.41,.39,.31),0,.86),
        Material('Algae_or_fungi',(.10,.12,.035),0,.65),
        Material('Weathered_fracture',(.18,.15,.11),0,.85),
    ])


def field(x, y, z=0., scale=1., octaves=3):
    return fractal(np.asarray(x)*scale, np.asarray(y)*scale, np.asarray(z)*scale, octaves)


def rotz(angle):
    c,s=np.cos(angle),np.sin(angle)
    return np.array([[c,s,0.],[-s,c,0.],[0.,0.,1.]])


def rotate_from_z(direction):
    z=unit(direction);axis=np.array([0.,1.,0.]) if abs(z[1])<.9 else np.array([1.,0.,0.])
    x=unit(np.cross(axis,z));y=np.cross(z,x)
    return np.stack([x,y,z])


def indexed_closed_solid(vertices, faces, label):
    """Check local enclosed water/stone surfaces, not arbitrary open landscape skins."""
    mesh=trimesh.Trimesh(vertices,faces,process=False)
    check={'name':label,'watertight':bool(mesh.is_watertight),
           'winding_consistent':bool(mesh.is_winding_consistent),
           'positive_signed_volume':bool(mesh.volume>0)}
    if not all(check[k] for k in ('watertight','winding_consistent','positive_signed_volume')):
        raise RuntimeError(check)
    return check


_FRACTURE_SPHERES = {}

def fracture_block(seed,scale,family='slab',subdivision=3):
    """Joint-cut polyhedra, with limited edge rounding rather than inflated spheres."""
    rng=np.random.default_rng(seed)
    sub=min(subdivision,4)
    if sub not in _FRACTURE_SPHERES:
        m=trimesh.creation.icosphere(subdivisions=sub)
        _FRACTURE_SPHERES[sub]=(np.array(m.vertices),np.array(m.faces))
    directions,faces=_FRACTURE_SPHERES[sub]
    normals=unit(np.r_[np.eye(3),-np.eye(3)]+rng.normal(0,.19,(6,3)))
    normals=np.r_[normals,unit(rng.normal(size=(9,3)))]
    distances=np.r_[rng.uniform(.80,1.12,6),rng.uniform(.66,1.18,9)]
    q=directions@normals.T/distances
    # Nearly exact planar intersection; a small blend rounds only edges.
    maximum=np.maximum(np.max(q,axis=1),.01)
    rounded=np.sum(np.maximum(q,0)**30,axis=1)**(1/30)
    erode=.50 if family=='rounded' else .10
    radius=1/((1-erode)*maximum+erode*rounded)
    v=directions*radius[:,None]
    if family=='rounded':
        # Mixed abrasion, not the same balloon shape for every cobble.
        v=.85*v+.15*directions
    shift=rng.uniform(-40,40,3)
    dis=.010*field(v[:,0]+shift[0],v[:,1]+shift[1],v[:,2]+shift[2],scale=6.1,octaves=3)
    v+=directions*dis[:,None]
    # One bounded fracture scar leaves a planar, non-continuous bite.
    p=unit(rng.normal(size=3));d=v@p
    cut=np.maximum(d-rng.uniform(.49,.79),0)
    v-=p*cut[:,None]*.55
    v*=np.asarray(scale)
    angles=rng.uniform(-.42,.42,2)
    v=v@rotate_from_z([angles[0],angles[1],1])@rotz(rng.uniform(0,2*np.pi))
    return v,faces


def embed(b, floor, x,y,scale, family, material=2,label='Fracture_products', sub=2, burial=.30):
    v,f=fracture_block(int(b.rng.integers(1,2**30)),scale,family,sub)
    # Sample actual footprint, rather than nominal radius, when choosing burial.
    low=float(np.min(v[:,2]));height=float(np.ptp(v[:,2]))
    z=float(floor(x,y))-low-height*burial
    v+=np.array([x,y,z]);b.add(label,v,f,mat=material)
    return v,f


def granular_ground(x,y,baseheight,amplitude=.010):
    """Resolved millimetre/centimetre relief; smaller terms live in the shader."""
    return baseheight+amplitude*(.55*n3(x*29.1,y*29.1)+.27*n3(x*67,y*67)+.11*n3(x*139,y*139))


# ---------------------------------------------------------------------------
# Sandstone passage: stratified jointed alcoves, undercuts, rockfall and alluvium.
# ---------------------------------------------------------------------------
def canyon_center(y):
    y=np.asarray(y)
    return .40*np.sin(y*.21)+1.35*np.exp(-((y-18)/6.8)**2)-.9*np.exp(-((y-30)/4.8)**2)+6.2*smooth(17,30,y)


def canyon_width(y,z,side):
    """Differentially weathered beds with finite joint recesses and patchy spalls.

    Thickness, erosion resistance and outcrop offsets differ by sedimentary unit.
    The same bed coordinate is evaluated by the active material implementation.
    The model is authored geometry, not a calibrated geological simulation.
    """
    y,z=np.broadcast_arrays(y,z)
    bed=z+.035*y+.13*n3(y*.24+side*2,1.)
    w=2.45+.032*z+.22*field(y+side*19,z,scale=.32,octaves=3)
    for yy,zz,sy,sz,depth in [(1.2,2.1,2.6,2.0,.56),(9.0,6.5,3.6,2.9,.78),
                              (18.5,3.7,3.1,1.9,.70),(28.,7.,3.0,3.5,.85)]:
        w+=depth*np.exp(-((y-yy-side*1.2)/sy)**2-((z-zz)/sz)**2)
    w-=.55*np.exp(-((y-12.7+side)/2.4)**2)*smooth(.2,4,z)
    # Random, seeded bed thicknesses and resistance. No repeated sinusoidal bands.
    levels=np.array([-.8,-.19,.22,.94,1.28,2.09,2.72,3.01,3.94,4.59,5.04,
                     5.76,6.03,6.91,7.49,8.35,8.82,9.60,10.34,10.69,11.58,12.35,13.6,15.])
    recess=np.array([.02,.15,-.04,.11,-.09,.04,.22,-.03,.06,-.12,.12,-.02,
                     .20,-.055,.12,-.09,.11,.045,-.06,.15,-.04,.07,-.03])
    for i in range(len(recess)):
        a,b=levels[i:i+2]
        local=bed+.025*field(y+i*2,z,scale=1.25,octaves=2)
        mask=smooth(a-.026,a+.026,local)*(1-smooth(b-.03,b+.03,local))
        t=np.clip((local-a)/(b-a),0,1)
        # Resistant lips, granular undercut and finite sloping broken faces.
        toe=.095*np.exp(-t/0.09)*(0.3+.7*smooth(-.3,.4,n3(y*.7+i,side*3)))
        w+=mask*(recess[i]+toe+.055*(1-t))
        # Bedding-parallel spalls occupy only a subset of the face, at real scale.
        patch=smooth(.08,.40,n3(y*2.3+i*.81,local*4.2+side))
        w+=mask*patch*(.018+.047*(i%4==1))
    # Erosion pockets are subtractive. Their boundaries retain small sharp lips.
    pocket=smooth(.20,.56,field(y*1.7+side*14,z*2.9,scale=1,octaves=3))
    w+=.051*pocket*(.25+.75*smooth(-.1,.4,n3(y*.4,z*.5)))
    w+=.006*field(y+side*6,z,scale=11,octaves=3)
    # Finite joints terminate or change direction at weak bedding planes.
    for j,yy in enumerate([-4.1,-.8,3.6,7.0,11.9,16.4,20.0,24.9,31.,38.1]):
        center=yy+side*.63+.12*n3(z*.6,j*3.)+.035*z
        aperture=.018+.013*(j%3)
        zone=smooth(.20,.7,n3(z*.5+j,side*6.)+.30)
        w+=(.085+.08*(j%2))*np.exp(-((y-center)/aperture)**2)*zone
    w+=.32*np.exp(-((z-.55)/.22)**2)*np.exp(-((y-4-side)/3.3)**2)
    return w


def canyon_floor(x,y):
    x,y=np.broadcast_arrays(x,y);center=canyon_center(y)
    wall=np.abs(x-center)
    talus=.36*smooth(1.65,3.6,wall)*(1+.33*n3(y*.8,x*.4))
    wash=-.08*np.exp(-((x-center+.40*np.sin(y*.47))/.50)**2)
    return -.14+.012*y+talus+wash+.045*field(x,y,scale=.7,octaves=3)


def canyon(out,seed,glb=True):
    b=Builder('canyon',seed);rng=b.rng
    x=np.linspace(-10,10,650);y=np.linspace(-11,48,1350);xx,yy=np.meshgrid(x,y)
    zz=granular_ground(xx,yy,canyon_floor(xx,yy),.005)
    # Small ripple patches are localized fine sediment, never a full-image texture.
    zz+=.003*np.sin(xx*72+4*np.sin(yy*.55))*smooth(.10,.45,n3(xx*.9,yy*.7))
    b.surface('Alluvial_sand_and_rockfall_support',np.stack([xx,yy,zz],-1),0)
    y=np.linspace(-11,46,1700);z=np.linspace(-.65,13.3,730);yy,zz=np.meshgrid(y,z)
    for side in (-1,1):
        xx=canyon_center(yy)+side*canyon_width(yy,zz,side)
        b.surface(('West' if side<0 else 'East')+'_bedded_sandstone',np.stack([xx,yy,zz],-1),1,flip=side>0)
    # Four concentrated rockfall fans, plus small sparse fragments in the wash.
    for side,cy in [(-1,-.3),(1,4.4),(-1,11.5),(1,23.5)]:
        for j in range(660):
            y=rng.normal(cy,1.4);edge=float(canyon_center(y)+side*canyon_width(y,.15,side))
            x=edge-side*rng.exponential(.50)
            r=np.exp(rng.uniform(np.log(.021),np.log(.23)))
            if abs(x-canyon_center(y))<1.15:continue
            embed(b,canyon_floor,x,y,(r,r*rng.uniform(.55,1.2),r*rng.uniform(.14,.39)),
                  'slab',2,'Rockfall_fans',1 if r<.08 else 2,burial=rng.uniform(.10,.28))
    for _ in range(7500):
        y=rng.uniform(-9,38);x=float(canyon_center(y))+rng.uniform(-2.5,2.5)
        density=.05+.75*smooth(.45,2.5,abs(x-canyon_center(y)))
        if rng.uniform()>density:continue
        r=np.exp(rng.uniform(np.log(.007),np.log(.062)))
        embed(b,canyon_floor,x,y,(r,r*.8,r*.39),'rounded',2,'Wash_gravel',1,.34)
    for x,y,r in [(-1.8,-2.3,.68),(2.0,1.8,.54),(-1.6,5.5,.83),(2.35,9.4,.88),(-.8,19.,.70)]:
        x+=float(canyon_center(y))
        embed(b,canyon_floor,x,y,(r,r*.79,r*.48),'slab',2,'Fallen_jointed_slabs',4,.16)
    # Bedding steps are formed by the continuous wall surfaces themselves.
    # Independent small plates read as unsupported platforms at native resolution.
    # No random-dependent geometry follows this removed decorative loop.
    # A connected sandstone buttress at the far bend removes the open plane horizon.
    x=np.linspace(-13,17,560);z=np.linspace(-.5,24,640);xx,zz=np.meshgrid(x,z)
    # The back wall continues outside both side walls: no exposed planar fin/end cap.
    yy=32+2.3*np.sin(xx*.24)+1.2*field(xx,zz,scale=.30,octaves=3)
    yy+=2.4*np.exp(-((xx-3.1)/3.8)**2-((zz-4.5)/5.3)**2)
    yy+=.70*(canyon_width(xx,zz,-1)-2.5)
    yy+=.025*field(xx,zz,scale=4.7,octaves=3)
    b.surface('Far_bend_continuous_wall',np.stack([xx,yy,zz],-1),1)
    cfg={'scene':'canyon','title':'Sandstone Passage — Strata & Rockfall',
         'camera':[-.42,-5.8,1.56],'target':[.15,9.8,3.12],'fov':68,
         'sun':[-.24,-.33,.913],'exposure':2.5,'white_balance':5900,
         'sun_scale':1.,'sky_scale':.95,'water_absorption':1.}
    return b.finish(out,cfg,glb)


# ---------------------------------------------------------------------------
# Basalt tide: unstructured cooling cells, slanted joints, toe collapse and lag.
# ---------------------------------------------------------------------------
def shore_height(x,y):
    x,y=np.broadcast_arrays(x,y)
    edge=1.0+.13*y+.42*np.sin(y*.31)+.25*n3(y*.65,3)
    h=.09-.17*(x-edge)+.070*field(x,y,scale=.8,octaves=3)
    h-=3.2*smooth(19,55,y)
    return np.minimum(h,1.85+.16*field(x,y,scale=.22,octaves=2))


def polygon_column(b,poly,z0,height,seed,label='Cooling_columns',fallen=None):
    """Jointed cooling cells with coherent face displacement and partial failures.

    Faces share positional edge samples. Crown damage, oblique segment shear,
    localized vertical scars and toe abrasion are actual mesh features.
    """
    rng=np.random.default_rng(seed);poly=np.asarray(poly,float);center=poly.mean(0)
    xy=poly-center
    if np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1))<0:xy=xy[::-1]
    n=len(xy);radius=float(np.mean(np.linalg.norm(xy,axis=1)))
    bevel=rng.uniform(.055,.13);outline=[]
    for j in range(n):
        outline.extend([xy[j]*(1-bevel)+xy[(j-1)%n]*bevel,
                        xy[j]*(1-bevel)+xy[(j+1)%n]*bevel])
    outline=np.asarray(outline);ns=len(outline)
    lean=rng.uniform(-.07,.07,2);tilt=rng.uniform(-.34,.34,2)
    damage=rng.uniform(.02,.16,ns);damage[rng.random(ns)<.24]*=2.8
    joints=np.cumsum(rng.uniform(.42,1.31,max(3,int(height/.55)+1)))
    joints=joints[joints<height-.14]
    zrows=np.unique(np.r_[np.linspace(0,height,max(10,int(height/.08)+1)),
                         joints,joints-.028,joints+.031])
    zrows=zrows[(zrows>=0)&(zrows<=height)]
    u=np.linspace(0,1,7);shift=rng.uniform(-30,30,3)
    top_edges=[];bottom_edges=[]
    for j in range(ns):
        a=outline[j];c=outline[(j+1)%ns];uu,zz=np.meshgrid(u,zrows);t=zz/height
        planar=a[None,None,:]*(1-uu[:,:,None])+c[None,None,:]*uu[:,:,None]
        # Coherent radial field gives the SAME coordinates on both sides of an edge.
        xx=planar[:,:,0]+center[0];yy=planar[:,:,1]+center[1]
        erosion=(.018*field(xx+shift[0],yy+shift[1],zz+shift[2],scale=4.,octaves=3)
                +.009*field(xx+shift[0],yy+shift[1],zz+shift[2],scale=15.,octaves=2))
        cavities=smooth(.22,.62,field(xx+shift[0],yy+shift[1],zz+shift[2],scale=7.,octaves=3))
        erosion+=.030*cavities
        seam=np.zeros_like(zz);shearx=np.zeros_like(zz);sheary=np.zeros_like(zz)
        for k,h in enumerate(joints):
            joint=h+.11*xx-.055*yy
            support=smooth(-.25,.30,n3(xx*2+k,yy*2+shift[2]))
            seam+=(.010+.010*(k%3))*np.exp(-((zz-joint)/.021)**2)*support
            shearx+=(.018*np.sin(k*3.4+shift[0]))*smooth(h-.05,h+.05,zz)
            sheary+=(.014*np.sin(k*4.7+shift[1]))*smooth(h-.05,h+.05,zz)
        radius0=np.maximum(np.linalg.norm(planar,axis=-1),.05)
        factor=1-(erosion+seam)/radius0-.035*t
        factor-=.12*np.exp(-((zz+z0-.20)/.55)**2)
        planar=planar*factor[:,:,None]+lean*zz[:,:,None]+center
        planar[:,:,0]+=shearx;planar[:,:,1]+=sheary
        crown=(1-uu)*damage[j]+uu*damage[(j+1)%ns]
        z=zz+z0+np.einsum('...k,k->...',planar-center,tilt)-crown*t**5
        points=np.dstack([planar,z]);top_edges.append(points[-1,:-1]);bottom_edges.append(points[0,:-1])
        if fallen is not None:
            origin,direction=fallen;points=(points-np.r_[center,z0])@rotate_from_z(direction)+origin
        b.surface(label,points,1)
    for edge,reverse in [(bottom_edges,True),(top_edges,False)]:
        rim=np.concatenate(edge);count=len(rim)
        # A small off-center fracture crown prevents a perfectly machined top.
        mid=rim.mean(0);mid[2]-=radius*rng.uniform(.02,.12)
        v=np.vstack([rim,mid]);f=np.array([(count,j,(j+1)%count) for j in range(count)])
        if reverse:f=f[:,::-1]
        if fallen is not None:
            origin,direction=fallen;v=(v-np.r_[center,z0])@rotate_from_z(direction)+origin
        b.add(label+'_broken_caps',v,f,mat=13,flat=True)


def coast(out,seed,glb=True):
    b=Builder('coast',seed);rng=b.rng
    xx,yy=np.meshgrid(np.linspace(-23,32,800),np.linspace(-16,72,1150))
    zz=granular_ground(xx,yy,shore_height(xx,yy),.015)
    b.surface('Intertidal_lag_and_submerged_platform',np.stack([xx,yy,zz],-1),0)
    # A perturbed cooling-cell field, clipped by an irregular erosional cliff edge.
    points=[]
    for row,y in enumerate(np.r_[np.arange(-2,22,.93),np.arange(22,66,1.7)]):
      for x in np.arange(-12,1.,1.08):
        points.append([x+(row%2)*.53+rng.normal(0,.15),y+rng.normal(0,.13)])
    points=np.array(points);vor=Voronoi(points)
    kept=[]
    for k,p in enumerate(points):
        region=vor.regions[vor.point_region[k]]
        if not region or -1 in region:continue
        x,y=p;edge=-.8+.42*np.sin(y*.34)+.30*n3(y*.8,8)
        if x>edge:continue
        if y<0 and x>-4.2:continue
        poly=vor.vertices[region]
        if np.max(np.linalg.norm(poly-p,axis=1))>2.10:continue
        cen=poly.mean(axis=0);poly=cen+(poly-cen)*rng.uniform(.981,.994)
        h=1.4+5.0*smooth(edge,edge-5.5,x)+1.1*field(x,y,scale=.29,octaves=2)
        h+=rng.normal(0,.48)
        h*=1-.95*smooth(23,57,y)
        # Missing crown blocks and stepped collapse pockets interrupt the palisade.
        if rng.uniform()<.27:h*=rng.uniform(.18,.66)
        z0=float(shore_height(x,y))-.35
        polygon_column(b,poly,z0,max(.65,h),int(rng.integers(1,2**30)))
        kept.append((poly,h))
    # Sea stacks use actual fractured cooling-cell aggregates, not smooth
    # radially deformed cones with a separate floating cap.
    for cx,cy,radius,top in [(5.4,35,2.0,4.7),(20,75,4.0,9.5)]:
        spacing=.64 if radius<3 else 1.0
        sites=[]
        for jj,yy in enumerate(np.arange(-radius*1.65,radius*1.65,spacing)):
            for xx in np.arange(-radius*1.65,radius*1.65,spacing):
                sites.append([xx+(jj%2)*spacing*.46+rng.normal(0,spacing*.14),yy+rng.normal(0,spacing*.14)])
        sites=np.asarray(sites);cells=Voronoi(sites)
        for idx,point in enumerate(sites):
            region=cells.regions[cells.point_region[idx]]
            if not region or -1 in region:continue
            r=np.linalg.norm(point)/radius
            if r>1.05+.08*np.sin(np.arctan2(point[1],point[0])*5):continue
            polygon=cells.vertices[region]
            if np.max(np.linalg.norm(polygon-point,axis=1))>spacing*1.5:continue
            polygon=point+(polygon-point)*.976+np.array([cx,cy])
            height=2.8+top*(.40+.60*max(0.,1-r)**.35)+rng.uniform(-.5,.5)
            polygon_column(b,polygon,-2.8,max(.5,height),int(rng.integers(1,2**30)),label='Fractured_stack_cells')
    # Collapsed prisms are visibly made of the same material as the vertical cliff.
    for _ in range(75):
        y=rng.uniform(-3,20);x=rng.uniform(-3.1,1.5)+.08*y
        if shore_height(x,y)<-.15:continue
        rad=rng.uniform(.16,.38);n=int(rng.integers(5,8));aa=np.arange(n)*2*np.pi/n
        poly=np.c_[np.cos(aa)*rad,np.sin(aa)*rad]
        direction=unit([rng.uniform(-1,1),rng.uniform(-1,1),rng.uniform(.0,.20)])
        origin=np.array([x,y,float(shore_height(x,y))+rad*.38])
        if rng.uniform()<.22:
            polygon_column(b,poly,0,rng.uniform(.35,1.05),int(rng.integers(1,2**30)),
                           'Toppled_column_fragments',(origin,direction))
        else:
            embed(b,shore_height,x,y,(rad*rng.uniform(1.2,2.4),rad,rad*.77),'block',2,
                  'Fractured_cliff_toe_rubble',3,.25)
    # Beach armour has clustered size grading and partial burial, not even spacing.
    for i in range(36000):
        x=rng.uniform(-8,10);y=rng.uniform(-13,23);z=float(shore_height(x,y))
        if z<-.45 or z>1.6:continue
        density=.36+.60*smooth(-.35,.4,n3(x*.6+4,y*.6))
        if rng.uniform()>density:continue
        r=np.exp(rng.uniform(np.log(.012),np.log(.20)))
        family='rounded' if z<.28 else ('slab' if rng.uniform()<.5 else 'block')
        embed(b,shore_height,x,y,(r,r*rng.uniform(.6,1.2),r*rng.uniform(.3,.7)),family,2,
              'Size_sorted_beach_armour',1 if r<.07 else 2,burial=rng.uniform(.18,.35))
    for x,y,r in [(-.8,-4.9,.73),(2.0,-.3,.61),(4.2,6.7,.8),(-2.7,-6.1,.44),(4.2,12.7,1.1)]:
        embed(b,shore_height,x,y,(r,r*.82,r*.67),'slab',2,'Wave_worn_boulders',4,.37)
    # Small actual shells/encrustations, only in the intertidal envelope.
    for _ in range(1800):
        x=rng.uniform(-1.5,6);y=rng.uniform(-6,16);z=float(shore_height(x,y))
        if not -.03<z<.19:continue
        r=rng.uniform(.003,.012)
        v,f=rock_mesh(int(rng.integers(1,2**30)),(r,r*.65,r*.23),1)
        v+=np.array([x,y,z+.003]);b.add('Intertidal_shell_fragments',v,f,mat=14)
    Water('coast').add(b,np.r_[np.linspace(-20,35,720),np.linspace(36,1050,35)],
                        np.r_[np.linspace(-17,83,1024),np.linspace(87,2000,60)],bottom=-45)
    cfg={'scene':'coast','title':'Basalt Tide — Cooling Cells & Collapse',
         'camera':[5.3,-8.8,1.7],'target':[-.8,7.9,2.5],'fov':66,
         'sun':[-.50,-.69,.523],'exposure':2.0,'white_balance':6200,
         'sun_scale':1.05,'sky_scale':.92,'water_absorption':.7}
    return b.finish(out,cfg,glb)


# ---------------------------------------------------------------------------
# Fernwater: irregular woodland corridor with tree archetypes and bank collapse.
# ---------------------------------------------------------------------------
def stream_center(y):
    y=np.asarray(y)
    return .70*np.sin(y*.24)+.30*np.sin(y*.51+1.0)+.014*y+4.5*smooth(12,27,y)


def forest_floor(x,y):
    x,y=np.broadcast_arrays(x,y);s=stream_center(y);d=np.abs(x-s)
    # Low irregular banks, sand/gravel bars and local undercut steps.
    width=1.15+.19*n3(y*.53,5)+.16*np.sin(y*.39)
    edge=width+.11*field(y*2.1,x*.3,scale=1,octaves=3)
    bank=smooth(edge,edge+.40,d)
    h=-.29+.75*bank+.115*field(x,y,scale=1.05,octaves=3)*(.26+.74*bank)
    h+=.036*field(x,y,scale=8,octaves=3)*bank
    h-=.085*np.exp(-((d-edge-.18)/.12)**2)*smooth(-.1,.5,n3(y*1.4,x*.35))
    h+=.10*np.exp(-((y-1.6)/1.8)**2)*np.exp(-((x-s-.54)/.40)**2)
    h+=6.0*smooth(9,32,y)*bank
    h+=.45*field(x,y,scale=.22,octaves=2)*smooth(12,29,y)*bank
    return h


# Reuse only the divided-pinna topology from the supplied fern, not its old floor.
base.forest_floor=forest_floor
base.stream_center=stream_center


def riparian_bough(b, anchor, stream_x, mat, radius, phase):
    """A real attached limb with secondary shoots filling the stream light gap."""
    rng=b.rng;anchor=np.asarray(anchor,float)
    target=anchor+np.array([stream_x-anchor[0]+rng.uniform(-.75,.75),
                            rng.uniform(.8,2.7),rng.uniform(.42,.84)])
    t=np.linspace(0,1,18);path=anchor+(target-anchor)*t[:,None]
    path[:,2]+=.22*np.sin(t*np.pi)
    b.tube('Riparian_overhanging_boughs',path,np.linspace(radius*.28,.007,18),mat,18,True,phase)
    along=unit(target-anchor);crossing=unit(np.cross(along,[0,0,1]))
    for index in range(int(rng.integers(22,32))):
        q=rng.uniform(.14,.96);u=q*17;j=min(16,int(u));a=u-j
        origin=path[j]*(1-a)+path[j+1]*a
        sign=1 if index%2 else -1
        length=rng.uniform(.48,1.25)*(1-.32*q)
        tip=origin+crossing*sign*length+along*length*.29+np.array([0,0,rng.uniform(-.16,.27)])
        secondary=np.array([origin,(origin+tip)*.5+[0,0,rng.uniform(.05,.16)],tip])
        b.tube('Riparian_secondary_shoots',secondary,[.015,.007,.0014],mat,6)
        for twig_index in range(int(rng.integers(7,12))):
            tt=rng.uniform(.10,.96);ii=0 if tt<.5 else 1;f=tt*2-ii
            start=secondary[ii]*(1-f)+secondary[ii+1]*f
            turn=1 if twig_index%2 else -1
            direction=unit((tip-origin)*.5+along*turn*.55+[0,0,rng.uniform(-.3,.4)])
            twig_length=rng.uniform(.24,.49)
            end=start+direction*twig_length
            twig=np.array([start,(start+end)*.5+[0,0,rng.uniform(.015,.06)],end])
            b.tube('Riparian_attached_twigs',twig,[.003,.0016,.00045],mat,4)
            for leaf_index in range(int(rng.integers(9,16))):
                a=rng.uniform(.08,.98);ii=0 if a<.5 else 1;f=a*2-ii
                leafbase=twig[ii]*(1-f)+twig[ii+1]*f
                outward=unit(np.cross(direction,[0,0,1]))
                orient=unit(direction*.56+outward*(1 if leaf_index%2 else -1)*.85+[0,0,rng.uniform(-.15,.19)])
                L=rng.uniform(.065,.13)
                b.leaf('Riparian_laminae',leafbase,orient,L,L*rng.uniform(.45,.68),9,
                       rng.uniform(-.85,.85),rng.uniform(.025,.10))


def tree(b,x,y,height,radius,kind):
    rng=b.rng;z=float(forest_floor(x,y));origin=np.array([x,y,z]);phase=rng.uniform(0,7)
    count=80 if radius>.25 else 42;ts=np.linspace(0,1,count)
    lean=rng.uniform(-.6,.6,2)
    if kind=='leaning':lean=np.array([-np.sign(x)*height*.16,height*.025])
    if kind=='snag':height*=.63
    path=origin+np.c_[lean[0]*ts**1.4+.05*np.sin(ts*11+phase)*ts,
                     lean[1]*ts**1.2+.035*np.sin(ts*17+phase)*ts,height*ts]
    # A flared, nonuniform base and geometry-resolved bark ridges.
    rr=radius*(1-.87*ts)**.85*(1+.42*np.exp(-ts*21))
    mat=14 if kind=='birch' else 8
    b.tube('Trunks_'+kind,path,rr,mat,72 if radius>.20 else 32,True,phase)
    # Roots terminate in the real ground and arise inside the trunk volume.
    for k in range(int(rng.integers(5,10))):
        a=phase+k*2.39996;length=radius*rng.uniform(3.0,6.8);ss=np.linspace(0,1,18)
        xy=origin[:2]+np.c_[np.cos(a)*length*ss,np.sin(a)*length*ss]
        zz=np.array([forest_floor(px,py) for px,py in xy])+radius*.10+radius*.55*np.exp(-ss*4)
        root=np.c_[xy,zz];root[0]=origin+[0,0,radius*.42];root[-1,2]-=radius*.23
        b.tube('Exposed_embedded_roots',root,radius*.39*(1-ss)**1.6+.004,mat,12,True,phase)
    if kind=='snag':
        for _ in range(5):
            a=rng.uniform(0,2*np.pi);at=path[-1]+[np.cos(a)*radius*.15,np.sin(a)*radius*.15,0]
            b.tube('Splintered_crown',[at,at+[np.cos(a)*.03,np.sin(a)*.03,rng.uniform(.10,.38)]],[radius*.09,.001],12,5)
        return
    # Distinct branching statistics, not fixed counts per tree.
    nbranches=int(rng.integers(9,16) if kind=='birch' else rng.integers(12,24))
    for k in range(nbranches):
        frac=rng.uniform(.28,.88);basepos=path[int(frac*(count-1))]
        angle=phase+k*2.39996+rng.normal(0,.52)
        # Riparian crowns occupy the open light gap with attached, reaching limbs.
        lower_riparian=height<9.0 and abs(x-float(stream_center(y)))<4.6
        if lower_riparian and k%3!=0:
            angle=(0.0 if x<float(stream_center(y)) else np.pi)+rng.normal(0,.62)
        reach=height*rng.uniform(.13,.26)*(1-.45*frac)
        if kind=='oak':reach*=1.4
        if lower_riparian:reach*=1.32
        rise=reach*rng.uniform(.18,.92)
        direction=np.array([np.cos(angle),np.sin(angle),0])
        u=np.linspace(0,1,9);branch=basepos+direction*u[:,None]*reach
        branch[:,2]+=rise*u+.15*reach*np.sin(u*np.pi)
        br=radius*rng.uniform(.10,.24)*(1-u)**1.5+.004
        b.tube('Hierarchical_branches_'+kind,branch,br,mat,8,True,phase)
        for j in range(int(rng.integers(8,17))):
            t=rng.uniform(.25,.97);idx=min(7,int(t*8));f=t*8-idx
            at=branch[idx]*(1-f)+branch[idx+1]*f
            parent=branch[idx+1]-branch[idx]
            projection=branch[idx]+parent*np.dot(at-branch[idx],parent)/np.dot(parent,parent)
            b.attachment_errors.append(float(np.linalg.norm(at-projection)))
            theta=angle+rng.uniform(-1.45,1.45);L=reach*rng.uniform(.22,.55)
            tip=at+[np.cos(theta)*L,np.sin(theta)*L,rng.uniform(-.22,.85)*L]
            twig=np.array([at,(at+tip)*.5+[0,0,.055*L],tip])
            b.tube('Attached_secondary_twigs',twig,[.008,.0038,.0007],mat,5)
            for kk in range(int(rng.integers(30,47))):
                q=rng.uniform(.12,.98);ii=0 if q<.5 else 1;f=q*2-ii
                leafbase=twig[ii]*(1-f)+twig[ii+1]*f
                alternate=1 if kk%2 else -1
                dire=unit(tip-at)+np.array([np.cos(theta+alternate*1.32),np.sin(theta+alternate*1.32),rng.uniform(-.35,.3)])
                length=rng.uniform(.060,.115) if kind=='birch' else rng.uniform(.095,.175)
                width=length*rng.uniform(.44,.70)
                # A short connected petiole makes leaf attachment visible nearby.
                petiole=unit(dire)*length*.13
                if abs(leafbase[0])<6 and leafbase[1]<17 and leafbase[2]<6:
                    b.tube('Leaf_petioles',[leafbase,leafbase+petiole],[.0007,.0004],mat,4)
                else:
                    # Subpixel petioles are omitted; the lamina remains attached
                    # directly to the actual twig rather than floating at an offset.
                    petiole=np.zeros(3)
                b.leaf('Living_canopy',leafbase+petiole,dire,length,width,9,rng.uniform(-1.3,1.3),rng.uniform(.06,.20))

    if abs(x-float(stream_center(y)))<5.2 and -3.2<y<17.5:
        for extra in range(2):
            fraction=min(.62,(2.35+extra*.55)/height)
            q=fraction*(len(path)-1);index=min(len(path)-2,int(q));f=q-index
            anchor=path[index]*(1-f)+path[index+1]*f
            riparian_bough(b,anchor,float(stream_center(y+1.7)),mat,radius,phase+extra)


def fern(b,x,y,size):
    # Age, damage and frond number differ per cluster; all pinnae remain explicit.
    rng=b.rng;origin=np.array([x,y,float(forest_floor(x,y))+.008]);count=int(rng.integers(5,12))
    for k in range(count):
        a=rng.uniform(0,2*np.pi);d=np.array([np.cos(a),np.sin(a),0]);side=np.array([-d[1],d[0],0])
        L=size*rng.uniform(.55,1.18);rise=rng.uniform(.47,.85);fall=rng.uniform(.27,.52)
        ts=np.linspace(0,1,23);path=origin+ts[:,None]*L*d+np.c_[np.zeros(23),np.zeros(23),(rise*ts-fall*ts**2)*L]
        mat=13 if rng.uniform()<.09 else 9
        b.tube('Fern_rachis',path,np.linspace(.0026,.00032,23)*size,mat,5)
        for t in np.linspace(.13,.97,int(rng.integers(16,25))):
            if rng.uniform()<.035:continue
            center=origin+d*t*L+[0,0,(rise*t-fall*t*t)*L]
            reach=L*.22*np.sin(t*np.pi)**.75
            for sign in [-1,1]:
                end=center+side*sign*reach+d*reach*.30+[0,0,rng.uniform(-.02,.03)*L]
                b.tube('Fern_pinna_stems',[center,end],[.00085*size,.00015],mat,4)
                fd=unit(end-center)
                for q in np.linspace(.13,.94,7):
                    for ss in [-1,1]:
                        ll=reach*.28*(1-.57*q)
                        b.leaf('Divided_fern_pinnules',center+(end-center)*q,fd*.43+d*ss*.73+[0,0,.10],ll,ll*.40,mat,rng.uniform(-.32,.32),.06)
    if rng.uniform()<.5:
        # A young unfurling frond with curved, attached geometry.
        a=rng.uniform(0,2*np.pi);t=np.linspace(0,1,28)
        path=origin+np.c_[.08*size*np.cos(a)*(1-np.cos(t*4)),.08*size*np.sin(a)*(1-np.cos(t*4)),.35*size*t]
        b.tube('Young_fiddleheads',path,np.linspace(.004,.0013,28)*size,9,6)


def moss_boulder(b,x,y,r):
    rng=b.rng;v,f=fracture_block(int(rng.integers(1,2**30)),(r,r*.78,r*.49),'block',4)
    v+=np.array([x,y,float(forest_floor(x,y))-v[:,2].min()-r*.30]);b.add('Fractured_mossy_stream_boulders',v,f,mat=2)
    normals=vertex_normals(v,f)
    for _ in range(int(52000*r*r)):
        idx=int(rng.integers(len(v)));p=v[idx];n=normals[idx]
        if n[2]<.26 or p[2]<.08:continue
        mask=float(n3(p[0]*4,p[1]*4,p[2]*4))
        if mask<-.15 or rng.uniform()>.80:continue
        h=rng.uniform(.004,.016)
        b.tube('Moss_microshoots',[p,p+n*h],[.0014,.0003],10,4)


def forest(out,seed,glb=True):
    b=Builder('forest',seed);rng=b.rng
    xx,yy=np.meshgrid(np.linspace(-23,23,1000),np.linspace(-14,70,1450))
    zz=granular_ground(xx,yy,forest_floor(xx,yy),.015)
    b.surface('Rooted_forest_soil_and_streambed',np.stack([xx,yy,zz],-1),0)
    # Bank deposits and collapse clusters erase the smooth paired bank silhouette.
    for _ in range(5400):
        y=rng.uniform(-9,33);side=rng.choice([-1,1]);x=float(stream_center(y))+side*rng.uniform(.80,3.4)
        r=np.exp(rng.uniform(np.log(.018),np.log(.16)))
        mat=2 if abs(x-stream_center(y))<1.7 else 0
        embed(b,forest_floor,x,y,(r,r*.85,r*.6),'rounded',mat,'Bank_collapse_and_alluvium',1 if r<.07 else 2,.34)
    for x,y,r in [(-1.38,-3.3,.45),(1.95,-.7,.39),(-1.5,4.4,.48),(2.3,7.,.53),(-2.4,10.4,.60),(.5,13.2,.29),(2.6,-4.3,.34)]:
        moss_boulder(b,x,y,r)
    # Dense understory and several distinct tree families: no empty bright horizon.
    sites=[(-2.9,1.8,7.4,.23,'oak'),(3.1,4.7,7.9,.22,'oak'),(-3.6,8.8,8.1,.24,'leaning'),(3.0,11.8,8.0,.21,'oak'),(-3.2,-2.1,10.9,.42,'oak'),(3.9,-.4,12.6,.44,'leaning'),(-4.7,5.5,13.,.37,'oak'),
           (4.5,8.,12.,.32,'birch'),(-3.0,13,10.8,.30,'leaning'),(6.7,2.8,14.1,.31,'birch'),
           (-7.2,-.8,12.,.44,'oak'),(2.8,16.,10.6,.22,'birch'),(-6.2,10.,8.5,.26,'snag')]
    for _ in range(30):
        y=rng.uniform(3,59);x=rng.uniform(-18,18)
        if abs(x-stream_center(y))<2.6:continue
        if any((x-s[0])**2+(y-s[1])**2<1.5 for s in sites):continue
        kind=rng.choice(['oak','birch','leaning','snag'],p=[.45,.32,.18,.05]);h=rng.uniform(9,16.5)
        sites.append((x,y,h,rng.uniform(.16,.34),kind))
    # Lower canopy fills the stream corridor with actual branches and leaves.
    # Its alternating positions are clustered around the winding banks, not a wall.
    for yy in [12.5,16.8,21.3,25.1,29.7,34.4,39.8]:
        for side in [-1,1]:
            xx=float(stream_center(yy))+side*rng.uniform(2.7,4.2)
            sites.append((xx,yy+rng.uniform(-.7,.7),rng.uniform(5.5,8.0),rng.uniform(.10,.17),'oak'))
    for x,y,h,r,k in sites:tree(b,x,y,h,r,k)
    # Fallen log has longitudinal curvature, a jagged end, exposed pale wood,
    # and broken attached side branches. It sits partly on the banks.
    start=np.array([-3.4,5.8,float(forest_floor(-3.4,5.8))+.16]);end=np.array([2.7,8.2,float(forest_floor(2.7,8.2))+.14]);t=np.linspace(0,1,65)
    path=start+(end-start)*t[:,None];path[:,2]-=.17*np.sin(np.pi*t)
    b.tube('Fallen_decaying_log',path,.21*(1-.15*t),8,52,True,2.9)
    tangent=unit(end-start);tt=unit(np.cross(tangent,[0,0,1]));uu=np.cross(tangent,tt)
    aa=np.arange(96)*2*np.pi/96;rad=.175*(1+.035*np.sin(aa*13))
    rim=end+tangent*.006+(tt*np.cos(aa)[:,None]+uu*np.sin(aa)[:,None])*rad[:,None]
    vv=np.vstack([end+tangent*.008,rim]);ff=np.array([(0,j+1,(j+1)%96+1) for j in range(96)])
    b.add('Log_exposed_heartwood',vv,ff,mat=12)
    for _ in range(9):
        q=rng.uniform(.13,.85);idx=int(q*64);at=path[idx];a=rng.uniform(0,2*np.pi)
        tip=at+np.array([np.cos(a)*.6,np.sin(a)*.6,rng.uniform(.18,.5)])
        b.tube('Log_broken_branches',[at,(at+tip)*.5+[0,0,.07],tip],[.045,.025,.008],8,9,True,a)
    # Sample the actual constructed height grid, not a different analytic height
    # below its microrelief. Leaf bases sit 3 mm above that bilinear surface, and
    # their long axes and roll follow its local tangent plane.
    candidates=200000
    lx=rng.uniform(-8,8,candidates);ly=rng.uniform(-10,28,candidates)
    coords=np.vstack([(ly+14)/84*(zz.shape[0]-1),(lx+23)/46*(zz.shape[1]-1)])
    lz=map_coordinates(zz,coords,order=1,mode='nearest',prefilter=False)
    dy,dx=np.gradient(zz,84/(zz.shape[0]-1),46/(zz.shape[1]-1))
    gx=map_coordinates(dx,coords,order=1,mode='nearest',prefilter=False)
    gy=map_coordinates(dy,coords,order=1,mode='nearest',prefilter=False)
    keep=(np.abs(lx-stream_center(ly))>1.05)&(lz>.045)
    keep&=rng.uniform(size=candidates)<(.65+.3*n3(lx*.6,ly*.5))
    lx,ly,lz,gx,gy=[v[keep] for v in [lx,ly,lz,gx,gy]]
    for x,y,z,sx,sy in zip(lx,ly,lz,gx,gy):
        a=rng.uniform(0,2*np.pi);L=rng.uniform(.035,.105)
        direction=unit([np.cos(a),np.sin(a),sx*np.cos(a)+sy*np.sin(a)])
        tangent_side=unit(np.cross([0,0,1],direction));normal0=np.cross(direction,tangent_side)
        terrain_normal=unit([-sx,-sy,1.0])
        align_roll=np.arctan2(-np.dot(tangent_side,terrain_normal),np.dot(normal0,terrain_normal))
        pos=np.array([x,y,z+.003])
        b.leaf('Layered_leaf_litter',pos,direction,L,L*rng.uniform(.50,.83),11,
               align_roll+rng.uniform(-.13,.13),rng.uniform(.035,.14))
    del coords,dx,dy,lx,ly,lz,gx,gy,keep
    for _ in range(310):
        x=rng.uniform(-7,7);y=rng.uniform(-9,27)
        if abs(x-stream_center(y))<1.5:continue
        at=np.array([x,y,float(forest_floor(x,y))+.02]);a=rng.uniform(0,2*np.pi);L=rng.uniform(.12,.95)
        end=at+[np.cos(a)*L,np.sin(a)*L,.03]
        b.tube('Forest_floor_branch_detritus',[at,(at+end)*.5+[0,0,.05],end],[.013,.008,.002],8,5,True,a)
    # Smaller ferns form ecologically clustered groups instead of identical icons.
    ferns=[(-1.85,-1.3,1.15),(1.95,.2,1.25),(-2.05,3.4,.9),(2.2,-2.7,1.0),(-2.1,-4.5,1.05),(2.3,-3.6,1.10),(-2.7,-1.8,.85),(2.7,1.1,.95),(-2.2,3.,.75),(-3.4,6.7,.9),(3.1,6,.85)]
    for _ in range(33):
        y=rng.uniform(-1,29);side=rng.choice([-1,1]);x=float(stream_center(y))+side*rng.uniform(1.8,5.5)
        ferns.append((x,y,rng.uniform(.40,.88)))
    ferns.extend([(-1.7,.9,1.05),(2.10,2.4,1.2),(-1.2,4.0,.95),
                  (2.5,5.8,1.15),(-2.0,7.3,1.0),(1.85,-.5,1.05)])
    for x,y,s in ferns:fern(b,x,y,s)
    # Low broadleaf understory occludes gaps between trunk stems.
    for _ in range(1050):
        y=rng.uniform(-3,47);x=rng.uniform(-15,15)
        if abs(x-stream_center(y))<1.8:continue
        origin=np.array([x,y,float(forest_floor(x,y))]);h=rng.uniform(.65,2.50)
        for k in range(int(rng.integers(4,9))):
            a=rng.uniform(0,2*np.pi);end=origin+[np.cos(a)*h*.4,np.sin(a)*h*.4,h]
            b.tube('Understory_stems',[origin,end],[.006,.001],8,5)
            for j in range(18):
                q=rng.uniform(.18,.96);at=origin+(end-origin)*q
                d=np.array([np.cos(a+j*2),np.sin(a+j*2),rng.uniform(-.18,.36)])
                ll=rng.uniform(.075,.18)
                side_tip=at+unit(d)*ll*.20
                b.tube('Understory_attached_petioles',[at,side_tip],[.0012,.0004],8,4)
                b.leaf('Understory_leaves',side_tip,d,ll,ll*.63,9,rng.uniform(-.7,.7))
    Water('forest').add(b,np.linspace(-18,18,750),np.linspace(-15,71,1250),bottom=-3.)
    cfg={'scene':'forest','title':'Fernwater — Rooted Banks & Mixed Woodland',
         'camera':[.25,-5.70,1.05],'target':[-.35,6.7,.42],'fov':67,
         'sun':[-.36,.53,.768],'exposure':2.55,'white_balance':6100,
         'sun_scale':1.15,'sky_scale':.84,'water_absorption':1.20}
    return b.finish(out,cfg,glb)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene',choices=['canyon','coast','forest','all'],default='all')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=20260916)
    p.add_argument('--no-glb',action='store_true');p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args();base.prepare_waves()
    if a.prepare_only:return
    for i,name in enumerate(['canyon','coast','forest']):
        if a.scene not in ['all',name]:continue
        start=time.monotonic();globals()[name](a.out/name,a.seed+i*1000,not a.no_glb)
        print(f'NEW_BUILD_COMPLETED {name} {time.monotonic()-start:.2f}s',flush=True)

if __name__=='__main__':main()
