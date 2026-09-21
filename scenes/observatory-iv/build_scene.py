"""Rebuild the observatory's transport mesh and physically scaled material maps.

Input: the delivered CYBR observatory GLB, whose mesh coordinates remain Z-up
(the GLB's scene graph applies the presentation rotation to Y-up).
No generated imagery, photo backplates, pretrained assets, or font binaries.
"""
from __future__ import annotations
import argparse, hashlib, json, math, struct, os
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter, zoom

ROOT=Path(__file__).resolve().parent
SCENE=ROOT/'scene'; ASSETS=ROOT/'assets'
RNG=np.random.default_rng(449173)
PARTS=[]

def srgb_to_linear(a):
    a=np.asarray(a,np.float32)
    return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)

def linear_to_srgb(a):
    a=np.maximum(a,0)
    return np.where(a<=.0031308,a*12.92,1.055*a**(1/2.4)-.055)

def field(n, size, seed):
    r=np.random.default_rng(seed).normal(size=(size,size)).astype(np.float32)
    a=zoom(r,(n/size,n/size),order=3,mode='wrap')[:n,:n]
    return (a-a.mean())/(a.std()+1e-8)

def save_texture(index, name, color, height, rough, metres, strength=1.):
    n=len(height); color=np.broadcast_to(color,(n,n,3)).copy().astype(np.float32)
    rough=np.broadcast_to(rough,(n,n)).copy().astype(np.float32)
    dy,dx=np.gradient(height.astype(np.float32))
    normal=np.dstack((-dx*n/metres[0]*strength,-dy*n/metres[1]*strength,np.ones((n,n),np.float32)))
    normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    out=np.concatenate([np.clip(color,0,.94),normal,np.clip(rough[:,:,None],.035,.95)],axis=-1).astype('<f4')
    p=SCENE/'textures'/f'{index}.cvtex'
    with p.open('wb') as f:
        f.write(struct.pack('<III',n,n,7));f.write(out.tobytes())
    Image.fromarray(np.uint8(np.clip(linear_to_srgb(color),0,1)*255+.5)).save(ASSETS/f'{name}_albedo.png')
    return {'index':index,'name':name,'resolution':n,'physical_size_m':metres,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def fonts(size):
    candidates=['/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf','/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf']
    for p in candidates:
        if Path(p).exists():return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def chart(n=2048,book=False):
    a=np.zeros((n,n,3),np.float32)
    base=np.array([.78,.714,.566],np.float32)
    f=field(n,12,411)*.010+field(n,72,913)*.006
    for k in range(3):a[:,:,k]=base[k]+f
    # Uneven edge oxidation, not a full-frame dirt overlay.
    yy,xx=np.mgrid[:n,:n]/n
    edge=np.exp(-np.minimum.reduce([xx,yy,1-xx,1-yy])*36)
    a-=edge[:,:,None]*np.array([.08,.11,.14])
    im=Image.fromarray(np.uint8(np.clip(a,0,1)*255));d=ImageDraw.Draw(im)
    ink=(58,48,32);faint=(120,99,64)
    margin=int(n*.055)
    d.rectangle((margin,margin,n-margin,n-margin),outline=faint,width=3)
    d.rectangle((margin+13,margin+13,n-margin-13,n-margin-13),outline=faint,width=1)
    title='TABULAE  MOTUUM  COELESTIUM' if book else 'HARMONIA  COELESTIS'
    d.text((n*.5,n*.089),title,fill=ink,font=fonts(int(n*.030)),anchor='mt')
    d.text((n*.5,n*.133),'OBSERVATIONES  ·  LONGITUDO  ·  DECLINATIO',fill=faint,font=fonts(int(n*.012)),anchor='mt')
    cx,cy=n*.51,n*.47
    radii=[.087,.135,.185,.228,.277]
    for ri,rad in enumerate(radii):
        r=n*rad;d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=faint,width=2)
        for deg in range(0,360,5):
            t=math.radians(deg);l=n*(.006 if deg%30==0 else .003)
            d.line((cx+math.cos(t)*(r-l),cy+math.sin(t)*(r-l),cx+math.cos(t)*(r+l),cy+math.sin(t)*(r+l)),fill=faint,width=1)
        if ri in (2,4):
            for deg in range(0,360,30):
                t=math.radians(deg);d.text((cx+math.cos(t)*(r+n*.015),cy+math.sin(t)*(r+n*.015)),str(deg),font=fonts(int(n*.010)),fill=ink,anchor='mm')
    for j in range(12):
        t=j*math.pi/6;d.line((cx,cy,cx+math.cos(t)*n*.28,cy+math.sin(t)*n*.28),fill=(145,126,91),width=1)
    d.ellipse((cx-n*.028,cy-n*.028,cx+n*.028,cy+n*.028),outline=ink,width=4)
    r=np.random.default_rng(371)
    for j in range(82):
        x,y=r.uniform(-.26,.26,2);rr=math.hypot(x,y)
        if rr>.27:continue
        x=cx+x*n;y=cy+y*n;k=2+(j%3)
        d.line((x-k,y,x+k,y),fill=ink,width=1);d.line((x,y-k,x,y+k),fill=ink,width=1)
    labels=['I.  DE SITU ET DISTANTIA STELLARUM','II.  MOTUS APPARENS PLANETARUM','III.  CORRECTIO REFRACTIONIS']
    for j,text in enumerate(labels):d.text((n*.12,n*(.789+j*.035)),text,font=fonts(int(n*.012)),fill=ink)
    if book:
        d.text((n*.5,n*.926),'VENETIIS  ·  MDCCLXVII',font=fonts(int(n*.012)),fill=ink,anchor='mm')
    return srgb_to_linear(np.asarray(im,np.float32)/255)

