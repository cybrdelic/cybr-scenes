"""Scale-aware authored geology and attached vegetation for CYBR GEO v8.

No image synthesis, neural assets, measured geology, or geochemistry claims.
All positions here are metres; the assembly adapter alone converts to mm.
"""
import numpy as np
import trimesh
from build_scene_v4 import noise,fbm,mesh_normals,erode

POOLS=[(.5,1.,4.1,3.2,.055,.95),(-3.5,10.,2.2,1.65,.245,.64)]
RIPPLE_SCALE=.16

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def poolq(x,y,i):
    cx,cy,rx,ry,level,depth=POOLS[i]
    dx=(np.asarray(x)-cx)/rx;dy=(np.asarray(y)-cy)/ry;a=np.arctan2(dy,dx)
    edge=1+.18*np.sin(3*a+.55)+.090*np.sin(2*a-1.3)+.038*np.sin(7*a+.9*i)
    edge+=.09*noise(np.asarray(x)*.55,np.asarray(y)*.55)+.025*noise(np.asarray(x)*2.7,np.asarray(y)*2.7)
    return np.sqrt(dx*dx+dy*dy)/edge

def height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    h=.185+.0015*y+.063*fbm(x*.17,y*.17,6)+.007*fbm(x*1.7,y*1.7,4)
    for i,(_,_,rx,ry,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i);d=(q-1)*rx;qi=np.minimum(q,1)
        bed=level+.018-depth*np.maximum(1-qi**2,0)**1.52
        bed+=(.047*fbm(x*.66+12,y*.81-4,5)+.008*fbm(x*4.1,y*4.1,4))*(1-smooth(.78,1.,q))
        positive=np.maximum(d,0)
        bank=level+.018+.18*(1-np.exp(-(positive*positive/(positive+.07))*1.65))
        shore=np.exp(-((q-1.04)/.24)**2)
        rills=.008*np.exp(-(np.sin(x*5.8+y*2.7+1.9*noise(x*1.9,y*1.9))/.14)**2)
        sediment=.007*fbm(x*3.9,y*3.9,5)+.0013*noise(x*34,y*34)
        desired=np.where(q<1,bed,bank)+shore*(sediment-rills)
        blend=1-smooth(1.44,1.95,q);h=h*(1-blend)+desired*blend
    line=x-(3.55+.29*np.sin(y*1.1)+.11*np.sin(y*3.6))
    h-=.070*np.exp(-(line/.32)**2)*np.exp(-((y+1.35)/3.3)**4)
    near=np.exp(-((x-.5)/15)**6-((y-1)/17)**6)
    return h+near*(.0012*fbm(x*23.7,y*23.7,4)+.0005*noise(x*92,y*92))

def rock_template(seed,sub):
    rng=np.random.default_rng(seed);mesh=trimesh.creation.icosphere(subdivisions=sub)
    d=mesh.vertices.copy();f=mesh.faces.copy()
    normals=np.vstack((trimesh.creation.icosphere(subdivisions=0).vertices+rng.normal(0,.20,(12,3)),rng.normal(size=(8,3))))
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    distances=rng.uniform(.52,.94,len(normals));den=d@normals.T
    radial=np.divide(distances,den,out=np.full_like(den,1e6),where=den>1e-7)
    near=radial.min(axis=1)
    rad=near-np.log(np.sum(np.exp(-(radial-near[:,None])*95),axis=1))/95
    rounding=rng.uniform(.18,.66)
    sphere=.80+.17*noise(d[:,0]*1.8+seed*.31,d[:,1]*1.8,d[:,2]*1.8)
    rad=rad*(1-rounding)+rounding*sphere
    v=d*rad[:,None];p=v+rng.uniform(-50,50,3)
    w=.0055*noise(p[:,0]*4.1,p[:,1]*4.1,p[:,2]*4.1)
    w+=.0055*noise(p[:,0]*13.3,p[:,1]*13.3,p[:,2]*13.3)
    w+=.0030*noise(p[:,0]*41.7,p[:,1]*41.7,p[:,2]*41.7)
    w-=.005*np.maximum(noise(p[:,0]*19,p[:,1]*19,p[:,2]*19)-.32,0)**1.7
    # Sparse structural fissures, distinct from granular surface weathering.
    # A localized crack field avoids engraving every rock with parallel bands.
    for crack in range(3):
        cn=rng.normal(size=3);cn/=np.linalg.norm(cn)
        plane=v@cn-rng.uniform(-.38,.38)
        plane+=.018*noise(p[:,0]*8.3,p[:,1]*8.3,p[:,2]*8.3)
        support=smooth(-.30,.32,noise(p[:,0]*1.9+crack*7,p[:,1]*1.9,p[:,2]*1.9))
        w-=rng.uniform(.018,.040)*np.exp(-(plane/rng.uniform(.007,.014))**2)*support
    v+=d*w[:,None];return v,f,mesh_normals(v,f)

