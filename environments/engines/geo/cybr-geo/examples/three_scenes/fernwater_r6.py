"""Fernwater R6: a new winding riparian woodland, native CYBR GEO geometry.

The formation models, leaf optics, rock and plant shapes are authored. They are
not scanned, image generated, a geophysical solver, or a botanical simulation.
All visible objects are triangles; leaves have attached petioles and local frames.
"""
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
import trimesh
import build_scenes as base
from build_scenes import Builder, Water, unit, n3, smooth, fractal, vertex_normals, sha, REPO, HERE
import rebuild_scenes as inherited


def field(x,y,z=0.,s=1.,octaves=3):
    return fractal(np.asarray(x)*s,np.asarray(y)*s,np.asarray(z)*s,octaves)


def channel(y):
    y=np.asarray(y)
    return .82*np.sin((y+2.2)*.26)+.42*np.sin(y*.47-.2)+.035*y+2.2*smooth(17,34,y)


def bank_width(y,side):
    y,side=np.broadcast_arrays(y,side)
    return (1.34+.32*np.sin(y*.33+.4)+.23*n3(y*.72,side*3)
            +.58*np.exp(-((y-2.5)/2.0)**2)*(side<0)
            -.35*np.exp(-((y-8.2)/2.2)**2)*(side>0))


def floor_height(x,y):
    x,y=np.broadcast_arrays(x,y);q=x-channel(y);side=np.where(q>0,1.,-1.);d=np.abs(q)
    w=bank_width(y,side)
    # Meandering asymmetric cut-bank / sediment-bar transitions. No constant-height
    # canal wall, no raised six-metre embankment immediately behind the log.
    steep=.30+.60*smooth(-.4,.6,np.sin(y*.27+side*1.7))
    transition=smooth(w-.38,w+steep,d)
    depth=.20+.20*np.exp(-((y-1.4)/3.1)**2)+.06*np.sin(y*.32)
    bed=-depth+.065*field(x,y,s=1.35)+.014*field(x,y,s=9,octaves=2)
    bank=.23+.18*field(x,y,s=.63)+.11*field(x,y,s=2.6)
    bank+=.21*smooth(1.6,5.8,d)+.54*smooth(5,15,d)
    bank+=2.1*smooth(23,59,y)+.24*field(x,y,s=.18)*smooth(17,37,y)
    z=bed*(1-transition)+bank*transition
    # Actual sediment tongues on alternating inside bends.
    z+=.13*np.exp(-((q-.83*np.sin(y*.28))/.43)**2)*np.exp(-((y-5.7)/1.8)**2)
    z+=.13*np.exp(-((q+.89)/.38)**2-((y+3.8)/1.8)**2)
    # Low hummocks, localized exposed roots, and denuded depressions.
    z+=.043*field(x,y,s=6.8,octaves=2)*transition
    return z