def make_textures():
    SCENE.joinpath('textures').mkdir(parents=True,exist_ok=True);ASSETS.mkdir(exist_ok=True)
    records=[];n=1024;y,x=np.mgrid[:n,:n].astype(np.float32)/n
    # Walnut: varying longitudinal fibres, growth-ring drift, knots, open pores,
    # rubbing and fine scratches. Relief is in metres; no arbitrary normal noise.
    broad=field(n,9,103);fine=field(n,80,205)
    warp=.020*field(n,7,44)+.014*np.sin(9*x+field(n,5,23)*.4)
    phase=(y+warp)*118
    for cx,cy,amp in [(.27,.31,.54),(.78,.73,.37)]:
        dx=(x-cx)/.23;dy=(y-cy)/.075
        influence=np.exp(-(dx*dx+dy*dy)*1.7)
        phase+=amp*influence*np.arctan2(dy,dx)*5
    ring=np.sin(phase*2*np.pi);hair=np.sin(phase*2*np.pi*3.03+x*70)
    rng=np.random.default_rng(772)
    line=gaussian_filter(rng.normal(size=(n,n)).astype(np.float32),(1.0,24))
    line/=line.std()+1e-8
    fibers=.10*np.tanh(line)+.055*ring+.027*hair+.05*broad
    color=np.array([.17,.081,.031])*(1+fibers[:,:,None])
    # Fine lengthwise pores and restrained scratches, never giant zebra bands.
    scratch=Image.new('F',(n,n));d=ImageDraw.Draw(scratch)
    for j in range(360):
        u,v=rng.uniform(0,n,2);ll=rng.uniform(2,31)
        d.line((u,v,u+ll,v+rng.normal(0,.5)),fill=float(rng.uniform(.12,.65)),width=1)
    marks=np.asarray(scratch);color*=1-.12*marks[:,:,None]
    h=(ring*.000020+hair*.000005+line*.000018-marks*.000024)
    rough=.28+.033*broad+.055*marks+.018*fine
    records.append(save_texture(0,'oiled_walnut',color,h,rough,(3.6,1.25)))
    # Hand-trowelled lime plaster, sub-millimetre surface with broad cured variation.
    low=field(n,6,62);medium=field(n,45,63);micro=field(n,220,64)
    color=np.array([.56,.512,.422])*(1+(.025*low+.016*medium+.005*micro)[:,:,None])
    h=low*.00043+medium*.00013+micro*.000018
    records.append(save_texture(1,'lime_plaster',color,h,.76+.04*medium,(2.8,2.8)))
    # Worn limestone: distinct sediment, pits and soft worn roughness.
    a=field(n,7,401);b=field(n,38,403);c=field(n,160,404)
    stratum=np.sin((y+.04*field(n,5,91))*71+.35*b)
    pore=np.maximum(c-1.45,0)
    col=np.array([.415,.353,.264])*(1+(.052*a+.029*b+.012*stratum-.075*pore)[:,:,None])
    records.append(save_texture(2,'cut_limestone',col,a*.0009+b*.00019-pore*.00018,.60+.035*b+.06*pore,(1.6,1.6)))
    # Very low-contrast hand-rubbed brass; changing roughness, not black blotches.
    a=field(n,13,882);b=field(n,120,883)
    grime=np.clip((a-.6)*.27,0,.32)
    col=np.array([.79,.61,.29])*(1-.23*grime[:,:,None])
    records.append(save_texture(3,'rubbed_brass',col,np.zeros_like(x),.205+.027*a+.007*b,(.6,.6)))
    # Woven flax cloth. Filterable weave, not a checkerboard painted on the cloth.
    warp=np.sin(x*2*np.pi*222);weft=np.sin(y*2*np.pi*228)
    weave=.5*(warp+weft)+.25*warp*weft
    col=np.array([.048,.082,.074])*(1+.12*weave[:,:,None]+.03*field(n,12,98)[:,:,None])
    records.append(save_texture(4,'woven_teal_linen',col,weave*.000033,.78,(.85,.85)))
    # Paper fibre for page edges and plain leaves.
    a=field(n,20,823);b=field(n,200,834)
    col=np.array([.73,.645,.484])*(1+(.010*a+.005*b)[:,:,None])
    records.append(save_texture(5,'laid_vellum',col,a*.000008+b*.000002,.84,(.55,.55)))
    # Maps are authored diagram textures attached to real paper surfaces.
    for idx,nm,book in [(6,'celestial_chart',False),(7,'folio_chart',True)]:
        col=chart(2048,book);z=np.zeros((2048,2048),np.float32)
        records.append(save_texture(idx,nm,col,z,.83,(.62,.80)))
    # Supple leather grain with small pores, used with per-book color multipliers.
    a=field(n,80,288);b=field(n,240,911)
    col=np.ones((n,n,3),np.float32)*(.82+.06*a+.018*b)[:,:,None]
    records.append(save_texture(8,'leather_grain',col,a*.000036+b*.000009,.47+.028*a,(.38,.38)))
    # A quiet warm-gray floor, contrasting smooth wear with rough joints.
    a=field(n,7,367);b=field(n,41,368);c=field(n,170,369)
    col=np.array([.275,.255,.216])*(1+(.10*a+.033*b+.010*c)[:,:,None])
    records.append(save_texture(9,'flagstone',col,a*.0008+b*.00012+c*.000012,.52+.08*np.clip(b,-1,1),(1.1,1.1)))
    # Unbleached curtain. Transmittance is handled in the transport kernel.
    col=np.array([.62,.56,.448])*(1+.027*weave[:,:,None])
    records.append(save_texture(10,'window_linen',col,weave*.000018,.89,(.85,.85)))
    (SCENE/'texture_manifest.json').write_text(json.dumps(records,indent=2))


