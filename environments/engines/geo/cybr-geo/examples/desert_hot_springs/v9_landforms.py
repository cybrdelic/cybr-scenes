"""Authored geothermal landforms, fracture surfaces, and branching dry scrub.

Geometry, including the mineral shore, is in metres.  This is not a site survey
or a geochemical, hydrodynamic, or botanical simulation.  No generative images.
"""
from __future__ import annotations
import numpy as np
import trimesh
from numba import vectorize, float64
from scipy.ndimage import gaussian_filter
from build_scene_v4 import noise, fbm, mesh_normals, erode
from v8_landforms import poolq, smooth

POOLS=[(.5,1.,4.1,3.2,.055,2.15),(-3.5,10.,2.2,1.65,.245,.92)]
RIPPLE_SCALE=.22

@vectorize([float64(float64,float64)], nopython=True,cache=True)
def cellular_gap(x,y):
    ix=int(np.floor(x));iy=int(np.floor(y));d1=1.e10;d2=1.e10
    for a in range(-1,2):
        for b in range(-1,2):
            h=np.uint32(np.uint32(ix+a)*np.uint32(374761393)+np.uint32(iy+b)*np.uint32(668265263)+np.uint32(1274126177))
            h=np.uint32(np.uint32(h^(h>>np.uint32(13)))*np.uint32(1274126177));h=np.uint32(h^(h>>np.uint32(16)))
            j=np.uint32(np.uint32(h)*np.uint32(1664525)+np.uint32(1013904223))
            xx=ix+a+.18+.64*float(h)/4294967295.;yy=iy+b+.18+.64*float(j)/4294967295.
            ds=(xx-x)**2+(yy-y)**2
            if ds<d1:d2=d1;d1=ds
            elif ds<d2:d2=ds
    return np.sqrt(d2)-np.sqrt(d1)

def height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    h=.21+.0015*y+.052*fbm(x*.18,y*.18,6)+.006*fbm(x*2.3,y*2.3,4)
    for i,(_,_,rx,ry,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i);d=(q-1)*rx;qi=np.minimum(q,1)
        # A deeper vent, smoothly rising through carbonate shoals.  The pale
        # substrate and absorption, rather than an emissive tint, color the water.
        bed=level+.016-depth*np.maximum(1-qi**3.6,0)**1.68
        bed+=(.085*fbm(x*.83+12,y*.75-4,5)+.007*fbm(x*5.7,y*5.7,4))*(1-smooth(.80,1.,q))
        pos=np.maximum(d,0)
        bank=level+.016+.125*(1-np.exp(-pos*pos/(pos+.045)*2.1))
        patch=smooth(-.25,.42,fbm(x*.93+4,y*.86-2,4))
        # Unequal shallow treads along a broken carbonate shore, in centimetres.
        rim=.049*np.exp(-((d-.075-.06*noise(x*4,y*4))/.105)**2)*(0.12+.88*patch)
        rim+=.029*np.exp(-((d-.31-.09*noise(x*2.9,y*2.9))/.12)**2)*patch
        rim+=.014*np.exp(-((d-.56-.13*noise(x*1.8,y*1.8))/.085)**2)*patch
        pores=.0037*fbm(x*23.4,y*23.4,4)+.002*noise(x*67,y*67)
        sediments=.008*fbm(x*4.1,y*4.1,5)+pores
        shore=np.exp(-((q-1.07)/.27)**2)
        desired=np.where(q<1,bed,bank)+shore*(sediments+rim)
        blend=1-smooth(1.42,1.93,q);h=h*(1-blend)+desired*blend
    q=poolq(x,y,0)
    near=np.exp(-((x-.5)/15)**6-((y-1)/17)**6)
    cracked=smooth(1.07,1.25,q)*(1-smooth(1.8,2.1,q))*smooth(-.15,.22,noise(x*.72,y*.72))
    gap=cellular_gap(x*6.3+.25*noise(x*3,y*3),y*6.3+.25*noise(x*3+8,y*3))
    h-=near*cracked*.004*np.exp(-(gap/.038)**2)
    # Small runoff rills occupy the lowest side of the spring, not a universal ring.
    line=x-(3.28+.27*np.sin(y*.94)+.13*noise(y*3.7,np.zeros_like(y)))
    drain=np.exp(-(line/.28)**2)*np.exp(-((y+1.65)/2.8)**4)
    h-=.039*drain
    return h+near*(.0022*fbm(x*22.7,y*22.7,4)+.0006*noise(x*87,y*87))

