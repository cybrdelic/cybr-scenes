#!/usr/bin/env python3
"""Obsidian Reach IV: explicit detached crust, rubble levees and thermal light.

All surfaces are built in metres. CYBR GEO owns the named-part assembly and
validation. Thermal radiation uses the vendored CYBR ELEMENTS optics. This is
an authored geological still, not a calibrated lava-flow simulation.
"""
from authoring import *
from scipy.spatial import Voronoi
from shapely.geometry import Polygon, box
import gc

# Slightly warmer, darker mineral palette than the previous blue-grey frame.
for i in rockm:
    q=list(mats[i]);q[0]*=1.12;q[2]*=.91;mats[i]=tuple(q)
raftm=[material('Detached_cooling_crust_%02d'%i,(v,v*.97,v*.93),.38+.018*i,.046,kind=6)
       for i,v in enumerate(np.linspace(.022,.052,14))]
edgeheat=[material('Thin_incandescent_crust_edge_%02d'%i,(.022,.022,.022),.55,.043,kind=7,temp=t)
          for i,t in enumerate([990,1060,1130,1210])]

# High density close to the camera, graded outside the focal reach.
x=np.r_[np.linspace(-65,-18,75,endpoint=False),np.linspace(-18,20,410,endpoint=False),np.linspace(20,75,80)]
z=np.r_[np.linspace(-30,22,420,endpoint=False),np.linspace(22,160,260)]
X,Z=np.meshgrid(x,z);Y=terrain(X,Z)
add('Layered_broken_channel_banks',np.c_[X.ravel(),Y.ravel(),Z.ravel()],gridfaces(*X.shape),groundmat)
# Broader material/erosion context, not a black void behind the set.
x=np.linspace(-450,450,150);z=np.linspace(151,1500,130);X,Z=np.meshgrid(x,z)
Y=5.6+.018*Z+18*(field(X,Z,.018,4)-.5)
add('Distant_volcanic_apron',np.c_[X.ravel(),Y.ravel(),Z.ravel()],gridfaces(*X.shape),rockm[2])
dem_sources=json.loads((A/'dem/source.json').read_text());tiles=[]
for src in dem_sources:
    rgb=np.asarray(Image.open(A/'dem'/src['filename']),np.float64)
    tiles.append(rgb[...,0]*256+rgb[...,1]+rgb[...,2]/256-32768)
dem=np.concatenate(tiles,axis=0)[::-1,::-1].T[::2,::2]
spacing=2*np.pi*6378137/2**11*np.cos(np.deg2rad(33.82))/256*2
XX,ZZ=np.meshgrid((np.arange(dem.shape[1])-(dem.shape[1]-1)/2)*spacing*.60,
                 np.arange(dem.shape[0])*spacing*.60+3500)
YY=np.maximum(dem-200,0)*.60+20
add('Relocated_DEM_derived_horizon',np.c_[XX.ravel(),YY.ravel(),ZZ.ravel()],gridfaces(*XX.shape),rockm[2],group='dem_backdrop')
print('Built terrain',round(time.monotonic()-t0,1),flush=True)

