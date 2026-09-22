"""Deterministic desert geothermal landscape authored as a real CYBR GEO Assembly.

Geometry is generated in metres, stored by CYBR GEO in millimetres, and exported
through a metre-native transport adapter. A CC0 photographic grayscale gravel
texture guides authored microrelief and modulates albedo; no generated images or backplates. This is an authored
landscape, not a site survey, a geology simulation, or a thermofluid solution.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import Voronoi, ConvexHull, HalfspaceIntersection
from scipy.ndimage import gaussian_filter, map_coordinates
from numba import njit, vectorize, float64
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from cybrgeo import Assembly, Part, Material

SEED = 9132026
POOLS = [(0.5, 0.0, 3.55, 2.65, 0.07, 1.6), (-3.8, 7.0, 2.4, 1.72, 0.235, 0.9)]

# Photo-guided, authored microrelief. Grayscale is NOT a measured height map.
# The original photograph is also used in the albedo shader, so location and
# scale are correlated rather than independently randomized. Relief is kept
# within millimetres; all silhouette/occlusion comes from the resulting mesh.
_photo=np.asarray(Image.open(Path(__file__).parent/'assets/gravel_periodic.pgm'),dtype=np.float64)/255
_photo=np.where(_photo<=.04045,_photo/12.92,((_photo+.055)/1.055)**2.4)
PHOTO_HEIGHT=gaussian_filter(_photo/_photo.mean(),1.05,mode='wrap')

@vectorize([float64(float64,float64)],nopython=True)
def photo_microheight(x,y):
    u=(x*.917+y*.399)/1.3*512-.5
    v=(y*.917-x*.399)/1.3*512-.5
    ix=int(np.floor(u));iy=int(np.floor(v));fx=u-ix;fy=v-iy
    x0=ix%512;y0=iy%512;x1=(ix+1)%512;y1=(iy+1)%512
    value=(PHOTO_HEIGHT[y0,x0]*(1-fx)+PHOTO_HEIGHT[y0,x1]*fx)*(1-fy)+(PHOTO_HEIGHT[y1,x0]*(1-fx)+PHOTO_HEIGHT[y1,x1]*fx)*fy
    return max(0.,value-.18)**.72



@vectorize([float64(float64,float64,float64)], nopython=True, cache=True)
def _noise3(x,y,z):
    ix=int(np.floor(x));iy=int(np.floor(y));iz=int(np.floor(z))
    fx=x-ix;fy=y-iy;fz=z-iz
    ux=fx*fx*(3-2*fx);uy=fy*fy*(3-2*fy);uz=fz*fz*(3-2*fz)
    result=0.
    for a in range(2):
        for b in range(2):
            for c in range(2):
                hh=np.uint32(np.uint32(ix+a)*np.uint32(374761393)+np.uint32(iy+b)*np.uint32(668265263)+np.uint32(iz+c)*np.uint32(2147483647)+np.uint32(1274126177))
                hh=np.uint32(np.uint32(hh ^ (hh >> np.uint32(13)))*np.uint32(1274126177))
                hh=np.uint32(hh ^ (hh >> np.uint32(16)))
                value=float(hh)/4294967295.*2-1
                result+=value*(ux if a else 1-ux)*(uy if b else 1-uy)*(uz if c else 1-uz)
    return result

def noise(x,y,z=0.):
    return _noise3(x,y,z)


def fbm(x, y, octaves=5):
    result = np.zeros(np.broadcast(x,y).shape)
    for i in range(octaves):
        f = 2.07**i
        result += noise(x*f+11*i, y*f-7*i, i*.31) * .5**i
    return result


def poolq(x, y, i):
    cx,cy,rx,ry,level,depth=POOLS[i]
    dx,dy=(x-cx)/rx,(y-cy)/ry
    angle=np.arctan2(dy,dx)
    edge=1 + .14*np.sin(3*angle+.7+i) + .058*np.sin(7*angle-1.4) + .015*np.sin(13*angle+i)
    edge+= .050*noise(np.asarray(x)*.83,np.asarray(y)*.83) + .024*noise(np.asarray(x)*3.4,np.asarray(y)*3.4)
    return np.sqrt(dx*dx+dy*dy)/edge


def height(x, y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    h=.20 + .0035*y + .042*fbm(x*.22,y*.22,6) + .002*noise(x*19,y*19)
    for i,(_,_,_,_,level,depth) in enumerate(POOLS):
        q=poolq(x,y,i)
        qi=np.minimum(q,1.)
        bed=level+.028-depth*(1-qi**3.6)
        bed+= .045*fbm(x*2.1,y*2.1,4)*np.minimum(q,1)
        bed+= .004*noise(x*23,y*23)
        terrace=.040*np.sin(np.minimum(q,1.15)*63 + .45*fbm(x*2,y*2,3))
        terrace*=np.exp(-((q-.92)/.13)**2)
        bank=level+.028+.13*(1-np.exp(-np.maximum(q-1,0)*2.9))
        bank+=.027*np.exp(-((q-1.075)/.067)**2)*(1+.95*noise(x*6,y*6))
        bank+= .0024*fbm(x*15,y*15,4)+.0005*noise(x*80,y*80)
        desired=np.where(q<1,bed+terrace,bank)
        blend=np.clip((1.48-q)/.24,0,1);blend=blend*blend*(3-2*blend)
        h=h*(1-blend)+desired*blend
    line=x-(3.48+.32*np.sin(y*1.9))
    drain=np.exp(-(line/.20)**2)*np.exp(-((y+1.7)/2.4)**4)
    h-=.040*drain
    # Resolve this relief only in the fine-tessellated foreground; no distant
    # subpixel height noise or invented photogrammetric calibration.
    mask=np.clip((8-np.abs(x-1))/2,0,1)*np.clip((7-np.abs(y+1))/2,0,1)
    h+=.0012*photo_microheight(x,y)*mask*(1+.28*noise(x*.8,y*.8))
    return h

RIPPLE_MODES=np.asarray(json.loads((Path(__file__).parent/'assets/ripple_modes.json').read_text())['modes_kx_ky_amplitude_phase'])

def water(x,y,i):
    # Authored broadband ripple modes, not a solved hydrodynamic simulation.
    xx,yy=np.broadcast_arrays(x,y)
    result=np.zeros_like(xx,dtype=float)+POOLS[i][4]
    for kx,ky,amplitude,phase in RIPPLE_MODES:
        result+=amplitude*np.sin(kx*xx+ky*yy+phase+.37*i)
    return result


def gridmesh(xs, ys, heights):
    xx,yy=np.meshgrid(xs,ys)
    v=np.column_stack((xx.ravel(),yy.ravel(),heights.ravel()))
    ny,nx=xx.shape
    index=np.arange(nx*ny).reshape(ny,nx)
    a=index[:-1,:-1].ravel(); b=index[:-1,1:].ravel(); c=index[1:,1:].ravel(); d=index[1:,:-1].ravel()
    f=np.vstack((np.column_stack((a,b,c)),np.column_stack((a,c,d))))
    gy,gx=np.gradient(heights,ys,xs)
    normals=np.column_stack((-gx.ravel(),-gy.ravel(),np.ones(nx*ny)))
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    return v,f,normals


def mesh_normals(v,f):
    n=np.zeros_like(v)
    face=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    for j in range(3): np.add.at(n,f[:,j],face)
    n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-20)
    return n


def join(items):
    vs,fs,ns=[],[],[]; offset=0
    for v,f,n in items:
        vs.append(v);fs.append(f+offset);ns.append(n);offset+=len(v)
    return np.concatenate(vs),np.concatenate(fs),np.concatenate(ns)


@njit(cache=True)
def erode(a, droplets, seed):
    np.random.seed(seed)
    h,w=a.shape
    for drop in range(droplets):
        x=np.random.uniform(2,w-3);y=np.random.uniform(2,h-3)
        dx=dy=0.;speed=1.;water=1.;sediment=0.
        for life in range(48):
            ix=int(x);iy=int(y);fx=x-ix;fy=y-iy
            old=(a[iy,ix]*(1-fx)+a[iy,ix+1]*fx)*(1-fy)+(a[iy+1,ix]*(1-fx)+a[iy+1,ix+1]*fx)*fy
            gx=(a[iy,ix+1]-a[iy,ix])*(1-fy)+(a[iy+1,ix+1]-a[iy+1,ix])*fy
            gy=(a[iy+1,ix]-a[iy,ix])*(1-fx)+(a[iy+1,ix+1]-a[iy,ix+1])*fx
            dx=dx*.08-gx*.92;dy=dy*.08-gy*.92
            ll=(dx*dx+dy*dy)**.5
            if ll<1e-9:break
            dx/=ll;dy/=ll
            xn=x+dx;yn=y+dy
            if xn<2 or xn>w-3 or yn<2 or yn>h-3:break
            jx=int(xn);jy=int(yn);fxx=xn-jx;fyy=yn-jy
            new=(a[jy,jx]*(1-fxx)+a[jy,jx+1]*fxx)*(1-fyy)+(a[jy+1,jx]*(1-fxx)+a[jy+1,jx+1]*fxx)*fyy
            dh=new-old
            cap=max(-dh,.015)*speed*water*3.
            if sediment>cap or dh>0:
                amount=min(dh,sediment) if dh>0 else (sediment-cap)*.18
                sediment-=amount
                a[iy,ix]+=amount*(1-fx)*(1-fy);a[iy,ix+1]+=amount*fx*(1-fy)
                a[iy+1,ix]+=amount*(1-fx)*fy;a[iy+1,ix+1]+=amount*fx*fy
            else:
                amount=min((cap-sediment)*.12,-dh,.35)
                for yy in range(-1,2):
                    for xx in range(-1,2):
                        ww=.25 if xx==0 and yy==0 else (.125 if xx==0 or yy==0 else .0625)
                        a[iy+yy,ix+xx]-=amount*ww
                sediment+=amount
            speed=max(.01,(speed*speed-dh*2)**.5) if speed*speed-dh*2>0 else .01
            speed=min(speed,4.0);water*=.97;x=xn;y=yn
    return a


def stream_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=REPO.parent/'output')
    parser.add_argument('--seed',type=int,default=SEED)
    parser.add_argument('--no-glb',action='store_true')
    args=parser.parse_args(); root=args.out;root.mkdir(parents=True,exist_ok=True)
    start=time.time(); rng=np.random.default_rng(args.seed); parts=[]
    materials=[
        Material('Mineral sediment',(.46,.365,.25),0,.72),
        Material('Pale weathered limestone',(.53,.48,.39),0,.68),
        Material('Desert varnish rock',(.20,.16,.11),0,.63),
        Material('Dry desert grass',(.34,.23,.085),0,.84),
        Material('Fractured mineral crust',(.54,.47,.34),0,.74),
        Material('Distant stony ridges',(.31,.29,.265),0,.91),
        Material('Spring water main - native transmission',(.19,.35,.38),0,.025),
        Material('Spring water upper - native transmission',(.19,.35,.38),0,.025),
        Material('Dry woody shrubs',(.19,.125,.062),0,.92),
        Material('Sparse muted shrub leaves',(.20,.22,.10),0,.9)]

    def add(name,v,f,n,mat,group='landscape',**metadata):
        parts.append(Part(name,v*1000,f,n,material=mat,group=group,
                          role='Authored environmental mesh, not analytic CAD or surveyed geology',
                          metadata=metadata))

    # Nonuniform tessellation retains centimetre-scale foreground geometry and
    # smoothly relaxes far from the camera. No screen-space displaced plane.
    xs=np.unique(np.r_[np.linspace(-29,-10,65),np.linspace(-10,-4,121),np.linspace(-4,-1,151),np.linspace(-1,6,1001),np.linspace(6,11,251),np.linspace(11,30,65)])
    ys=np.unique(np.r_[np.linspace(-18,-7,56),np.linspace(-7,-5,101),np.linspace(-5,3,1144),np.linspace(3,14,251),np.linspace(14,46,105)])
    xx,yy=np.meshgrid(xs,ys)
    v,f,n=gridmesh(xs,ys,height(xx,yy));add('Displaced_mineral_ground',v,f,n,0,geometry='actual displaced triangles')
    print('terrain',len(f),'triangles',flush=True)

    # An outer continuation and genuine distant ridge meshes, not a backplate.
    xs2=np.linspace(-1400,1400,701);ys2=np.linspace(45.8,1600,651)
    xx,yy=np.meshgrid(xs2,ys2)
    envelope=np.clip((yy-70)/180,0,1);envelope=envelope*envelope*(3-2*envelope)
    warp=70*fbm(xx*.0029,yy*.0037,4)
    broad=(52+35*fbm((xx+warp)*.0028,yy*.0023,6))
    broad+=59*np.exp(-((xx+100)/180)**2-((yy-390)/200)**2)
    broad+=90*np.exp(-((xx-380)/230)**2-((yy-800)/290)**2)
    ridges=broad*np.exp(-((yy-680)/900)**2)
    ridge_noise=fbm((xx+warp)*.015,yy*.011,7)
    ridges+=27*ridge_noise
    ridges-=14*np.abs(fbm(xx*.048+yy*.006,yy*.014,5))
    zz=height(xx,yy)+envelope*np.maximum(ridges,0)
    zz=erode(zz.astype(np.float64),200000,args.seed+813)*(1-envelope*.015)
    # Smooth the coarse erosion field, then evaluate it with cubic reconstruction
    # on a camera-aware LOD grid. This changes silhouette/occlusion geometry,
    # rather than disguising coarse triangles with normal maps.
    fine_x=np.unique(np.r_[np.linspace(-1400,-450,191),np.linspace(-450,200,1301),np.linspace(200,1400,241)])
    fine_y=np.unique(np.r_[np.linspace(45.8,260,308),np.linspace(260,650,196),np.linspace(650,1600,191)])
    fx,fy=np.meshgrid(fine_x,fine_y)
    coords=np.array([(fy-ys2[0])/(ys2[1]-ys2[0]),(fx-xs2[0])/(xs2[1]-xs2[0])])
    fine_z=map_coordinates(gaussian_filter(zz,.60),coords,order=3,mode='nearest')
    v,f,n=gridmesh(fine_x,fine_y,fine_z);add('Fluvially_incised_basin_ridges',v,f,n,5,
        erosion='200000 deterministic hydraulic droplets; artistic terrain, not a surveyed site')
    # Wider flat terrain closes side rays below the sky.
    for name,xl,xh in [('West_plain',-320,-28.9),('East_plain',29.9,320)]:
        xa=np.linspace(xl,xh,100);ya=np.linspace(-50,46,90);xx,yy=np.meshgrid(xa,ya)
        v,f,n=gridmesh(xa,ya,.2+.003*yy+.12*fbm(xx*.1,yy*.1,4));add(name,v,f,n,0)

    for i,(cx,cy,rx,ry,_,_) in enumerate(POOLS):
        xs=np.linspace(cx-rx*1.30,cx+rx*1.30,601 if i==0 else 361)
        ys=np.linspace(cy-ry*1.30,cy+ry*1.30,481 if i==0 else 281)
        xx,yy=np.meshgrid(xs,ys)
        v,f,n=gridmesh(xs,ys,water(xx,yy,i))
        # Complete closed volume. Invisible sides lie behind opaque banks.
        nx=len(xs);ny=len(ys)
        boundary=np.r_[np.arange(nx),np.arange(2*nx-1,nx*ny,nx),
                       np.arange(nx*ny-2,nx*(ny-1)-1,-1),np.arange(nx*(ny-2),0,-nx)]
        top=v[boundary]; bottom=top.copy();bottom[:,2]=-2.5
        sidev=np.vstack((top,bottom));nn=len(top);a=np.arange(nn);b=(a+1)%nn
        sidef=np.vstack((np.c_[a,a+nn,b+nn],np.c_[a,b+nn,b]))
        sidef=np.vstack((sidef,np.c_[np.full(nn-2,nn),np.arange(nn+2,2*nn),np.arange(nn+1,2*nn-1)]))
        sv,sf,sn=sidev,sidef,mesh_normals(sidev,sidef)
        v,f,n=join([(v,f,n),(sv,sf,sn)])
        add(f'Closed_spring_water_{i+1}',v,f,n,6+i,'water',optics='16-band absorption; achromatic IOR 1.334',water_pool=i)

    # Weathered, irregular stone templates. Every placed stone is real mesh.
    templates={}
    for sub in (0,1,2,3,4):
        for j in range(12):
            if sub<=1:
                base=trimesh.creation.icosphere(subdivisions=sub)
                vv=base.vertices.copy();ff=base.faces.copy()
                vv*= (1+.21*noise(vv[:,0]*3+j,vv[:,1]*3,vv[:,2]*3))[:,None]
            else:
                directions=rng.normal(size=(18,3));directions/=np.linalg.norm(directions,axis=1)[:,None]
                directions=np.vstack((directions,np.eye(3),-np.eye(3)))
                distances=rng.uniform(.66,1.20,len(directions))
                halves=np.c_[directions,-distances]
                verts=HalfspaceIntersection(halves,np.zeros(3)).intersections
                hull=ConvexHull(verts)
                ff=hull.simplices.copy()
                for k,face in enumerate(ff):
                    if np.dot(np.cross(verts[face[1]]-verts[face[0]],verts[face[2]]-verts[face[0]]),verts[face].mean(axis=0))<0:
                        ff[k]=face[::-1]
                vv=verts
                for _ in range(sub):vv,ff=trimesh.remesh.subdivide(vv,ff)
                edges=np.unique(np.sort(np.vstack((ff[:,[0,1]],ff[:,[1,2]],ff[:,[2,0]])),axis=1),axis=0)
                counts_v=np.bincount(edges.ravel(),minlength=len(vv))
                for iteration in range(2):
                    average=np.zeros_like(vv)
                    np.add.at(average,edges[:,0],vv[edges[:,1]])
                    np.add.at(average,edges[:,1],vv[edges[:,0]])
                    vv=vv*.55+.45*average/np.maximum(counts_v,1)[:,None]
                nn=mesh_normals(vv,ff)
                relief=.021*fbm(vv[:,0]*5+j*19,vv[:,1]*5+vv[:,2]*7,5)
                relief+=.005*noise(vv[:,0]*27+j,vv[:,1]*29,vv[:,2]*26)
                bedding=np.sin((vv[:,2]+.21*vv[:,0])*28 + 1.2*fbm(vv[:,0]*4+j,vv[:,1]*4,3))
                relief-= .025*np.maximum(0,1-np.abs(bedding)*7)
                vv+=nn*relief[:,None]
            templates[sub,j]=(vv,ff,mesh_normals(vv,ff))
    rock_items={1:[],2:[]}; counts={'boulders':0,'stones':0,'gravel':0,'grass_tufts':0,'shrubs':0}
    settings=[('boulders',38,(.24,.76),4),('stones',1400,(.028,.15),2),('gravel',22000,(.008,.045),1)]
    for kind,count,scale,sub in settings:
        for k in range(count):
            # Spatially clustered, never a decorative evenly spaced grid.
            x=rng.uniform(-11,13);y=rng.uniform(-9,22)
            if kind=='gravel':x,y=rng.uniform(-10,11),rng.uniform(-9,16)
            if kind=='boulders':
                x,y=rng.uniform(-10,12),rng.uniform(-1,26)
                if rng.random()<.65:x=rng.normal(4.7,1.2);y=rng.normal(3.5,2.1)
            q=min(float(poolq(x,y,j)) for j in range(2))
            if q<1.08 and kind=='boulders': continue
            if q<.75 and rng.random()<.87:continue
            if q<.98 and rng.random()<.45:continue
            if kind=='gravel' and y>10 and rng.random()<.45:continue
            radius=np.exp(rng.uniform(np.log(scale[0]),np.log(scale[1])))
            stone_lod=2 if kind=='gravel' and 0<x<6 and -5<y<1 else sub
            v0,f0,n0=templates[stone_lod,int(rng.integers(12))]
            sizes=radius*np.array([rng.uniform(.75,1.5),rng.uniform(.65,1.2),rng.uniform(.40,.90)])
            az=rng.uniform(0,2*np.pi);co,si=np.cos(az),np.sin(az)
            r=np.array([[co,-si,0],[si,co,0],[0,0,1]])
            v=(v0*sizes)@r.T
            z=float(height(x,y))+sizes[2]*.04
            v+=np.array([x,y,z]);n=(n0/sizes)@r.T;n/=np.linalg.norm(n,axis=1)[:,None]
            mat=1 if rng.random()<.35 else 2
            rock_items[mat].append((v,f0,n));counts[kind]+=1
    for mat,items in rock_items.items():
        v,f,n=join(items);add(f'Irregular_rock_scatter_{mat}',v,f,n,mat,'stones',placed_stones=sum(counts[k] for k in ('boulders','stones','gravel')))
    print('stone geometry',counts,flush=True)

    # Thick, separated crust plates create real cracks and little overhangs.
    pts=rng.uniform([-9,-8],[11,13],(15000,2))
    vor=Voronoi(pts)
    chips=[]
    for i,region_index in enumerate(vor.point_region):
        region=vor.regions[region_index]
        if len(region)<3 or -1 in region:continue
        center=pts[i];x,y=center
        q=min(float(poolq(x,y,j)) for j in range(2))
        if q<1.04 or q>1.65 or rng.random()<.13:continue
        if 0<x<7 and y<2:continue # expose detailed granular bank instead of large crust plates
        poly=vor.vertices[region]
        if np.max(np.linalg.norm(poly-center,axis=1))>1:continue
        # Leave narrow, nonzero, explicit gaps between the plates.
        poly=center+(poly-center)*rng.uniform(.971,.989)
        area=np.sum(poly[:,0]*np.roll(poly[:,1],-1)-poly[:,1]*np.roll(poly[:,0],-1))
        if area<0:poly=poly[::-1]
        jagged=[]
        for j in range(len(poly)):
            a,b=poly[j],poly[(j+1)%len(poly)]
            direction=b-a;perp=np.array([-direction[1],direction[0]])
            for t in [0,.23,.52,.78]:
                jagged.append(a+(b-a)*t+perp*rng.uniform(-.037,.037))
        poly=np.array(jagged)
        top=np.c_[poly,height(poly[:,0],poly[:,1])+.0018+rng.uniform(.0003,.0011)]
        cen=np.r_[poly.mean(axis=0),float(height(*poly.mean(axis=0)))+.0024]
        nv=len(poly); vv=np.vstack((cen,top,top-np.array([0,0,.0045])))
        ff=[]
        for k in range(nv):
            a=k+1;b=(k+1)%nv+1
            ff.extend([[0,a,b],[a,a+nv,b+nv],[a,b+nv,b]])
        ff=np.array(ff,dtype=int);nn=mesh_normals(vv,ff);chips.append((vv,ff,nn))
    if chips:
        v,f,n=join(chips);add('Separated_mineral_crust_plates',v,f,n,4,'mineral_crust',plate_count=len(chips))

    # Curved blade ribbons and branched woody stems, not billboard sprites.
    grass=[]; wood=[]; leaves=[]
    for k in range(820):
        y=rng.uniform(-8,120);x=rng.uniform(-25,25) if y<20 else -.65*y+rng.uniform(-.65*y,.65*y)
        q=min(float(poolq(x,y,j)) for j in range(2))
        if q<1.25:continue
        if -3<x<4 and y<4 and rng.random()<.7:continue
        tall=rng.uniform(.12,.52)*(1 if y<18 else 1.2)
        for b in range(int(rng.integers(22,56))):
            az=rng.uniform(0,2*np.pi);s=rng.uniform(.025,.24)
            ground=float(height(x,y)) if y<45.8 else float(map_coordinates(fine_z,np.array([[np.interp(y,fine_y,np.arange(len(fine_y)))],[np.interp(x,fine_x,np.arange(len(fine_x)))]]),order=1)[0])
            base=np.array([x+np.cos(az)*s,y+np.sin(az)*s,ground])
            length=tall*rng.uniform(.55,1.5);bend=rng.uniform(.18,.95)*length
            axis=np.array([np.cos(az),np.sin(az),0]);width=rng.uniform(.002,.006)
            side=np.array([-np.sin(az),np.cos(az),0])
            vv=[]
            for t in np.linspace(0,1,5):
                p=base+np.array([0,0,length*(t-.18*t*t)])+axis*(bend*t*t)
                w=width*(1-t)**.65+.0001
                vv.extend([p-side*w,p+side*w])
            vv=np.array(vv);ff=[]
            for j in range(4):ff.extend([[2*j,2*j+1,2*j+3],[2*j,2*j+3,2*j+2]])
            ff=np.array(ff);grass.append((vv,ff,mesh_normals(vv,ff)))
        counts['grass_tufts']+=1
    v,f,n=join(grass);add('Curved_dry_grass_blades',v,f,n,3,'vegetation',tuft_count=counts['grass_tufts'])

    def stem(p,q,radius):
        d=q-p;d/=np.linalg.norm(d)
        u=np.cross(d,[0,0,1])
        if np.linalg.norm(u)<.01:u=np.cross(d,[0,1,0])
        u/=np.linalg.norm(u);w=np.cross(d,u)
        a=np.arange(5)*2*np.pi/5
        offsets=np.cos(a)[:,None]*u+np.sin(a)[:,None]*w
        vv=np.vstack((p+offsets*radius,q+offsets*radius*.45))
        ff=[]
        for j in range(5):a=j;b=(j+1)%5;ff.extend([[a,b,b+5],[a,b+5,a+5]])
        ff=np.array(ff);return vv,ff,mesh_normals(vv,ff)
    for k in range(310):
        y=rng.uniform(7,180);x=-.65*y+rng.uniform(-.55*y,.55*y)
        if min(float(poolq(x,y,j)) for j in range(2))<1.4:continue
        ground=float(height(x,y)) if y<45.8 else float(map_coordinates(fine_z,np.array([[np.interp(y,fine_y,np.arange(len(fine_y)))],[np.interp(x,fine_x,np.arange(len(fine_x)))]]),order=1)[0])
        base=np.array([x,y,ground]); h=rng.uniform(.32,1.1)
        for j in range(int(rng.integers(28,46))):
            az=rng.uniform(0,2*np.pi);offset=np.array([np.cos(az),np.sin(az),0])*h*rng.uniform(.25,.7)
            p=base+np.array([0,0,h*.16]);tip=base+offset+np.array([0,0,h*rng.uniform(.45,1.1)])
            wood.append(stem(p,tip,.0055*h))
            for b in range(5):
                source=p+(tip-p)*rng.uniform(.40,.88)
                angle=az+rng.uniform(-1.3,1.3)
                end=source+np.array([np.cos(angle),np.sin(angle),rng.uniform(.2,.8)])*h*.23
                wood.append(stem(source,end,.0022*h))
                for l in range(7):
                    c=source+(end-source)*(l+.5)/7
                    a=np.array([np.cos(angle),np.sin(angle),.6]) *.032*h
                    bvec=np.array([-np.sin(angle),np.cos(angle),.12]) *.012*h
                    vv=np.array([c-a,c+bvec,c+a,c-bvec]);ff=np.array([[0,1,2],[0,2,3]])
                    leaves.append((vv,ff,mesh_normals(vv,ff)))
        counts['shrubs']+=1
    for name,items,mat in [('Branched_desert_shrubs',wood,8),('Sparse_shrub_leaf_geometry',leaves,9)]:
        if items:
            v,f,n=join(items);add(name,v,f,n,mat,'vegetation')

    assembly=Assembly('CYBR_DESERT_HOT_SPRINGS',parts,materials,metadata={
        'authoring':'Procedural scene built with cybrgeo.Assembly and cybrgeo.Part',
        'seed':args.seed,'source_units':'mm','transport_units':'m',
        'no_image_generation':True,'no_photographic_backplates':True,'photographic_albedo_detail':'CC0 Gravel04 grayscale via scikit-image; not measured PBR','microrelief':'photo-guided authored height, NOT measured photogrammetry','revision':'v4 correlated photo-guided microgeometry',
        'scene_type':'Authored geothermal desert, not a specific real location',
        'counts':counts,'pools_m':POOLS,
        'limitations':['No thermal or groundwater simulation','Steam is an authored density field',
                       'Water waves are authored geometry, not CFD','No measured site reflectance data',
                       'GLB is geometry/preview only; native spectral/volume materials are not baked']})
    assembly.save(root/'scene')
    if not args.no_glb:assembly.export_glb(root/'desert_hot_springs.glb')
    # Unmodified CYBR GEO is the scene authority; native triangles are derived
    # only from the saved/loaded Assembly, not a separate look-alike model.
    del assembly,parts,rock_items,grass,wood,leaves,chips
    import gc;gc.collect()
    loaded=Assembly.load(root/'scene')
    meshpath=root/'scene.meshbin'
    with meshpath.open('wb') as stream:
        total=sum(len(p.faces) for p in loaded.parts)
        stream.write(np.uint32(total).tobytes())
        for group,p in enumerate(loaded.parts):
            data=np.empty((len(p.faces),20),dtype='<f4')
            data[:,:9]=(p.vertices[p.faces]*.001).reshape(-1,9)
            data[:,9:18]=p.normals[p.faces].reshape(-1,9)
            data[:,18]=p.material;data[:,19]=group;stream.write(data.tobytes())
    report=loaded.validate()
    report.update(counts=counts,seconds=time.time()-start,seed=args.seed,
        transport_mesh_sha256=stream_hash(meshpath),
        generated_images_used=False,actual_cybrgeo_save_load_roundtrip=True)
    (root/'geometry_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    (root/'camera.json').write_text(json.dumps({
       'hero':{'origin':[4.3,-6.1,2.6],'target':[-1.0,2.4,.30],'horizontal_fov_degrees':70},
       'detail':{'origin':[4.,-5.7,2.0],'target':[1.6,-1.65,.11],'horizontal_fov_degrees':64}},indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
