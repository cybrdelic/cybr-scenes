"""Scale-separated authored terrain and physically tessellated rock damage.

This is authored geometry, not a terrain scan or a calibrated erosion model.
Coordinates are metres; CYBR GEO serializes millimetres at its existing boundary.
"""
from __future__ import annotations
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter, map_coordinates
from build_scene_v4 import noise, fbm, mesh_normals, erode
from v10_landforms import poolq, POOLS, RIPPLE_SCALE
from v9_landforms import smooth, cellular_gap
from fluvial_detail_v9 import drainage
from pathlib import Path

HERE=Path(__file__).parent
MICRO=np.load(HERE/'assets'/'granular_relief.npy')

def micro_height(x,y):
    # A reconstructed granular support field derived from the supplied CC0
    # gravel photograph. NOT measured displacement; relief scale is authored.
    u=(x*.917+y*.399)/.68*MICRO.shape[1]
    v=(y*.917-x*.399)/.68*MICRO.shape[0]
    shape=np.broadcast(x,y).shape
    h=map_coordinates(MICRO,np.stack([np.ravel(v),np.ravel(u)]),order=1,mode='grid-wrap')
    return h.reshape(shape)

def height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    h=.215+.0015*y+.055*fbm(x*.24,y*.24,6)+.014*fbm(x*2.2,y*2.2,5)
    # Interleaved low alluvial fans with channels, rather than a flat tabletop.
    h+=.26*np.exp(-((x+12)/8)**2-((y-23)/18)**2)
    h+=.47*np.exp(-((x-16)/11)**2-((y-38)/22)**2)
    h+=.55*np.exp(-((x+27)/13)**2-((y-84)/40)**2)
    for i,(_,_,rx,ry,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i);d=(q-1)*rx;qi=np.minimum(q,1.)
        # Shallow broken shelves around an offset vent, no uniform bowl gradient.
        bed=level+.006-.25*np.maximum(1-qi**4,0)**1.12
        vent=1-smooth(.26,.82,qi+.065*fbm(x*1.1,y*.8,4))
        bed-=1.24*depth*vent
        bed+=(.064*fbm(x*1.7+13,y*1.3-7,5)+.010*fbm(x*12.7,y*13.1,4))*(1-smooth(.88,1.0,q))
        pos=np.maximum(d,0.)
        bank=level+.006+.172*(1-np.exp(-pos*2.4))
        patch=smooth(-.27,.26,fbm(x*.92+8,y*.81+4,5))
        warp=.057*fbm(x*5.4,y*4.7,5)+.019*fbm(x*17.1,y*18.7,4)
        # Staggered accretion margins. Most are low and interrupted, not a rail.
        rim=.030*np.exp(-((d-.053-warp)/.047)**2)*patch
        rim+=.024*np.exp(-((d-.18-warp)/.042)**2)*smooth(-.12,.35,fbm(x*2.7,y*2.9,4))
        rim+=.014*np.exp(-((d-.35-warp)/.031)**2)*patch
        grains=.006*fbm(x*17.7,y*17.7,5)+.0021*noise(x*51,y*51)
        shore=np.exp(-((q-1.045)/.22)**2)
        desired=np.where(q<1,bed,bank)+shore*(grains+rim)
        blend=1-smooth(1.32,1.88,q);h=h*(1-blend)+desired*blend
    q=poolq(x,y,0)
    # Fine mud cracks, separated from the sandy/granular areas.
    crust=smooth(1.07,1.28,q)*(1-smooth(1.75,2.4,q))*smooth(-.26,.27,noise(x*.47,y*.51))
    gap=cellular_gap(x*6.3+.26*noise(x*3.1,y*3.1),y*6.3+.26*noise(x*3.1+9,y*3.1))
    h-=crust*.0075*np.exp(-(gap/.06)**2)
    # Branching damp rills on the low side, not a painted unbroken orange band.
    line=x-(3.28+.27*np.sin(y*.94)+.13*noise(y*3.7,np.zeros_like(y)))
    drain=np.exp(-(line/.28)**2)*np.exp(-((y+1.65)/2.8)**4)
    h-=.050*drain
    near=np.exp(-((x-.5)/20)**8-((y-1)/25)**8)
    gravel=smooth(-.40,.44,fbm(x*.53+3,y*.57-9,5))
    h+=near*(.0009*fbm(x*63,y*63,3)+micro_height(x,y)*(.26+.74*gravel))
    return h