# Photogrammetric rocks; hero fragments preserve the source UVs and normals.
scans=[];lods=[]
for i,name in enumerate(('boulder_01','namaqualand_boulder_03')):
    folder=A/'scans'/name;mesh=trimesh.load(folder/(name+'_2k.gltf'),force='scene').to_geometry()
    v=np.asarray(mesh.vertices)-mesh.bounds.mean(0);f=np.asarray(mesh.faces);n=np.asarray(mesh.vertex_normals);uv=np.asarray(mesh.visual.uv)
    scans.append((v,f,n,uv))
    per=[]
    for cells in [6,14,28]:
        keys=np.floor((v-v.min(0))/np.maximum(np.ptp(v,axis=0),1e-9)*cells).astype(np.int32)
        _,inv=np.unique(keys,axis=0,return_inverse=True);ct=np.bincount(inv)
        cv=np.zeros((len(ct),3));cn=np.zeros_like(cv);np.add.at(cv,inv,v);np.add.at(cn,inv,n);cv/=ct[:,None];cn/=np.maximum(np.linalg.norm(cn,axis=1,keepdims=True),1e-9)
        cf=inv[f];good=np.logical_and.reduce([cf[:,0]!=cf[:,1],cf[:,0]!=cf[:,2],cf[:,1]!=cf[:,2]])
        ff=f[good];cf=cf[good]
        # Keep coincident UV seam corners separate, never average texture charts.
        pp=cv[cf].reshape(-1,3);nn=cn[cf].reshape(-1,3);uu=uv[ff].reshape(-1,2);faces=np.arange(len(pp)).reshape(-1,3)
        per.append((pp,faces,nn,uu))
    lods.append(per)
    diff=srgb(np.asarray(Image.open(folder/'textures'/(name+'_diff_2k.jpg')).convert('RGB'),np.float32)/255)
    nor=np.asarray(Image.open(folder/'textures'/(name+'_nor_gl_2k.jpg')).convert('RGB'),np.float32)/127.5-1
    arm=np.asarray(Image.open(folder/'textures'/(name+'_arm_2k.jpg')).convert('RGB'),np.float32)/255
    tex=np.concatenate([diff,nor,arm[...,1:2],arm[...,0:1]],-1).astype('<f4')
    with (A/f'scan_texture_{i}.bin').open('wb') as out:out.write(struct.pack('<II',tex.shape[1],tex.shape[0]));out.write(tex.tobytes())
    del diff,nor,arm,tex

def scan(name,which,x,z,scale,angle,lod=-1,buried=.36):
    vv,f,nn,uv=scans[which] if lod<0 else lods[which][lod]
    R=trimesh.transformations.euler_matrix(rng.uniform(-.65,.65),angle,rng.uniform(-.6,.6))[:3,:3]
    v=(vv*scale)@R.T;n=nn@R.T
    y=float(terrain(x,z))-v[:,1].min()-buried*np.ptp(v[:,1]);v+=np.array([x,y,z])
    keep=v[f].mean(axis=1)[:,1]>float(terrain(x,z))-.15*scale
    add(name,v,f[keep],scanm[which],group='measured_rock_fragments',uv=uv,normals=n)

# Purposeful, partly buried outcrops frame the flow; not equally spaced props.
hero=[(0,-6.9,-11,.70),(1,-8.7,-8,.75),(0,-7.3,-5,.72),
      (1,8.8,-7,.78),(0,9.3,-2,.88),(1,9.8,5,.85),
      (1,-6.1,7,1.2),(0,-7.8,13,1.4),(1,-9.8,20,1.2),
      (0,6.0,16,1.0),(1,7.2,26,.95),(1,-8.3,31,1.05)]
for j,(k,xx,zz,s) in enumerate(hero):scan('Embedded_outcrop_%02d'%j,k,xx,zz,s,rng.uniform(0,2*np.pi))
for j in range(95):
    zz=rng.uniform(-22,98);side=-1 if j%2 else 1;xx=center(zz)+side*(width(zz)+rng.uniform(.40,7.0))
    scan('Levee_scan_%03d'%j,j%2,xx,zz,rng.uniform(.24,.72),rng.uniform(0,2*np.pi),lod=1,buried=.45)

# Thousands of real scan fragments replace the flat-shaded icosahedra.
# UVs and scan normals are preserved down to the small-fragment LOD.
N=7400
zz=rng.uniform(-26,142,N);side=rng.choice([-1,1],N)
bank=rng.exponential(3.35,N)+.12
xx=center(zz)+side*(width(zz)+bank)
sc=np.clip(rng.lognormal(-1.06,.55,N),.085,.80)
yy=terrain(xx,zz)
for j in range(N):
    if bank[j]>17 or (zz[j]>90 and j%2):continue
    k=j%2;close=(xx[j]+2.8)**2+(zz[j]+15)**2<95;vv,f,nn,uv=lods[k][1 if close else 0]
    R=trimesh.transformations.euler_matrix(rng.uniform(-1.1,1.1),rng.uniform(0,6.283),rng.uniform(-1.1,1.1))[:3,:3]
    v=(vv*sc[j])@R.T;n=nn@R.T
    y=yy[j]-v[:,1].min()-.40*np.ptp(v[:,1])
    v+=np.array([xx[j],y,zz[j]])
    add('Photogrammetry_clinker_%05d'%j,v,f,scanm[k],group='dense_scanned_clinker',uv=uv,normals=n)