def add(name,mesh,mat,tex=-1,tint=(1,1,1),uv=None):
    if not len(mesh.faces):return
    PARTS.append((name,mesh,int(mat),int(tex),np.asarray(tint,np.float32),uv))

def cube(name,center,extent,mat,tex=-1,tint=(1,1,1)):
    m=trimesh.creation.box(extents=extent);m.apply_translation(center);add(name,m,mat,tex,tint);return m

def rod(name,a,b,r,mat=3,tex=3,sections=20):
    a=np.array(a);b=np.array(b);d=b-a;m=trimesh.creation.cylinder(radius=r,height=np.linalg.norm(d),sections=sections)
    t=trimesh.geometry.align_vectors([0,0,1],d);t[:3,3]=(a+b)/2;m.apply_transform(t);add(name,m,mat,tex)

def lathe(name,profile,center,mat=3,tex=3,segments=80):
    p=np.asarray(profile,float);th=np.linspace(0,2*np.pi,segments,endpoint=False)
    v=np.stack([p[:,0,None]*np.cos(th),p[:,0,None]*np.sin(th),np.broadcast_to(p[:,1,None],(len(p),segments))],-1).reshape(-1,3)
    f=[]
    for j in range(len(p)-1):
        for k in range(segments):
            a=j*segments+k;b=j*segments+(k+1)%segments;c=(j+1)*segments+k;d=(j+1)*segments+(k+1)%segments
            f.extend([(a,b,d),(a,d,c)])
    m=trimesh.Trimesh(v+np.asarray(center),f,process=False);add(name,m,mat,tex)

