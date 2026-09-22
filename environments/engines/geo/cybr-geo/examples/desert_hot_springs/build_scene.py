"""CYBR GEO v10: scale-aware geology, fine sediment and connected vegetation.

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
MODES=np.asarray(json.loads((Path(__file__).parent/'assets/ripple_modes.json').read_text())['modes_kx_ky_amplitude_phase'])
from v11_landforms import height, poolq, rock_template, landscape_ridges, connected_shrub, POOLS, RIPPLE_SCALE, smooth

def water(x,y,i):
    x,y=np.broadcast_arrays(x,y);z=np.zeros_like(x,dtype=float)+POOLS[i][4]
    for kx,ky,a,phase in MODES:z+=a*RIPPLE_SCALE*np.sin(kx*x+ky*y+phase+.37*i)
    return z

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
    xs=np.unique(np.r_[np.linspace(-180,-14,65),np.linspace(-14,-7,130),np.linspace(-7,8,1201),np.linspace(8,20,130),np.linspace(20,180,65)])
    ys=np.unique(np.r_[np.linspace(-80,-7,35),np.linspace(-7,6,1101),np.linspace(6,18,110),np.linspace(18,150,120)])
    xx,yy=np.meshgrid(xs,ys);v,f,n=gridmesh(xs,ys,height(xx,yy));add('Continuous_irregular_spring_shelf',v,f,n,0)
    print('ground',len(f),flush=True);del xx,yy,v,f,n
    mx=np.linspace(-7500,7500,1501);my=np.linspace(149.9,12000,1151)
    cache=out/('ridge_heights_'+hashlib.sha256((Path(__file__).parent/'v11_landforms.py').read_bytes()+(Path(__file__).parent/'fluvial_detail_v9.py').read_bytes()+str(args.seed).encode()).hexdigest()[:14]+'.npy')
    if cache.is_file():z=np.load(cache)
    else:z=landscape_ridges(mx,my,args.seed);np.save(cache,z)
    v,f,n=gridmesh(mx,my,z);add('Continuous_eroded_ridge_backbone',v,f,n,5,erosion_droplets=310000)
    print('mountains',len(f),flush=True)
    def ground(x,y):
        if y<149.9:return float(height(x,y))
        return float(map_coordinates(z,np.array([[(y-my[0])/(my[1]-my[0])],[(x-mx[0])/(mx[1]-mx[0])]]),order=1,mode='nearest')[0])
    # Shore-conforming closed enclosures prevent the former rectangular
    # water caps from leaking visually beyond an elevated bank.
    from contour_water import closed_contour_water
    for i,pool in enumerate(POOLS):
        v,f,n,boundary=closed_contour_water(pool,i,poolq,height,MODES,RIPPLE_SCALE)
        add(f'Closed_water_{i}',v,f,n,6+i,'water',pool=i,**boundary)
        print('water collar',i,boundary,flush=True)
    # Carbonate relief is connected terrain, not disconnected floating shells.
    # Extra apparent roughness comes from the actual normal/material model.
    templates={(sub,k):rock_template(args.seed+sub*100+k,sub) for sub in [0,1,2,3,4,5] for k in range(9 if sub>=5 else 12)}
    stones={1:[],2:[],4:[]};counts={'large_rocks':0,'small_rocks':0,'gravel':0,'mineral_nodules':0,'shrubs':0,'grass_tufts':0}
    # Deliberate hero outcrop, partly buried rather than floating on the terrain.
    placements=[(3.96,2.05,.40),(4.39,2.24,.53),(4.90,2.65,.39),
                (4.04,2.96,.72),(4.64,3.61,.80),(5.16,3.73,.44),
                (3.64,3.91,.36),(4.87,4.04,.37),(5.48,2.76,.28),
                (3.55,.41,.25),(4.08,-.73,.24),(3.95,-2.2,.21),
                (-3.74,3.62,.32),(-3.58,1.08,.24),(-4.14,-.65,.22),
                (-2.81,4.3,.17)]
    # Outcrop joint fragments form a grounded cluster instead of five foam blocks.
    for _ in range(42):
        placements.append((rng.uniform(3.62,5.52),rng.uniform(1.9,4.6),rng.uniform(.09,.30)))
    def place(x,y,r,sub,mat,kind,burial=.2):
        key=int(rng.integers(9 if sub>=5 else 12));vv,ff,nn=templates[sub,key]
        sizes=r*np.array([rng.uniform(.9,1.35),rng.uniform(.66,1.05),rng.uniform(.47,.83)])
        az=rng.uniform(0,2*np.pi);tilt=rng.uniform(-.28,.28);co,si=np.cos(az),np.sin(az)
        rz=np.array([[co,-si,0],[si,co,0],[0,0,1]]);ct,st=np.cos(tilt),np.sin(tilt);rt=np.array([[1,0,0],[0,ct,-st],[0,st,ct]])@rz
        v=(vv*sizes)@rt.T
        span=np.ptp(v[:,2]);bottom=v[:,2].min()
        buried_fraction=np.clip(burial+.25,.25,.78)
        v+=np.array([x,y,ground(x,y)-bottom-buried_fraction*span]);n=(nn/sizes)@rt.T;n/=np.linalg.norm(n,axis=1)[:,None]
        stones[mat].append((v,ff,n));counts[kind]+=1
    for j,(x,y,r) in enumerate(placements):place(x,y,r,5 if r>.35 else 4,2 if j%3 else 1,'large_rocks',.08)
    # Refraction now reveals actual submerged fragments and shelves. They are
    # embedded in the same bed mesh, not a caustic texture projected on a bowl.
    submerged=0
    for _ in range(3800):
        x=rng.uniform(-4.1,4.2);y=rng.uniform(-3.8,5.1)
        q=float(poolq(x,y,0))
        patch=smooth(-.08,.48,float(fbm(x*.94+7,y*.87+12,4)))
        if not .59<q<.98 or rng.random()>.025+.28*patch:continue
        r=np.exp(rng.uniform(np.log(.026),np.log(.17)))
        place(x,y,r,2 if r<.075 else 3,1 if rng.random()<.76 else 2,'small_rocks',.15)
        submerged+=1
    print('submerged rock shelf fragments',submerged,flush=True)
    for j in range(100):
        x=rng.uniform(-23,26);y=rng.uniform(-2,55)
        if min(float(poolq(x,y,i)) for i in range(2))<1.14:continue
        place(x,y,np.exp(rng.uniform(np.log(.12),np.log(.54))),3,2 if rng.random()<.5 else 1,'large_rocks',.25)
    # Gravel concentrates in a few sediment lobes and runnels; quiet fine-sand
    # areas remain quiet. It no longer blankets every square metre equally.
    for j in range(26000):
        x=rng.uniform(-12,14);y=rng.uniform(-7,24)
        q=min(float(poolq(x,y,i)) for i in range(2))
        cluster=smooth(-.05,.60,float(fbm(np.array(x*.53),np.array(y*.49),4)))
        if rng.random()>.06+.60*cluster:continue
        if q<.90 and rng.random()<.90:continue
        radius=np.exp(rng.uniform(np.log(.006),np.log(.064)))
        if radius>.026:kind='small_rocks';sub=2
        else:kind='gravel';sub=1
        place(x,y,radius,sub,1 if rng.random()<.63 else 2,kind,.36)
    # Near-field sediment pockets: dense, embedded millimetre-to-centimetre
    # gravel whose clustering leaves genuinely fine-sediment quiet patches.
    for j in range(32000):
        x=rng.uniform(-3.5,7.0);y=rng.uniform(-5.0,6.2)
        q=min(float(poolq(x,y,i)) for i in range(2))
        cluster=smooth(-.34,.45,float(fbm(np.array(x*.91),np.array(y*.87),4)))
        if rng.random()>.20+.68*cluster:continue
        if q<.90 and rng.random()<.90:continue
        radius=np.exp(rng.uniform(np.log(.005),np.log(.045)))
        place(x,y,radius,2 if radius>.013 else 1,1 if rng.random()<.69 else 2,
              'small_rocks' if radius>.013 else 'gravel',.39)
    # Real sub-centimetre grit: use 20-triangle clasts rather than copying a
    # gravel photograph into displaced large tiles. The rendered footprint is
    # normally subpixel, with larger clasts resolving in the detail view.
    for j in range(65000):
        x=rng.uniform(-3.7,7.0);y=rng.uniform(-5.0,5.8)
        q=float(poolq(x,y,0))
        cluster=smooth(-.48,.50,float(fbm(x*.74,y*.84,4)))
        if rng.random()>.28+.59*cluster:continue
        if q<.90 and rng.random()<.95:continue
        radius=np.exp(rng.uniform(np.log(.0020),np.log(.013)))
        place(x,y,radius,0,1 if rng.random()<.72 else 2,'gravel',.44)
    # Sparse flat carbonate flakes, not an uninterrupted porous ring.
    for j in range(6500):
        x=rng.uniform(-6,7);y=rng.uniform(-4,7);q=float(poolq(x,y,0))
        if q<1.02 or q>1.38 or float(fbm(x*1.1,y*1.2,4))<.22:continue
        r=rng.uniform(.007,.032)
        vv,ff,nn=rock_template(args.seed+j,1)
        sizes=np.array([r,r*rng.uniform(.45,.9),r*rng.uniform(.08,.21)]);v=vv*sizes+[x,y,ground(x,y)+.0008]
        nn=nn/sizes;nn/=np.linalg.norm(nn,axis=1)[:,None]
        stones[4].append((v,ff,nn));counts['mineral_nodules']+=1
    for mat,items in stones.items():
        if items:v,f,n=join(items);add(f'Buried_weathered_rock_and_sediment_{mat}',v,f,n,mat,'stones')
    stones.clear();templates.clear();del items,v,f,n;gc.collect()
    print('stones',counts,flush=True)
    # Irregular small plate islands, confined to genuinely dry evaporative banks.
    pts=rng.uniform([-7,-6],[8,13],(10500,2));vor=Voronoi(pts);chips=[]
    for k,regid in enumerate(vor.point_region):
        ids=vor.regions[regid]
        if len(ids)<3 or -1 in ids:continue
        c=pts[k];q=float(poolq(*c,0));poly=vor.vertices[ids]
        if q<1.18 or q>1.60 or float(noise(c[0]*.8,c[1]*.8))<.22:continue
        if np.max(np.linalg.norm(poly-c,axis=1))>.7:continue
        poly=c+(poly-c)*rng.uniform(.984,.995)
        if np.sum(poly[:,0]*np.roll(poly[:,1],-1)-poly[:,1]*np.roll(poly[:,0],-1))<0:poly=poly[::-1]
        # Multiple samples along each edge prevent smooth ideal polygon outlines.
        edge=[]
        for a,b in zip(poly,np.roll(poly,-1,axis=0)):
            d=b-a;side=np.array([-d[1],d[0]])
            for t in [0,.3,.65]:edge.append(a+d*t+side*rng.uniform(-.038,.038))
        edge=np.asarray(edge);nn=len(edge);top=np.c_[edge,height(edge[:,0],edge[:,1])+.0018]
        center=np.r_[c,float(height(*c))+.0008];v=np.vstack((center,top,top-[0,0,.004]));f=[]
        for j in range(nn):a=j+1;b=(j+1)%nn+1;f.extend([[0,a,b],[a,a+nn,b+nn],[a,b+nn,b]])
        f=np.asarray(f);chips.append((v,f,mesh_normals(v,f)))
    if chips:v,f,n=join(chips);add('Cupped_dry_mud_microplates',v,f,n,0,'mineral',count=len(chips))
    chips.clear();gc.collect()
    grass=[];wood=[];leaves=[]
    plants=[(-3.75,4.8,1.02),(-5.,1.,.79),(5.8,3.,1.08),(3.6,7.8,.65),
        (-1.7,7.,.49),(-4.7,-.5,.70),(-5.4,2.,.65),(6.5,.8,.55),(-7.,8.,.88),
        (2.7,9.5,.83),(7.5,7.,.94),(-2.5,5.9,.41),(-6.,14.,.83),(4.5,14,.93),
        (-.5,18,.82),(9.2,15,.86),(-9,13,.85)]
    plants += [(-3.85,-.70,.66),(-4.55,1.70,.76),(-2.70,5.65,.72),
               (5.70,1.20,.88),(5.20,5.15,.94),(1.20,7.55,.75),(-6.35,5.60,.98),
               (-3.60,-2.75,.47),(4.94,-1.02,.58),(6.3,2.55,.72)]
    for i in range(780):
        x=rng.uniform(-85,85);y=np.exp(rng.uniform(np.log(8),np.log(410)))
        if rng.random()>.30+.37*smooth(-.25,.35,float(fbm(x*.055,y*.065,4))):continue
        plants.append((x,y,rng.uniform(.36,1.1)))
    for x,y,h in plants:
        if min(float(poolq(x,y,k)) for k in range(2))<1.20:continue
        w,l=connected_shrub(rng,np.array([x,y,ground(x,y)-.008]),h,0 if y<28 else 1,stem)
        wood+=w;leaves+=l;counts['shrubs']+=1
    print('attached shrubs',counts['shrubs'],flush=True)
    positions=[(-1.8,-2.8,.25),(-3.5,2.8,.28),(4.9,1.4,.33),(-3.6,-2.5,.28),(5.4,-.1,.4),(-4.7,2.8,.28),(3.8,6.8,.44)]
    positions += [(-2.82,-2.70,.34),(3.56,-2.64,.32),(4.48,-1.15,.39),
                  (-3.75,.80,.40),(3.51,5.20,.45),(2.54,5.68,.33)]
    positions +=[(rng.uniform(-35,35),rng.uniform(-3,180),rng.uniform(.12,.42)) for _ in range(400)]
    for x,y,h in positions:
        if min(float(poolq(x,y,i)) for i in range(2))<1.12:continue
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
        if items:
            v,f,n=join(items);add(name,v,f,n,mat,'vegetation')
            items.clear();del v,f,n;gc.collect()
    assembly=Assembly('CYBR_HOT_SPRINGS_V11',parts,mats,metadata={
        'revision':'V11 jointed mesogeometry, routed spur ridges, reconstructed granular support, connected compact vegetation','seed':args.seed,
        'source_units':'mm','transport_units':'m','no_image_generation':True,'no_photographic_backplates':True,
        'geometry_source':'CYBR GEO Assembly and Part','pools_m':POOLS,'counts':counts,
        'ripples':'128 prescribed directional modes; 0.6 mm RMS; not CFD',
        'limitations':['Authored landscape, not a site scan','Authored steam, not CFD','Authored reflectance, not measured spectra']})
    assembly.save(out/'scene')
    if not args.no_glb:assembly.export_glb(out/'scene.glb')
    del assembly,parts,stones,grass,wood,leaves,chips,templates;gc.collect()
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