# A compact shape library is retained only for tiny, entrained fragments.
rocklib=[]
for j in range(36):
    ico=trimesh.creation.icosphere(subdivisions=1)
    v=np.asarray(ico.vertices).copy();f=np.asarray(ico.faces)
    v*=rng.uniform(.80,1.10,(len(v),1));v[:,1]*=.36
    rocklib.append((v,f))
print('Built interlocked rocky banks',sum(len(p.faces) for p in parts),round(time.monotonic()-t0,1),flush=True)

# Lava material coordinates. Most cooling crust is now separate geometry above
# this hot continuous interior; the intervening gaps are actual 3D openings.
LW,LH=1024,4096;xmin,xmax,zmin,zmax=-5.3,5.3,-27.,137.
U,ZZ=np.meshgrid(np.linspace(xmin,xmax,LW,dtype=np.float32),np.linspace(zmin,zmax,LH,dtype=np.float32))
f0=field(U+73,ZZ-62,.60,4);f1=field(U-29,ZZ+3,2.3,4)
height=.14*(f0-.5)+.033*(f1-.5)+.15*np.maximum(0,1-(U/4.5)**2)
# Longitudinal skin shear and curved ropes are only the residual hot-fluid skin;
# discrete cold rafts, modeled below, dominate the broad surface silhouettes.
height+=.023*np.sin((ZZ+.14*U*U+.16*np.sin(U*1.7))*17)*(0.3+.7*f0)
# Molten upper skin ranges from red-orange to pale amber, not a flat emissive color.
T=1340+145*field(U+91,ZZ-12,1.9,4)+25*field(U-104,ZZ+70,7,3)
T-=70*np.clip(np.abs(U)/4.6,0,1)**3
skin=np.clip((field(U+312,ZZ*.48-97,3.0,4)-.55)*9,0,1)
T=T*(1-skin)+1030*skin
rough=.25+.2*f0
ny,nx=np.gradient(height,(zmax-zmin)/(LH-1),(xmax-xmin)/(LW-1))
normal=np.stack([-nx,np.ones_like(nx),-ny],-1);normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
tex=np.stack([.020+.008*f0,height,T,rough,normal[...,0],normal[...,1],normal[...,2],np.ones_like(T)],-1).astype('<f4')
with (A/'lava_skin.bin').open('wb') as f:f.write(struct.pack('<II4f',LW,LH,xmin,xmax,zmin,zmax));f.write(tex.tobytes())

def sample_h(u,z):
    u,z=np.broadcast_arrays(u,z)
    return map_coordinates(height,np.stack([((z-zmin)/(zmax-zmin)*(LH-1)).ravel(),((u-xmin)/(xmax-xmin)*(LW-1)).ravel()]),order=1,mode='nearest').reshape(u.shape)

def base_world(u,z):
    u,z=np.broadcast_arrays(u,z)
    return np.c_[(center(z)+u).ravel(),(level(z)+sample_h(u,z)).ravel(),z.ravel()]

NX=260;zl=np.r_[np.linspace(zmin,24,800,endpoint=False),np.linspace(24,zmax,450)]
UU,ZG=np.meshgrid(np.linspace(-1,1,NX),zl);UL=UU*width(ZG)
v=base_world(UL,ZG);f=gridfaces(*ZG.shape)
uv=np.c_[((UL-xmin)/(xmax-xmin)).ravel(),((ZG-zmin)/(zmax-zmin)).ravel()]
add('Continuous_exposed_molten_interior',v,f,heatmat,group='molten_interior',uv=uv)
for edge in [0,NX-1]:
    top=v.reshape(-1,NX,3)[:,edge];bot=top.copy();bot[:,1]-=1.1
    wall=np.stack([top,bot],1).reshape(-1,3);ff=gridfaces(len(top),2)
    if edge==0:ff=ff[:,::-1]
    add('Molten_channel_flank_%d'%edge,wall,ff,edgeheat[2],group='molten_interior')