def panel_grid(name,x,y,zfunc,mat,tex,tint=(1,1,1),uvrange=None):
    yy,xx=np.meshgrid(y,x,indexing='ij');zz=zfunc(xx,yy);v=np.stack((xx,yy,zz),-1).reshape(-1,3)
    ny,nx=xx.shape;i=np.arange((ny-1)*nx).reshape(ny-1,nx)[:,:-1].ravel()
    f=np.vstack([np.stack([i,i+1,i+nx+1],-1),np.stack([i,i+nx+1,i+nx],-1)])
    m=trimesh.Trimesh(v,f,process=False)
    uv=np.stack(((xx-x.min())/(x.max()-x.min()),(yy-y.min())/(y.max()-y.min())),-1).reshape(-1,2) if uvrange else None
    add(name,m,mat,tex,tint,uv);return m


def import_room():
    s=trimesh.load(ASSETS/'observatory_interior_source.glb',force='scene',process=False)
    # Per-mesh GLB vertices are in the original native Z-up world.
    omit=('Draped_woven','Bronze_window','Wall_celestial','Retained_Curled','Desk_folio')
    for name,m0 in s.geometry.items():
        if name.startswith(omit):continue
        m=m0.copy();col=np.asarray(m.visual.vertex_colors[0,:3],np.float32)/255
        mat,tex,tint=1,2,np.ones(3)
        low=name.lower()
        if 'quartz' in low:mat,tex=8,-1
        elif name.startswith(('Retained','Pivot','Adjustment','Tangent','Telescope','Drawer_pull','Drawer_bail','Book_spine','Astrolabe','Wall_astrolabe')):
            mat,tex=3,3
            if any(w in low for w in ['recess','inner_black','eyepiece','bearing','tripod_foot']):mat,tex,tint=4,3,np.array([.42,.46,.43])
            if 'tripod_leg' in low:mat,tex=2,0
            if 'marker' in low:mat,tex,tint=9,8,np.array([.02,.12,.095])
            if 'slot' in low:mat,tex,tint=5,-1,np.array([.04,.045,.045])
            if 'maker_name' in low:mat,tex,tint=10,-1,np.array([.06,.045,.025])
            if 'encapsulated' in low:mat,tex=3,3
        elif any(w in low for w in ['walnut','breadboard','table_','stretcher','drawer_face','shutter_louver','opened_shutter','library_upright','library_cornice','library_back','library_shelf','framed_chart']):
            mat,tex=2,0
            if 'shutter' in low:tint=np.array([.67,.68,.68])
        elif name.startswith('Library_book'):
            mat,tex=9,8;tint=np.maximum(srgb_to_linear(col),.012)*1.55
            # Break the grid: small book-specific rotations about the shelf base.
            i=int(name.rsplit('_',1)[-1]);bound=m.bounds;bottom=(bound[0]+bound[1])/2;bottom[2]=bound[0,2]
            angle=([0,.012,-.024,0,.035,-.011,0,.014,-.02,.015][i%10])
            m.apply_transform(trimesh.transformations.rotation_matrix(angle,[0,1,0],bottom))
        elif 'shutter_strap' in low:mat,tex,tint=5,-1,np.array([.09,.10,.105])
        elif any(w in low for w in ['wall','arch_spandrel','lime_plaster','continuous_arch','outer_arch']):mat,tex=0,1
        elif name.startswith('Floor_flagstone'):mat,tex=1,9;tint=np.ones(3)*(.91+.15*RNG.random())
        elif 'mortar' in low:mat,tex=0,1;tint=np.array([.43,.44,.45])
        # Small, spatially smooth geometric weathering, not independent vertex jitter.
        if mat in (0,1):
            p=m.vertices
            scalar=(np.sin(p[:,0]*2.7+p[:,1]*1.2)*np.sin(p[:,2]*3.1+.6)+.4*np.sin(p[:,0]*11.3+p[:,1]*9.1+p[:,2]*7.3))
            amount=.0014 if mat==0 else .00065
            m.vertices=p+np.asarray(m.vertex_normals)*scalar[:,None]*amount
        add(name,m,mat,tex,tint)
    # Close the formerly open front of the room around a real off-camera window.
    # This removes the global, flat fill; both apertures are visibility-tested.
    cube('Front_wall_left',(-3.08,-3.78,2.85),(1.05,.34,5.9),0,1)
    cube('Front_wall_right',(1.25,-3.78,2.85),(4.72,.34,5.9),0,1)
    cube('Front_window_under',(-1.78,-3.78,.52),(1.58,.34,1.15),0,1)
    cube('Front_window_above',(-1.78,-3.78,4.75),(1.58,.34,2.20),0,1)
    # New hardwood glazing bars: recognizable joinery rather than prison bars.
    for x in [1.065,1.635]:
        cube(f'Glazing_vertical_{x}',(x,3.10,2.15),(.037,.046,2.55),2,0,(.40,.40,.40))
    for z in [1.68,2.47]:
        cube(f'Glazing_cross_{z}',(1.35,3.10,z),(1.63,.046,.038),2,0,(.40,.40,.40))
    # Modelled shallow irregular glass sheets, ordinary achromatic glass is not used
    # here: leave aperture unobstructed to retain the original open-window premise.