class WoodlandBuilder(Builder):
    """Native mesh assembly + compact per-component material-coordinate table.

    Triangles keep CYBR's 20-float mesh layout. The existing group slot is a
    material-frame index; separate assembly parts remain intact. Frame records
    are 16 float32 values: origin, longitudinal axis, transverse axis, normal,
    length, width/radius, species/type, seed. No image UV projection/backplate.
    """
    def __init__(self,seed):
        super().__init__('forest',seed)
        self.frames=[np.zeros(16,np.float32)]
        self.frame_ranges={};self.current_frame=0
        self.terrain=None;self.terrain_bounds=None;self.moss_count=0
        self.leaf_positions=[];self.chunk_triangles={}

    def make_frame(self,origin,d,side,normal,length,width,kind,seed):
        idx=len(self.frames)
        self.frames.append(np.array([*origin,*d,*side,*normal,length,width,kind,seed],np.float32))
        return idx

    def add(self,label,v,f,n=None,mat=0,flat=False):
        if len(f)==0:return
        # Chunk large independent foliage groups without changing any vertices.
        # This bounds temporary concatenation memory during native Assembly export.
        if any(token in label for token in ('laminae','litter','pinnules','crown_shoots')):
            original=label;total=self.chunk_triangles.get(original,0)
            label=f'{original}_section{total//180000:03d}'
            self.chunk_triangles[original]=total+len(f)
        super().add(label,v,f,n,mat,flat)
        self.frame_ranges.setdefault((label,mat),[]).append((len(f),self.current_frame))

    def ground(self,x,y):
        x,y=np.broadcast_arrays(x,y)
        if self.terrain is None:return floor_height(x,y)
        x0,x1,y0,y1=self.terrain_bounds;ny,nx=self.terrain.shape
        coords=np.array([(y-y0)/(y1-y0)*(ny-1),(x-x0)/(x1-x0)*(nx-1)])
        return map_coordinates(self.terrain,coords.reshape(2,-1),order=1,mode='nearest',prefilter=False).reshape(x.shape)

    def ground_normal(self,x,y):
        e=.023;dx=(self.ground(x+e,y)-self.ground(x-e,y))/(2*e)
        dy=(self.ground(x,y+e)-self.ground(x,y-e))/(2*e)
        return unit(np.stack([-dx,-dy,np.ones_like(dx)],axis=-1))

    def tube(self,label,path,radii,mat=8,sides=9,bark=False,phase=0):
        path=np.asarray(path,float);rr=np.broadcast_to(radii,(len(path),))
        if len(path)<2:return
        d=unit(path[-1]-path[0]);side=unit(np.cross(d,[0,0,1]))
        if np.linalg.norm(side)<.5:side=np.array([1.,0.,0.])
        normal=np.cross(d,side)
        idx=self.make_frame(path[0],d,side,normal,float(np.linalg.norm(path[-1]-path[0])),float(np.max(rr)),2 if mat==14 else 1,phase) if bark else 0
        old=self.current_frame;self.current_frame=idx
        # Parallel-transport frame avoids sudden 90-degree bands along curved roots.
        distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
        large=bark and np.max(rr)>.075
        if large:
            dense=np.linspace(0,distances[-1],max(len(path),min(180,int(distances[-1]/.10)+2)))
            rr=np.interp(dense,distances,rr)
            path=np.stack([np.interp(dense,distances,path[:,k]) for k in range(3)],axis=-1)
            distances=dense;sides=max(sides,48 if rr.max()>.22 else 24)
        tangent=unit(np.gradient(path,axis=0));first=unit(np.cross(tangent[0],[0,1,0]))
        if np.linalg.norm(first)<.5:first=np.array([1.,0,0])
        T=[first]
        for tg in tangent[1:]:
            v=T[-1]-tg*np.dot(T[-1],tg)
            T.append(unit(v))
        T=np.array(T);B=np.cross(tangent,T);ang=np.linspace(0,2*np.pi,sides+1)
        ring=np.cos(ang)[None,:,None]*T[:,None,:]+np.sin(ang)[None,:,None]*B[:,None,:]
        mod=np.ones((len(path),len(ang)))
        if large:
            ax=ang[None,:];hh=distances[:,None]
            rills=.023*np.sin(ax*19+phase+.27*np.sin(hh*.72))+.016*np.sin(ax*31+phase*2+.45*np.sin(hh*1.1))
            basal=.11*np.cos(ax*5+phase)*np.exp(-hh/np.maximum(.2,rr[0]*3))
            mod+=rills+basal
        v=(path[:,None,:]+ring*(rr[:,None]*mod)[:,:,None]).reshape(-1,3)
        f=base.grid_faces(len(path),sides+1)
        # Weld the seam before normal evaluation; tube caps stay below other joints.
        f[f%(sides+1)==sides]-=sides
        caps=[]
        for j in range(1,sides-1):
            caps.append((0,j+1,j));a=(len(path)-1)*(sides+1);caps.append((a,a+j,a+j+1))
        f=np.r_[f,np.array(caps,np.int64)]
        self.add(label,v,f,mat=mat)
        self.current_frame=old

    def leaf(self,label,origin,direction,length,width,mat=9,roll=0.,fold=.07,kind=None,detail=None):
        origin=np.asarray(origin,float);d=unit(direction)
        side=unit(np.cross([0,0,1],d))
        if np.linalg.norm(side)<.5:side=np.array([1.,0.,0.])
        normal=unit(np.cross(d,side));s=side*np.cos(roll)+normal*np.sin(roll);n=unit(np.cross(d,s))
        seed=float(self.rng.uniform(0,512))
        if kind is None:kind=4 if mat==11 else 3
        # Larger living leaves have serrated or lobed outlines, varying curvature,
        # taper and an off-centre midrib. Distal canopy is simplified by scale.
        near=(-7<origin[1]<16 and abs(origin[0])<8 and origin[2]<5.5)
        rows=9 if detail or (near and length>.065) else 4
        if kind==5:rows=4
        t=np.linspace(0,1,rows)
        leafshape=np.sin(np.pi*t)**(.76 if kind!=6 else .64)
        if kind==6:
            leafshape*=.73+.27*np.cos(t*9*np.pi+seed*.07)**2
        else:
            leafshape*=1+.075*np.sin(t*27*np.pi+seed)
        zz=length*(fold*np.sin(np.pi*t)-.045*t*t)
        mid=origin+t[:,None]*d*length+zz[:,None]*n
        wav=.018*np.sin(t*15+seed)*length
        spread=width*.5*leafshape
        left=mid-spread[:,None]*s*(1+.05*np.sin(t*8+seed))[:,None]+(wav-.020*length*np.sin(np.pi*t))[:,None]*n
        right=mid+spread[:,None]*s*(1-.04*np.sin(t*9+seed))[:,None]+(wav-.016*length*np.sin(np.pi*t))[:,None]*n
        verts=np.stack([left,mid,right],axis=1).reshape(-1,3)
        f=base.grid_faces(rows,3);tr=verts[f];areas=np.linalg.norm(np.cross(tr[:,1]-tr[:,0],tr[:,2]-tr[:,0]),axis=1);f=f[areas>1e-13]
        idx=self.make_frame(origin,d,s,n,length,width,kind,seed)
        old=self.current_frame;self.current_frame=idx;self.add(label,verts,f,mat=mat);self.current_frame=old
        if near:self.leaf_positions.append([*origin,length,width,int(mat)])

    def finish(self,out,config,glb=False):
        # Snapshot component mapping before the base builder consumes its groups.
        ranges=[(key,list(self.frame_ranges[key])) for key in self.groups]
        report=super().finish(out,config,glb)
        a=np.memmap(out/'scene.meshbin',dtype='<f4',mode='r+',offset=4,shape=(report['triangles'],20));start=0;serial=[]
        for (label,mat),items in ranges:
            for count,index in items:
                a[start:start+count,19]=index;serial.append([start,count,index]);start+=count
        if start!=len(a):raise RuntimeError('Frame/mesh ordering mismatch')
        a.flush();del a
        with (out/'surface_frames.bin').open('wb') as f:
            f.write(b'FRM6');f.write(np.array([len(self.frames)],'<u4').tobytes());f.write(np.asarray(self.frames,'<f4').tobytes())
        np.savez_compressed(out/'assembly/surface_coordinates.npz',frames=np.asarray(self.frames,'<f4'),ranges=np.asarray(serial,'<u4'))
        report.update({'mesh_sha256':sha(out/'scene.meshbin'),'surface_frames_sha256':sha(out/'surface_frames.bin'),
                       'surface_coordinate_frames':len(self.frames),'leaf_components':sum(v for k,v in self.counts.items() if any(t in k for t in ['lamina','litter','pinnule'])),
                       'authored_not_measured':True,'image_generation':False,'script_sha256':sha(Path(__file__))})
        (out/'geometry.json').write_text(json.dumps(report,indent=2))
        np.save(out/'near_leaf_samples.npy',np.asarray(self.leaf_positions,np.float32))
        return report


