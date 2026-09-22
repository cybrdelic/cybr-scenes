"""CYBR GEO v5: an irregular spring shelf, lithology-aware debris and basin.

All visible surfaces are actual CYBR GEO Part meshes. This scene is authored,
not a surveyed place or a claim of solved geological or geothermal dynamics.
No generated imagery, photographic backplates, or replacement renders.
"""
from __future__ import annotations
import argparse, gc, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial import Voronoi
from numba import njit, vectorize, float64
from PIL import Image
from build_scene_v4 import noise, fbm, gridmesh, mesh_normals, join, erode, stream_hash

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'))
from cybrgeo import Assembly,Part,Material
SEED=20260914
POOLS=[(.5,1.0,4.1,3.2,.055,1.30),(-3.5,10.,2.2,1.65,.245,.75)]
MODES=np.asarray(json.loads((Path(__file__).parent/'assets/ripple_modes.json').read_text())['modes_kx_ky_amplitude_phase'])
RIPPLE_SCALE=.29

_photo=np.asarray(Image.open(Path(__file__).parent/'assets/gravel_periodic.pgm'),dtype=float)/255
_photo=np.where(_photo<=.04045,_photo/12.92,((_photo+.055)/1.055)**2.4)
PHOTO_HEIGHT=gaussian_filter(_photo/_photo.mean(),1.2,mode='wrap')
@vectorize([float64(float64,float64)],nopython=True)
def sediment_microrelief(x,y):
    u=(x*.917+y*.399)/.45*512-.5;v=(y*.917-x*.399)/.45*512-.5
    ix=int(np.floor(u));iy=int(np.floor(v));fx=u-ix;fy=v-iy
    x0=ix%512;y0=iy%512;x1=(ix+1)%512;y1=(iy+1)%512
    a=(PHOTO_HEIGHT[y0,x0]*(1-fx)+PHOTO_HEIGHT[y0,x1]*fx)*(1-fy)+(PHOTO_HEIGHT[y1,x0]*(1-fx)+PHOTO_HEIGHT[y1,x1]*fx)*fy
    return max(.0,a-.22)**.65

def poolq(x,y,i):
    cx,cy,rx,ry,level,depth=POOLS[i]
    dx=(np.asarray(x)-cx)/rx;dy=(np.asarray(y)-cy)/ry
    a=np.arctan2(dy,dx)
    edge=1+.16*np.sin(2*a+.55)+.050*np.sin(5*a-1.3)+.027*np.sin(9*a+.9*i)
    edge+=.09*noise(np.asarray(x)*.55,np.asarray(y)*.55)+.025*noise(np.asarray(x)*2.7,np.asarray(y)*2.7)
    return np.sqrt(dx*dx+dy*dy)/edge

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=np.float64),np.asarray(y,dtype=np.float64))
    h=.19+.0035*y+.055*fbm(x*.17,y*.17,5)+.015*fbm(x*1.6,y*1.6,4)
    for i,(_,_,rx,ry,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i);d=(q-1)*rx
        # A gently sloping shelf replaces the previous almost-vertical rim.
        bed=level+.012-depth*np.maximum(1-np.minimum(q,1)**2,0)**1.72
        bank=level+.012+.28*(1-np.exp(-np.maximum(d,0)*.77))
        bed+=.017*fbm(x*2,y*2,5)*smooth(.45,.90,q)
        # Incised rills and accretion follow shoreline position, but do not make
        # concentric uniformly spaced rings. Both surfaces meet continuously.
        lamina=np.sin(d*34+1.8*fbm(x*.8,y*.8,4))
        accretion=.010*np.maximum(lamina-.15,0)**1.4
        shore=np.exp(-((q-1.03)/.20)**2)
        rough=.011*fbm(x*7,y*7,4)+.0022*noise(x*61,y*61)
        desired=np.where(q<1,bed,bank)+shore*(rough+accretion)
        blend=1-smooth(1.6,1.93,q);h=h*(1-blend)+desired*blend
    # One broad wet outflow rather than an identically clean closed pool ring.
    xx=x-(3.75+.20*np.sin(y*1.45)+.08*np.sin(y*4.1))
    drain=np.exp(-(xx/.31)**2)*np.exp(-((y+1.9)/3.0)**4)
    h-=.08*drain
    # Small actual relief, not enlarged bump noise masquerading as rocks.
    h+=.0003*noise(x*43,y*43)
    mask=np.exp(-((x-1.5)/9)**6-((y+1.5)/7)**6)
    h+=.0011*sediment_microrelief(x,y)*mask
    return h