def paper_and_cloth():
    # Recreate the diagram on the physically framed wall surface.
    v=np.array([[-.987,2.593,2.346],[-.353,2.593,2.346],[-.353,2.593,3.174],[-.987,2.593,3.174]])
    uv=np.array([[0,1],[1,1],[1,0],[0,0]])
    add('Wall_celestial_engraving',trimesh.Trimesh(v,[[0,1,2],[0,2,3]],process=False),6,6,uv=uv)
    # Main folio spread: independently curved leaves, textured with real diagrams.
    # Two covers and several separating leaf edges make the thickness legible.
    center=np.array([.62,-.28, .928]);theta=-.19
    def rotate(m):
        t=trimesh.transformations.rotation_matrix(theta,[0,0,1]);t[:3,3]=center;m.apply_transform(t)
    for side in [-1,1]:
        cover=trimesh.creation.box(extents=(.33,.45,.012));cover.apply_translation((side*.165,0,-.008));rotate(cover);add('Open_folio_cover_'+str(side),cover,9,8,(.085,.032,.016))
        for leaf in range(6):
            x=np.linspace(.009*side,.321*side,65);y=np.linspace(-.219,.219,81)
            yy,xx=np.meshgrid(y,x,indexing='ij');s=np.abs(xx)/.321
            zz=.015+.027*np.sin(np.pi*s)*np.exp(-s*.4)+.007*s+.0018*leaf+.002*np.sin(yy*19+s*5)*s
            verts=np.stack((xx,yy,zz),-1).reshape(-1,3);ii=np.arange((len(y)-1)*len(x)).reshape(-1,len(x))[:,:-1].ravel()
            faces=np.vstack([np.stack((ii,ii+1,ii+len(x)+1),-1),np.stack((ii,ii+len(x)+1,ii+len(x)),-1)])
            if side<0:faces=faces[:,::-1]
            m=trimesh.Trimesh(verts,faces,process=False);uv=np.stack((s,1-(yy+.219)/.438),-1).reshape(-1,2)
            rotate(m);add(f'Curved_folio_leaf_{side}_{leaf}',m,6,7 if leaf==5 else 5,uv=uv if leaf==5 else None)
    # Loose survey chart at the left of the armillary.
    x=np.linspace(-1.40,-.79,91);y=np.linspace(-.33,.23,81)
    def zz(x,y):return .921+.008*(x+1.1)**2+.026*np.exp(-((x+1.4)/.057)**2)+.002*np.sin(y*16+x*5)
    panel_grid('Survey_chart_on_worktop',x,y,zz,6,6,uvrange=True)
    # Rebuild the drape with slack across the table and folds extending over the edge.
    u=np.linspace(0,1,105);v=np.linspace(0,1,151);vv,uu=np.meshgrid(v,u,indexing='ij')
    x=.91+uu*.48+.018*np.sin(vv*4+uu*9)
    y=.60-vv*1.58
    over=np.maximum(-y-.60,0)
    y=np.where(y<-.60,-.60-.022*np.sin(over*4),y)
    z=.914+(.006+.012*vv)*(1+np.sin(uu*7*np.pi+vv*.8))-over*1.35+.001*np.sin(uu*24*np.pi+vv*5)
    verts=np.stack((x,y,z),-1).reshape(-1,3);i=np.arange((len(v)-1)*len(u)).reshape(-1,len(u))[:,:-1].ravel()
    f=np.vstack([np.stack((i,i+1,i+len(u)+1),-1),np.stack((i,i+len(u)+1,i+len(u)),-1)])
    add('Slack_linen_runner',trimesh.Trimesh(verts,f,process=False),7,4,uv=np.stack((uu*.7,vv*1.7),-1).reshape(-1,2))
    # Restrained tied-back curtain on the right: actual three-dimensional folds.
    u=np.linspace(0,1,97);v=np.linspace(0,1,151);vv,uu=np.meshgrid(v,u,indexing='ij')
    width=.49-.27*np.exp(-((vv-.64)/.15)**2)
    x=2.05+uu*width+.035*np.sin(vv*6)
    y=2.39+.055*np.cos(uu*10*np.pi+vv*.3)*(1-.6*np.exp(-((vv-.64)/.15)**2))
    z=3.55-vv*2.59+.018*np.sin(uu*9)
    verts=np.stack((x,y,z),-1).reshape(-1,3);i=np.arange((len(v)-1)*len(u)).reshape(-1,len(u))[:,:-1].ravel();f=np.vstack([np.stack((i,i+1,i+len(u)+1),-1),np.stack((i,i+len(u)+1,i+len(u)),-1)])
    add('Gathered_window_curtain',trimesh.Trimesh(verts,f,process=False),12,10,uv=np.stack((uu*.6,vv*3),-1).reshape(-1,2))
    rod('Curtain_rail',(1.97,2.40,3.57),(2.65,2.40,3.57),.009,4,3)
    for xx in np.linspace(2.07,2.54,8):
        m=trimesh.creation.torus(major_radius=.015,minor_radius=.003,major_sections=24,minor_sections=8)
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1,0,0]));m.apply_translation((xx,2.4,3.555));add('Curtain_ring',m,3,3)