def point_on(path,q):
    f=q*(len(path)-1);i=min(len(path)-2,int(f));return path[i]*(1-(f-i))+path[i+1]*(f-i)


def grow_spray(b,start,heading,reach,material,phase,leafsize=.11,count=9):
    """A connected tertiary shoot carrying paired, slightly drooping laminae."""
    r=b.rng;u=np.linspace(0,1,4);d=unit(heading)
    path=np.asarray(start)+u[:,None]*d*reach
    path[:,2]+=.05*reach*np.sin(np.pi*u)-.08*reach*u*u
    b.tube('Attached_crown_shoots',path,[.0026,.0018,.0011,.0003],material,4)
    side=unit(np.cross(d,[0,0,1]))
    for j in range(count):
        t=.08+.90*j/max(1,count-1);at=point_on(path,t)
        sign=(-1 if j%2 else 1);dire=unit(d*.35+side*sign+[0,0,r.uniform(-.80,.45)])
        L=leafsize*r.uniform(.74,1.24);petiole=L*.12
        tip=at+dire*petiole
        if at[1]<18 and abs(at[0])<8 and at[2]<5:
            b.tube('Crown_petioles',[at,tip],[.0006,.00024],material,3)
        else:tip=at
        b.leaf('Broadleaf_laminae',tip,dire,L,L*r.uniform(.46,.65),9,r.uniform(-1.25,1.25),r.uniform(.025,.12),kind=6 if material==8 and phase%4<1 else 3)


def crown_branch(b,path,radius,material,phase,leafsize,amount=1):
    r=b.rng
    b.tube('Living_branch_hierarchy',path,np.linspace(radius,.004,len(path)),material,8,bark=radius>.06,phase=phase)
    for k in range(int(r.integers(13,20)*amount)):
        q=r.uniform(.22,.98);at=point_on(path,q);local=unit(path[-1]-path[0]);side=unit(np.cross(local,[0,0,1]))
        sign=1 if k%2 else -1;heading=unit(local*.65+side*sign*r.uniform(.4,.95)+[0,0,r.uniform(-.1,.3)])
        L=r.uniform(.34,.75)*(1.05-.35*q);end=at+heading*L
        sec=np.array([at,(at+end)*.5+[0,0,.03],end]);b.tube('Secondary_crown_twigs',sec,[.009,.0045,.0011],material,5)
        for j in range(int(r.integers(4,7))):
            t=r.uniform(.15,.98);ss=point_on(sec,t);h=unit(heading*.52+side*(1 if j%2 else -1)*.8+[0,0,r.uniform(-.1,.1)])
            grow_spray(b,ss,h,r.uniform(.20,.34),material,phase+k*.1,leafsize,int(r.integers(6,10)))