# Irregular non-tiling crust rafts with independent slopes, thickness, curled
# rims and folded upper surfaces. Voronoi is only a fracture partition; shared
# nonlinear deformation and unequal opening widths remove straight tiling.
points=np.c_[rng.uniform(-7,7,1200),rng.uniform(zmin-8,zmax+8,1200)]
points=np.r_[points,np.c_[rng.uniform(-5,5,330),rng.uniform(-26,18,330)]]
vor=Voronoi(points);bound=box(-5.0,zmin,5.0,zmax)

def warp(u,z):
    return u+.14*np.sin(z*1.7+u*2.3)+.065*np.sin(u*8.2-z*3.4), z+.27*np.sin(u*2.4+z*.55)+.035*np.sin(u*9.1-z*2.7)

def raft_height(u,z,cu,cz,phase,pitch,amp,tilt):
    a=u-cu;b=z-cz
    # Curved, compression-aligned millimetre-to-centimetre ropes.
    phase1=(b+.30*a*a+.10*np.sin(a*3+phase)+.065*np.sin(b*5+a*4))/pitch+phase
    coarse=(.5+.5*np.cos(phase1*2*np.pi))**.76
    fine=(.5+.5*np.sin(phase1*2*np.pi*3.8+a*9))
    return .092+amp*coarse+.008*fine+tilt[0]*a+tilt[1]*b

raftcount=0
for i,p in enumerate(points):
    cu,cz=p
    if not (-4.9<cu<4.9 and zmin<cz<zmax):continue
    ids=vor.regions[vor.point_region[i]]
    if not ids or -1 in ids:continue
    poly=Polygon(vor.vertices[ids]).intersection(bound)
    if poly.is_empty or poly.geom_type!='Polygon' or poly.area<.04:continue
    # Exposure corridors follow shear, and vary along the reach. Not every crack glows.
    chance=.030
    if abs(cu-(.45*np.sin(cz*.39)+.40))<.58:chance=.28
    if 8<cz<15:chance=.17
    if rng.random()<chance:continue
    scale=rng.uniform(.92,.98)
    if abs(cu)<1.1:scale=rng.uniform(.81,.94)
    xy=np.asarray(poly.exterior.coords)[:-1];mid=xy.mean(axis=0);xy=mid+(xy-mid)*scale
    # Boundary clipping to the actual meandering, nonuniform channel width.
    if np.any(np.abs(xy[:,0])>width(xy[:,1])-.035):
        xy[:,0]=np.clip(xy[:,0],-width(xy[:,1])+.035,width(xy[:,1])-.035)
    if np.ptp(xy[:,0])<.03:continue
    mid=xy.mean(axis=0);n=len(xy)
    pts=np.r_[mid[None],xy];faces=np.array([[0,j+1,(j+1)%n+1] for j in range(n)])
    # Work in x-z plane, maintaining positive Y-facing normals.
    pv=np.c_[pts[:,0],np.zeros(len(pts)),pts[:,1]];faces=faces[:,::-1]
    maxedge=.075 if cz<22 else .14 if cz<58 else .30
    pv,faces=trimesh.remesh.subdivide_to_size(pv,faces,max_edge=maxedge,max_iter=7)
    u,z=warp(pv[:,0],pv[:,2]);u=np.clip(u,-width(z)+.015,width(z)-.015)
    phase=rng.uniform(0,6.3);pitch=rng.uniform(.12,.26);amp=rng.uniform(.035,.072)
    tilt=rng.normal(0,.028,2)
    h=raft_height(u,z,cu,cz,phase,pitch,amp,tilt)
    # Remaining pressure waves are localized on each body, not on the whole river.
    vv=base_world(u,z);vv[:,1]+=h
    add('Detached_folded_crust_%04d'%i,vv,faces,int(rng.choice(raftm)),group='separate_folded_rafts')
    # Free-edge side walls give thickness and permit inter-raft shadows.
    # Resample every edge before warping, so the wall follows the same curvature.
    ring=[]
    for j in range(n):
        a,b=xy[j],xy[(j+1)%n];steps=max(2,int(np.linalg.norm(a-b)/maxedge)+1)
        ring.extend(a[None]+np.linspace(0,1,steps,endpoint=False)[:,None]*(b-a))
    ring=np.array(ring);ru,rz=warp(ring[:,0],ring[:,1]);ru=np.clip(ru,-width(rz)+.015,width(rz)-.015)
    upper=base_world(ru,rz);upper[:,1]+=raft_height(ru,rz,cu,cz,phase,pitch,amp,tilt)
    lower=upper.copy();lower[:,1]=level(rz)+sample_h(ru,rz)-.025
    vv=np.stack([upper,lower],1).reshape(-1,3);ids=np.arange(len(ring))*2;nxt=np.roll(ids,-1)
    ff=np.r_[np.c_[ids,nxt,ids+1],np.c_[nxt,nxt+1,ids+1]]
    add('Free_crust_edges_%04d'%i,vv,ff,edgeheat[int(rng.choice([0,0,1,1,2,3]))],group='separate_folded_rafts',smooth=False)
    raftcount+=1
    if raftcount%200==0:print('Crust bodies',raftcount,round(time.monotonic()-t0,1),flush=True)