def landscape_ridges(xs,ys,seed):
    from scipy.ndimage import gaussian_filter
    x,y=np.meshgrid(xs,ys)
    spine=4800+490*np.sin(x*.00063)+200*fbm(x*.00078,np.zeros_like(x)+3,4)
    peak=420+210*np.exp(-((x+1900)/1700)**2)+510*np.exp(-((x-2600)/1900)**2)
    peak+=80*fbm(x*.0011,np.zeros_like(x)+19,5)
    dy=y-spine;width=np.where(dy<0,1400.,2350.)
    base=peak*np.exp(-np.abs(dy/width)**1.8)
    envelope=smooth(650,2300,y)*(1-smooth(6600,9400,y))
    warp=x+180*fbm(x*.0010,y*.00095,4)+dy*.21
    # Long downslope corrugations and broad tributary shoulders; no inverse
    # value-noise cells, whose square valleys made the previous ridge artificial.
    folds=52*np.sin(warp*.0061+noise(x*.002,y*.0011)*1.1)
    folds+=23*fbm(warp*.0085,y*.0019,5)
    base+=envelope*(folds+37*fbm(x*.0041,y*.0030,5))
    base=np.maximum(base,0)*smooth(330,850,y)+.19+.0015*y
    spacing=float(xs[1]-xs[0])
    eroded=erode((base/spacing).astype(float),750000,seed+700)*spacing
    z=gaussian_filter(base*.32+eroded*.68,.70)
    z+=envelope*(1.1*noise(x*.12,y*.12)+.3*noise(x*.28,y*.28))
    fade=smooth(149.9,430,y)
    return height(x,y)*(1-fade)+z*fade

def connected_shrub(rng,base,h,lod,stem):
    """Leaf base vertices are on explicit branch segments, not cloud samples."""
    wood=[];leaf_v=[];leaf_f=[];off=0
    main=int(rng.integers(16,25)) if lod==0 else int(rng.integers(9,15))
    wind=rng.normal(0,.08,3);wind[2]=0
    for j in range(main):
        az=rng.uniform(0,2*np.pi);axis=np.array([np.cos(az),np.sin(az),0.])
        root=base+np.r_[rng.normal(0,.018*h,2),0]
        mid=root+axis*h*rng.uniform(.09,.25)+[0,0,h*rng.uniform(.23,.40)]
        tip=root+axis*h*rng.uniform(.32,.67)+[0,0,h*rng.uniform(.53,.96)]+wind*h
        wood.extend((stem(root,mid,.008*h),stem(mid,tip,.0045*h)))
        nk=6 if lod==0 else 4
        for k in range(nk):
            t=(k+.5+rng.uniform(-.2,.2))/nk;start=mid*(1-t)+tip*t
            phi=az+rng.uniform(-1.5,1.5)
            branch=start+np.array([np.cos(phi),np.sin(phi),rng.uniform(.25,.70)])*h*rng.uniform(.11,.28)
            wood.append(stem(start,branch,.0017*h));branches=[(start,branch)]
            if lod==0:
                for u in [.40,.74]:
                    s=start*(1-u)+branch*u
                    end=s+np.array([np.cos(phi+1.4),np.sin(phi+1.4),.7])*h*rng.uniform(.065,.14)
                    wood.append(stem(s,end,.0008*h));branches.append((s,end))
            for s,end in branches:
                axis2=end-s;axis2/=np.linalg.norm(axis2)
                perp=np.cross(axis2,[0,0,1]);perp/=max(np.linalg.norm(perp),1e-12)
                nl=9 if lod==0 else 6
                for ll in range(nl):
                    t=(ll+.40)/nl;attach=s*(1-t)+end*t
                    for side in [-1,1]:
                        length=h*rng.uniform(.044,.074)
                        direction=perp*side+axis2*.25+np.array([0,0,rng.uniform(-.22,.35)])
                        direction/=np.linalg.norm(direction)
                        lateral=np.cross(direction,[0,0,1]);lateral/=max(np.linalg.norm(lateral),1e-12)
                        middle=attach+direction*length*.52;width=length*rng.uniform(.20,.30)
                        v=np.vstack((attach,middle+lateral*width,attach+direction*length,middle-lateral*width,middle+[0,0,length*.075]))
                        f=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])+off
                        leaf_v.append(v);leaf_f.append(f);off+=5
    v=np.concatenate(leaf_v);f=np.concatenate(leaf_f)
    return wood,[(v,f,mesh_normals(v,f))]