def tree(b,x,y,height,radius,archetype='beech',near=False):
    r=b.rng;origin=np.array([x,y,float(b.ground(x,y))]);phase=r.uniform(0,2*np.pi)
    lean=r.uniform(-.38,.38,2)
    if archetype=='lean':lean=np.array([-np.sign(x-channel(y))*.9,.4])
    t=np.linspace(0,1,40 if near else 24)
    path=origin+np.c_[lean[0]*t**1.3+.045*np.sin(t*8+phase)*t,lean[1]*t**1.6,height*t]
    radii=radius*(1-.87*t)**.92*(1+.32*np.exp(-t*14))
    mat=14 if archetype=='birch' else 8
    b.tube('Mature_'+archetype+'_trunks',path,radii,mat,56 if near else 28,True,phase)
    for k in range(int(r.integers(5,9))):
        a=phase+k*2.4+r.uniform(-.2,.2);L=radius*r.uniform(3.3,6.6);ss=np.linspace(0,1,15)
        xx=x+L*np.cos(a)*ss;yy=y+L*np.sin(a)*ss;zz=b.ground(xx,yy)+radius*.38*(1-ss)**2
        root=np.c_[xx,yy,zz];root[0]=origin+[0,0,radius*.40];root[-1,2]-=.035
        b.tube('Buttress_and_exposed_roots',root,radius*.35*(1-ss)**1.6+.002,mat,16,True,phase+k)
    # Variable clear-bole heights and broad arching crowns instead of a single
    # repeated fixed branch/twig count. Forked crowns occupy actual light gaps.
    clear=.40 if height>11 else .25
    n=int(r.integers(8,13) if near else r.integers(7,10))
    for k in range(n):
        q=r.uniform(clear,.91);at=point_on(path,q);a=phase+k*2.39996+r.uniform(-.47,.47)
        reach=height*r.uniform(.18,.29)*(1-.50*q)
        direction=np.array([np.cos(a),np.sin(a),0.]);rise=reach*r.uniform(.22,.65)
        ts=np.linspace(0,1,8);branch=at+ts[:,None]*direction*reach
        branch[:,2]+=rise*ts+.12*reach*np.sin(np.pi*ts)
        crown_branch(b,branch,radius*r.uniform(.18,.34)*(1-.5*q),mat,phase+k,.12 if archetype=='birch' else .15,1.1 if near else 1.0)
    # Low reaching boughs are rooted in the trunk, not floating canopy planes.
    if near and y<15:
        at=point_on(path,r.uniform(2.4,3.2)/height)
        target=channel(y+1.8);direction=unit([target-x,r.uniform(.5,1.5),.20])
        reach=min(3.6,abs(target-x)+.7);ts=np.linspace(0,1,9)
        branch=at+direction*reach*ts[:,None];branch[:,2]+=.68*np.sin(ts*np.pi)+.32*ts
        crown_branch(b,branch,radius*.20,mat,phase,.14,1.65)


def moss_shell(b,v,f,coverage=.65):
    """Geometry attached to actual rock triangles, with discontinuous furry edges."""
    n=vertex_normals(v,f);cent=v[f].mean(axis=1);norm=n[f].mean(axis=1)
    mask=(norm[:,2]>.12)&(cent[:,2]>.025)&(n3(cent[:,0]*5,cent[:,1]*5,cent[:,2]*5)>.035)
    selected=f[mask]
    if len(selected)==0:return
    raised=v+n*(.004+.007*(.5+.5*n3(v[:,0]*19,v[:,1]*19,v[:,2]*19)))[:,None]
    b.add('Attached_moss_cushions',raised,selected,n,10)
    area=np.linalg.norm(np.cross(v[selected][:,1]-v[selected][:,0],v[selected][:,2]-v[selected][:,0]),axis=1)*.5
    samples=min(2800,int(area.sum()*5500))
    if samples<1:return
    r=b.rng;ii=r.choice(len(selected),size=samples,p=area/area.sum());tr=selected[ii]
    uv=r.uniform(size=(samples,2));over=uv.sum(axis=1)>1;uv[over]=1-uv[over];w=np.c_[1-uv.sum(axis=1),uv]
    pos=np.sum(raised[tr]*w[:,:,None],axis=1);nn=unit(np.sum(n[tr]*w[:,:,None],axis=1))
    # One small folded blade per shoot, not thousands of fat rounded tubes.
    t=unit(np.cross(nn,np.where((np.abs(nn[:,2])>.9)[:,None],[0,1,0],[0,0,1])))
    h=r.uniform(.004,.014,samples);wid=r.uniform(.0005,.0012,samples)
    tips=pos+nn*h[:,None]
    vv=np.stack([pos-t*wid[:,None],pos+t*wid[:,None],tips+t*.0003,tips-t*.0003],axis=1).reshape(-1,3)
    ff=np.tile([[0,1,2],[0,2,3]],(samples,1))+np.repeat(np.arange(samples)*4,2)[:,None]
    b.add('Moss_capsule_blades',vv,ff,mat=10);b.moss_count+=samples