def water(x,y,i):
    xx,yy=np.broadcast_arrays(x,y);z=np.zeros_like(xx,dtype=float)+POOLS[i][4]
    for kx,ky,a,phase in MODES:
        z+=a*RIPPLE_SCALE*np.sin(kx*xx+ky*yy+phase+.37*i)
    return z

def rock_template(seed,sub):
    """Rounded intersections of actual joint planes, not a noise-inflated sphere."""
    rng=np.random.default_rng(seed)
    base=trimesh.creation.icosphere(subdivisions=sub)
    directions=base.vertices.copy();f=base.faces.copy()
    # Non-axis-aligned joint families and oblique truncations avoid cubic blocks.
    normals=np.vstack((trimesh.creation.icosphere(subdivisions=0).vertices+rng.normal(0,.23,(12,3)),rng.normal(size=(4,3))))
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    distances=rng.uniform(.62,1.02,len(normals))
    den=directions@normals.T
    radial=np.divide(distances[None,:],den,out=np.full_like(den,1e6),where=den>1e-6)
    nearest=radial.min(axis=1)
    # Stable soft minimum rounds only narrow joint boundaries.
    width=rng.uniform(45,85)
    radius=nearest-np.log(np.sum(np.exp(-(radial-nearest[:,None])*width),axis=1))/width
    v=directions*radius[:,None]
    offset=rng.uniform(-50,50,3)
    p=v+offset
    weather=.027*noise(p[:,0]*7,p[:,1]*7,p[:,2]*7)
    weather+=.010*noise(p[:,0]*23,p[:,1]*23,p[:,2]*23)
    weather+=.003*noise(p[:,0]*81,p[:,1]*81,p[:,2]*81)
    bed=v[:,2]+.12*v[:,0]-.07*v[:,1]
    groove=np.exp(-(np.sin(bed*rng.uniform(18,34)+.5*noise(p[:,0]*4,p[:,1]*4))/.18)**2)
    weather-=.012*groove
    v+=directions*weather[:,None]
    return v,f,mesh_normals(v,f)