def rock_template(seed,sub):
    """Independently fractured angular clasts, with weathered faces, no ring cuts.

    A soft intersection of halfspaces defines the large form. Surface relief
    follows its local face normal; broad grooves are not engraved into boulders.
    """
    rng=np.random.default_rng(seed);mesh=trimesh.creation.icosphere(subdivisions=sub)
    d=mesh.vertices.copy();f=mesh.faces.copy()
    ns=np.vstack((np.eye(3),-np.eye(3),rng.normal(size=(11,3))))
    ns[:6]+=rng.normal(0,.21,(6,3));ns/=np.linalg.norm(ns,axis=1)[:,None]
    ds=rng.uniform(.56,1.02,len(ns));den=d@ns.T
    radii=np.divide(ds,den,out=np.full_like(den,1e6),where=den>1e-7)
    nearest=np.min(radii,axis=1)
    weights=np.exp(-(radii-nearest[:,None])*34)
    rr=nearest-np.log(weights.sum(axis=1))/34
    rr=rr*.96+(.82+.10*noise(d[:,0]*2+seed*.3,d[:,1]*2,d[:,2]*2))*.04
    v=d*rr[:,None]
    surf=weights@ns;surf/=np.linalg.norm(surf,axis=1)[:,None]
    p=v+np.array([rng.uniform(-80,80),rng.uniform(-80,80),rng.uniform(-80,80)])
    # Directional sedimentary laminations form relief, not dark equator bands.
    warp=noise(p[:,0]*3.7,p[:,1]*3.7,p[:,2]*3.7)
    relief=.037*noise(p[:,0]*5.7+warp,p[:,1]*6.2,p[:,2]*8.9)
    relief+=.016*noise(p[:,0]*17.3,p[:,1]*14.6,p[:,2]*32.3)
    relief+=.006*noise(p[:,0]*48.1,p[:,1]*51.7,p[:,2]*61.3)
    relief-=.012*np.maximum(noise(p[:,0]*22,p[:,1]*22,p[:,2]*22)-.18,0)
    # An eroded edge nick is localized in three dimensions, never a full groove.
    if sub>=3:
        centre=rng.uniform(-.55,.55,3)
        r=np.linalg.norm(v-centre,axis=1)
        relief-=.070*np.exp(-(r/.24)**4)
    v+=surf*relief[:,None]
    return v,f,mesh_normals(v,f)

def ridge_noise(x,y,octaves=7):
    out=np.zeros_like(x);amp=1.;weight=np.ones_like(x)
    for k in range(octaves):
        raw=noise(x,y,k*.763)
        ridge=(1-np.abs(raw))**2
        out+=amp*ridge*weight
        weight=np.clip(ridge*1.4,0,1)
        x,y=(.7986*x-.6018*y)*2.07+17.4,(.6018*x+.7986*y)*2.07-9.6
        amp*=.48
    return out

def landscape_ridges(xs,ys,seed):
    """Broad fault-block massing, drainage erosion, and slope-limited talus.

    The earlier preview's high-frequency ridged-noise peaks are deliberately
    rejected. Erosion is constrained not to turn the ridge into needle towers.
    This is an authored landform, not a reconstruction of a particular mountain.
    """
    x,y=np.meshgrid(xs,ys)
    spine=4900+290*fbm(x*.00065,np.zeros_like(x)+3.7,5)+130*np.sin(x*.00045)
    peak=560+370*np.exp(-((x+2200)/1600)**2)+690*np.exp(-((x-2850)/2250)**2)
    peak+=45*fbm(x*.00072,np.zeros_like(x)+21,5)
    dy=y-spine
    env=np.exp(-np.abs(dy/np.where(dy<0,1830.,2630.))**1.55)
    # Unequal tributary shoulders; amplitude falls with their spatial scale.
    nx=x+180*fbm(x*.00091,y*.00087,4)
    relief=70*fbm(nx*.0020+7,y*.0012,6)+26*fbm(nx*.0051-4,y*.0033,5)
    relief+=10*fbm(nx*.013,y*.009,4)
    base=(peak*env+relief*env**.72)*smooth(390,1150,y)
    spacing=float(xs[1]-xs[0])
    eroded=erode((base/spacing).astype(float),1050000,seed+947)*spacing
    z=gaussian_filter(.40*base+.60*eroded,.7)
    from fluvial_detail_v9 import incise
    z=gaussian_filter(incise(z,spacing,float(ys[1]-ys[0]),passes=5),.45)
    # Conservative talus relaxation: excess above a 37-degree diagonal slope
    # is shared with its downslope neighbour, without inflating isolated peaks.
    sy=float(ys[1]-ys[0]);limit=np.tan(np.deg2rad(37))
    for _ in range(18):
        delta=np.zeros_like(z)
        for axis,step in [(0,sy),(1,spacing)]:
            diff=np.diff(z,axis=axis)
            flux=np.sign(diff)*np.maximum(np.abs(diff)-limit*step,0)*.13
            if axis==0:delta[:-1]+=flux;delta[1:]-=flux
            else:delta[:,:-1]+=flux;delta[:,1:]-=flux
        z+=delta
    exposed=smooth(35,170,z)
    z+=exposed*(.80*noise(x*.072,y*.057)+.22*noise(x*.19,y*.17))
    z+=.20+.0015*y
    fade=smooth(149.9,650,y)
    return height(x,y)*(1-fade)+z*fade