def boulder(b,x,y,scale,seed,moss=True,burial=.38):
    # Joint planes generate silhouettes; larger-scale edge smoothing, unequal
    # planar facets and embedded base replace the old spherical noisy blobs.
    v,f=inherited.fracture_block(seed,scale,'block',4 if max(scale)>.28 else 2)
    # Stream transport rounds exposed convex edges, while unequal fracture faces
    # remain. Blend in normalized metric space so unequal axes are preserved.
    scale_array=np.asarray(scale,float);local=v/scale_array;direction=unit(local)
    weathered=direction*(.72+.060*field(direction[:,0]+seed,direction[:,1],direction[:,2],s=2.7))[:,None]
    v=(.37*local+.63*weathered)*scale_array
    v+=unit(v)*(.020*field(v[:,0]+seed,v[:,1],v[:,2],s=7)+.005*field(v[:,0]+seed,v[:,1],v[:,2],s=35))[:,None]
    v+=np.array([x,y,float(b.ground(x,y))-v[:,2].min()-np.ptp(v[:,2])*burial])
    b.add('Stream_jointed_greywacke',v,f,mat=2)
    if moss:moss_shell(b,v,f)
    return v,f


def fern(b,x,y,size):
    r=b.rng;o=np.array([x,y,float(b.ground(x,y))+.012]);phase=r.uniform(0,6.28)
    for j in range(int(r.integers(6,11))):
        a=phase+j*2.39996+r.uniform(-.26,.26);d=np.array([np.cos(a),np.sin(a),0.]);side=np.array([-d[1],d[0],0])
        L=size*r.uniform(.62,1.18);t=np.linspace(0,1,29);rise=r.uniform(.9,1.3);drop=r.uniform(.63,.90)
        path=o+t[:,None]*d*L;path[:,2]+=L*(rise*t-drop*t*t)
        b.tube('Curved_fern_rachis',path,np.linspace(.0029,.0003,len(t))*size,9,5)
        for k,q in enumerate(np.linspace(.10,.95,int(r.integers(18,26)))):
            if r.uniform()<.025:continue
            center=point_on(path,q);length=L*.235*np.sin(np.pi*q)**.80
            tangent=unit(d+np.array([0.,0.,rise-2*drop*q]))
            desired_normal=unit(np.cross(tangent,side))
            for sign in (-1,1):
                tip=center+side*sign*length+tangent*length*.32+[0,0,-.015*L*q]
                b.tube('Fern_secondary_stems',[center,tip],[.0008,.00015],9,4)
                sd=unit(tip-center);across=unit(tangent-sd*np.dot(tangent,sd))
                for qi in np.linspace(.12,.94,7):
                    at=center+(tip-center)*qi
                    for ss in (-1,1):
                        length2=length*.275*(1-.70*qi)
                        direction=unit(sd*.35+across*ss*.82)
                        transverse=unit(np.cross([0,0,1],direction));normal0=unit(np.cross(direction,transverse))
                        roll=np.arctan2(-np.dot(transverse,desired_normal),np.dot(normal0,desired_normal))
                        b.leaf('Fern_divided_pinnules',at,direction,length2,length2*.53,9,roll+r.uniform(-.18,.18),.04,5)


def hollow_log(b,start,end,radius):
    r=b.rng;start=np.array(start);end=np.array(end);d=unit(end-start)
    side=unit(np.cross(d,[0,0,1]));normal=unit(np.cross(d,side));ns=80;nt=64
    ts=np.linspace(0,1,nt);ang=np.linspace(0,2*np.pi,ns+1);path=start+ts[:,None]*(end-start);path[:,2]-=.08*np.sin(np.pi*ts)
    radial=np.cos(ang)[None,:,None]*side+np.sin(ang)[None,:,None]*normal
    mod=1+.048*np.sin(ang*17+.4*np.sin(ts[:,None]*9))+.017*np.sin(ang*37)
    outer=path[:,None,:]+radial*(radius*(1-.10*ts[:,None])*mod)[:,:,None]
    inner=path[:,None,:]+radial*(radius*(.66-.04*ts[:,None]))[:,:,None]
    # Jagged openings extend both inner/outer rings, leaving genuine open cavities.
    rag=.065*np.sin(ang*7)+.025*np.sin(ang*13+1)
    outer[-1]+=rag[:,None]*d;inner[-1]+=rag[:,None]*d
    old=b.current_frame;b.current_frame=b.make_frame(start,d,side,normal,np.linalg.norm(end-start),radius,1,49.2)
    b.surface('Hollow_log_outer_bark',outer,8);b.current_frame=0
    b.surface('Hollow_log_inner_decay',inner,12,flip=True)
    for endindex in [0,-1]:
        ring=np.stack([outer[endindex],inner[endindex]],axis=0)
        b.surface('Splintered_log_end_annulus',ring,12,flip=endindex==0)
    b.current_frame=old
    for q in [.23,.46,.76]:
        at=point_on(path,q);tip=at+side*r.uniform(-.7,.7)+normal*r.uniform(.28,.52)
        b.tube('Broken_log_branch_stubs',[at,at+(tip-at)*.75,tip],[radius*.22,.048,.018],8,9,True,q*23)
    # Local attached top moss; follows the curved trunk surface.
    aa=np.linspace(.10,2.95,70);tt=np.linspace(.06,.89,180);pp=start+tt[:,None]*(end-start);pp[:,2]-=.08*np.sin(np.pi*tt)
    v=pp[:,None,:]+(np.cos(aa)[None,:,None]*side+np.sin(aa)[None,:,None]*normal)*(radius*1.038)
    b.surface('Log_moss_cap',v,10)


