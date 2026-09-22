"""Three deterministic environment assemblies using the recovered CYBR GEO core.

Authored geometry, not measured geology, fluid simulation, or image synthesis.
Metres in this recipe -> millimetres in CYBR GEO -> metres in native mesh stream.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import ConvexHull
import trimesh

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'src'))
from cybrgeo import Assembly,Part,Material

PALETTE=[
 Material('Sediment',(.3,.22,.13),0,.85),Material('Primary_rock',(.24,.23,.2),0,.8),
 Material('Secondary_rock',(.16,.17,.18),0,.72),Material('Grass',(.24,.25,.08),0,.8),
 Material('Sand_and_crust',(.6,.4,.2),0,.88),Material('Distant_rock',(.22,.22,.21),0,.9),
 Material('Water',(.1,.25,.28),0,.04),Material('Secondary_water',(.1,.25,.28),0,.04),
 Material('Bark',(.10,.058,.024),0,.93),Material('Living_foliage',(.065,.18,.02),0,.7),
 Material('Moss',(.07,.13,.018),0,.9),Material('Fallen_leaves',(.17,.088,.017),0,.86),
 Material('Heartwood',(.26,.15,.06),0,.8)]

def unit(v):
    v=np.asarray(v,dtype=np.float64)
    return v/np.maximum(np.linalg.norm(v,axis=-1,keepdims=True),1e-15)

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1)
    return t*t*(3-2*t)

def n3(x,y,z=0.):
    """Deterministic smoothly interpolated lattice field, bounded near [-1,1]."""
    x,y,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float),np.asarray(z,float))
    ix=np.floor(x).astype(np.int64);iy=np.floor(y).astype(np.int64);iz=np.floor(z).astype(np.int64)
    u=x-ix;v=y-iy;w=z-iz
    u=u*u*(3-2*u);v=v*v*(3-2*v);w=w*w*(3-2*w)
    out=np.zeros(x.shape)
    for a in (0,1):
      for b in (0,1):
       for c in (0,1):
        h=((ix+a)*374761393+(iy+b)*668265263+(iz+c)*2147483647+1274126177)&0xffffffff
        h=((h^(h>>13))*1274126177)&0xffffffff;h=h^(h>>16)
        out+=(h/4294967295.*2-1)*(u if a else 1-u)*(v if b else 1-v)*(w if c else 1-w)
    return out

def fractal(x,y,z=0.,octaves=4):
    out=0
    for k in range(octaves):
        f=2.03**k
        out=out+n3(x*f+11*k,y*f-7*k,z*f+.31*k)*.5**k
    return out

def grid_faces(ny,nx):
    a=np.arange((ny-1)*nx).reshape(ny-1,nx)[:,:-1].ravel()
    return np.concatenate((np.stack([a,a+1,a+nx+1],1),np.stack([a,a+nx+1,a+nx],1)))

def parameter_mesh(v,flip=False):
    v=np.asarray(v,float);ny,nx,_=v.shape
    du=np.gradient(v,axis=1);dv=np.gradient(v,axis=0)
    nn=unit(np.cross(du,dv)).reshape(-1,3);ff=grid_faces(ny,nx)
    if flip: nn=-nn;ff=ff[:,::-1]
    return v.reshape(-1,3),ff,nn

def vertex_normals(v,f):
    out=np.zeros_like(v,float);tri=v[f];area=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    for k in range(3):np.add.at(out,f[:,k],area)
    return unit(out)

class Builder:
    def __init__(self,name,seed):
        self.name=name;self.seed=seed;self.rng=np.random.default_rng(seed)
        self.groups={};self.counts={};self.water_checks=[];self.attachment_errors=[]
    def add(self,label,v,f,n=None,mat=0,flat=False):
        v=np.asarray(v,float);f=np.asarray(f,np.int64)
        if len(f)==0:return
        if flat:
            tv=v[f];nn=unit(np.cross(tv[:,1]-tv[:,0],tv[:,2]-tv[:,0]));v=tv.reshape(-1,3)
            f=np.arange(len(v)).reshape(-1,3);n=np.repeat(nn,3,axis=0)
        elif n is None:n=vertex_normals(v,f)
        assert np.isfinite(v).all() and np.isfinite(n).all()
        self.groups.setdefault((label,mat),[]).append((v,f,np.asarray(n,float)))
        self.counts[label]=self.counts.get(label,0)+1
    def surface(self,label,v,mat,flip=False):
        vv,f,n=parameter_mesh(v,flip);self.add(label,vv,f,n,mat)
    def tube(self,label,path,radii,mat=8,sides=10,bark=False,phase=0):
        path=np.asarray(path,float);rr=np.broadcast_to(radii,(len(path),))
        if len(path)<2 or np.any(rr<0):raise ValueError('Invalid tube')
        # Large trunks get geometry-resolved longitudinal bark, not a world-space
        # diagonal stripe. Smaller twigs keep an economical watertight mesh.
        large=bark and float(np.max(rr))>.055 and sides>=9
        if large:
            length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
            dense=np.linspace(0,length[-1],max(len(path),min(260,int(length[-1]/.055)+2)))
            rr=np.interp(dense,length,rr)
            path=np.stack([np.interp(dense,length,path[:,k]) for k in range(3)],1)
            sides=max(sides,32 if rr.max()>.10 else 16)
        tang=unit(np.gradient(path,axis=0));reference=np.tile([0.,0.,1.],(len(path),1))
        reference[np.abs(tang[:,2])>.85]=[1.,0.,0.]
        t=unit(np.cross(tang,reference));u=np.cross(tang,t)
        for i in range(1,len(t)):
            if np.dot(t[i],t[i-1])<0:t[i]=-t[i];u[i]=-u[i]
        ang=np.arange(sides)*2*np.pi/sides;points=[]
        distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
        for i in range(len(path)):
            if large:
                h=distance[i]
                ridges=(.043*np.sin(ang*17+phase+.18*np.sin(h*1.4))+
                        .025*np.sin(ang*29+phase*3+.20*np.sin(h*3.1)))
                fissure=np.maximum(0,np.cos(ang*11+phase+.32*np.sin(h*1.3)))**9
                relief=(ridges-.055*fissure)*np.clip(rr[i]/.12,.25,1)
                modulation=1+relief
            else:
                modulation=1+.015*np.sin(ang*7+phase)
            points.append(path[i]+(np.cos(ang)[:,None]*t[i]+np.sin(ang)[:,None]*u[i])*(rr[i]*modulation)[:,None])
        v=np.concatenate(points);f=[]
        for i in range(len(path)-1):
            a=i*sides+np.arange(sides);bb=i*sides+(np.arange(sides)+1)%sides
            c=a+sides;dd=bb+sides
            f.extend(np.stack([a,bb,dd],1));f.extend(np.stack([a,dd,c],1))
        for j in range(1,sides-1):
            f.append((0,j+1,j));a=(len(path)-1)*sides;f.append((a,a+j,a+j+1))
        self.add(label,v,np.array(f),mat=mat)
    def leaf(self,label,base,direction,length,width,mat=9,roll=0.,fold=.13):
        """Attached tapered lamina with actual midrib, curled edges and asymmetric lobes."""
        base=np.asarray(base,float);d=unit(direction)
        side=unit(np.cross([0,0,1],d))
        if np.linalg.norm(side)<.5:side=np.array([1.,0.,0.])
        normal=np.cross(d,side);side=side*np.cos(roll)+normal*np.sin(roll);normal=np.cross(d,side)
        # Keep fine distant foliage compact; resolve near litter/understory silhouettes.
        detail=(mat==11 or label in ('Understory_leaves','Divided_fern_pinnules') or
                (abs(base[0])<6 and base[1]<12 and base[2]<5))
        rows=5 if mat==11 else (7 if detail else 4)
        ts=np.linspace(0,1,rows);phase=float(base@np.array([9.31,3.17,6.29]))
        points=[]
        for t in ts:
            shape=np.sin(np.pi*t)**.82
            serration=1+.05*np.sin(t*35+phase)
            curvature=length*(fold*np.sin(np.pi*t)+.022*t*t)
            mid=base+d*length*t+normal*curvature
            w=width*.5*shape*serration
            curl=normal*length*(.040+.021*np.sin(phase))*shape
            points.extend([mid-side*w*(1+.055*np.sin(phase+t*7))-curl,
                           mid,mid+side*w*(1+.07*np.sin(phase+2+t*8))-curl])
        v=np.array(points);f=[]
        for j in range(rows-1):
            a=j*3;c=a+3
            f.extend([(a,c,a+1),(c,c+1,a+1),(a+1,c+1,a+2),(c+1,c+2,a+2)])
        # The base and tip edges collapse geometrically; remove zero-area triangles.
        f=np.asarray(f);tv=v[f];area=np.linalg.norm(np.cross(tv[:,1]-tv[:,0],tv[:,2]-tv[:,0]),axis=1)
        self.add(label,v,f[area>1e-14],mat=mat)
    def finish(self,out,config,glb=True):
        out.mkdir(parents=True,exist_ok=True);parts=[]
        label_counts={}
        for label,mat in self.groups:label_counts[label]=label_counts.get(label,0)+1
        for label,mat in list(self.groups):
            pieces=self.groups.pop((label,mat))
            unique_label=label if label_counts[label]==1 else f'{label}_mat{mat:02d}'
            counts=np.cumsum([0]+[len(v) for v,f,n in pieces])
            v=np.concatenate([q[0] for q in pieces]);f=np.concatenate([q[1]+counts[i] for i,q in enumerate(pieces)]);n=np.concatenate([q[2] for q in pieces])
            component_count=len(pieces)
            del pieces
            v*=1000
            parts.append(Part(unique_label,v,f,n,material=mat,group=label,metadata={'components':component_count,'authored':True}))
            del v,f,n,counts
        self.groups.clear()
        assembly=Assembly('CYBR_'+self.name.upper(),parts,PALETTE,metadata={
            'scene':self.name,'seed':self.seed,'source':'Deterministic authored geometric recipe',
            'renderer':'Recovered CYBR GEO V11 native spectral transport extended with scene profiles',
            'image_generation':False,'measured_geometry':False,'material_spectra':'Authored RGB-anchor reconstruction'})
        scene=assembly.save(out/'assembly')
        # The transport adapter deliberately reads the saved CYBR GEO assembly.
        part_count=len(assembly.parts)
        del assembly,parts
        restored=Assembly.load(scene)
        assert len(restored.parts)==part_count
        total=sum(len(p.faces) for p in restored.parts)
        meshpath=out/'scene.meshbin'
        with meshpath.open('wb') as stream:
            stream.write(np.asarray([total],'<u4').tobytes())
            for group,p in enumerate(restored.parts):
                for start in range(0,len(p.faces),30000):
                    faces=p.faces[start:start+30000];a=np.empty((len(faces),20),np.float32)
                    a[:,:9]=(p.vertices[faces]*.001).reshape(-1,9);a[:,9:18]=p.normals[faces].reshape(-1,9)
                    a[:,18]=p.material;a[:,19]=group;stream.write(a.astype('<f4').tobytes())
        if glb:restored.export_glb(out/(self.name+'.glb'))
        (out/'camera.json').write_text(json.dumps(config,indent=2)+'\n')
        report={'scene':self.name,'triangles':total,'parts':len(restored.parts),'components':self.counts,
                'saved_and_reloaded_with_CYBR_GEO':True,'finite_vertices':all(np.isfinite(p.vertices).all() for p in restored.parts),
                'valid_indices':all(p.faces.min()>=0 and p.faces.max()<len(p.vertices) for p in restored.parts),
                'water_checks':self.water_checks,'tested_twig_roots':len(self.attachment_errors),'maximum_twig_root_centerline_error_m':max(self.attachment_errors,default=0.),'mesh_sha256':sha(meshpath),'image_generation':False}
        (out/'geometry.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)
        return report

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
      for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

SPHERES={}
def rock_mesh(seed,scale=(1,1,1),sub=2,angular=False):
    if sub not in SPHERES:
        m=trimesh.creation.icosphere(subdivisions=sub,radius=1)
        SPHERES[sub]=(np.array(m.vertices),np.array(m.faces))
    v,f=SPHERES[sub];v=v.copy();f=f.copy();rng=np.random.default_rng(seed)
    shift=rng.uniform(-20,20,3)
    disp=.085*fractal(v[:,0]*2.3+shift[0],v[:,1]*2.3+shift[1],v[:,2]*2.3+shift[2],3)
    v*=1+disp[:,None]
    if angular:
        for _ in range(5):
            plane=unit(rng.normal(size=3));dist=rng.uniform(.69,.91);d=v@plane
            v-=np.maximum(d-dist,0)[:,None]*plane
    v*=np.asarray(scale)
    angle=rng.uniform(0,2*np.pi);c,s=np.cos(angle),np.sin(angle)
    v=v@np.array([[c,s,0],[-s,c,0],[0,0,1.]])
    return v,f

def scatter_rocks(b,terrain,regions,count,scale=(.025,.12),mat=1,label='Pebbles',reject=None):
    rng=b.rng
    for _ in range(count):
        x=rng.uniform(*regions[0]);y=rng.uniform(*regions[1])
        if reject is not None and reject(x,y):continue
        r=np.exp(rng.uniform(np.log(scale[0]),np.log(scale[1])))
        v,f=rock_mesh(int(rng.integers(1,2**30)),(r,r*rng.uniform(.65,1.1),r*rng.uniform(.35,.75)),1 if r<.1 else 2,False)
        z=float(terrain(x,y));v+=np.array([x,y,z-v[:,2].min()-r*rng.uniform(.2,.55)])
        b.add(label,v,f,mat=mat)

WATER_DOMAINS={'coast':(10,40,100,160),'forest':(0,20,18,55),'canyon':(0,0,1,1)}
def prepare_waves():
    all_modes={}
    for style,seed in [('coast',911),('forest',912),('canyon',913)]:
        rng=np.random.default_rng(seed);m=[]
        for i in range(128):
            wavelength=np.exp(rng.uniform(np.log(.75 if style=='coast' else .3),np.log(13.0 if style=='coast' else 2.6)))
            angle=rng.normal(.12 if style=='coast' else 1.4,.34)
            k=2*np.pi/wavelength
            amp=(.0028 if style=='coast' else .00013)*np.sqrt(wavelength)*(rng.uniform(.6,1.25))
            m.append([k*np.cos(angle),k*np.sin(angle),amp,rng.uniform(0,2*np.pi)])
        all_modes[style]=m
    (HERE/'wave_modes.json').write_text(json.dumps(all_modes,indent=2))
    old=(REPO/'native/broadband_ripples.h').read_text();body=old[old.index('struct RippleField'):]
    body=body.replace('for(const auto&m:RIPPLE_MODES)','for(const auto&m:(sceneStyle==1?COAST_MODES:FOREST_MODES))')
    tables='// GPL-2.0-only. Authored modes shared byte-for-byte with recipe. Not CFD.\n#pragma once\nconstexpr int RIPPLE_COUNT=128;\nconstexpr double RIPPLE_SCALE=1.0;\n'
    for name,key in [('COAST_MODES','coast'),('FOREST_MODES','forest')]:
        tables+='constexpr double '+name+'[RIPPLE_COUNT][4]={\n'+',\n'.join(' {'+','.join(f'{v:.17g}' for v in m)+'}' for m in all_modes[key])+'\n};\n'
    (REPO/'native/scene_ripples.h').write_text(tables+body)
    native=REPO/'native/spectral_scenes.cpp';native.write_text(native.read_text().replace('#include "broadband_ripples.h"','#include "scene_ripples.h"'))

class Water:
    def __init__(self,style):
        self.style=style;self.domain=WATER_DOMAINS[style]
        cx,cy,rx,ry=self.domain;self.x0=cx-rx*1.35;self.y0=cy-ry*1.35
        self.sx=800/(2.7*rx);self.sy=640/(2.7*ry)
        x=self.x0+np.arange(801)/self.sx;y=self.y0+np.arange(641)/self.sy
        xx,yy=np.meshgrid(x,y);h=np.zeros_like(xx);dx=h.copy();dy=h.copy()
        for kx,ky,a,phi in json.loads((HERE/'wave_modes.json').read_text())[style]:
            phase=kx*xx+ky*yy+phi;h+=a*np.sin(phase);dx+=a*kx*np.cos(phase);dy+=a*ky*np.cos(phase)
        self.fields=np.array([h,dx,dy],np.float32)
    def sample(self,x,y):
        x,y=np.broadcast_arrays(x,y);coords=np.array([np.clip((y-self.y0)*self.sy,0,639.9999).ravel(),np.clip((x-self.x0)*self.sx,0,799.9999).ravel()])
        return np.array([map_coordinates(a,coords,order=1,mode='nearest',prefilter=False).reshape(x.shape) for a in self.fields])
    def add(self,b,x,y,bottom=-8.):
        xx,yy=np.meshgrid(x,y);h,dx,dy=self.sample(xx,yy)
        top=np.stack([xx,yy,h],-1);v=top.reshape(-1,3);f=grid_faces(len(y),len(x));n=unit(np.stack([-dx,-dy,np.ones_like(h)],-1)).reshape(-1,3)
        # Share top perimeter vertices with walls, then bottom cap using the same ring.
        ny,nx=h.shape
        ring=np.r_[np.arange(nx),np.arange(1,ny)*nx+nx-1,(ny-1)*nx+np.arange(nx-2,-1,-1),np.arange(ny-2,0,-1)*nx]
        bot=v[ring].copy();bot[:,2]=bottom;bi=np.arange(len(bot))+len(v)
        ff=[]
        for i in range(len(ring)):
            j=(i+1)%len(ring);ff.extend([(int(ring[i]),int(bi[i]),int(bi[j])),(int(ring[i]),int(bi[j]),int(ring[j]))])
        center=np.array([[np.mean(x),np.mean(y),bottom]]);center_idx=len(v)+len(bot)
        for i in range(len(bi)):ff.append((int(bi[(i+1)%len(bi)]),int(bi[i]),center_idx))
        vertices=np.concatenate([v,bot,center]);faces=np.concatenate([f,np.array(ff)])
        normals=np.concatenate([n,np.tile([0,0,-1],(len(bot)+1,1))])
        mesh=trimesh.Trimesh(vertices,faces,process=False)
        check={'name':'Water_enclosure','watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),'positive_volume':bool(mesh.volume>0)}
        if not all(check[k] for k in ['watertight','winding_consistent','positive_volume']):raise RuntimeError(check)
        b.water_checks.append(check);b.add('Water_enclosure',vertices,faces,normals,mat=6)

# ---------------- scene 1: curved sandstone slot ----------------
def canyon(out,seed,glb=True):
    b=Builder('canyon',seed);rng=b.rng
    def floor(x,y):
        x,y=np.broadcast_arrays(x,y)
        return -.10+.011*np.asarray(y)+.075*n3(x*.55,y*.55)+.0027*np.sin(53*x+3*np.sin(y*1.1))*(.4+.6*smooth(-.5,.5,n3(x*2,y*2)))
    xx,yy=np.meshgrid(np.linspace(-12,12,551),np.linspace(-10,44,921));zz=floor(xx,yy)
    b.surface('Canyon_sand',np.stack([xx,yy,zz],-1),0)
    y=np.linspace(-9,39,1201);z=np.linspace(-.7,10.5,451);yy,zz=np.meshgrid(y,z)
    center=.9*np.sin(yy*.25)+.44*np.sin(yy*.48+1)
    width=2.65+.48*np.sin(yy*.38-.6)+.23*np.sin(yy*.67+1.2)
    for side in (-1,1):
        swell=.66*np.sin(zz*.58+yy*.30+side*.7)+.20*np.sin(zz*1.02-yy*.19)
        flute=.23*np.sin(yy*1.15+zz*.25+side)*(.7+.3*np.sin(zz*.42))
        layer=zz+.23*np.sin(yy*.54)+.11*np.sin(yy*.28+zz*.1)
        micro=.003*np.sin(layer*7+.7*n3(yy*.6,zz*.4))
        micro+=.0025*n3(yy*7,zz*7,side+2)
        xx=center+side*(width+swell+flute+micro+.018*zz)
        # Make the upper opening narrower at alternating bends, without a sky card.
        xx+=side*(-.16*np.exp(-((zz-9.5)/3.6)**2)*(1+np.sin(yy*.43)))
        b.surface('Left_sandstone' if side<0 else 'Right_sandstone',np.stack([xx,yy,zz],-1),1,flip=side>0)
    scatter_rocks(b,floor,((-3.6,3.6),(-8,30)),500,(.005,.044),2,'Sandstone_fragments')
    # A few larger naturally buried fragments at turns.
    for x,y,r in [(-1.65,-.4,.30),(2.35,4.7,.43),(-1.0,11.5,.50),(-2.1,-3.2,.19)]:
        v,f=rock_mesh(int(rng.integers(1,2**30)),(r,r*.65,r*.37),3,True);v+=np.array([x,y,float(floor(x,y))+.04]);b.add('Fallen_blocks',v,f,mat=2)
    cfg={'scene':'canyon','title':'Sandstone Passage','camera':[-1.1,-5.7,1.60],'target':[.40,7.5,2.6],'fov':74,
         'sun':[-.33,-.12,.936],'exposure':2.5,'white_balance':6200,'sun_scale':1.0,'sky_scale':1.4,'water_absorption':1.0}
    return b.finish(out,cfg,glb)

# ---------------- scene 2: columnar basalt at a quiet coast ----------------
def basalt_column(b,x,y,r,height,z0=-.15,seed=1,label='Basalt_columns'):
    rng=np.random.default_rng(seed);count=int(rng.choice([5,6,6,6,7]));angles=np.arange(count)*2*np.pi/count+rng.uniform(-.12,.12)
    radii=r*rng.uniform(.88,1.12,count);poly=np.stack([np.cos(angles)*radii,np.sin(angles)*radii],1)
    # Bevel only the sharp corners, preserving broad polygonal cleavage faces.
    outline=[]
    for i,p in enumerate(poly):
        outline.extend([p*.93+poly[(i-1)%count]*.07,p*.93+poly[(i+1)%count]*.07])
    outline=np.array(outline);ns=len(outline)
    breaks=[z0];z=z0
    while z<height-.18:
        z=min(height,z+rng.uniform(.68,1.92));breaks.append(z)
    if breaks[-1]<height:breaks.append(height)
    lean=rng.uniform(-.07,.07,2);toptilt=rng.uniform(-.24,.24,2)
    for si in range(len(breaks)-1):
        a=breaks[si]+(.005 if si else 0);c=breaks[si+1]-.004
        levels=np.array([a,a+.016,min(a+.07,(a+c)/2),(a+c)/2,max(c-.07,(a+c)/2),c-.016,c])
        taper=1-.025*levels/height
        for j in range(ns):
            j2=(j+1)%ns;uu=np.linspace(0,1,5)
            ring=outline[j][None]*(1-uu[:,None])+outline[j2][None]*uu[:,None]
            points=np.empty((len(levels),len(uu),3))
            for k,z in enumerate(levels):
                shrink=.988 if k in (0,len(levels)-1) else 1.
                pts=ring*taper[k]*shrink
                pts+=lean*(z-z0)
                points[k,:,:2]=pts+[x,y]
                points[k,:,2]=z+(ring@toptilt)*(z/height)
            b.surface(label,points,1,flip=False)
        # Caps, with sloped tops and genuine closed solid construction at segments.
        for z,rev in [(a,True),(c,False)]:
            v=np.c_[outline*(1-.025*z/height)*.988+lean*(z-z0)+[x,y],z+(outline@toptilt)*(z/height)]
            f=np.array([(0,j,j+1) for j in range(1,ns-1)])
            if rev:f=f[:,::-1]
            b.add(label,v,f,mat=1,flat=True)

def coast(out,seed,glb=True):
    b=Builder('coast',seed);rng=b.rng
    def floor(x,y):
        x,y=np.broadcast_arrays(x,y)
        shoreline=1.4+.15*y+.75*np.sin(y*.24)
        base=.12-.245*(x-shoreline)+.09*fractal(x*.55,y*.55,octaves=3)
        base-=3.8*smooth(10,34,y)
        return np.minimum(base,1.7+.10*fractal(x*.2,y*.2,octaves=2))
    xx,yy=np.meshgrid(np.linspace(-24,29,621),np.linspace(-18,65,841))
    z=floor(xx,yy);b.surface('Volcanic_shore',np.stack([xx,yy,z],-1),0)
    # Unstructured edge and staggered column heights, not an evenly cut architectural wall.
    r=.56
    for row in range(13):
      for col in range(8):
        x=-7.4+col*.98+(row%2)*.47;y=-.4+row*.85
        if x>-.7+.5*np.sin(y*.51):continue
        edge=smooth(-.2,-4.5,x)
        h=.85+4.9*edge+1.85*n3(x*.54+3,y*.48)-.09*abs(y-5)+rng.uniform(-.45,.45)
        if h<.55:continue
        z0=max(-.25,float(floor(x,y))-.55)
        basalt_column(b,x,y,r*rng.uniform(.91,1.04),max(z0+.5,h),z0,int(rng.integers(1,2**30)))
    # Sea stacks: bundles of broken columns, all three-dimensional.
    for centerx,centery,rad,h in [(9.0,38,1.6,5.8),(19,62,2.5,10.0),(-12,46,3.,8.)]:
      for j in range(16):
        a=rng.uniform(0,2*np.pi);rr=rad*np.sqrt(rng.uniform());x=centerx+rr*np.cos(a);y=centery+rr*np.sin(a)
        basalt_column(b,x,y,.56+rng.uniform(0,.2),h*(1-.3*rr/rad)+rng.uniform(-.4,.4),-4,int(rng.integers(1,2**30)),'Sea_stacks')
    scatter_rocks(b,floor,((-11,9),(-15,24)),5900,(.012,.17),2,'Basalt_pebbles',lambda x,y:floor(x,y)<-.75)
    for x,y,r in [(-.2,-4.0,.75),(2.8,1.2,.9),(-2.9,-7.2,.52),(3.5,6,.6),(6.5,12,1.2)]:
        v,f=rock_mesh(int(rng.integers(1,2**30)),(r,r*.85,r*.65),3,True)
        v+=np.array([x,y,float(floor(x,y))+.10]);b.add('Broken_shore_rocks',v,f,mat=2)
    Water('coast').add(b,np.r_[np.linspace(-19,28,541),np.linspace(28.5,1050,31)],np.r_[np.linspace(-18,75,801),np.linspace(80,2000,56)],bottom=-45)
    cfg={'scene':'coast','title':'Basalt Tide','camera':[5.3,-8.8,2.05],'target':[-.2,6.9,1.95],'fov':69,
         'sun':[-.43,-.64,.637],'exposure':1.55,'white_balance':6400,'sun_scale':.82,'sky_scale':1.1,'water_absorption':.65}
    return b.finish(out,cfg,glb)

# ---------------- scene 3: mossy woodland stream ----------------
def stream_center(y):return .54*np.sin(np.asarray(y)*.26)+.43*np.sin(np.asarray(y)*.12+1.3)
def forest_floor(x,y):
    x,y=np.broadcast_arrays(x,y);distance=np.abs(x-stream_center(y))
    bank=smooth(1.10,2.50,distance)
    return -.44+1.11*bank+.12*fractal(x*.58,y*.58,octaves=3)*(.22+.78*bank)+.026*np.sin(y*.32)*bank

def fern(b,x,y,size=1.):
    rng=b.rng;z=float(forest_floor(x,y))+.007;origin=np.array([x,y,z]);num=int(rng.integers(6,11))
    for k in range(num):
        angle=2*np.pi*k/num+rng.uniform(-.20,.20);d=np.array([np.cos(angle),np.sin(angle),0.])
        length=size*rng.uniform(.6,1.05);ts=np.linspace(0,1,13)
        path=origin+ts[:,None]*length*d+np.array([0,0,1])[None]*((.60*ts-.31*ts*ts)*length)[:,None]
        b.tube('Fern_stems',path,np.linspace(.0023,.0006,len(ts))*size,9,5)
        side=np.array([-d[1],d[0],0])
        for j,t in enumerate(np.linspace(.16,.97,17)):
            center=origin+d*(t*length)+np.array([0,0,(.60*t-.31*t*t)*length])
            reach=length*.235*np.sin(np.pi*t)**.72
            for sign in (-1,1):
                end=center+sign*side*reach+d*reach*.32+np.array([0,0,.035*length])
                b.tube('Fern_stems',[center,end],[.0009*size,.0003*size],9,4)
                fd=unit(end-center)
                # Divided pinnae rather than large solid leaf ribbons.
                for q in np.linspace(.16,.94,7):
                    at=center+(end-center)*q;leaflen=reach*.27*(1-.45*q)
                    for s in (-1,1):
                        dire=fd*.4+d*s*.70+np.array([0,0,.12])
                        b.leaf('Fern_leaflets',at,dire,leaflen,leaflen*.34,9,rng.uniform(-.2,.2),.07)


def tree(b,x,y,height,radius,index):
    rng=b.rng;z=float(forest_floor(x,y));ts=np.linspace(0,1,35)
    bend=rng.uniform(-.7,.7,2);phase=rng.uniform(0,7)
    path=np.c_[x+bend[0]*ts**1.4+.06*np.sin(ts*9+phase)*ts,y+bend[1]*ts**1.4,z+height*ts]
    radii=radius*(1-.75*ts)**.8*(1+.17*np.exp(-ts*17))
    b.tube('Tree_trunks',path,radii,8,24,True,phase)
    for k in range(5):
        a=phase+2*np.pi*k/5;end=np.array([x+np.cos(a)*radius*3.8,y+np.sin(a)*radius*3.8,0]);end[2]=forest_floor(end[0],end[1])+.01
        st=np.array([x,y,z+radius*.6]);mid=st*.35+end*.65+np.array([0,0,radius*.12]);b.tube('Buttress_roots',[st,mid,end],[radius*.45,radius*.19,.012],8,9,True,phase)
    # Connected branches and clusters. Camera-near trees get fuller crowns.
    for k in range(15):
        t=rng.uniform(.27,.86);base=path[int(t*34)];a=phase+k*2.39996;spread=height*rng.uniform(.18,.29)
        tip=base+np.array([np.cos(a)*spread,np.sin(a)*spread,spread*.45]);mid=base*.45+tip*.55+np.array([0,0,spread*.12])
        b.tube('Canopy_branches',[base,mid,tip],[radius*.15,radius*.066,.01],8,7,True,phase)
        for j in range(11):
            q=rng.uniform(.25,1)
            at=base+(mid-base)*(q/.55) if q<.55 else mid+(tip-mid)*((q-.55)/.45)
            # Secondary twig roots must lie on the actual polyline tube, not
            # on the straight chord below the curved parent branch.
            parent_a,parent_b=(base,mid) if q<.55 else (mid,tip)
            param=np.clip(np.dot(at-parent_a,parent_b-parent_a)/np.dot(parent_b-parent_a,parent_b-parent_a),0,1)
            b.attachment_errors.append(float(np.linalg.norm(at-(parent_a+(parent_b-parent_a)*param))))
            theta=a+rng.uniform(-1.4,1.4);length=spread*rng.uniform(.20,.45)
            end=at+np.array([np.cos(theta)*length,np.sin(theta)*length,rng.uniform(-.08,.20)*length]);b.tube('Fine_twigs',[at,end],[.005,.0015],8,5)
            for l in range(11):
                f=(l+1)/12;pos=at*(1-f)+end*f;dire=unit(end-at)+np.array([np.cos(theta+1.6*(1 if l%2 else -1)),np.sin(theta+1.6*(1 if l%2 else -1)),rng.uniform(-.25,.25)])
                b.leaf('Canopy_leaves',pos,dire,rng.uniform(.22,.39),rng.uniform(.11,.20),9,rng.uniform(-1.0,1.0))

def forest(out,seed,glb=True):
    b=Builder('forest',seed);rng=b.rng
    xx,yy=np.meshgrid(np.linspace(-22,22,721),np.linspace(-13,60,1001));z=forest_floor(xx,yy)
    z+=.004*n3(xx*35,yy*35)*smooth(.0,.55,z)
    b.surface('Forest_substrate',np.stack([xx,yy,z],-1),0)
    rock_points=[(-1.75,-3.1,.90),(2.1,-2.1,.85),(-1.1,1.4,.69),(2.4,3.4,1.04),(-1.5,6.2,.85),(.0,7.5,.47),(-2.0,11.8,1.2),(2.8,13,.9)]
    for j,(x,y,r) in enumerate(rock_points):
        v,f=rock_mesh(seed+j*101,(r,r*.72,r*.60),4,False);v+=np.array([x,y,float(forest_floor(x,y))+.08]);b.add('Mossy_boulders',v,f,mat=1)
        # Sparse physical moss filaments only on upper rock patches.
        take=rng.choice(len(v),min(360,len(v)),replace=False)
        for idx in take:
            pos=v[idx]
            if pos[2]<.17 or n3(*pos*3)<.02:continue
            up=np.array([rng.uniform(-.01,.01),rng.uniform(-.01,.01),rng.uniform(.006,.022)])
            b.tube('Moss_filaments',[pos,pos+up],[.001,.0003],10,4)
    scatter_rocks(b,forest_floor,((-9,9),(-11,40)),2200,(.012,.12),2,'Stream_gravel')
    positions=[(-3.4,-1.2,12,.39),(4.2,.8,13,.48),(-4.4,5.2,14,.47),(3.5,10,15,.43),(-3.2,14,13,.38),(6.0,14,14,.42)]
    for k in range(128):
        y=rng.uniform(12,57);x=rng.uniform(-18,18)
        if abs(x-stream_center(y))<2.9:continue
        positions.append((x,y,rng.uniform(10,18),rng.uniform(.16,.43)))
    positions += [(-2.9,11,6.2,.12),(3.5,18,6.8,.14),(-4.8,22,7.4,.16),(2.9,27,7.1,.15)]
    for i,(x,y,h,r) in enumerate(positions):tree(b,x,y,h,r,i)
    # Fallen log crossing the stream farther up, with actual circular end grain.
    start=np.array([-3.0,8.8,1.4]);end=np.array([3.9,12.8,1.14]);ts=np.linspace(0,1,39)
    path=start+(end-start)*ts[:,None];path[:,2]-=.16*np.sin(np.pi*ts)
    b.tube('Fallen_log',path,.235*(1-.15*ts),8,40,True,1.5)
    tangent=unit(end-start);tt=unit(np.cross(tangent,[0,0,1]));uu=np.cross(tangent,tt)
    angles=np.linspace(0,2*np.pi,65)[:-1];center=end+tangent*.004
    disk=np.vstack([center,center+(tt[None]*np.cos(angles)[:,None]+uu[None]*np.sin(angles)[:,None])*.197])
    f=np.array([(0,j+1,(j+1)%64+1) for j in range(64)]);b.add('Log_endgrain',disk,f,mat=12)
    # Roots, branches and leaf litter break the bank's uniformity.
    for _ in range(26):
        x=rng.uniform(-5,5);y=rng.uniform(-6,24)
        if abs(x-stream_center(y))<1.5:continue
        pos=np.array([x,y,forest_floor(x,y)+.02]);end=pos+np.array([rng.uniform(-.5,.5),rng.uniform(.15,.8),.07])
        b.tube('Fallen_twigs',[pos,(pos+end)*.5+[0,0,.05],end],[.012,.008,.003],8,6)
    for _ in range(3400):
        x=rng.uniform(-7,7);y=rng.uniform(-9,27)
        if abs(x-stream_center(y))<1.65:continue
        base=np.array([x,y,float(forest_floor(x,y))+.012]);d=[rng.uniform(-1,1),rng.uniform(-1,1),.03]
        b.leaf('Forest_litter',base,d,rng.uniform(.045,.13),rng.uniform(.025,.070),11,rng.uniform(-.4,.4),.15)
    for x,y,sz in [(-1.9,-3.75,1.65),(2.15,-3.45,1.65),(-2.5,-2.4,1.2),(2.7,-1.4,1.3),(-2.2,3.5,1.0),(2.5,6,.95),(-3.0,8,.9),(3.3,13,1.1),(-2.8,17,1.2),(-4.3,1.8,.75),(4.2,3.0,1.0)]:fern(b,x,y,sz)
    Water('forest').add(b,np.linspace(-16,16,601),np.linspace(-14,64,1101),bottom=-3.)
    cfg={'scene':'forest','title':'Fernwater','camera':[.30,-5.65,1.26],'target':[.1,9.0,1.75],'fov':72,
         'sun':[-.43,.44,.788],'exposure':2.4,'white_balance':6200,'sun_scale':.92,'sky_scale':1.2,'water_absorption':1.1}
    return b.finish(out,cfg,glb)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--scene',choices=['canyon','coast','forest','all'],default='all');parser.add_argument('--out',type=Path,required=True);parser.add_argument('--seed',type=int,default=20260915);parser.add_argument('--no-glb',action='store_true');parser.add_argument('--prepare-only',action='store_true')
    a=parser.parse_args();prepare_waves()
    if a.prepare_only:return
    for i,name in enumerate(['canyon','coast','forest']):
        if a.scene not in (name,'all'):continue
        start=time.monotonic();globals()[name](a.out/name,a.seed+i*1000,not a.no_glb);print(f'{name}: completed in {time.monotonic()-start:.1f}s',flush=True)
if __name__=='__main__':main()