def instruments():
    # An optical bench at true desk scale, with rails, screw stage and lens mount.
    # It is a new assembly, not a flat decoration.
    for y in [.41,.54]:rod('Optical_bench_rail',(-1.36,y,.951),(-.82,y,.951),.006,5,-1)
    for x in [-1.31,-.89]:
        cube('Optical_bench_foot',(x,.475,.932),(.07,.21,.023),4,3)
    for x in [-1.22,-.99]:
        cube('Sliding_lens_carriage',(x,.475,.973),(.055,.16,.022),4,3)
        rod('Lens_vertical_post',(x,.475,.98),(x,.475,1.13),.006,3,3)
        m=trimesh.creation.torus(major_radius=.064,minor_radius=.005,major_sections=100,minor_sections=12)
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0,1,0]));m.apply_translation((x,.475,1.17));add('Optical_lens_mount',m,3,3)
        # Closed biconvex lens as a flattened smooth ellipsoid.
        m=trimesh.creation.uv_sphere(radius=1,count=[48,64]);m.apply_scale((.014,.060,.060));m.apply_translation((x,.475,1.17));add('Bench_quartz_lens',m,8,-1)
    rod('Micrometer_feed_screw',(-1.4,.475,.985),(-.80,.475,.985),.0025,5,-1)
    lathe('Micrometer_dial',[(0,0),(.017,0),(.018,.003),(.018,.019),(.016,.021),(0,.021)],(-1.42,.475,.971),3,3)
    # Ink well with a stopper; turning contours create real highlight bands.
    lathe('Bronze_inkwell',[(0,0),(.055,0),(.06,.008),(.055,.015),(.043,.026),(.044,.071),(.036,.082),(.032,.084),(0,.084)],(-1.42,.49,.921),4,3)
    lathe('Ink_well_stopper',[(0,0),(.039,0),(.039,.009),(.019,.015),(.009,.034),(0,.038)],(-1.42,.49,1.007),3,3)
    # Original horizon has no engraving in the inspectable GLB: build actual
    # shallow blackened strokes on the broad ring, not post-render marks.
    # Infer plane from the retained horizon band's principal axes.
    candidates=[p for p in PARTS if p[0]=='Retained_Horizon_band']
    if candidates:
        m=candidates[0][1];pts=m.vertices;center=pts.mean(0);_,_,vh=np.linalg.svd(pts-center,full_matrices=False);normal=vh[-1]
        if normal[2]<0:normal=-normal
        e1=vh[0];e2=np.cross(normal,e1);rad=np.median(np.linalg.norm((pts-center)-np.outer((pts-center)@normal,normal),axis=1))
        top=np.max((pts-center)@normal)+.00016
        for j in range(180):
            a=j*2*np.pi/180;d=e1*np.cos(a)+e2*np.sin(a);l=.009 if j%5 else .017
            start=center+normal*top+d*(rad-l*.5);end=center+normal*top+d*(rad+l*.5)
            rod('Blackened_horizon_division_'+str(j),start,end,.00040 if j%5 else .0006,10,-1,6)
    # Fine individual fastener slots are dark actual geometry, not noise.
    for name,m,mat,tex,tint,uv in list(PARTS):
        if name.startswith('Retained_Pedestal_bolt'):
            b=m.bounds;c=(b[0]+b[1])/2;c[2]=b[1,2]+.00008
            cube('Pedestal_screw_slot',c,(.009,.0018,.00032),10,-1,(.03,.024,.015))