def background_broadleaf(b,x,y,height,radius):
    """A densely branched distant broadleaf tier with real lanceolate laminae.

    Each distant leaf has its own opaque, two-triangle silhouette and attached
    shoot. These are simplified actual leaves, not alpha cards or crown solids.
    """
    r=b.rng;origin=np.array([x,y,float(b.ground(x,y))]);phase=r.uniform(0,2*np.pi)
    lean=r.uniform(-.30,.30,2);t=np.linspace(0,1,14)
    trunk=origin+np.c_[lean[0]*t,lean[1]*t,height*t]
    b.tube('Background_broadleaf_trunks',trunk,radius*(1-.98*t)**.83,8,10,True,phase)
    needles=[]
    # The lowest branches vary from dense near-ground fir to older clear-bole trees.
    levels=int(r.integers(29,46));bottom=r.uniform(.12,.30)
    for level,q in enumerate(np.sort(r.uniform(bottom,.95,levels))):
        at=point_on(trunk,q);branches=1
        for k in range(branches):
            a=phase+level*2.34+k*2*np.pi/branches+r.uniform(-.24,.24)
            L=height*r.uniform(.125,.19)*np.sin(np.pi*q)**.65
            d=np.array([np.cos(a),np.sin(a),0]);side=np.array([-d[1],d[0],0])
            ts=np.linspace(0,1,5);branch=at+ts[:,None]*d*L
            branch[:,2]+=L*(r.uniform(.10,.42)*ts+.14*np.sin(np.pi*ts))
            b.tube('Distant_woody_lateral_branches',branch,np.linspace(radius*.16,.0007,5),8,4)
            for qq in np.linspace(.15,.96,5):
                for sign in (-1,1):
                    start=point_on(branch,qq);dire=unit(d*.48+side*sign+.12*np.array([0.,0.,1.]))
                    length=L*.36*(1-.71*qq);end=start+dire*length
                    b.tube('Distant_attached_leaf_shoots',[start,end],[.0014,.0003],8,3)
                    n=5;u=np.linspace(.05,.97,n)
                    centers=start+dire*(length*u[:,None])
                    transverse=unit(np.cross(dire,[0,0,1]));vertical=np.cross(dire,transverse)
                    for sideSign in (-1,1):
                        rotation=r.uniform(-1.0,1.0,n)
                        outward=sideSign*(np.cos(rotation)[:,None]*transverse+np.sin(rotation)[:,None]*vertical)
                        nd=unit(dire*.38+outward)
                        needlelength=r.uniform(.095,.185,n)
                        tip=centers+nd*needlelength[:,None]
                        width=r.uniform(.018,.040,n)
                        nn=unit(np.cross(nd,dire));mid=centers+nd*needlelength[:,None]*.55
                        vv=np.stack([centers,mid+nn*width[:,None],tip,mid-nn*width[:,None]],axis=1)
                        needles.append(vv.reshape(-1,3))
    if needles:
        vv=np.concatenate(needles);count=len(vv)//4
        ff=np.tile([[0,1,2],[0,2,3]],(count,1))+np.repeat(np.arange(count)*4,2)[:,None]
        b.add('Distant_lanceolate_laminae',vv,ff,mat=9)


