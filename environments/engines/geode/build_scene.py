"""Build a new metre-native CYBR GEO cavern from the two supplied archives.
No generative assets. Continuous displaced cave, scanned rocks, actual quartz
half-space facets, closed displaced water, explicit rubble and mineral druse.
"""
from __future__ import annotations
import argparse, hashlib, json, math, shutil, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.spatial.transform import Rotation
from scipy.spatial import cKDTree
import trimesh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from quartz_growth import polyhedron, rotation
SEED=20260920
rng=np.random.default_rng(SEED)

def normalize(v):
    return v/np.maximum(np.linalg.norm(v,axis=-1,keepdims=True),1e-15)

def noise(x,y,z=0.):
    x,y,z=np.broadcast_arrays(x,y,z)
    ix=np.floor(x).astype(np.int64); iy=np.floor(y).astype(np.int64); iz=np.floor(z).astype(np.int64)
    u=x-ix;v=y-iy;w=z-iz
    u=u*u*(3-2*u);v=v*v*(3-2*v);w=w*w*(3-2*w)
    out=np.zeros(x.shape)
    for a in range(2):
      for b in range(2):
       for c in range(2):
        h=((ix+a)*374761393+(iy+b)*668265263+(iz+c)*2147483647+1274126177)&0xffffffff
        h=((h^(h>>13))*1274126177)&0xffffffff;h=h^(h>>16)
        out+=(h*(2/4294967295)-1)*(u if a else 1-u)*(v if b else 1-v)*(w if c else 1-w)
    return out

def fbm(x,y,z=0.,octaves=5):
    out=0.;amp=1.
    for i in range(octaves):
        out=out+amp*noise(x,y,z);x=x*2.07+11;y=y*2.07-7;z=z*2.07+.31;amp*=.49
    return out

def normals(v,f):
    q=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    n=np.zeros_like(v)
    for k in range(3):np.add.at(n,f[:,k],q)
    return normalize(n)

def grid_faces(ny,nx):
    i=np.arange((ny-1)*nx).reshape(ny-1,nx)[:,:-1].ravel()
    return np.concatenate([np.c_[i,i+1,i+nx],np.c_[i+1,i+nx+1,i+nx]])

def pool_q(x,y):
    X=(x-.55*np.sin(y*.20))/5.6;Y=(y-9)/21
    a=np.arctan2(Y,X)
    return np.sqrt(X*X+Y*Y)/(1+.055*np.sin(5*a)+.035*np.sin(9*a+1)+.024*noise(x*1.4,y*1.4))

def floor_height(x,y):
    q=pool_q(x,y)
    z=np.where(q<1,-.02-2.25*(1-np.minimum(q,1)**1.9),.6*(1-np.exp(-(q-1)*7)))
    # Irregular pale submerged shelves, not a hard disc around the waterline.
    z+=.08*fbm(x*.5,y*.5)+.021*fbm(x*6,y*6,octaves=3)
    z+=.08*np.exp(-((q-.86)/.10)**2)*(.6+.4*noise(x*1.7,y*1.7))
    return z

def water_height(x,y):
    return .075+.010*np.sin(1.25*x+1.7*y)+.004*np.sin(-2.8*x+3.3*y+1.2)+.0012*np.sin(8.5*x-2.3*y+.4)

