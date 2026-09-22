"""Connected flooded mineral cathedral. Authored fracture-cell CSG, not a geology solver.
All visible structures are 3D. No synthesized backgrounds or image generation.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.spatial import ConvexHull,HalfspaceIntersection,cKDTree
from scipy.spatial.transform import Rotation
from skimage.measure import marching_cubes
import trimesh
from build_scene import Writer,noise,fbm,normalize,normals,grid_faces,make_textures
from src.quartz_growth import polyhedron,rotation,NORMALS
ROOT=Path(__file__).resolve().parent
SEED=735019
RNG=np.random.default_rng(SEED)

def basin_height(x,y):
    center=-.3+1.1*np.sin(y*.135+.3);width=6.5+1.0*np.sin(y*.12+.4)
    q=np.abs((x-center)/width);z=np.minimum(-2.8+3.35*np.clip(q,0,1.3)**2.7,1.25)
    z+=.18*fbm(x*.37,y*.37,octaves=4)+.045*fbm(x*2.4,y*2.4,octaves=3)
    z+=.035*np.sin(y*5.0+.7*noise(x*.8,y*.6))*np.exp(-((q-.65)/.25)**2)
    return z+.65*np.exp(-((y+4)/5.5)**2)*np.exp(-((x-2)/4.5)**2)

def wave_height(x,y):
    return .075+.012*np.sin(1.08*x+1.48*y)+.006*np.sin(-2.31*x+2.05*y+1.2)+.002*np.sin(5.7*x-3.2*y+.4)

def ellipsoid(x,y,z,c,r):
    return (np.sqrt(((x-c[0])/r[0])**2+((y-c[1])/r[1])**2+((z-c[2])/r[2])**2)-1)*min(r)

def smooth_union(a,b,k=.95):
    h=np.clip(.5+.5*(b-a)/k,0,1);return b*(1-h)+a*h-k*h*(1-h)

def cavity_field(x,y,z):
    f=ellipsoid(x,y,z,(0,9,5.6),(11.8,23.5,10.5))
    for c,r,k in [((7.5,20,5.7),(8.1,14.7,8.0),1.6),((-3.5,33,4.8),(6.8,13.8,7.0),1.4),((-1.5,-12,4.2),(7,11,7.3),1.3),((-5.5,43,3.8),(3.1,10,4.6),.8)]:
        f=smooth_union(f,ellipsoid(x,y,z,c,r),k)
    f=smooth_union(f,ellipsoid(x,y,z,(1.2,12.8,19.8),(6.3,8.4,12.5)),.65)
    f=smooth_union(f,ellipsoid(x,y,z,(-4.8,2.0,20.0),(2.6,4.3,10.8)),.5)
    f+=.8*noise(x*.13+4,y*.14-8,z*.18)+.34*noise(x*.36,y*.31,z*.3)+.09*noise(x*.9,y*.7,z*.82)
    # Finite exterior roof: the former deep shafts become true shallow collapses.
    return np.minimum(f,17.1+.48*noise(x*.22,y*.19)-z)

def build_cave(w,out):
    step=.155;lo=np.array([-17.,-20.,-5.5])
    xs=np.arange(-17,18+step/2,step,dtype='f4');ys=np.arange(-20,55+step/2,step,dtype='f4');zs=np.arange(-5.5,25+step/2,step,dtype='f4')
    field=np.empty((len(zs),len(ys),len(xs)),dtype='f4');X,Y=np.meshgrid(xs,ys)
    # Fracture-aligned cellular bedrock: classify irregular 3D cells as solid
    # or excavated, then reconstruct their common boundary. This creates a
    # connected jointed cliff, not isolated scan blocks pasted on a smooth wall.
    seeds_rng=np.random.default_rng(40017)
    gx,gy,gz=np.meshgrid(np.arange(-23,25,1.9),np.arange(-27,64,2.25),np.arange(-12,33,1.25),indexing='ij')
    seeds=np.c_[gx.ravel(),gy.ravel(),gz.ravel()]
    seeds+=seeds_rng.uniform(-.43,.43,seeds.shape)*[1.9,2.25,1.25]
    seeds[:,2]+=.055*seeds[:,0]+.045*seeds[:,1]
    values=cavity_field(seeds[:,0],seeds[:,1],seeds[:,2])
    void_tree=cKDTree(seeds[values<0]);solid_tree=cKDTree(seeds[values>=0])
    xy=np.c_[X.ravel(),Y.ravel()]
    for j,z in enumerate(zs):
        pts=np.c_[xy,np.full(len(xy),z)]
        dv=void_tree.query(pts,workers=5)[0];ds=solid_tree.query(pts,workers=5)[0]
        cellular=(.5*(dv-ds)).reshape(X.shape)
        field[j]=.78*cellular+.22*cavity_field(X,Y,z)
    vv,ff,_,_=marching_cubes(field,0,spacing=(step,step,step),allow_degenerate=False)
    vv=vv[:,[2,1,0]]+lo;ff=ff[:,::-1];tri=vv[ff]
    ff=ff[tri[:,:,2].max(1)>-3.7]
    nn=normals(vv,ff)
    levels=np.array([-10,-4,-2,-.8,.2,1.1,1.7,2.85,3.3,4.4,5.35,6.0,7.2,8.05,8.5,9.8,10.6,11.5,12.1,13.6,14.2,15.4,16.1,17.5,18.8,20,22,24,28])
    offsets=np.random.default_rng(873).uniform(-.11,.19,len(levels))
    zz=vv[:,2]+.067*vv[:,1]+.045*vv[:,0]+.17*noise(vv[:,0]*.27,vv[:,1]*.29)
    gap=np.min(np.abs(zz[:,None]-levels[3:-4]),axis=1)
    relief=np.interp(zz,levels,offsets)-.055*np.exp(-(gap/.04)**2)+.025*fbm(vv[:,0]*4.1,vv[:,1]*4.1,vv[:,2]*4.1,3)
    height=np.asarray(Image.open(ROOT/'assets/inputs/cybr-geo/examples/desert_hot_springs_v2/assets/rock_boulder_dry_disp_4k.jpg').convert('L').resize((2048,2048),Image.Resampling.LANCZOS),dtype='f4')/255
    weights=np.abs(nn)**4;weights/=np.maximum(weights.sum(1,keepdims=True),1e-9)
    for axis,inds in enumerate([(1,2),(0,2),(0,1)]):
        u=np.mod(vv[:,inds[0]]*.52,1)*(height.shape[1]-1);v=np.mod(vv[:,inds[1]]*.52,1)*(height.shape[0]-1)
        relief+=.075*weights[:,axis]*(map_coordinates(height,[v,u],order=1,mode='wrap')-.5)
    vv+=nn*relief[:,None]
    tint=np.tile([1.25,1.31,1.34],(len(vv),1));leach=np.clip(.5+.9*noise(vv[:,0]*.36,vv[:,1]*.25,vv[:,2]*.035),0,1);tint*=1+.15*leach[:,None]
    w.add('Continuous_fracture_cell_bedrock_and_collapsed_roof',vv,ff,mat=0,tex=-2,col=tint)
    np.savez_compressed(out/'cavern_surface.npz',vertices=vv.astype('f4'),faces=ff.astype('u4'))
    return vv,ff

class Batch:
    def __init__(self):self.v=[];self.f=[];self.c=[];self.count=0
    def add(self,v,f,col):
        v=np.asarray(v);self.v.append(v);self.f.append(np.asarray(f)+self.count);self.c.append(np.broadcast_to(col,(len(v),3)).copy());self.count+=len(v)
    def flush(self,w,name,mat,tex=-1,flat=False):
        if self.count:w.add(name,np.concatenate(self.v),np.concatenate(self.f),mat=mat,tex=tex,col=np.concatenate(self.c),flat=flat)

def tube(points,radii,sides=9):
    pts=np.asarray(points);rs=np.broadcast_to(radii,(len(pts),));tangent=normalize(np.gradient(pts,axis=0));ref=np.tile([0,1,0],(len(pts),1));ref[np.abs(tangent[:,1])>.95]=[1,0,0]
    side=normalize(np.cross(tangent,ref));up=np.cross(side,tangent);theta=np.arange(sides)*2*np.pi/sides
    vv=pts[:,None,:]+rs[:,None,None]*(np.cos(theta)[None,:,None]*side[:,None,:]+np.sin(theta)[None,:,None]*up[:,None,:])
    i=np.arange((len(pts)-1)*sides).reshape(-1,sides);j=np.roll(i,-1,axis=1)
    f=np.r_[np.c_[i.ravel(),j.ravel(),(i+sides).ravel()],np.c_[j.ravel(),(j+sides).ravel(),(i+sides).ravel()]]
    return vv.reshape(-1,3),f

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'assets/built_v3');args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    ar=ROOT/'assets/inputs/cybr-geo/examples/desert_hot_springs_v3/assets';make_textures(ar,out);w=Writer(out);cave_v,cave_f=build_cave(w,out)
    X,Y=np.meshgrid(np.linspace(-18,19,490),np.linspace(-18,55,790));Z=basin_height(X,Y)
    w.add('Eroded_basin_with_submerged_foreground_shelves',np.c_[X.ravel(),Y.ravel(),Z.ravel()],grid_faces(*X.shape),mat=1,tex=-3,col=[1.4,1.55,1.58])
    X,Y=np.meshgrid(np.linspace(-18,19,280),np.linspace(-18,55,580));Z=wave_height(X,Y);vv=np.c_[X.ravel(),Y.ravel(),Z.ravel()];ff=grid_faces(*X.shape);ny,nx=X.shape
    bd=np.r_[np.arange(nx),np.arange(2*nx-1,ny*nx,nx),np.arange(ny*nx-2,(ny-1)*nx-1,-1),np.arange((ny-2)*nx,0,-nx)]
    n=len(vv);bottom=vv[bd].copy();bottom[:,2]=-7;vv=np.r_[vv,bottom];sides=[]
    for i,j in enumerate(bd):
        k=(i+1)%len(bd);sides.extend([[j,n+i,n+k],[j,n+k,bd[k]]])
    cen=len(vv);vv=np.r_[vv,[[.5,18.5,-7]]];b=n+np.arange(len(bd));ff=np.r_[ff,np.array(sides),np.c_[np.full(len(bd),cen),np.roll(b,-1),b]]
    w.add('Closed_wave_resolved_lake',vv,ff,mat=6)
    protos=[];scans={}
    for name in ['boulder_01','namaqualand_boulder_02','namaqualand_boulder_03']:
        mesh=next(iter(trimesh.load(ar/name/f'{name}_2k.gltf',force='scene',process=False).geometry.values()));R=np.array([[1,0,0],[0,0,-1],[0,1,0]])
        p=np.asarray(mesh.vertices)@R.T;n=np.asarray(mesh.vertex_normals)@R.T;p-=np.r_[(p.max(0)[:2]+p.min(0)[:2])/2,p[:,2].min()];p/=np.ptp(p,axis=0).max();uv=np.asarray(mesh.visual.uv).copy();uv[:,1]=1-uv[:,1];f=np.array(mesh.faces)
        _,inv=np.unique(np.round(p/.045).astype(int),axis=0,return_inverse=True);pc=np.zeros((inv.max()+1,3));nc=pc.copy();count=np.bincount(inv);np.add.at(pc,inv,p);np.add.at(nc,inv,n);pc/=count[:,None];nc=normalize(nc)
        p2=pc[inv];n2=nc[inv];good=np.linalg.norm(np.cross(p2[f[:,1]]-p2[f[:,0]],p2[f[:,2]]-p2[f[:,0]]),axis=1)>1e-9;protos.append(((p,f,n,uv),(p2,f[good],n2,uv)))
    def rock(name,xyz,size,index=0,scale=(1,1,1),rot=(0,0,0),hero=False,tint=(1,1,1)):
        p,f,n,uv=protos[index][0 if hero else 1];R=Rotation.from_euler('xyz',rot).as_matrix();s=size*np.asarray(scale);v=(p*s)@R.T+xyz;norm=normalize((n/s)@R.T)
        w.add(name,v,f,mat=2,tex=index,uv=uv,n=norm,col=np.array(tint)*RNG.uniform(.94,1.05))
        if hero:scans[name]=(v,f)
        return name
    hero=rock('Quartz_bearing_fracture',[4.,.2,-.25],5.,0,(1.05,1.15,.55),(.08,-.1,-.65),True,(1.05,1.04,1.0))
    rock('Right_bank_recessed_support',[6.1,2.6,-.1],4.8,1,(1,1.2,.72),(.02,.08,1.0),True,(1.1,1.09,1.05))
    rock('Foreground_split_wet_ledge',[-5.2,-5.7,-.42],3.6,2,(1.1,.9,.55),(.02,.13,1.9),True,(.92,1,1))
    rock('Left_midground_outcrop',[-7.,6.5,-.15],6.3,1,(.85,1.3,.82),(.05,-.1,2.6),True,(1.13,1.18,1.2))
    farhero=rock('Far_mineral_vein',[7.8,14.5,-.05],3.9,2,(1,1.3,.7),(.12,.04,-.8),True,(1.02,1.08,1.12))
    rock('Back_collapse',[-4.8,26,-.2],4.1,0,(1,1.15,.65),(.1,.1,.6),True,(1.12,1.2,1.19))
    for j in range(65):
        y=RNG.uniform(-9,44);x=RNG.choice([-1,1])*RNG.uniform(6,10);z=float(basin_height(x,y));s=RNG.uniform(.28,1.7)
        rock(f'Bank_talus_{j:03}',[x,y,z-.23*s],s,j%3,(1,RNG.uniform(.8,1.3),RNG.uniform(.48,.82)),tuple(RNG.uniform(-.17,.17,2))+(RNG.uniform(0,6.28),),False,(1.05,1.11,1.14))
    # Scanned collapse fragments are used at the roof rim only. The main
    # continuous chamber above is authored fracture-cell geometry, not a scan.
    medium=[]
    for p,f,n,uv in [a[0] for a in protos]:
        _,inv=np.unique(np.round(p/.011).astype(int),axis=0,return_inverse=True)
        pc=np.zeros((inv.max()+1,3));nc=pc.copy();cnt=np.bincount(inv)
        np.add.at(pc,inv,p);np.add.at(nc,inv,n);pc/=cnt[:,None];nc=normalize(nc)
        v=pc[inv];good=np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1)>1e-9
        medium.append((v,f[good],nc[inv],uv))
    def cliff(name,xyz,size,index,scale,rot):
        p,f,n,uv=medium[index];R=Rotation.from_euler('xyz',rot).as_matrix();sz=size*np.asarray(scale)
        v=(p*sz)@R.T+xyz;normal=normalize((n/sz)@R.T)
        w.add(name,v,f,mat=0,tex=index,n=normal,uv=uv,col=np.array([1.25,1.38,1.44])*RNG.uniform(.88,1.14))
    roof_tree=cKDTree(cave_v[:,:2])
    for j in range(14):
        a=j*2*np.pi/14+RNG.uniform(-.10,.1);x=1.2+6.8*np.cos(a);y=12.8+9.0*np.sin(a)
        ids=roof_tree.query_ball_point([x,y],.45)
        zc=cave_v[ids,2] if ids else np.array([16.])
        zc=zc[(zc>7)&(zc<22)]
        z=float(zc.min())+.35 if len(zc) else 16.
        cliff(f'Collapsed_oculus_block_{j}',[x,y,z],RNG.uniform(.65,1.45),j%3,(1.4,1.35,.7),(np.pi+RNG.uniform(-.2,.2),RNG.uniform(-.2,.2),a))
    stones=Batch();unit=trimesh.creation.icosphere(subdivisions=1)
    for j in range(7200):
        x=RNG.uniform(-8.5,9);y=RNG.uniform(-10,44)
        if RNG.random()>.35+.55*np.clip(.5+noise(x*.4,y*.4),0,1):continue
        r=np.exp(RNG.uniform(np.log(.014),np.log(.25)));z=float(basin_height(x,y));R=Rotation.random(random_state=RNG).as_matrix();p=np.asarray(unit.vertices).copy();p*=1+.19*RNG.normal(size=(len(p),1));p=(p*[r,r*RNG.uniform(.6,1.4),r*RNG.uniform(.25,.53)])@R.T+[x,y,z+.16*r]
        stones.add(p,unit.faces,np.array([.88,.93,.91])*RNG.uniform(.65,1.42))
    stones.flush(w,'Graded_angular_gravel',2,-2)
    anchors=[];cores=Batch();inclusions=Batch()
    def anchor(name,x,y):
        v,f=scans[name];t=v[f];d=np.array([0.,0.,-1.]);o=np.array([x,y,7.]);e1=t[:,1]-t[:,0];e2=t[:,2]-t[:,0];p=np.cross(d,e2);det=(e1*p).sum(1);inv=np.divide(1.,det,out=np.zeros_like(det),where=abs(det)>1e-10);q=o-t[:,0];u=(q*p).sum(1)*inv;qq=np.cross(q,e1);v2=(qq*d).sum(1)*inv;dist=(e2*qq).sum(1)*inv
        valid=(abs(det)>1e-10)&(u>=0)&(v2>=0)&(u+v2<=1)&(dist>0)
        if not valid.any():return None
        k=np.argmin(np.where(valid,dist,np.inf));n=normalize(np.cross(e1[k],e2[k]));n=n if n[2]>=0 else -n
        return o+d*dist[k],n
    def point(name,origin,width,height,axis,spin,large):
        offsets=np.r_[width*RNG.uniform(.84,1.17,6),height*.625*RNG.uniform(.96,1.04,6),width*.24];v,f,_=polyhedron(offsets);planes=np.c_[NORMALS,-offsets];hull=ConvexHull(v);eq=hull.equations;extra=[]
        for i,neighbors in enumerate(hull.neighbors):
            for j in neighbors:
                if j<=i or np.dot(eq[i,:3],eq[j,:3])>.998:continue
                n=eq[i,:3]+eq[j,:3];n/=np.linalg.norm(n);extra.append(np.r_[n,-(v@n).max()+width*.010])
        if RNG.random()<.25:
            nn=normalize(np.array([RNG.uniform(-.4,.4),RNG.uniform(-.4,.4),1]));extra.append(np.r_[nn,-(v@nn).max()+height*RNG.uniform(.04,.14)])
        if extra:
            pp=np.r_[planes,np.array(extra)];inside=v.mean(0)
            if np.max(pp[:,:3]@inside+pp[:,3])<-1e-8:
                v=HalfspaceIntersection(pp,inside).intersections;h=ConvexHull(v);f=h.simplices.copy();n=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);flip=np.einsum('ij,ij->i',n,v[f].mean(1)-v.mean(0))<0;f[flip]=f[flip][:,::-1]
        # Retriangulate the actual float32 positions that the native renderer
        # receives. This removes tiny half-space slivers before serialization,
        # rather than deleting individual faces and opening dielectric shells.
        quantum=width*2e-4
        v=np.unique(np.round(v/quantum)*quantum,axis=0)
        R=rotation(axis,spin);p=(v@R.T+origin).astype('f4').astype(float)
        for repair in range(20):
            hull=ConvexHull(p);f=hull.simplices.copy()
            fn=np.cross(p[f[:,1]]-p[f[:,0]],p[f[:,2]]-p[f[:,0]])
            bad=np.flatnonzero(np.linalg.norm(fn,axis=1)<2e-9)
            if not len(bad):break
            # Eliminate the redundant nearly collinear corner, then construct
            # a new CLOSED convex hull. Never delete just the tiny triangle.
            remove=[]
            for j in bad:
                ids=f[j];q=p[ids];lengths=[np.linalg.norm(q[1]-q[2]),np.linalg.norm(q[2]-q[0]),np.linalg.norm(q[0]-q[1])]
                remove.append(ids[int(np.argmax(lengths))])
            keep=np.ones(len(p),dtype=bool);keep[np.unique(remove)]=False
            p=p[keep];v=v[keep]
        else:raise RuntimeError('Unable to repair float32 crystal slivers: '+name)
        flipped=np.einsum('ij,ij->i',fn,p[f].mean(1)-p.mean(0))<0
        f[flipped]=f[flipped][:,::-1]
        w.add(name,p,f,mat=8 if large else 9,flat=True)
        if large and RNG.random()<.7:
            c=v*.76;c[:,2]*=.38;c[:,0]+=.08*width;cores.add(c@R.T+origin,f,[.28,.30,.29])
        if large:
            for k in range(RNG.integers(1,4)):
                r=width*RNG.uniform(.055,.095);c=np.array([RNG.uniform(-.2,.2)*width,RNG.uniform(-.25,.25)*width,RNG.uniform(.18,.52)*height]);shape=np.array([[-r,0,0],[.7*r,-.4*r,0],[r,.2*r,.001],[0,r,.003]])
                inclusions.add((shape+c)@R.T+origin,[[0,1,2],[0,2,3]],[.07,.065,.06])
    for ci,(obj,cx,cy,scale,total) in enumerate([(hero,3.9,.2,1.,32),(farhero,7.8,14.5,.53,24)]):
        accepted=[]
        for attempt in range(total*7):
            if len(accepted)>=total:break
            xx=cx+RNG.uniform(-1.7,.9)*scale;yy=cy+RNG.uniform(-1.65,.7)*scale
            if abs((yy-cy)*.75+.4*(xx-cx))>.7*scale:continue
            hit=anchor(obj,xx,yy)
            if hit is None:continue
            p,n=hit
            if n[2]<.38:continue
            wi=RNG.uniform(.075,.16)*scale
            if any(np.linalg.norm(p-q)<1.5*(wi+r) for q,r in accepted):continue
            h=wi*RNG.uniform(4.4,7.8);axis=normalize(n*.38+[RNG.normal(-.24,.29),RNG.normal(-.12,.23),.8]);accepted.append((p,wi));point(f'Beveled_quartz_{ci}_{len(accepted):02}',p-axis*wi*.1,wi,h,axis,RNG.uniform(0,6.28),ci==0)
            anchors.append({'host':obj,'surface_point':p.tolist(),'axis':axis.tolist(),'width':wi,'height':h})
        for j in range(190 if ci==0 else 65):
            xx=cx+RNG.uniform(-1.7,1.1)*scale;yy=cy+RNG.uniform(-1.6,.9)*scale
            if abs((yy-cy)*.75+.4*(xx-cx))>.65*scale:continue
            hit=anchor(obj,xx,yy)
            if hit is None:continue
            p,n=hit;wi=RNG.uniform(.022,.056)*scale
            if n[2]<.32 or any(np.linalg.norm(p-q)<1.3*r+.025 for q,r in accepted):continue
            point(f'Fracture_druse_{ci}_{j:03}',p-n*.012,wi,wi*RNG.uniform(1.9,3.5),normalize(n+[0,0,.5]),RNG.uniform(0,6.28),False)
    cores.flush(w,'Milky_mineral_roots_inside_quartz',3,flat=True);inclusions.flush(w,'Embedded_mineral_platelets',3,flat=True);(out/'crystal_anchors_v3.json').write_text(json.dumps(anchors,indent=2))
    tree=cKDTree(cave_v[:,:2]);drip=Batch();root=Batch();foliage=Batch()
    for j in range(125):
        x=RNG.uniform(-9,10);y=RNG.uniform(-4,38);idx=tree.query_ball_point([x,y],.22)
        if not idx:continue
        zs=cave_v[idx,2];ok=zs[(zs>6)&(zs<17.3)]
        if not len(ok):continue
        z=float(ok.min());length=np.exp(RNG.uniform(np.log(.35),np.log(3.2)));radius=length*RNG.uniform(.075,.16);t=np.linspace(0,1,42);rings=24;theta=np.arange(rings)*2*np.pi/rings;rr=radius*((1-t)**.67+.018)*(1+.14*np.sin(t*31+j));zz=z+.11-length*t
        p=np.stack(np.broadcast_arrays(x+rr[:,None]*np.cos(theta)*(1+.11*np.sin(theta*7+j)),y+rr[:,None]*np.sin(theta)*(1+.11*np.sin(theta*7+j)),zz[:,None]),axis=-1);p[:,:,:2]+=.006*noise(p[:,:,0]*14,p[:,:,1]*14,p[:,:,2]*8)[:,:,None]
        i=np.arange((len(t)-1)*rings).reshape(-1,rings);k=np.roll(i,-1,axis=1);f=np.r_[np.c_[i.ravel(),k.ravel(),(i+rings).ravel()],np.c_[k.ravel(),(k+rings).ravel(),(i+rings).ravel()]];drip.add(p.reshape(-1,3),f,[1.48,1.44,1.28])
    drip.flush(w,'Anchored_fluted_dripstone',5,-2)
    for j in range(48):
        a=RNG.uniform(0,2*np.pi);cx,cy=(1.2,12.8) if j<31 else (-4.8,2);rx,ry=(6.6,8.7) if j<31 else (2.8,4.4);x=cx+rx*np.cos(a);y=cy+ry*np.sin(a);z=17.5 if j<31 else 16.3;ids=tree.query_ball_point([x,y],.7)
        if ids:
            zs=cave_v[ids,2];ok=zs[(zs>10)&(zs<23)]
            if len(ok):z=float(ok.min())+.1
        length=RNG.uniform(1.3,4.7);t=np.linspace(0,1,27);points=np.c_[x+.1*np.sin(t*7+j)*t,y+.13*np.sin(t*9+j)*t,z-length*t];v,f=tube(points,.02*(1-.8*t),7);root.add(v,f,[.13,.10,.06])
        if j%2==0:
            for k in [11,17]:
                tt=np.linspace(0,1,12);start=points[k];side=RNG.choice([-1,1]);ps=start+np.c_[side*.2*np.sin(tt*2),tt*.12,-tt*.8];v,f=tube(ps,.007*(1-.9*tt),5);root.add(v,f,[.13,.10,.055])
    root.flush(w,'Branching_roof_roots',3)
    for j in range(32):
        y=RNG.uniform(1,23);x=RNG.choice([-1,1])*RNG.uniform(6.5,8.8);z=float(basin_height(x,y));scale=RNG.uniform(.35,.75)
        for k in range(RNG.integers(4,8)):
            ang=RNG.uniform(0,2*np.pi);direction=np.array([np.cos(ang),np.sin(ang),0]);side=np.array([-np.sin(ang),np.cos(ang),0])
            for l in range(1,15):
                t=l/16;center=np.array([x,y,z])+direction*(scale*.78*t)+[0,0,scale*np.sin(t*2.1)*.72];leaflen=scale*.22*np.sin(t*np.pi)**.6
                for s in [-1,1]:
                    tip=center+side*s*leaflen+direction*scale*.07;mid=(center+tip)*.5+[0,0,.025*scale];wid=scale*.038*(1-t*.65);v=np.array([center,mid-direction*wid,tip,mid+direction*wid,mid+[0,0,.007]])
                    foliage.add(v,[[0,1,4],[1,2,4],[2,3,4],[3,0,4]],RNG.uniform(.75,1.2)*np.array([.065,.125,.022]))
    foliage.flush(w,'Divided_fern_fronds',4)
    w.close();manifest=json.loads((out/'geometry_manifest.json').read_text());manifest.update(seed=SEED,revision='V3',scene='Connected flooded mineral cathedral',image_generation=False)
    (out/'geometry_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'triangles':w.count,'parts':len(w.parts)}),flush=True)
if __name__=='__main__':main()
