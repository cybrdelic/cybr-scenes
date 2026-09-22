"""CYBR GEO v7: an irregular spring shelf, lithology-aware debris and basin.

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
RIPPLE_SCALE=.42

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
    edge=1+.18*np.sin(3*a+.55)+.090*np.sin(2*a-1.3)+.038*np.sin(7*a+.9*i)
    edge+=.09*noise(np.asarray(x)*.55,np.asarray(y)*.55)+.025*noise(np.asarray(x)*2.7,np.asarray(y)*2.7)
    return np.sqrt(dx*dx+dy*dy)/edge

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def height(x,y):
    """Continuous alluvium, eroded shelf, irregular sediment bars, in metres."""
    x,y=np.broadcast_arrays(np.asarray(x,dtype=np.float64),np.asarray(y,dtype=np.float64))
    h=.16+.0016*y+.036*fbm(x*.19,y*.19,6)+.005*fbm(x*1.9,y*1.9,5)
    for i,(_,_,rx,ry,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i);d=(q-1)*rx;qi=np.minimum(q,1)
        bed=level+.018-depth*np.maximum(1-qi**2,0)**1.63
        bed+=.13*fbm(x*.72+12,y*.87-4,6)*smooth(.20,.63,q)+.022*fbm(x*4.1,y*4.1,5)
        bank=level+.018+.19*(1-np.exp(-np.maximum(d,0)*1.55))
        shore=np.exp(-((q-1.015)/.25)**2)
        field=d*35+4.0*fbm(x*.66,y*.79,5)+1.3*noise(x*6.7,y*6.7)
        lamina=.014*np.maximum(np.sin(field)-.22,0)**1.3
        cracks=.005*np.exp(-((np.sin(x*13.3+y*9.4+2*fbm(x*1.2,y*1.2,4)))/.07)**2)
        rough=.013*fbm(x*4.2,y*4.2,5)+.0028*noise(x*35,y*35)
        desired=np.where(q<1,bed,bank)+shore*(rough+lamina-cracks)
        blend=1-smooth(1.47,1.93,q);h=h*(1-blend)+desired*blend
    xx=x-(3.55+.29*np.sin(y*1.1)+.11*np.sin(y*3.6))
    h-=.095*np.exp(-(xx/.37)**2)*np.exp(-((y+1.35)/3.3)**4)
    mask=np.exp(-((x-1.)/13)**6-((y-.5)/14)**6)
    h+=(.00075*sediment_microrelief(x,y)+.0006*noise(x*73,y*73))*mask
    return h

def water(x,y,i):
    xx,yy=np.broadcast_arrays(x,y);z=np.zeros_like(xx,dtype=float)+POOLS[i][4]
    for kx,ky,a,phase in MODES:
        z+=a*RIPPLE_SCALE*np.sin(kx*xx+ky*yy+phase+.37*i)
    return z

def rock_template(seed,sub):
    """Fracture-plane intersections, bedding grooves and granular erosion."""
    rng=np.random.default_rng(seed)
    base=trimesh.creation.icosphere(subdivisions=sub)
    directions=base.vertices.copy();f=base.faces.copy()
    normals=np.vstack((trimesh.creation.icosphere(subdivisions=0).vertices+rng.normal(0,.30,(12,3)),rng.normal(size=(7,3))))
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    distances=rng.uniform(.52,1.04,len(normals));den=directions@normals.T
    radial=np.divide(distances[None,:],den,out=np.full_like(den,1e6),where=den>1e-6)
    near=radial.min(axis=1)
    radius=near-np.log(np.sum(np.exp(-(radial-near[:,None])*110),axis=1))/110
    v=directions*radius[:,None];p=v+rng.uniform(-50,50,3)
    weather=np.zeros(len(v))
    for freq,amp in [(5.3,.055),(14.7,.030),(39.3,.012),(92,.005)]:
        weather+=amp*noise(p[:,0]*freq,p[:,1]*freq,p[:,2]*freq)
    bed=v[:,2]+.34*v[:,0]-.11*v[:,1]
    groove=np.exp(-(np.sin(bed*rng.uniform(20,37)+.22*noise(p[:,0]*5,p[:,1]*5))/.13)**2)
    weather-=.023*groove+.05*np.maximum(noise(p[:,0]*23,p[:,1]*23,p[:,2]*23)-.20,0)**1.5
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
    xs=np.unique(np.r_[np.linspace(-125,-14,65),np.linspace(-14,-7,130),np.linspace(-7,8,1301),np.linspace(8,20,130),np.linspace(20,125,65)])
    ys=np.unique(np.r_[np.linspace(-80,-7,35),np.linspace(-7,6,1151),np.linspace(6,18,110),np.linspace(18,105,100)])
    xx,yy=np.meshgrid(xs,ys);v,f,n=gridmesh(xs,ys,height(xx,yy));add('Continuous_irregular_spring_shelf',v,f,n,0)
    print('ground',len(f),flush=True);del xx,yy,v,f,n
    mx=np.linspace(-3800,3800,1301);my=np.linspace(104.9,6400,1001);xx,yy=np.meshgrid(mx,my)
    wx=xx+125*fbm(xx*.0013,yy*.0016,5);wy=yy+165*fbm(xx*.0015+20,yy*.0013-14,5)
    ridge_sum=np.zeros_like(xx);weight=np.ones_like(xx)
    for k in range(8):
        frequency=.00120*2.04**k
        a=(wx*.85+wy*.32)*frequency;b=(wy*.85-wx*.32)*frequency
        ridge=(1-np.abs(noise(a+19*k,b-11*k)))**2
        ridge_sum+=ridge*weight*.52**k;weight=np.clip(ridge*1.9,.05,1)
    ridge_sum=(ridge_sum-.18)/1.50
    envelope=smooth(620,1670,yy)
    broad=.62+.23*np.sin(xx*.00056-1.2)+.17*np.cos(yy*.00051+1.5)
    z=height(xx,yy)+envelope*np.maximum(670*ridge_sum*broad,0)
    z=erode((z/5.7).astype(float),720000,args.seed+700)*5.7
    v,f,n=gridmesh(mx,my,z);add('Eroded_multiscale_basin_ridges',v,f,n,5,
        erosion_droplets=720000,method='Authored ridged multifractal, then hydraulic erosion; not a surveyed site')
    print('mountains',len(f),flush=True)
    def ground(x,y):
        if y<104.9:return float(height(x,y))
        return float(map_coordinates(z,np.array([[(y-my[0])/(my[1]-my[0])],[(x-mx[0])/(mx[1]-mx[0])]]),order=1,mode='nearest')[0])
    # Shore-conforming closed enclosures prevent the former rectangular
    # water caps from leaking visually beyond an elevated bank.
    from contour_water import closed_contour_water
    for i,pool in enumerate(POOLS):
        v,f,n,boundary=closed_contour_water(pool,i,poolq,height,MODES,RIPPLE_SCALE)
        add(f'Closed_water_{i}',v,f,n,6+i,'water',pool=i,**boundary)
        print('water collar',i,boundary,flush=True)
    templates={(sub,k):rock_template(args.seed+sub*100+k,sub) for sub in [1,2,3,4,5,6] for k in range(9 if sub>=5 else 12)}
    stones={1:[],2:[],4:[]};counts={'large_rocks':0,'small_rocks':0,'gravel':0,'mineral_nodules':0,'shrubs':0,'grass_tufts':0}
    # Deliberate hero outcrop, partly buried rather than floating on the terrain.
    placements=[(3.7,1.8,1.23),(4.65,2.5,.91),(3.85,3.75,1.58),
                (5.15,3.6,1.02),(3.30,4.35,.73),(5.75,2.15,.64),
                (3.35,-.55,.46),(4.25,-1.05,.61),(3.95,-2.25,.42),
                (-3.55,3.6,.67),(-3.55,.8,.55),(-4.1,-.65,.39),
                (-2.85,4.2,.36),(-1.6,5.25,.28)]
    def place(x,y,r,sub,mat,kind,burial=.2):
        key=int(rng.integers(9 if sub>=5 else 12));vv,ff,nn=templates[sub,key]
        sizes=r*np.array([rng.uniform(.9,1.35),rng.uniform(.66,1.05),rng.uniform(.65,1.03)])
        az=rng.uniform(0,2*np.pi);tilt=rng.uniform(-.28,.28);co,si=np.cos(az),np.sin(az)
        rz=np.array([[co,-si,0],[si,co,0],[0,0,1]]);ct,st=np.cos(tilt),np.sin(tilt);rt=np.array([[1,0,0],[0,ct,-st],[0,st,ct]])@rz
        v=(vv*sizes)@rt.T;v+=np.array([x,y,ground(x,y)-r*burial]);n=(nn/sizes)@rt.T;n/=np.linalg.norm(n,axis=1)[:,None]
        stones[mat].append((v,ff,n));counts[kind]+=1
    for j,(x,y,r) in enumerate(placements):place(x,y,r,6,2 if j%4 else 1,'large_rocks',.13)
    for j in range(100):
        x=rng.uniform(-23,26);y=rng.uniform(-2,55)
        if min(float(poolq(x,y,i)) for i in range(2))<1.14:continue
        place(x,y,np.exp(rng.uniform(np.log(.12),np.log(.54))),3,2 if rng.random()<.5 else 1,'large_rocks',.25)
    # Gravel concentrates in a few sediment lobes and runnels; quiet fine-sand
    # areas remain quiet. It no longer blankets every square metre equally.
    for j in range(22000):
        x=rng.uniform(-12,14);y=rng.uniform(-7,24)
        q=min(float(poolq(x,y,i)) for i in range(2))
        cluster=smooth(-.05,.60,float(fbm(np.array(x*.53),np.array(y*.49),4)))
        if rng.random()>.06+.60*cluster:continue
        if q<.74 and rng.random()<.85:continue
        radius=np.exp(rng.uniform(np.log(.006),np.log(.064)))
        if radius>.026:kind='small_rocks';sub=2
        else:kind='gravel';sub=1
        place(x,y,radius,sub,1 if rng.random()<.73 else 2,kind,.16)
    # Near-field sediment pockets: dense, embedded millimetre-to-centimetre
    # gravel whose clustering leaves genuinely fine-sediment quiet patches.
    for j in range(31000):
        x=rng.uniform(-3.5,7.0);y=rng.uniform(-5.0,6.2)
        q=min(float(poolq(x,y,i)) for i in range(2))
        cluster=smooth(-.34,.45,float(fbm(np.array(x*.91),np.array(y*.87),4)))
        if rng.random()>.20+.68*cluster:continue
        if q<.65 and rng.random()<.65:continue
        radius=np.exp(rng.uniform(np.log(.004),np.log(.040)))
        place(x,y,radius,2 if radius>.013 else 1,1 if rng.random()<.69 else 2,
              'small_rocks' if radius>.013 else 'gravel',.40)
    # Carbonate nodules cluster on the uneven banks. Mixed sizes and shallow
    # burial avoid the previous equilateral-shard shoreline.
    for j in range(14000):
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
        if q<1.12 or q>1.63 or float(noise(c[0]*.8,c[1]*.8))<.22:continue
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
    fixed=[(-3.8,4.8,.76),(-5.0,1.0,.52),(5.8,3.0,.91),(3.6,7.8,.47),
        (-1.7,7.0,.33),(-4.7,-.5,.62),(-5.4,2,.45),(6.5,.8,.45),
        (-7.,8.,.66),(2.7,9.5,.48),(7.5,7.,.58),(-2.5,5.9,.28)]
    plants=list(fixed)
    for j in range(1000):
        x=rng.uniform(-110,110);y=np.exp(rng.uniform(np.log(6),np.log(520)))
        if rng.random()>.43+.34*float(fbm(x*.037,y*.037,4)):continue
        plants.append((x,y,rng.uniform(.15,.83)*rng.uniform(.65,1.15)))
    for ix,(x,y,h) in enumerate(plants):
        if min(float(poolq(x,y,i)) for i in range(2))<1.18:continue
        base=np.array([x,y,ground(x,y)-.012]);counts['shrubs']+=1
        stretch=rng.uniform(.85,1.48);wind=rng.normal(0,.08,3);wind[2]=0
        crowns=[]
        for j in range(int(rng.integers(9,18))):
            az=rng.uniform(0,2*np.pi);rad=h*rng.uniform(.15,.66)
            axis=np.array([np.cos(az),np.sin(az),0])
            mid=base+axis*rad*.52+[0,0,h*rng.uniform(.16,.34)]
            tip=base+axis*rad*stretch+[0,0,h*rng.uniform(.34,.73)]+wind*h
            wood.extend([stem(base+rng.normal(0,h*.022,3),mid,h*.008),stem(mid,tip,h*.0043)])
            for k in range(int(rng.integers(3,7))):
                a=mid+(tip-mid)*rng.uniform(.3,.95)
                end=a+rng.normal(0,h*.115,3)+[0,0,h*.09]
                wood.append(stem(a,end,h*.0016));crowns.append(end)
        # Batch the independent, folded leaves. No billboard/alpha-card plants.
        nleaf=37 if y<25 else (23 if y<75 else 13)
        centers=np.repeat(crowns,nleaf,axis=0);nn=len(centers)
        centers+=rng.normal(size=(nn,3))*[h*.12,h*.12,h*.085]
        az=rng.uniform(0,2*np.pi,nn);tilt=rng.uniform(-.6,.6,nn)
        ax=np.c_[np.cos(az),np.sin(az),tilt];ax/=np.linalg.norm(ax,axis=1)[:,None]
        side=np.c_[-np.sin(az),np.cos(az),np.zeros(nn)]
        ll=h*rng.uniform(.021,.041,nn);ww=ll*rng.uniform(.37,.63,nn)
        vv=np.stack([centers-ax*ll[:,None],centers+side*ww[:,None],centers+ax*ll[:,None],centers-side*ww[:,None],centers+np.c_[np.zeros((nn,2)),ll*.23]],axis=1).reshape(-1,3)
        ff=(np.arange(nn)[:,None,None]*5+np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])).reshape(-1,3)
        leaves.append((vv,ff,mesh_normals(vv,ff)))
    positions=[(-1.8,-2.8,.25),(-3.5,2.8,.28),(4.9,1.4,.33),(-3.6,-2.5,.28),(5.4,-.1,.4),(-4.7,2.8,.28),(3.8,6.8,.44)]
    positions +=[(rng.uniform(-35,35),rng.uniform(-3,180),rng.uniform(.12,.42)) for _ in range(620)]
    for x,y,h in positions:
        if min(float(poolq(x,y,i)) for i in range(2))<1.16:continue
        counts['grass_tufts']+=1;nb=int(rng.integers(80,190));az=rng.uniform(0,2*np.pi,nb)
        ax=np.c_[np.cos(az),np.sin(az),np.zeros(nb)];side=np.c_[-np.sin(az),np.cos(az),np.zeros(nb)]
        base=np.array([x,y,ground(x,y)])+ax*rng.uniform(0,.07,nb)[:,None]
        length=h*rng.uniform(.48,1.4,nb);bend=length*rng.uniform(.3,.95,nb);width=rng.uniform(.001,.0024,nb)
        t=np.linspace(0,1,7)
        center=base[:,None,:]+ax[:,None,:]*bend[:,None,None]*t[None,:,None]**2
        center[:,:,2]+=length[:,None]*(t-.33*t**3)
        w=width[:,None]*(1-t)**.8+.00006
        vv=np.stack([center-side[:,None,:]*w[:,:,None],center+side[:,None,:]*w[:,:,None]],axis=2).reshape(-1,3)
        local=np.array([[2*k,2*k+1,2*k+3] for k in range(6)]+[[2*k,2*k+3,2*k+2] for k in range(6)])
        ff=(np.arange(nb)[:,None,None]*14+local).reshape(-1,3)
        grass.append((vv,ff,mesh_normals(vv,ff)))
    print('vegetation',counts,flush=True)
    for name,items,mat in [('Curved_dry_grass',grass,3),('Desert_shrub_branches',wood,8),('Curled_small_leaves',leaves,9)]:
        if items:v,f,n=join(items);add(name,v,f,n,mat,'vegetation')
    from carbonate_shelves import carbonate_shelves
    v,f,n=carbonate_shelves(POOLS,poolq)
    add('Porous_overhanging_carbonate_shelves',v,f,n,4,'mineral',
        method='Marching cubes of an authored 3D signed field, not geochemistry',
        spatial_step_m=.006)
    print('overhanging carbonate',len(f),flush=True)
    assembly=Assembly('CYBR_HOT_SPRINGS_V7',parts,mats,metadata={
        'revision':'v7 eroded ridge hierarchy, broken mineral shore, buried fracture geometry, tangled vegetation','seed':args.seed,
        'source_units':'mm','transport_units':'m','no_image_generation':True,'no_photographic_backplates':True,
        'geometry_source':'CYBR GEO Assembly and Part','pools_m':POOLS,'counts':counts,
        'ripples':'32 prescribed modes at 0.42 times original amplitude; not CFD',
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