def stem(p,q,radius,sides=5):
    d=q-p;d/=np.linalg.norm(d);u=np.cross(d,[0,0,1])
    if np.linalg.norm(u)<.01:u=np.cross(d,[0,1,0])
    u/=np.linalg.norm(u);b=np.cross(d,u)
    a=np.arange(sides)*2*np.pi/sides;offset=np.cos(a)[:,None]*u+np.sin(a)[:,None]*b
    v=np.vstack((p+offset*radius,q+offset*radius*.44));f=[]
    for k in range(sides):j=(k+1)%sides;f.extend([[k,j,j+sides],[k,j+sides,k+sides]])
    f=np.asarray(f);return v,f,mesh_normals(v,f)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=REPO.parent/'output')
    ap.add_argument('--seed',type=int,default=SEED);ap.add_argument('--no-glb',action='store_true')
    args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    start=time.time();rng=np.random.default_rng(args.seed);parts=[]
    mats=[Material('Mixed sand and carbonate sediment',(.50,.40,.29),0,.86),
          Material('Weathered pale carbonate',(.58,.53,.44),0,.81),
          Material('Jointed desert rock',(.29,.235,.17),0,.82),
          Material('Dry curled grass',(.35,.245,.12),0,.91),
          Material('Carbonate accretion and crust',(.72,.68,.58),0,.86),
          Material('Desert ridge geology',(.33,.30,.26),0,.89),
          Material('Main water boundary',(.17,.30,.33),0,.02),
          Material('Upper water boundary',(.17,.30,.33),0,.02),
          Material('Dry branch wood',(.14,.092,.05),0,.93),
          Material('Sparse grey olive leaves',(.21,.23,.14),0,.88)]
    def add(name,v,f,n,mat,group='landscape',**meta):
        parts.append(Part(name,np.asarray(v)*1000,np.asarray(f),np.asarray(n),material=mat,group=group,
                          role='Authored environmental mesh; not a surveyed or simulated landform',metadata=meta))
    # ~1 cm foreground geometry; a smoothly graded density budget rather than
    # millions of distant gravel triangles with almost no projected area.
    xs=np.unique(np.r_[np.linspace(-75,-12,100),np.linspace(-12,-7,101),np.linspace(-7,-2,251),np.linspace(-2,5,1401),np.linspace(5,8,151),np.linspace(8,18,180),np.linspace(18,75,80)])
    ys=np.unique(np.r_[np.linspace(-40,-7,50),np.linspace(-7,-5,81),np.linspace(-5,0,1001),np.linspace(0,5.5,371),np.linspace(5.5,18,150),np.linspace(18,80,121)])
    xx,yy=np.meshgrid(xs,ys);v,f,n=gridmesh(xs,ys,height(xx,yy));add('Continuous_irregular_spring_shelf',v,f,n,0)
    print('ground',len(f),flush=True);del xx,yy,v,f,n
    # Broad, eroded, intersecting rock ridges. The scene retains a full horizon.
    mx=np.linspace(-1800,1800,1001);my=np.linspace(79.95,2100,751);xx,yy=np.meshgrid(mx,my)
    env=smooth(540,950,yy)
    warp=90*fbm(xx*.0028,yy*.0035,5)
    z=38+58*fbm((xx+warp)*.0024,yy*.0020,5)
    z+=150*np.exp(-((xx+250)/300)**2-((yy-700)/490)**2)
    z+=205*np.exp(-((xx-650)/430)**2-((yy-1350)/680)**2)
    # Folded bedding at differently oriented scales makes a rocky rather than
    # dune-like silhouette. Hydraulic droplets cut tributary channels.
    ridges=np.zeros_like(xx)
    for k in range(5):
        freq=.005*1.9**k;ridge=1-np.abs(noise((xx+warp)*freq+13*k,yy*freq*.72-7*k))
        ridges+=(ridge**4-.43)*37*.55**k
    z+=ridges;z=height(xx,yy)+env*np.maximum(z,0)
    z=erode((z/5.0).astype(float),300000,args.seed+700)*5.0
    z=gaussian_filter(z,.65)
    v,f,n=gridmesh(mx,my,z);add('Eroded_layered_basin_ridges',v,f,n,5,
                               erosion_droplets=300000,method='Authored ridged field with numerical hydraulic erosion')
    print('mountains',len(f),flush=True)
    def ground(x,y):
        if y<79.95:return float(height(x,y))
        return float(map_coordinates(z,np.array([[(y-my[0])/(my[1]-my[0])],[(x-mx[0])/(mx[1]-mx[0])]]),order=1,mode='nearest')[0])
    # Dense top meshes and buried closed sides. Normals use the same wave modes
    # as direct-light connections; closed volumes are verified separately.
    for i,(cx,cy,rx,ry,level,depth) in enumerate(POOLS):
        xa=np.linspace(cx-rx*1.42,cx+rx*1.42,841 if i==0 else 341)
        ya=np.linspace(cy-ry*1.42,cy+ry*1.42,641 if i==0 else 281)
        a,b=np.meshgrid(xa,ya);v,f,n=gridmesh(xa,ya,water(a,b,i));nx=len(xa);ny=len(ya)
        ids=np.r_[np.arange(nx),np.arange(2*nx-1,nx*ny,nx),np.arange(nx*ny-2,nx*(ny-1)-1,-1),np.arange(nx*(ny-2),0,-nx)]
        top=v[ids];bottom=top.copy();bottom[:,2]=-3.;nv=len(top);sv=np.vstack((top,bottom));ii=np.arange(nv);jj=(ii+1)%nv
        sf=np.vstack((np.c_[ii,ii+nv,jj+nv],np.c_[ii,jj+nv,jj],np.c_[np.full(nv-2,nv),np.arange(nv+2,2*nv),np.arange(nv+1,2*nv-1)]))
        v,f,n=join([(v,f,n),(sv,sf,mesh_normals(sv,sf))]);add(f'Closed_water_{i}',v,f,n,6+i,'water',pool=i)
    templates={(sub,k):rock_template(args.seed+sub*100+k,sub) for sub in [1,2,3,4,5] for k in range(7 if sub==5 else 12)}
    stones={1:[],2:[],4:[]};counts={'large_rocks':0,'small_rocks':0,'gravel':0,'mineral_nodules':0,'shrubs':0,'grass_tufts':0}
    # Deliberate hero outcrop, partly buried rather than floating on the terrain.
    placements=[(4.1,3.1,.80),(5.0,3.2,.60),(4.0,4.3,1.10),(5.1,4.8,.72),(3.9,5.3,.52),(5.8,3.8,.43),
                (3.9,-1.8,.29),(4.45,-2.4,.44),(-4.2,4.0,.41),(-3.5,2.5,.34),(-4.7,-1.4,.27)]
    def place(x,y,r,sub,mat,kind,burial=.2):
        key=int(rng.integers(7 if sub==5 else 12));vv,ff,nn=templates[sub,key]
        sizes=r*np.array([rng.uniform(.9,1.35),rng.uniform(.66,1.05),rng.uniform(.52,.91)])
        az=rng.uniform(0,2*np.pi);tilt=rng.uniform(-.28,.28);co,si=np.cos(az),np.sin(az)
        rz=np.array([[co,-si,0],[si,co,0],[0,0,1]]);ct,st=np.cos(tilt),np.sin(tilt);rt=np.array([[1,0,0],[0,ct,-st],[0,st,ct]])@rz
        v=(vv*sizes)@rt.T;v+=np.array([x,y,ground(x,y)-r*burial]);n=(nn/sizes)@rt.T;n/=np.linalg.norm(n,axis=1)[:,None]
        stones[mat].append((v,ff,n));counts[kind]+=1
    for j,(x,y,r) in enumerate(placements):place(x,y,r,5,2 if j%4 else 1,'large_rocks',.15)
    for j in range(100):
        x=rng.uniform(-23,26);y=rng.uniform(-2,55)
        if min(float(poolq(x,y,i)) for i in range(2))<1.14:continue
        place(x,y,np.exp(rng.uniform(np.log(.12),np.log(.54))),3,2 if rng.random()<.5 else 1,'large_rocks',.25)
    # Gravel concentrates in a few sediment lobes and runnels; quiet fine-sand
    # areas remain quiet. It no longer blankets every square metre equally.
    for j in range(15500):
        x=rng.uniform(-12,14);y=rng.uniform(-7,24)
        q=min(float(poolq(x,y,i)) for i in range(2))
        cluster=smooth(-.05,.60,float(fbm(np.array(x*.53),np.array(y*.49),4)))
        if rng.random()>.06+.60*cluster:continue
        if q<.74 and rng.random()<.85:continue
        radius=np.exp(rng.uniform(np.log(.004),np.log(.048)))
        if radius>.026:kind='small_rocks';sub=2
        else:kind='gravel';sub=1
        place(x,y,radius,sub,1 if rng.random()<.73 else 2,kind,.16)
    # Near-field sediment pockets: dense, embedded millimetre-to-centimetre
    # gravel whose clustering leaves genuinely fine-sediment quiet patches.
    for j in range(18000):
        x=rng.uniform(-3.5,7.0);y=rng.uniform(-5.0,6.2)
        q=min(float(poolq(x,y,i)) for i in range(2))
        cluster=smooth(-.34,.45,float(fbm(np.array(x*.91),np.array(y*.87),4)))
        if rng.random()>.20+.68*cluster:continue
        if q<.65 and rng.random()<.65:continue
        radius=np.exp(rng.uniform(np.log(.0035),np.log(.027)))
        place(x,y,radius,2 if radius>.013 else 1,1 if rng.random()<.69 else 2,
              'small_rocks' if radius>.013 else 'gravel',.40)
    # Carbonate nodules cluster on the uneven banks. Mixed sizes and shallow
    # burial avoid the previous equilateral-shard shoreline.
    for j in range(9000):
        x=rng.uniform(-6,7);y=rng.uniform(-4,7);q=float(poolq(x,y,0))
        if q<.98 or q>1.27:continue
        if rng.random()>.43+.42*float(noise(x*1.3,y*1.3)):continue
        r=np.exp(rng.uniform(np.log(.008),np.log(.095)))
        place(x,y,r,2 if r<.035 else 3,4,'mineral_nodules',.35)
    for mat,items in stones.items():
        if items:v,f,n=join(items);add(f'Buried_weathered_rock_and_sediment_{mat}',v,f,n,mat,'stones')
    print('stones',counts,flush=True)
    # Irregular small plate islands, confined to genuinely dry evaporative banks.
    pts=rng.uniform([-7,-6],[8,13],(4200,2));vor=Voronoi(pts);chips=[]
    for k,regid in enumerate(vor.point_region):
        ids=vor.regions[regid]
        if len(ids)<3 or -1 in ids:continue
        c=pts[k];q=float(poolq(*c,0));poly=vor.vertices[ids]
        if q<1.08 or q>1.54 or float(noise(c[0]*.8,c[1]*.8))<.0:continue
        if np.max(np.linalg.norm(poly-c,axis=1))>.7:continue
        poly=c+(poly-c)*rng.uniform(.965,.989)
        if np.sum(poly[:,0]*np.roll(poly[:,1],-1)-poly[:,1]*np.roll(poly[:,0],-1))<0:poly=poly[::-1]
        # Multiple samples along each edge prevent smooth ideal polygon outlines.
        edge=[]
        for a,b in zip(poly,np.roll(poly,-1,axis=0)):
            d=b-a;side=np.array([-d[1],d[0]])
            for t in [0,.3,.65]:edge.append(a+d*t+side*rng.uniform(-.038,.038))
        edge=np.asarray(edge);nn=len(edge);top=np.c_[edge,height(edge[:,0],edge[:,1])+.004]
        center=np.r_[c,float(height(*c))+.002];v=np.vstack((center,top,top-[0,0,.007]));f=[]
        for j in range(nn):a=j+1;b=(j+1)%nn+1;f.extend([[0,a,b],[a,a+nn,b+nn],[a,b+nn,b]])
        f=np.asarray(f);chips.append((v,f,mesh_normals(v,f)))
    if chips:v,f,n=join(chips);add('Broken_evaporative_crust_islands',v,f,n,4,'mineral',count=len(chips))
    grass=[];wood=[];leaves=[]
    # Botanical silhouette: three tapered branching orders and small curled
    # leaves. Far silhouettes are real geometry, not alpha-card bushes.
    fixed=[(-3.8,4.8,.65),(-5.0,1.0,.48),(5.8,3.0,.62),(3.6,7.8,.52),(-1.7,7.0,.35),(-4.7,-.5,.47),(-5.4,2,.64),(6.5,.8,.46),(-7.,8.,.75),(2.7,9.5,.5),(7.5,7.,.62)]
    plants=fixed+[(rng.uniform(-60,60),rng.uniform(6,180),rng.uniform(.3,1.1)) for _ in range(440)]
    for x,y,h in plants:
        if min(float(poolq(x,y,i)) for i in range(2))<1.19:continue
        base=np.array([x,y,ground(x,y)]);counts['shrubs']+=1
        for j in range(int(rng.integers(10,19))):
            az=rng.uniform(0,2*np.pi);axis=np.array([np.cos(az),np.sin(az),0]);side=np.array([-axis[1],axis[0],0])
            p=base+np.array([0,0,h*.05]);mid=base+axis*h*.19+[0,0,h*.28]
            tip=base+axis*h*rng.uniform(.4,.72)+[0,0,h*rng.uniform(.56,.94)]
            wood.extend([stem(p,mid,h*.009),stem(mid,tip,h*.005)])
            for b in range(10):
                a=mid+(tip-mid)*rng.uniform(.10,.95);end=a+axis*h*.10+side*h*rng.uniform(-.26,.26)+[0,0,h*.14]
                wood.append(stem(a,end,h*.0017))
                for l in range(12):
                    c=a+(end-a)*(l+.4)/12+rng.normal(0,h*.008,3);angle=az+rng.uniform(-1.6,1.6);ax=np.array([np.cos(angle),np.sin(angle),.3]);bx=np.array([-np.sin(angle),np.cos(angle),.3])
                    ll=h*rng.uniform(.032,.057);ww=ll*.38
                    v=np.array([c-ax*ll,c+bx*ww,c+ax*ll+[0,0,ll*.32],c-bx*ww,c+[0,0,ll*.20]])
                    f=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]]);leaves.append((v,f,mesh_normals(v,f)))
    positions=[(-1.8,-2.8,.25),(-3.5,2.8,.28),(4.9,1.4,.33),(-3.6,-2.5,.28),(5.4,-.1,.4),(-4.7,2.8,.28),(3.8,6.8,.44)]
    positions +=[(rng.uniform(-30,30),rng.uniform(-3,110),rng.uniform(.16,.47)) for _ in range(300)]
    for x,y,h in positions:
        if min(float(poolq(x,y,i)) for i in range(2))<1.16:continue
        counts['grass_tufts']+=1
        for j in range(int(rng.integers(40,90))):
            az=rng.uniform(0,2*np.pi);ax=np.array([np.cos(az),np.sin(az),0]);side=np.array([-ax[1],ax[0],0]);base=np.array([x,y,ground(x,y)])+ax*rng.uniform(.0,.07)
            length=h*rng.uniform(.48,1.4);bend=length*rng.uniform(.3,.95);width=rng.uniform(.0010,.0024);vv=[]
            for t in np.linspace(0,1,7):
                p=base+ax*bend*t*t+[0,0,length*(t-.33*t**3)];w=width*(1-t)**.8+.00006;vv.extend([p-side*w,p+side*w])
            v=np.asarray(vv);f=[]
            for k in range(6):f.extend([[2*k,2*k+1,2*k+3],[2*k,2*k+3,2*k+2]])
            f=np.asarray(f);grass.append((v,f,mesh_normals(v,f)))
    for name,items,mat in [('Curved_dry_grass',grass,3),('Desert_shrub_branches',wood,8),('Curled_small_leaves',leaves,9)]:
        if items:v,f,n=join(items);add(name,v,f,n,mat,'vegetation')
    assembly=Assembly('CYBR_HOT_SPRINGS_V6',parts,mats,metadata={
        'revision':'v6 joint-plane boulders, sediment pockets and filled foliage','seed':args.seed,
        'source_units':'mm','transport_units':'m','no_image_generation':True,'no_photographic_backplates':True,
        'geometry_source':'CYBR GEO Assembly and Part','pools_m':POOLS,'counts':counts,
        'ripples':'32 prescribed modes at 0.29 times original amplitude; not CFD',
        'limitations':['Authored landscape, not a site scan','Authored steam, not CFD','Authored reflectance, not measured spectra']})
    assembly.save(out/'scene')
    if not args.no_glb:assembly.export_glb(out/'scene.glb')
    del assembly,parts,stones,grass,wood,leaves,chips,templates,v,f,n;gc.collect()
    loaded=Assembly.load(out/'scene');meshpath=out/'scene.meshbin';total=sum(len(p.faces) for p in loaded.parts)
    with meshpath.open('wb') as stream:
        stream.write(np.uint32(total).tobytes())
        for group,p in enumerate(loaded.parts):
            # Bounded write chunks avoid peak copies for the terrain.
            for begin in range(0,len(p.faces),100000):
                faces=p.faces[begin:begin+100000];a=np.empty((len(faces),20),dtype='<f4')
                a[:,:9]=(p.vertices[faces]*.001).reshape(-1,9);a[:,9:18]=p.normals[faces].reshape(-1,9)
                a[:,18]=p.material;a[:,19]=group;stream.write(a.tobytes())
    report=loaded.validate();report.update(counts=counts,triangles=total,seconds=time.time()-start,
        mesh_sha256=stream_hash(meshpath),actual_cybrgeo_save_load_roundtrip=True,image_generation=False)
    (out/'geometry_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