# Broken clinker caught on top of colder margins connects skin to the rough bank.
N=1250;zz=rng.uniform(-26,135,N);side=rng.choice([-1,1],N);uu=side*(width(zz)-rng.uniform(.05,.5,N))
base=base_world(uu,zz)
for j in range(N):
    rr=rng.uniform(.06,.26);v,f=rocklib[j%len(rocklib)];v=v.copy()*rr
    R=trimesh.transformations.euler_matrix(rng.uniform(-1,1),rng.uniform(0,6.3),rng.uniform(-.6,.6))[:3,:3];v=v@R.T
    v+=base[j]+np.array([0,.06,0]);add('Entrained_clinker_%04d'%j,v,f,rockm[j%4],group='entrained_clinker',smooth=False)

assembly=Assembly('OBSIDIAN_REACH_IV',parts,palette,metadata={
    'source':'CYBR GEO named parts, CYBR ELEMENTS thermal optics, CYBR LIGHT native CPU core',
    'lava':'authored detached folded crust rafts above continuous hot interior',
    'fluid_simulation':False,'image_generation':False,'metres':True,
    'separate_crust_bodies':raftcount})
report=assembly.validate();(A/'geometry_validation.json').write_text(json.dumps(report,indent=2))
manifest={'name':assembly.name,'parts':[{'name':p.name,'group':p.group,'triangles':len(p.faces),'material':p.material} for p in parts],
          'materials':[{'name':m.name,'color':m.color,'kind':int(mats[i][-1])} for i,m in enumerate(palette)],'metadata':assembly.metadata}
(A/'scene_manifest.json').write_text(json.dumps(manifest,indent=2))
count=sum(len(p.faces) for p in parts)
with (A/'scene.bin').open('wb') as out:
    out.write(struct.pack('<4sIII',b'OBS2',len(mats),count,104))
    for m in mats:out.write(struct.pack('<8fi',*m))
    dtype=np.dtype([('v','<f4',(6,3)),('uv','<f4',(3,2)),('mat','<i4'),('obj','<i4')])
    for obj,(p,uv) in enumerate(zip(parts,uvs)):
        v=p.vertices[:,[0,2,1]]*np.array([.001,.001,-.001]);n=p.normals[:,[0,2,1]]*np.array([1,1,-1]);fc=p.faces
        packet=np.empty(len(fc),dtype=dtype);packet['v'][:,:3]=v[fc];packet['v'][:,3:]=n[fc]
        packet['uv']=uv[fc] if uv is not None else 0;packet['mat']=p.material;packet['obj']=obj;out.write(packet.tobytes())
record={'seconds':time.monotonic()-t0,'triangles':count,'parts':len(parts),'separate_folded_crust_bodies':raftcount,
        'lava_texture_dimensions':[LW,LH],'image_generation':False,'fluid_simulation':False}
(A/'build_record.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record),flush=True)