def build(out,seed=20260916):
    begin=time.monotonic();b=WoodlandBuilder(seed);r=b.rng
    # Complete first-part heightfield retains the existing conservative shadow certificate.
    x=np.linspace(-22,22,900);y=np.linspace(-13,65,1200);xx,yy=np.meshgrid(x,y)
    zz=floor_height(xx,yy)+.0045*n3(xx*41,yy*41)+.002*n3(xx*109,yy*109)
    b.terrain=zz;b.terrain_bounds=(-22,22,-13,65)
    b.surface('Continuous_winding_forest_floor',np.stack([xx,yy,zz],axis=-1),0)
    print('Terrain ready',time.monotonic()-begin,flush=True)
    # Gravel becomes dense only in the active streambed and inside-bend depositional bars.
    for i in range(11200):
        y0=r.uniform(-9,28);x0=float(channel(y0))+r.normal(0,1.35)
        z=float(b.ground(x0,y0));d=abs(x0-channel(y0))
        if d>2.7 or z>.18 and r.uniform()>.18:continue
        rr=np.exp(r.uniform(np.log(.012),np.log(.13)))
        vv,ff=base.rock_mesh(int(r.integers(1,2**30)),(rr,rr*r.uniform(.65,1.1),rr*r.uniform(.32,.7)),1 if rr<.07 else 2,True)
        vv+=np.array([x0,y0,z-vv[:,2].min()-np.ptp(vv[:,2])*.43]);b.add('Submerged_gravel_and_point_bars',vv,ff,mat=2)
    for i,(x0,y0,rr) in enumerate([(-1.3,-4.6,.65),(1.6,-3.0,.64),(-1.75,.6,.87),(2.25,1.8,.60),(-.95,5.8,.62),(1.5,8,.71),(-2.7,12.3,.59),(.4,3.2,.21),(.1,-2.1,.20)]):
        boulder(b,x0,y0,(rr,rr*.80,rr*.54),400+i,True,.30 if i<7 else .42)
    print('Substrate rocks ready',time.monotonic()-begin,flush=True)
    # Mature bank trees have different spacing, clear-bole heights and crown forms.
    sites=[(-3.9,.7,13.8,.46,'beech',True),(4.5,2.2,14.8,.49,'lean',True),(-3.8,5.9,12.0,.42,'beech',True),
           (4.3,7.6,14.5,.35,'birch',True),(-2.8,12.0,11.7,.36,'lean',True),(4.1,15.2,13.9,.42,'beech',True),
           (-6.2,-1.9,17,.48,'beech',False),(6.6,-2.0,15,.38,'birch',False),(-7.4,7,14,.40,'birch',False),
           (8.,9.3,16,.39,'beech',False)]
    for _ in range(48):
        y0=r.uniform(5,62);x0=r.uniform(-19,19)
        if abs(x0-channel(y0))<2.25 or any((x0-a)**2+(y0-c)**2<3.0 for a,c,*_ in sites):continue
        sites.append((x0,y0,r.uniform(10,18),r.uniform(.19,.39),r.choice(['beech','birch','lean'],p=[.56,.29,.15]),False))
    for i,site in enumerate(sites):
        tree(b,*site)
        if i%8==0:print('Trees',i+1,'/',len(sites),time.monotonic()-begin,flush=True)
    # Moisture-biased thickets fill the banks and screen distant sky at eye level.
    # Broad living laminae remain geometrically attached to their branching stems.
    for i in range(500):
        y0=r.uniform(-2.7,47);side=r.choice([-1,1]);x0=float(channel(y0))+side*r.uniform(2.05,11.2)
        origin=np.array([x0,y0,float(b.ground(x0,y0))]);h=r.uniform(.85,2.3)
        if origin[2]<.09:continue
        branches=int(r.integers(4,7));phase=r.uniform(0,6.28)
        for k in range(branches):
            a=phase+k*2.40;end=origin+[np.cos(a)*h*.34,np.sin(a)*h*.34,h*r.uniform(.68,1.0)]
            path=np.array([origin,(origin+end)*.5+[0,0,.06],end]);b.tube('Understory_woody_stems',path,[.009,.005,.0007],8,5)
            for j in range(int(r.integers(4,7))):
                q=.25+.70*j/6;at=point_on(path,q);aa=a+(1 if j%2 else -1)*1.1
                grow_spray(b,at,[np.cos(aa),np.sin(aa),r.uniform(-.12,.20)],r.uniform(.24,.43),8,k,.205,int(r.integers(8,12)))
    # A younger woodland tier fills the space below the tall mature crowns.
    for x0,y0,h0 in [(-3.0,1.9,5.7),(3.3,4.2,6.1),(-3.0,8.9,6.2),(3.6,12.3,7.2),(-3.8,16.8,7.8),(4.3,21,8.2),(-4.6,24,9.1),(4.8,29,7.4),(-6.2,30,8.2),(7.3,36,9)]:
        tree(b,x0,y0,h0,r.uniform(.105,.17),'beech',False)
    # A dense, genuinely three-dimensional broadleaf tier screens sky at eye level.
    # Randomized spacing and overlap are evaluated against the existing trees.
    background_sites=[]
    for candidate in range(550):
        y0=r.uniform(18,62);x0=r.uniform(-21,21)
        if abs(x0-channel(y0))<2.2 and y0<32:continue
        if any((x0-a)**2+(y0-c)**2<2.15 for a,c in background_sites):continue
        background_sites.append((x0,y0))
        background_broadleaf(b,x0,y0,r.uniform(8.5,16.2),r.uniform(.074,.16))
        if len(background_sites)>=88:break
    print('Background woodland ready',len(background_sites),time.monotonic()-begin,flush=True)
    print('Canopy ready',time.monotonic()-begin,flush=True)
    # Hollow diagonal nurse log, supported at both ends on the banks.
    start=[-2.4,6.2,float(b.ground(-2.4,6.2))+.27]
    end=[2.05,8.7,float(b.ground(2.05,8.7))+.24]
    hollow_log(b,start,end,.245)
    # Coherent leaf litter blankets the soil, with gaps where water washes it away.
    count=200000;lx=r.uniform(-9,9,count);ly=r.uniform(-9,31,count)
    lz=b.ground(lx,ly);prob=.52+.30*n3(lx*.7,ly*.7);keep=(lz>.06)&(r.uniform(size=count)<prob)
    lx,ly,lz=lx[keep],ly[keep],lz[keep];normals=b.ground_normal(lx,ly)
    for i,(x0,y0,z0,gn) in enumerate(zip(lx,ly,lz,normals)):
        a=r.uniform(0,6.28);d=unit([np.cos(a),np.sin(a),-(gn[0]*np.cos(a)+gn[1]*np.sin(a))/max(.25,gn[2])])
        side=unit(np.cross([0,0,1],d));normal=np.cross(d,side)
        roll=np.arctan2(-np.dot(side,gn),np.dot(normal,gn));L=r.uniform(.040,.103)
        b.leaf('Damp_layered_leaf_litter',[x0,y0,z0+.004],d,L,L*r.uniform(.48,.79),11,roll+r.uniform(-.13,.13),r.uniform(.025,.075),4)
    # Concentrated near-bank litter improves actual visible coverage, rather than
    # spending triangles on the far, hidden forest floor.
    near_y=r.uniform(-6.8,7.0,22000);side=r.choice([-1,1],size=len(near_y))
    near_x=channel(near_y)+side*r.uniform(1.45,3.3,len(near_y));near_z=b.ground(near_x,near_y)
    keep=near_z>.07;near_x,near_y,near_z=near_x[keep],near_y[keep],near_z[keep]
    gnall=b.ground_normal(near_x,near_y)
    for x0,y0,z0,gn in zip(near_x,near_y,near_z,gnall):
        a=r.uniform(0,6.28);d=unit([np.cos(a),np.sin(a),-(gn[0]*np.cos(a)+gn[1]*np.sin(a))/max(.25,gn[2])])
        sideways=unit(np.cross([0,0,1],d));nn=np.cross(d,sideways)
        roll=np.arctan2(-np.dot(sideways,gn),np.dot(nn,gn));L=r.uniform(.054,.12)
        b.leaf('Damp_layered_leaf_litter',[x0,y0,z0+r.uniform(.006,.014)],d,L,L*r.uniform(.50,.76),11,roll+r.uniform(-.15,.15),r.uniform(.025,.085),4)
    print('Litter ready',len(lx)+len(near_x),time.monotonic()-begin,flush=True)
    for _ in range(370):
        y0=r.uniform(-9,28);x0=r.uniform(-8,8);z=float(b.ground(x0,y0))
        if z<.045:continue
        a=r.uniform(0,6.28);L=r.uniform(.12,.86);x1=x0+L*np.cos(a);y1=y0+L*np.sin(a)
        path=np.array([[x0,y0,z+.01],[(x0+x1)/2,(y0+y1)/2,float(b.ground((x0+x1)/2,(y0+y1)/2))+.027],[x1,y1,float(b.ground(x1,y1))+.013]])
        b.tube('Fallen_fine_branches',path,[.009,.006,.0015],8,5,True,a)
    # Visually legible near fronds, with smaller shade clusters deeper in the image.
    ferns=[(1.72,-1.5,.78),(-1.75,-1.45,.81),(-1.8,-3.0,1.02),(2.6,-2.0,1.18),(-2.55,1.4,1.03),(2.45,3.8,1.14),(-2.65,5.7,.9),(3.25,8.5,.87),(-1.9,-.2,.83),(2.2,-4.6,.92)]
    for _ in range(26):
        y0=r.uniform(-3,24);side=r.choice([-1,1]);x0=float(channel(y0))+side*r.uniform(1.9,6.8)
        if b.ground(x0,y0)>.08:ferns.append((x0,y0,r.uniform(.45,.83)))
    for v in ferns:fern(b,*v)
    print('Ferns ready',len(ferns),time.monotonic()-begin,flush=True)
    Water('forest').add(b,np.linspace(-18,18,500),np.linspace(-15,71,860),bottom=-3.)
    cfg={'scene':'forest','title':'Fernwater R6 - Meander and Nurse Log','camera':[.48,-6.75,.94],
         'target':[.10,7.5,.35],'fov':66,'sun':[-.44,.52,.70],'sun_scale':1.12,'sky_scale':.95,
         'exposure':2.35,'white_balance':6100,'water_absorption':.85,
         'r6_local_material_frames':True}
    result=b.finish(out,cfg,False)
    result['elapsed_build_seconds']=time.monotonic()-begin
    (out/'geometry.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=20260916)
    a=p.parse_args();base.prepare_waves();print(json.dumps(build(a.out/'forest',a.seed),indent=2))
if __name__=='__main__':main()
