"""V10 coherent mineral banks, fault-block terrain and fractured outcrop geometry.

Metres throughout. The geology is authored and eroded numerically, not a survey.
No generated images or photographic replacement of the scene is used.
"""
from __future__ import annotations
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial import ConvexHull
from numba import njit
from build_scene_v4 import noise, fbm, mesh_normals, erode
from v9_landforms import smooth, cellular_gap, connected_shrub as inherited_shrub

POOLS=[(.5,1.,4.1,4.05,.055,1.48),(-3.5,10.,2.2,1.65,.245,.73)]
RIPPLE_SCALE=1.0

def poolq(x,y,i):
    cx,cy,rx,ry,level,depth=POOLS[i]
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    dx=(x-cx)/rx;dy=(y-cy)/ry;a=np.arctan2(dy,dx)
    edge=1+.13*np.sin(3*a+.55)+.065*np.sin(2*a-1.3)+.044*np.sin(7*a+.9*i)
    edge+=.10*noise(x*.55,y*.55)+.030*noise(x*2.7,y*2.7)
    q=np.sqrt(dx*dx+dy*dy)/edge
    if i==0:
        # A partly collapsed near-right shelf intrudes into the vent bowl.
        q+=.18*np.exp(-((x-3.0)/1.3)**2-((y+.55)/1.0)**2)
    return q


def connected_shrub(rng,base,h,lod,stem):
    # A second crown architecture: compact, silvery foliar tips on open wood.
    # The previous branch network is retained but shorter and less fan-like.
    wood,leaves=inherited_shrub(rng,base,h*.73,lod,stem)
    skew=rng.uniform(-.09,.09,2)
    ratio=rng.uniform(.77,1.08)
    transform=np.array([[ratio,0,skew[0]],[0,.82/ratio,skew[1]],[0,0,1.16]])
    result=[]
    for group in (wood,leaves):
        new=[]
        for v,f,n in group:
            vv=(v-base)@transform.T+base
            nn=n@np.linalg.inv(transform);nn/=np.maximum(np.linalg.norm(nn,axis=1)[:,None],1e-15)
            new.append((vv,f,nn))
        result.append(new)
    return result[0],result[1]


def height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    h=.22+.0015*y+.063*fbm(x*.28,y*.28,6)+.016*fbm(x*1.95,y*1.95,5)
    # Low, uneven alluvial rises interrupt the old flat 'infinite sandbox'.
    h+=.44*np.exp(-((x+10)/5.8)**2-((y-27)/15)**2)
    h+=.78*np.exp(-((x-12)/7.6)**2-((y-44)/16)**2)
    for i,(_,_,rx,ry,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i); d=(q-1)*rx; qi=np.minimum(q,1)
        # A submerged sediment shelf surrounds a deeper vent, not one uniform bowl.
        bed=level+.018-.35*np.maximum(1-qi**3.8,0)**1.2
        bed-=depth*.77*(1-smooth(.35,.79,qi))
        bed+=(.045*fbm(x*1.93+12,y*1.75-4,5)+.013*fbm(x*9.7,y*9.7,4))*(1-smooth(.85,1.,q))
        pos=np.maximum(d,0)
        bank=level+.018+.145*(1-np.exp(-pos*2.4))
        patch=smooth(-.23,.30,fbm(x*.73+8,y*.69+4,4))
        # Multiple eroded thin accretion treads, not an extruded uniform rim.
        # Displacements are centimetres and remain connected to the substrate.
        warp=.075*fbm(x*2.0+12,y*1.8,5)
        rim=.046*np.exp(-((d-.075-warp)/.095)**2)*(.12+.88*patch)
        rim+=.018*np.exp(-((d-.24-warp)/.061)**2)*patch
        rim+=.011*np.exp(-((d-.39-warp)/.045)**2)*patch
        # Carbonate cauliflower microrelief; separate frequencies for soil.
        pore=.0032*fbm(x*19.3,y*19.3,5)+.0012*noise(x*56,y*56)
        shore=np.exp(-((q-1.06)/.27)**2)
        desired=np.where(q<1,bed,bank)+shore*(pore+rim)
        blend=1-smooth(1.36,1.90,q);h=h*(1-blend)+desired*blend
    q=poolq(x,y,0)
    near=np.exp(-((x-.5)/18)**6-((y-1)/21)**6)
    # Distinct low-relief desiccation polygons on dry upper banks.
    cracked=smooth(1.08,1.25,q)*(1-smooth(1.9,2.1,q))*smooth(-.2,.18,noise(x*.53,y*.61))
    gap=cellular_gap(x*2.3+.19*noise(x*1.7,y*1.7),y*2.3+.19*noise(x*1.7+8,y*1.7))
    h-=near*cracked*.014*np.exp(-(gap/.054)**2)
    # Runoff trough from the right-hand shore, with subsidiary fine channels.
    line=x-(3.28+.27*np.sin(y*.94)+.13*noise(y*3.7,np.zeros_like(y)))
    drain=np.exp(-(line/.28)**2)*np.exp(-((y+1.65)/2.8)**4)
    h-=.046*drain
    h+=near*(.0026*fbm(x*13.7,y*13.7,5)+.00085*noise(x*71,y*71))
    return h