def rock_template(seed,sub):
    """Closed deformed halfspace solid with mesoscopic scars and anisotropic grain.

    Every large boulder receives its own independent shape. Normals derive from
    the final vertices; there is no flat polygon with a painted groove.
    """
    rng=np.random.default_rng(seed)
    level=6 if sub>=5 else sub
    mesh=trimesh.creation.icosphere(subdivisions=level)
    d=mesh.vertices.copy();f=mesh.faces.copy()
    # A rotated orthogonal joint set, plus irregular oblique broken faces.
    q,_=np.linalg.qr(rng.normal(size=(3,3)))
    if np.linalg.det(q)<0:q[:,0]*=-1
    ns=np.vstack([q,-q,rng.normal(size=(13,3))])
    ns/=np.linalg.norm(ns,axis=1)[:,None]
    ds=rng.uniform(.56,1.08,len(ns))
    den=d@ns.T
    radii=np.divide(ds,den,out=np.full_like(den,1e5),where=den>1e-5)
    nearest=np.min(radii,axis=1)
    weights=np.exp(-np.maximum(radii-nearest[:,None],0)*65.)
    rr=nearest-np.log(weights.sum(axis=1))/65.
    v=d*rr[:,None]
    surf=weights@ns;surf/=np.maximum(np.linalg.norm(surf,axis=1),1e-12)[:,None]
    p=v+np.array([rng.uniform(-70,70),rng.uniform(-70,70),rng.uniform(-70,70)])
    a,b,c=p.T
    # Different support lengths: joints, exfoliation scars, and granular pits.
    warp=.34*noise(a*3.3,b*3.6,c*3.2)
    relief=.043*noise(a*7.4+warp,b*6.8,c*8.9)
    relief+=.021*noise(a*20.1,b*18.4,c*24.9)
    relief+=.010*noise(a*51.4,b*49.6,c*67.4)
    relief+=.0036*noise(a*127.2,b*133.1,c*141.9)
    # Compact spalls are centered ON the surface, rather than sampling an
    # interior volume where most depressions never intersected the shell.
    for k in range(24 if sub>=5 else (9 if sub>=3 else 3)):
        idx=int(rng.integers(len(v)));centre=v[idx].copy();axis=surf[idx].copy()
        t=np.cross(axis,[0,0,1] if abs(axis[2])<.8 else [0,1,0]);t/=np.linalg.norm(t)
        binormal=np.cross(axis,t);dv=v-centre
        radius=rng.uniform(.045,.18);aspect=rng.uniform(.47,1.35)
        ru=(dv@t)/radius;rv=(dv@binormal)/(radius*aspect);rn=dv@axis
        metric=np.sqrt(ru*ru+rv*rv)
        jitter=.12*noise(v[:,0]*43+k,v[:,1]*41+k,v[:,2]*39)
        edge=metric+jitter
        # Broad concave scars have a short fractured transition; their support
        # is bounded to the selected face, so no far-side dents or painted rings.
        mask=(1-smooth(.64,1.04,edge))*np.exp(-(rn/.11)**4)
        relief-=rng.uniform(.020,.067)*mask*(.79+.21*np.maximum(1-metric,0))
        lip=np.exp(-((edge-.99)/.11)**2)*np.exp(-(rn/.09)**4)
        relief+=rng.uniform(.003,.010)*lip
    band=v@q[:,0]+.12*noise(a*5,b*5,c*5)
    # Worn lamination creates narrow local edges; amplitudes remain centimetres.
    relief-=.016*np.exp(-((band-rng.uniform(-.5,.5))/.018)**2)*smooth(-.2,.37,noise(a*4,b*4,c*4))
    v+=surf*relief[:,None]
    return v,f,mesh_normals(v,f)