def connected_shrub(rng,base,h,lod,stem):
    """Connected asymmetric scrub crowns with curved wood and attached leaves."""
    wood=[];leaf_v=[];leaf_f=[];off=0
    wind=np.r_[rng.normal(0,.16,2),0.]*h
    crown=np.array([rng.uniform(.7,1.3),rng.uniform(.65,1.0),rng.uniform(.45,.8)])
    main=int(rng.integers(7,12)) if lod==0 else int(rng.integers(5,8))
    def branch_curve(a,b,r):
        pts=[]
        bend=rng.normal(0,.075,3)*h;bend[2]+=h*.03
        for t in np.linspace(0,1,5 if lod==0 else 3):
            pts.append(a*(1-t)+b*t+bend*np.sin(t*np.pi))
        for j in range(len(pts)-1):wood.append(stem(pts[j],pts[j+1],r*(1-.75*j/(len(pts)-1))))
        return pts
    def emit_leaf(attach,axis,length):
        nonlocal off
        direction=axis+rng.normal(0,.65,3);direction/=np.linalg.norm(direction)
        transverse=np.cross(direction,rng.normal(size=3));transverse/=max(np.linalg.norm(transverse),1e-12)
        width=length*rng.uniform(.17,.31)
        middle=attach+direction*length*.47
        v=np.vstack((attach,middle+transverse*width,attach+direction*length,middle-transverse*width,middle+np.cross(direction,transverse)*length*.085))
        f=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])+off
        leaf_v.append(v);leaf_f.append(f);off+=5
    for j in range(main):
        az=rng.uniform(0,2*np.pi)
        root=base+np.r_[rng.normal(0,.025*h,2),0]
        endpoint=base+np.array([np.cos(az),np.sin(az),rng.uniform(.50,1.15)])*crown*h+wind
        primary=branch_curve(root,endpoint,.006*h)
        for k in range(8 if lod==0 else 4):
            index=int(rng.integers(1,len(primary)-1));t=rng.uniform(.05,.95)
            attach=primary[index]*(1-t)+primary[index+1]*t
            phi=az+rng.uniform(-1.7,1.7)
            end=attach+np.array([np.cos(phi),np.sin(phi),rng.uniform(-.35,.75)])*h*rng.uniform(.15,.35)
            twig=branch_curve(attach,end,.0019*h)
            for jj in range(len(twig)-1):
                axis=twig[jj+1]-twig[jj];axis/=np.linalg.norm(axis)
                count=7 if lod==0 else 4
                for n in range(count):
                    u=(n+rng.uniform(.05,.95))/count
                    a=twig[jj]*(1-u)+twig[jj+1]*u
                    # Leaves retain species-scale dimensions as the plant grows.
                    length=np.clip(h*.050,.016,.034)*rng.uniform(.66,1.32)
                    emit_leaf(a,axis,length)
                    if rng.random()<.82:emit_leaf(a,axis,length*.85)
            if lod==0:
                for kk in [1,2,3]:
                    a=twig[kk]
                    phi2=phi+rng.uniform(-2.5,2.5)
                    b=a+np.array([np.cos(phi2),np.sin(phi2),rng.uniform(-.1,.85)])*h*rng.uniform(.08,.19)
                    wood.append(stem(a,b,.0007*h));ax=b-a;ax/=np.linalg.norm(ax)
                    for n in range(9):
                        u=(n+.3)/9;a2=a*(1-u)+b*u
                        for side in range(2):emit_leaf(a2,ax,np.clip(h*.052,.015,.031)*rng.uniform(.65,1.3))
    v=np.concatenate(leaf_v);f=np.concatenate(leaf_f)
    return wood,[(v,f,mesh_normals(v,f))]