def landscape():
    # Continuous ground replaces the open gaps between the old terrain patches.
    # All visible land is geometry; no photo backplate or infinite sky below it.
    x=np.linspace(-180,180,321);y=np.linspace(3.35,420,361)
    def height(x,y):
        ramp=1-np.exp(-np.maximum(y-5,0)/70)
        hills=(4.5+3.3*np.sin(x*.033+y*.017)+2.4*np.sin(x*.069-y*.022)+.9*np.cos(x*.131+y*.041))
        return -.28+ramp*hills+.085*np.sin(x*.55+y*.45)*ramp
    panel_grid('Continuous_valley_floor',x,y,height,11,-1,(.145,.160,.105))
    # A far, finely tessellated limestone escarpment with unequal ridgelines.
    x=np.linspace(-1000,1000,501);y=np.linspace(400,2100,241)
    def mountains(x,y):
        envelope=np.exp(-((y-1030)/340)**2)
        ridge=(62+42*np.sin(x*.0041+.7)+28*np.sin(x*.0097-1.1)+19*np.sin(x*.0197))
        erosion=7*np.sin(x*.051+y*.028)+3.0*np.sin(x*.121-y*.083)
        return -4+envelope*(ridge+erosion)
    panel_grid('Distant_eroded_escarpment',x,y,mountains,11,-1,(.24,.225,.187))


def uv_coordinates(name,m,faces,mat,tex,explicit):
    if explicit is not None:return explicit[faces]
    p=m.vertices[faces];center=p.mean(axis=1);gn=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);axis=np.argmax(np.abs(gn),axis=1)
    uv=np.empty((len(faces),3,2),np.float32)
    # Consistent planar mapping. Orthogonal faces may have independent UVs.
    for a,pair in [(0,(1,2)),(1,(0,2)),(2,(0,1))]:
        idx=axis==a;uv[idx]=p[idx][:,:,pair]
    if tex==0:
        # Wood follows the actual length direction of each construction member.
        ext=m.bounds[1]-m.bounds[0];longaxis=int(np.argmax(ext))
        uv[:,:,0]=p[:,:,longaxis]/3.6
        transverse=1 if longaxis==0 else (0 if longaxis==1 else 0)
        if longaxis==0:
            trans=np.where(axis[:,None]==2,p[:,:,1],p[:,:,2])
        else:trans=p[:,:,transverse]
        uv[:,:,1]=trans/1.25
        off=(int(hashlib.sha1(name.encode()).hexdigest()[:6],16)%971)/971
        uv[:,:,1]+=off;uv[:,:,0]+=off*.29
    elif tex>=0:
        scale={1:2.8,2:1.6,3:.6,4:.85,5:.55,8:.38,9:1.1,10:.85}.get(tex,1)
        uv/=scale
        if tex not in (6,7):
            off=(int(hashlib.sha1(name.encode()).hexdigest()[:6],16)%971)/971
            uv+=off
    return uv