class Writer:
    def __init__(self,out):
        self.out=out;self.parts=[];self.count=0
        self.f=(out/'scene.meshbin').open('wb');self.f.write(b'CVR2'+struct.pack('<I',0))
        self.wire=[]
    def add(self,name,v,f,mat=0,tex=-1,uv=None,col=None,n=None,flat=False):
        v=np.asarray(v,float);f=np.asarray(f,np.int64)
        a=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
        keep=np.linalg.norm(a,axis=1)>(0.0 if mat in (6,8,9) else 1e-10);f=f[keep]
        if len(f)==0:return
        if n is None:n=normals(v,f)
        ns=np.repeat(normalize(a[keep])[:,None,:],3,axis=1) if flat else n[f]
        if uv is None:uv=np.zeros((len(v),2))
        if col is None:col=np.ones((len(v),3))
        if np.asarray(col).shape==(3,):col=np.broadcast_to(col,(len(v),3))
        # 36 float32 per triangle: xyz(9), normals(9), ids(2), UV(6), color(9), texture(1).
        data=np.c_[v[f].reshape(-1,9),ns.reshape(-1,9),np.full(len(f),mat),np.full(len(f),len(self.parts)),uv[f].reshape(-1,6),col[f].reshape(-1,9),np.full(len(f),tex)].astype('<f4')
        assert data.shape[1]==36 and np.isfinite(data).all()
        self.f.write(data.tobytes());self.count+=len(f)
        self.parts.append(dict(name=name,triangles=len(f),vertices=len(v),material=mat,texture=tex,bounds=[v.min(0).tolist(),v.max(0).tolist()]))
        # Sparse honest wireframe geometry for the audit preview only.
        step=max(1,len(f)//1600);self.wire.append(v[f[::step]])
        print(name,len(f),flush=True)
    def close(self):
        self.f.seek(4);self.f.write(struct.pack('<I',self.count));self.f.close()
        (self.out/'geometry_manifest.json').write_text(json.dumps(dict(seed=SEED,units='metres',triangles=self.count,parts=self.parts),indent=2))
        np.save(self.out/'audit_triangles.npy',np.concatenate(self.wire).astype('f4'))

def make_textures(asset_root,out):
    texdir=out/'textures';texdir.mkdir(exist_ok=True)
    records=[]
    names=['boulder_01','namaqualand_boulder_02','namaqualand_boulder_03']
    for k,name in enumerate(names+['brown_mud_rocks_01','rock_boulder_dry']):
        if k<3:
            d=asset_root/name/'textures';al=d/f'{name}_diff_2k.jpg';nr=d/f'{name}_nor_gl_2k.jpg';rr=d/f'{name}_arm_2k.jpg'
        elif k==3:
            al=asset_root/f'{name}_diff_2k.jpg';nr=asset_root/f'{name}_nor_gl_2k.jpg';rr=asset_root/f'{name}_rough_2k.jpg'
        else:
            d=asset_root.parent.parent/'desert_hot_springs_v2'/'assets';al=d/f'{name}_diff_4k.jpg';nr=None;rr=d/f'{name}_rough_4k.jpg'
        size=2048
        a=np.asarray(Image.open(al).convert('RGB').resize((size,size),Image.Resampling.LANCZOS),np.float32)/255
        a=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
        n=np.zeros_like(a);n[:,:,2]=1
        if k==4:
            height=np.asarray(Image.open(d/f'{name}_disp_4k.jpg').convert('L').resize((size,size),Image.Resampling.LANCZOS),np.float32)/255
            from scipy.ndimage import gaussian_filter
            height=gaussian_filter(height,1.0,mode='wrap')
            gy,gx=np.gradient(height)
            n=np.stack([-gx*size*.033,gy*size*.033,np.ones_like(height)],axis=-1)
            n=normalize(n)
        if nr is not None:n=np.asarray(Image.open(nr).convert('RGB').resize((size,size),Image.Resampling.LANCZOS),np.float32)/127.5-1
        r=np.asarray(Image.open(rr).convert('RGB').resize((size,size),Image.Resampling.LANCZOS),np.float32)[:,:,1]/255
        data=np.concatenate([a,n,r[:,:,None]],axis=2).astype('<f4')
        p=texdir/f'{k}.cvtex'
        with p.open('wb') as f:f.write(struct.pack('<III',size,size,7));f.write(data.tobytes())
        records.append({'id':k,'name':name,'source_albedo':str(al.name),'converted_resolution':[size,size],'mipmapped':True,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (out/'textures.json').write_text(json.dumps(records,indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,default=ROOT/'assets'/'inputs');ap.add_argument('--out',type=Path,default=ROOT/'assets'/'built');a=ap.parse_args()
    out=a.out;out.mkdir(parents=True,exist_ok=True)
    ar=a.input/'cybr-geo/examples/desert_hot_springs_v3/assets'
    make_textures(ar,out);w=Writer(out)
    # The cavern is a continuous rough vaulted shell, not a pile of primitives.
    y=np.linspace(-15,35,500);ang=np.linspace(0,np.pi,310)
    A,Y=np.meshgrid(ang,y)
    rad=8.0+.75*np.sin(Y*.18)+.36*noise(Y*.38,0)
    X=rad*np.cos(A);Z=.1+(11.2+.95*np.sin(Y*.12+1))*np.sin(A)
    # Large erosive recesses, stratified ledges and independent finer fracture relief.
    warp=fbm(X*.20,Y*.20,Z*.20)
    q=fbm(X*.35+warp*.5,Y*.33,Z*.39+warp*.3)
    # Broken irregular fracture cells, rather than evenly spaced sine bands.
    seeds=rng.uniform([-11,-17,-2],[11,37,15],(1900,3))
    dd,_=cKDTree(seeds).query(np.c_[X.ravel(),Y.ravel(),Z.ravel()],k=2)
    cracks=np.exp(-((dd[:,1]-dd[:,0])/.075)**2).reshape(X.shape)
    # Stratification is part of the actual surface; independent mesoscopic fractures.
    bedding=Z+.18*fbm(X*.32,Y*.25,Z*.22)+.07*Y
    layers=(np.sin(bedding*6.5)+.42*np.sin(bedding*13.0+.6))
    relief=.84*q+.20*noise(X*.75,Y*.73,Z*.80)-.16*cracks+.065*fbm(X*2.4,Y*2.4,Z*2.5,3)+.135*layers
    X+=np.cos(A)*relief;Z+=np.sin(A)*relief
    # Uneven collapsed oculus. The light is only admitted by this real opening.
    oculus=((X-1.2)/3.7)**2+((Y-10.8)/5.7)**2
    cut=(oculus<1+.15*noise(X*1.1,Y*1.1))&(Z>7.8)
    # A fractured remnant across one end of the opening breaks its outline.
    bridge=(np.abs(Y-(13.6+.55*X))<.35+.18*noise(X*2,Y*2))
    # No unsupported paper-thin bridge across the opening.
    cut &= ~((np.abs(Y-(15.7+.30*X))<.42)&(X<-1.9))
    v=np.c_[X.ravel(),Y.ravel(),Z.ravel()];f=grid_faces(*X.shape)
    f=f[~np.any(cut.ravel()[f],axis=1)]
    color=np.tile([1.05,1.01,.94],(len(v),1))
    w.add('Continuous_eroded_vault_with_collapsed_oculus',v,f,mat=0,tex=-2,col=color)
    edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    edge=unique[counts==1];mid=v[edge].mean(1)
    edge=edge[(mid[:,2]>7.0)&(mid[:,1]>3)&(mid[:,1]<19)]
    outer=v.copy();outer[:,2]+=1.15+.21*noise(v[:,0]*1.2,v[:,1]*1.2)
    nbase=len(v);side=np.concatenate([np.c_[edge[:,0],edge[:,1],edge[:,1]+nbase],np.c_[edge[:,0],edge[:,1]+nbase,edge[:,0]+nbase]])
    w.add('Solid_fractured_oculus_lips',np.r_[v,outer],side,tex=-2)
    # Physical outward-facing shell closes the top of the exposed rock thickness.
    w.add('External_oculus_stone_surface',outer,f[:,::-1],tex=-2,col=[.92,.92,.89])

    # Far wall, with a small water-carved passage into a darker chamber.
    X,Z=np.meshgrid(np.linspace(-10,10,230),np.linspace(-3,13,200));Y=33+.5*fbm(X*.3,Z*.3)
    X2=X+.12*noise(X*1.6,Z*1.6);Z2=Z+.1*noise(X*2.2,Z*2.2+7)
    v=np.c_[X2.ravel(),Y.ravel(),Z2.ravel()];f=grid_faces(*X.shape)
    hole=((X-1.8)/2.1)**2+((Z-1.8)/2.8)**2<1
    f=f[~np.any(hole.ravel()[f],axis=1)]
    w.add('Far_eroded_arch',v,f,tex=-2)
    v[:,1]+=8;w.add('Distant_passage_termination',v,grid_faces(*X.shape),tex=-2,col=[.4,.45,.49])
    # Highly resolved submerged floor continues through the banks.
    X,Y=np.meshgrid(np.linspace(-12,12,421),np.linspace(-15,40,641));Z=floor_height(X,Y)
    v=np.c_[X.ravel(),Y.ravel(),Z.ravel()];f=grid_faces(*X.shape)
    q=pool_q(X,Y);c=np.tile([1.0,1.0,1.0],(X.size,1))
    shelf=np.exp(-((q.ravel()-.88)/.19)**2)
    c*=np.array([1.32,1.65,1.95]);c=c*(1-.22*shelf[:,None])+np.array([1.7,1.95,2.12])*.22*shelf[:,None]
    w.add('Continuous_silt_floor_and_submerged_shelves',v,f,mat=1,tex=-3,col=c)
    # Closed water: top waves, four sides and bottom, all outward oriented.
    X,Y=np.meshgrid(np.linspace(-11.8,11.8,221),np.linspace(-14.8,39.8,461));Z=water_height(X,Y)
    v=np.c_[X.ravel(),Y.ravel(),Z.ravel()];f=grid_faces(*X.shape);ny,nx=X.shape
    boundary=np.r_[np.arange(nx),np.arange(2*nx-1,ny*nx,nx),np.arange(ny*nx-2,(ny-1)*nx-1,-1),np.arange((ny-2)*nx,0,-nx)]
    bottom=v[boundary].copy();bottom[:,2]=-5;n=len(v);v=np.r_[v,bottom]
    s=[]
    for i,j in enumerate(boundary):
        k=(i+1)%len(boundary);s.extend([[j,n+i,n+k],[j,n+k,boundary[k]]])
    # Boundary order is CCW as seen from above; orientation of side faces checked.
    center=len(v);v=np.r_[v,[[0.,12.5,-5.]]];bidx=n+np.arange(len(boundary));f=np.r_[f,np.asarray(s),np.c_[np.full(len(boundary),center),np.roll(bidx,-1),bidx]]
    w.add('Closed_rippled_water_volume',v,f,mat=6)
    # Scanned rock prototypes and seam-preserving vertex-clustering LODs.
    protos=[]; placed_scans={}
    for name in ['boulder_01','namaqualand_boulder_02','namaqualand_boulder_03']:
        m=next(iter(trimesh.load(ar/name/f'{name}_2k.gltf',force='scene',process=False).geometry.values()))
        R=np.array([[1,0,0],[0,0,-1],[0,1,0]])
        vv=np.array(m.vertices)@R.T;nn=np.array(m.vertex_normals)@R.T
        vv-=np.r_[(vv.max(0)[:2]+vv.min(0)[:2])/2,vv[:,2].min()];vv/=np.ptp(vv,axis=0).max()
        uv=np.array(m.visual.uv);uv[:,1]=1-uv[:,1]
        key=np.round(vv/.038).astype(int);_,inv=np.unique(key,axis=0,return_inverse=True)
        vc=np.zeros((inv.max()+1,3));nc=vc.copy();weights=np.bincount(inv)
        np.add.at(vc,inv,vv);np.add.at(nc,inv,nn);vc/=weights[:,None];nc=normalize(nc)
        lowv=vc[inv];lown=nc[inv]
        ff=np.array(m.faces);good=np.linalg.norm(np.cross(lowv[ff[:,1]]-lowv[ff[:,0]],lowv[ff[:,2]]-lowv[ff[:,0]]),axis=1)>1e-9
        protos.append(((vv,ff,nn,uv),(lowv,ff[good],lown,uv)))
    def rock(name,x,y,z,size,index=0,hero=False,scale=(1,1,1),rot=(0,0,0)):
        vv,ff,nn,uv=protos[index][0 if hero else 1];R=Rotation.from_euler('xyz',rot).as_matrix();s=size*np.array(scale)
        vr=(vv*s)@R.T;nr=normalize((nn/s)@R.T);vr+=np.array([x,y,z])
        w.add(name,vr,ff,n=nr,uv=uv,mat=2,tex=index,col=np.array([.88,.90,.88])*rng.uniform(.82,1.12))
        if hero:placed_scans[name]=(vr.copy(),ff.copy())
    # Foreground photographed fracture faces, large enough to inspect native detail.
    heroes=[(-4.9,-3.0,.05,3.4,0,(1,.85,1.1),(0,.14,.18)),
      (5.0,.8,.12,3.5,2,(1,.95,.9),(.04,-.18,-.30)),
      (-6.5,6,.25,5.2,1,(.7,1.2,1.6),(.1,.1,1.8)),
      (6.3,10,.1,4.8,0,(.9,1.1,1.4),(.1,-.15,-1.2)),
      (-4.8,15,-.1,2.7,2,(1.2,1,.8),(.13,.12,.7)),
      (4.6,23,.25,3.1,1,(1.2,.7,1.15),(.08,-.13,.8))]
    for i,(x,y,z,s,idx,sc,rot) in enumerate(heroes):rock(f'Photogrammetry_hero_{i:02d}',x,y,z,s,idx,True,sc,rot)
    # Actual scanned undercuts on the walls and overhead, not only textured relief.
    # Wall relief belongs to the shell. Remove conspicuous isolated cube-like
    # wall scans; preserve photographed fracture geometry on the actual banks.
    for i in range(48):
        y=rng.uniform(-8,31);x=rng.choice([-1,1])*rng.uniform(5.3,8.8);z=float(floor_height(x,y));sz=rng.uniform(.35,1.8)
        rock(f'Bank_collapse_{i:02d}',x,y,z-.07*sz,sz,i%3,False,rot=(rng.uniform(-.2,.2),rng.uniform(-.2,.2),rng.uniform(0,6.28)))
    # Loose underwater stones, with a continuous size distribution.
    allv=[];allf=[];cols=[];count=0
    unit=trimesh.creation.icosphere(subdivisions=1)
    for i in range(1650):
        x=rng.uniform(-7,7);y=rng.uniform(-11,33)
        if rng.random()>.38+.30*float(noise(x*.4,y*.4)):continue
        r=np.exp(rng.uniform(np.log(.017),np.log(.19)));z=float(floor_height(x,y))
        R=Rotation.random(random_state=rng).as_matrix();vv=(np.array(unit.vertices)*[r,r*rng.uniform(.6,1.2),r*.5])@R.T+[x,y,z+r*.15]
        allv.append(vv);allf.append(unit.faces+count);count+=len(vv);cols.append(np.tile(rng.uniform(.5,1.3)*np.array([.85,.83,.78]),(len(vv),1)))
    w.add('Individual_floor_pebbles',np.concatenate(allv),np.concatenate(allf),mat=2,tex=-2,col=np.concatenate(cols))
    # Quartz uses the actual uploaded half-space polyhedron builder. No prisms
    # are stretched from the rendered PNG; all crystal facets exist in 3D.
    fleck=trimesh.creation.icosphere(subdivisions=0);fv=[];ff=[];fc=0
    def crystal(name,origin,width,height,axis,spin,mat=8):
        nonlocal fc
        offsets=np.r_[np.full(6,width)*(1+rng.uniform(-.055,.055,6)),np.full(6,height*.625),width*.32]
        offsets[6:12]+=np.array([0,.012,0,.012,0,.012])*height
        vv,faces,_=polyhedron(offsets);R=rotation(axis,spin);vv=vv@R.T+origin
        w.add(name,vv,faces,mat=mat,flat=True,col=[1,1,1])
        for j in range(2):
            local=np.array([rng.uniform(-width*.55,width*.55),rng.uniform(-width*.55,width*.55),rng.uniform(.08*height,height*.72)])
            if not np.all(__import__('quartz_growth').NORMALS@local<offsets*.88):continue
            p=local@R.T+origin;r=rng.uniform(.001,.003)*height
            fv.append(np.asarray(fleck.vertices)*[r*2,r,r*.4]+p);ff.append(np.asarray(fleck.faces)+fc);fc+=len(fleck.vertices)
    # Ray-anchored crystal growth on actual photographed stone surfaces.
    # Each nucleus uses a geometric surface hit, not a guessed world-space Z.
    def anchor_ray(meshname, origin, direction):
        vv,faces=placed_scans[meshname];tri=vv[faces]
        e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];d=normalize(np.array(direction,float));o=np.array(origin,float)
        pp=np.cross(np.broadcast_to(d,e2.shape),e2);det=np.einsum('ij,ij->i',e1,pp)
        inv=np.divide(1.,det,out=np.zeros_like(det),where=np.abs(det)>1e-10)
        tt=o-tri[:,0];u=np.einsum('ij,ij->i',tt,pp)*inv;qq=np.cross(tt,e1)
        v2=qq@d*inv;t=np.einsum('ij,ij->i',e2,qq)*inv
        valid=(np.abs(det)>1e-10)&(u>=0)&(v2>=0)&(u+v2<=1)&(t>0)
        if not valid.any():return None
        idx=np.argmin(np.where(valid,t,np.inf));n=normalize(np.cross(e1[idx],e2[idx]))
        if np.dot(n,d)>0:n=-n
        return o+d*t[idx],n
    cluster_specs=[('Photogrammetry_hero_01',5.0,.8,1.0,42),('Photogrammetry_hero_00',-4.9,-3.0,.65,24),('Photogrammetry_hero_03',6.3,10.,.48,22)]
    anchored=[]
    for ci,(name,cx,cy,scale,ncount) in enumerate(cluster_specs):
        points=[]
        for j in range(ncount*5):
            if len(points)>=ncount:break
            x=cx+rng.uniform(-1.15,.65)*scale;y=cy+rng.uniform(-1.05,.1)*scale
            hit=anchor_ray(name,[x,y,5.5],[.0,.08,-1.])
            if hit is None:continue
            p0,n0=hit
            if n0[2]<.35:continue
            wi=rng.uniform(.04,.12)*scale
            if any(np.linalg.norm(p0-p1)<1.6*(wi+w1) for p1,w1 in points):continue
            points.append((p0,wi));axis=normalize(n0*.32+np.array([rng.normal(-.23,.15),rng.normal(-.26,.12),1.]))
            h=wi*rng.uniform(2.6,5.4);base=p0-axis*wi*.11
            crystal(f'Anchored_optical_quartz_{ci}_{len(points):03}',base,wi,h,axis,rng.uniform(0,6.28),8 if ci==0 else 9)
            anchored.append({'name':name,'base':p0.tolist(),'axis':axis.tolist(),'width':wi,'height':h})
        # Smaller druse fills the mineral seam but does not engulf larger optics.
        for j in range(100 if ci==0 else 45):
            x=cx+rng.uniform(-1.3,.72)*scale;y=cy+rng.uniform(-1.16,.22)*scale
            hit=anchor_ray(name,[x,y,5.5],[0,.06,-1])
            if hit is None:continue
            p0,n0=hit
            if n0[2]<.35 or any(np.linalg.norm(p0-p1)<1.45*w1+.025 for p1,w1 in points):continue
            wi=rng.uniform(.013,.038)*scale
            axis=normalize(n0*.35+np.array([rng.normal(0,.22),rng.normal(-.18,.22),1]))
            crystal(f'Anchored_druse_{ci}_{j:03}',p0-axis*.005,wi,wi*rng.uniform(2.,3.9),axis,rng.uniform(0,6.28),9)
    (out/'crystal_anchors.json').write_text(json.dumps(anchored,indent=2))
    if fv:w.add('Actual_quartz_mineral_inclusions',np.concatenate(fv),np.concatenate(ff),mat=3,col=[.36,.34,.29],flat=True)
    # Broken roof rubble makes the oculus edges genuinely irregular in silhouette.
    for i in range(12):
        a=i*2*np.pi/12;x=1.2+3.8*np.cos(a);y=10.8+5.8*np.sin(a)
        zz=.1+(11.2+.95*np.sin(y*.12+1))*np.sqrt(max(0,1-(x/8.5)**2))
        rock(f'Collapsed_roof_fracture_{i:02d}',x,y,zz-.45,rng.uniform(.7,1.8),i%3,False,scale=(1,.9,.65),rot=(0,0,rng.uniform(0,6.28)))
    rootv=[];rootf=[];rootc=[];rcount=0
    def tube(points,radius):
        nonlocal rcount
        pts=np.asarray(points);tang=normalize(np.gradient(pts,axis=0));side=normalize(np.cross(tang,np.array([0,1,0])));up=np.cross(side,tang)
        theta=np.arange(6)*2*np.pi/6
        vv=pts[:,None,:]+radius*(1-.75*np.linspace(0,1,len(pts)))[:,None,None]*(np.cos(theta)[None,:,None]*side[:,None,:]+np.sin(theta)[None,:,None]*up[:,None,:])
        vv=vv.reshape(-1,3);ff=[]
        for i in range(len(pts)-1):
            for j in range(6):k=(j+1)%6;ff.extend([[i*6+j,i*6+k,(i+1)*6+j],[i*6+k,(i+1)*6+k,(i+1)*6+j]])
        rootv.append(vv);rootf.append(np.array(ff)+rcount);rcount+=len(vv);rootc.append(np.tile([.075,.045,.017],(len(vv),1)))
    leafv=[];leaff=[];leafc=[];lcount=0
    for j in range(26):
        ang=rng.uniform(0,2*np.pi);x=1.2+3.6*np.cos(ang);y=10.8+5.6*np.sin(ang)
        z=.1+(11.2+.95*np.sin(y*.12+1))*np.sqrt(max(0,1-(x/8.5)**2))+.15
        length=rng.uniform(.45,2.4);t=np.linspace(0,1,22)
        points=np.c_[x+.20*np.sin(t*4+j)*t,y+.18*np.sin(t*3+j*2)*t,z-length*t]
        tube(points,rng.uniform(.014,.035))
        if j%3==0:continue
        # Small narrow paired leaflets on independently curved fronds.
        for k in range(4,20):
            c=points[k];az=rng.uniform(0,6.28);direction=np.array([np.cos(az),np.sin(az),-.15]);le=rng.uniform(.07,.22)*(1-k/26)
            wide=np.array([-direction[1],direction[0],.15])*le*.23
            vv=np.array([c,c+direction*le*.48+wide,c+direction*le*.48-wide,c+direction*le])
            leafv.append(vv);leaff.append(np.array([[0,1,2],[1,3,2]])+lcount);lcount+=4
            leafc.append(np.tile(np.array([.034,.093,.012])*rng.uniform(.65,1.25),(4,1)))
    w.add('Fine_hanging_roots',np.concatenate(rootv),np.concatenate(rootf),mat=3,col=np.concatenate(rootc))
    w.add('Explicit_rim_leaflets',np.concatenate(leafv),np.concatenate(leaff),mat=3,col=np.concatenate(leafc))
    w.close()
    print('SCENE COMPLETE',w.count,'triangles',flush=True)
if __name__=='__main__':main()