def rock_template(seed,sub):
    """Half-space fractured stones with scale-local chipped, not lumpy surfaces."""
    if sub>=5:
        from implicit_rocks_v10 import implicit_rock
        return implicit_rock(seed,112)
    rng=np.random.default_rng(seed)
    # A directional radial mesh still permits a closed, simple solid, while the
    # actual surface is the intersection of unequal joint halfspaces.
    mesh=trimesh.creation.icosphere(subdivisions=sub)
    d=mesh.vertices.copy();f=mesh.faces.copy()
    ns=rng.normal(size=(14,3));ns/=np.linalg.norm(ns,axis=1)[:,None]
    ns=np.vstack([ns,np.eye(3),-np.eye(3)])
    ds=rng.uniform(.46,1.06,len(ns))
    den=d@ns.T
    radii=np.divide(ds,den,out=np.full_like(den,1e7),where=den>1e-6)
    r=np.min(radii,axis=1)
    # Only 1% edge rounding; the old smooth-min rounded every face alike.
    r=.99*r+.01*np.median(r)
    v=d*r[:,None]
    s=rng.uniform(-200,200,3);p=v+s
    # Alter broad joint planes and local edge breakage, no continuous dark cuts.
    corr=.023*noise(p[:,0]*7.3,p[:,1]*5.9,p[:,2]*8.1)
    corr+=.011*noise(p[:,0]*21.4,p[:,1]*19.1,p[:,2]*17.2)
    corr+=.004*noise(p[:,0]*73,p[:,1]*64,p[:,2]*57)
    corr-=.020*np.maximum(noise(p[:,0]*12,p[:,1]*12,p[:,2]*12)-.35,0)
    v+=d*corr[:,None]
    v[:,2]+=.018*np.sin(v[:,0]*19+v[:,1]*8+seed)*noise(p[:,0]*17,p[:,1]*17,p[:,2]*17)
    return v,f,mesh_normals(v,f)


def ridged(x,y,seed,octaves=8):
    total=np.zeros_like(x);amp=1.;weight=np.ones_like(x)
    for k in range(octaves):
        r=(1-np.abs(noise(x,y,seed+k*.371)))**2
        total+=amp*r*weight
        weight=np.clip(r*1.38,0,1)
        x,y=(.82*x-.57*y)*2.03+13.1,(.57*x+.82*y)*2.03-31.7
        amp*=.48
    return total


def landscape_ridges(xs,ys,seed):
    """Unequal overlapping mountain ranges with slope-dependent erosion."""
    x,y=np.meshgrid(xs,ys)
    n=fbm(x*.00065,y*.00052,5)
    spine=3400+420*noise(x*.00055,np.zeros_like(x)+19)+160*np.sin(x*.0012)
    peak=430+280*np.exp(-((x+1700)/1600)**2)+340*np.exp(-((x-2400)/1100)**2)
    env=np.exp(-np.abs((y-spine)/1100)**1.7)
    nx=x+110*fbm(x*.0010,y*.00085,4)
    # Drainage structure is much larger than individual exposed-rock facets.
    # The rejected prototype gave 260 m cells the prominence of 800 m peaks.
    r=ridged(nx*.00124,y*.00113,3.71,7)
    r-=np.mean(r)
    base=(peak*env+82*r*env**.88)*smooth(300,950,y)
    # Offset overlapping watersheds. Facets have non-uniform talus-covered bases.
    tributary=fbm(nx*.0036,y*.0032,5)
    base+=29*tributary*env
    back=730+460*np.exp(-((x+4000)/2200)**2)+500*np.exp(-((x-450)/2600)**2)
    e2=np.exp(-np.abs((y-7700-330*noise(x*.00045,42))/1700)**1.7)
    base=np.maximum(base,back*e2+61*(ridged(x*.0012-4,y*.0014,17.,6)-1.0)*e2)
    spacing=float(xs[1]-xs[0])
    evolved=erode((base/spacing).astype(float),480000,seed+271)*spacing
    z=.26*base+.74*evolved
    z=gaussian_filter(z,.80)
    grad_y,grad_x=np.gradient(z,float(ys[1]-ys[0]),spacing)
    steep=smooth(.12,.48,np.hypot(grad_x,grad_y))
    z+=steep*(4.3*fbm(x*.031,y*.028,5)+1.25*noise(x*.089,y*.087))
    z=np.maximum(z,0)+.20+.0015*y
    fade=smooth(149.9,680,y)
    return height(x,y)*(1-fade)+z*fade