def export_scene():
    total=sum(len(p[1].faces) for p in PARTS);out=SCENE/'observatory.cvr2'
    stats=[];unique={};inspection=trimesh.Scene();machining=[]
    with out.open('wb') as f:
        f.write(b'CVR2'+struct.pack('<I',total))
        for group,(name,m,mat,tex,tint,explicit) in enumerate(PARTS):
            faces=m.faces;v=m.vertices[faces].astype(np.float32);norm=np.asarray(m.vertex_normals)[faces].astype(np.float32)
            # Flat paper remains physically thin; original smooth normals are kept.
            a=np.zeros((len(faces),36),'<f4');a[:,:9]=v.reshape(-1,9);a[:,9:18]=norm.reshape(-1,9);a[:,18]=mat;a[:,19]=group
            uv=uv_coordinates(name,m,faces,mat,tex,explicit);a[:,20:26]=uv.reshape(-1,6);a[:,26:35]=np.tile(tint,3);a[:,35]=tex
            if not np.isfinite(a).all():raise ValueError('Nonfinite geometry '+name)
            f.write(a.tobytes())
            stats.append({'name':name,'triangles':len(faces),'material':mat,'texture':tex,'bounds_m':np.asarray(m.bounds).tolist()})
            center=m.vertices.mean(axis=0);q=m.vertices-center
            values,vectors=np.linalg.eigh(q.T@q/max(1,len(q)));axis=np.array([0.,0.,1.]);aniso=0.
            if mat in (3,4,5):
                if values[-1]>values[-2]*2.7:axis=vectors[:,-1];aniso=.40
                elif values[0]<values[1]*.22:axis=vectors[:,0];aniso=.40
            machining.append(np.r_[center,axis,aniso])
            key=name;unique[key]=unique.get(key,0)+1
            if unique[key]>1:key+=f'_{unique[key]}'
            # GLB inspection uses simplified vertex colors, clearly separate from
            # the spectral renderer's physical texture/BRDF definitions.
            mesh=m.copy();rgb={0:[.65,.6,.51],1:[.52,.47,.39],2:[.33,.2,.1],3:[.77,.60,.30],4:[.32,.24,.12],5:[.13,.14,.15],6:[.80,.73,.58],7:[.12,.24,.23],8:[.78,.86,.89],9:[.15,.08,.04],10:[.05,.04,.03],11:[.19,.29,.16],12:[.76,.71,.60]}.get(mat,[.5]*3)
            mesh.visual=trimesh.visual.ColorVisuals(mesh,vertex_colors=np.tile(np.array(rgb+[1.])*255,(len(mesh.vertices),1)).astype(np.uint8));inspection.add_geometry(mesh,node_name=key,geom_name=key)
    # Z-up -> Y-up only at the exported scene's root.
    inspection.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]));inspection.export(SCENE/'observatory_v4_inspection.glb')
    manifest={'scene':'Quiet Observatory IV','parts':len(PARTS),'triangles':total,'mesh_bytes':out.stat().st_size,'mesh_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'source_glb_sha256':hashlib.sha256((ASSETS/'observatory_interior_source.glb').read_bytes()).hexdigest(),'image_generation':False,'mesh_coordinate_system':'metres, Z up','geometry_changes':['Off-camera wall and window, replacing open-front fill','New curved folio leaves and visible covers','New authored linen drape and gathered curtain','Optical rail and focusing stages with two closed quartz lenses','Real horizon division strokes','Geometric surface weathering','Continuous valley floor and distant eroded escarpment'],'objects':stats}
    with (SCENE/'observatory.groups').open('wb') as gf:
        gf.write(struct.pack('<I',len(machining)));gf.write(np.asarray(machining,'<f4').tobytes())
    (SCENE/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({k:v for k,v in manifest.items() if k!='objects'},indent=2),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--textures-only',action='store_true');ap.add_argument('--geometry-only',action='store_true');args=ap.parse_args()
    if not args.geometry_only:make_textures()
    if args.textures_only:return
    import_room();paper_and_cloth();instruments();landscape();export_scene()

if __name__=='__main__':main()