def landscape_ridges(xs,ys,seed):
    """Branching spur skeleton plus routed area-dependent incision.

    This is an authored geomorphology construction, not a claim of a site DEM,
    sediment conservation, or a calibrated geological timescale.
    """
    rng=np.random.default_rng(seed+182)
    x,y=np.meshgrid(xs,ys)
    z=np.zeros_like(x)
    # Tall irregular main ridges; spurs lead downhill into separate watersheds.
    for layer,(centre,width,peakbase) in enumerate([(3650,1700,720),(6950,2400,1260),(10800,3000,1720)]):
        knots=np.linspace(xs[0]-2000,xs[-1]+2000,21)
        yy=centre+rng.normal(0,280,len(knots))
        zz=peakbase*rng.uniform(.52,1.16,len(knots))
        ridge=np.zeros_like(x)
        for k in range(len(knots)-1):
            ax,ay=knots[k],yy[k];bx,by=knots[k+1],yy[k+1]
            vx,vy=bx-ax,by-ay
            t=np.clip(((x-ax)*vx+(y-ay)*vy)/(vx*vx+vy*vy),0,1)
            dist=np.hypot(x-ax-t*vx,y-ay-t*vy)
            h=zz[k]*(1-t)+zz[k+1]*t
            # Slightly convex ridges become flatter talus at the base.
            surface=h*np.maximum(1-dist/width,0)**1.42
            ridge=np.maximum(ridge,surface)
        for k in range(1,len(knots)-1):
            for sign in [-1,1]:
                # Uneven downhill spurs branch from the main peak.
                origin=np.array([knots[k],yy[k]])
                end=origin+np.array([rng.uniform(-520,520),sign*rng.uniform(950,1650)])
                points=[origin,(origin+end)/2+np.array([rng.uniform(-140,140),0]),end]
                heights=[zz[k],zz[k]*rng.uniform(.39,.63),zz[k]*.025]
                for j in range(2):
                    aa,bb=points[j],points[j+1];v=bb-aa
                    t=np.clip(((x-aa[0])*v[0]+(y-aa[1])*v[1])/np.dot(v,v),0,1)
                    dist=np.hypot(x-aa[0]-t*v[0],y-aa[1]-t*v[1])
                    h=heights[j]*(1-t)+heights[j+1]*t
                    ridge=np.maximum(ridge,h-np.maximum(dist,0)*rng.uniform(.59,.91))
        # Add directional rough rock to the skeleton, at much smaller scale.
        envelope=smooth(20,160,ridge)
        wx=x+95*fbm(x*.0018,y*.0016,5)
        wy=y+95*fbm(x*.0016+7,y*.0018-5,5)
        r=fbm(wx*.0039,wy*.0036,7)
        ridge+=envelope*(42*r+18*fbm(x*.013,y*.012,5))
        z=np.maximum(z,ridge)
    dx=float(xs[1]-xs[0]);dy=float(ys[1]-ys[0])
    # Real routed drainage changes the surface, not just its albedo.
    evolved=erode(np.maximum(z,0).astype(float)/dx,310000,seed+284)*dx
    z=.20*z+.80*evolved
    for it in range(5):
        area,slope=drainage(z,dx,dy)
        cut=np.minimum(np.sqrt(area)*np.sqrt(slope)*.32,4.5)*smooth(20,160,z)
        z-=.55*cut+.45*gaussian_filter(cut,.7)
    # No broad final Gaussian blur: retain tributaries and angular rock outcrops.
    gy,gx=np.gradient(z,dy,dx);steep=smooth(.13,.56,np.hypot(gx,gy))
    # Resistant rock beds stand above scree. Relief varies with steepness.
    bedding=z*.017+x*.006-y*.0015+.7*fbm(x*.009,y*.009,5)
    steps=np.sin(bedding)+.27*np.sin(bedding*3.7)
    z+=steep*(9*steps+7.5*fbm(x*.038,y*.034,5)+2.8*noise(x*.094,y*.089))
    z=np.maximum(z,0)+.215+.0015*y
    fade=smooth(149.9,840,y)
    return height(x,y)*(1-fade)+z*fade


def connected_shrub(rng,base,h,lod,stem):
    """Uneven rounded multi-stem shrubs; all leaves originate on real twigs."""
    wood=[];leaf_v=[];leaf_f=[];offset=0
    wind=np.r_[rng.normal(0,.12,2),0.]*h
    def leaf(at,axis,length):
        nonlocal offset
        tangent=axis+rng.normal(0,.5,3);tangent/=np.linalg.norm(tangent)
        side=np.cross(tangent,rng.normal(size=3));side/=max(np.linalg.norm(side),1e-9)
        up=np.cross(tangent,side);w=length*rng.uniform(.16,.32)
        mid=at+tangent*length*.52
        vv=np.array([at,mid+side*w,at+tangent*length,mid-side*w,mid+up*w*.33])
        ff=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])+offset
        leaf_v.append(vv);leaf_f.append(ff);offset+=5
    def branch(a,b,r,order):
        axis=b-a;length=np.linalg.norm(axis)
        bend=rng.normal(0,.08,3)*length
        ts=np.linspace(0,1,5 if lod==0 else 3)
        points=a[None,:]*(1-ts[:,None])+b[None,:]*ts[:,None]+np.sin(ts[:,None]*np.pi)*bend
        for j in range(len(points)-1):wood.append(stem(points[j],points[j+1],r*(1-.65*j/(len(points)-1))))
        if order<2:
            count=5 if order==0 else (5 if lod==0 else 3)
            for k in range(count):
                t=(k+1.2)/(count+1.7);idx=min(int(t*(len(points)-1)),len(points)-2)
                u=t*(len(points)-1)-idx;attach=points[idx]*(1-u)+points[idx+1]*u
                phi=rng.uniform(0,2*np.pi);spread=.46 if order==0 else .26
                direction=axis/length*.35+np.array([np.cos(phi)*spread,np.sin(phi)*spread,rng.uniform(.22,.80)])
                direction/=np.linalg.norm(direction)
                end=attach+direction*length*rng.uniform(.30,.62)
                branch(attach,end,r*.35,order+1)
        else:
            axis/=length
            for j in range(len(points)-1):
                count=6 if lod==0 else 3
                for k in range(count):
                    t=(k+.35)/count;at=points[j]*(1-t)+points[j+1]*t
                    for side in range(2):leaf(at,axis,rng.uniform(.010,.024))
    for j in range(int(rng.integers(6,10))):
        phi=rng.uniform(0,2*np.pi);rad=h*rng.uniform(.27,.56)
        end=base+np.array([np.cos(phi)*rad,np.sin(phi)*rad,h*rng.uniform(.56,1.05)])+wind
        branch(base+np.r_[rng.normal(0,.035*h,2),0],end,.0055*h,0)
    v=np.concatenate(leaf_v);f=np.concatenate(leaf_f)
    return wood,[(v,f,mesh_normals(v,f))]
