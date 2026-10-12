"""Connected, shallow dry erosion replaces the wavy visible shoulder height field.
USGS Mojave lower-fan description and Lake Mead incision photo are shape analogues,
not measured site dimensions. Depths and extents below are explicit scene parameters.
"""
import bpy,numpy as np,math,json,hashlib,ast
from pathlib import Path
R=Path(__file__).resolve().parents[1];source=R/'preview/road_r6_k.blend';bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene
ns={'np':np};tree=ast.parse((R/'src/build_scene.py').read_text());names={'field','grade','edge_y','road_z','wash','terrain','tint_ground'};exec(compile(ast.Module(body=[q for q in tree.body if isinstance(q,ast.FunctionDef) and q.name in names],type_ignores=[]),'<terrain>', 'exec'),ns)
kt=ast.parse((R/'src/prepare_sediment_patches.py').read_text());exec(compile(ast.Module(body=[q for q in kt.body if isinstance(q,ast.FunctionDef) and q.name in {'smooth','sorting'}],type_ignores=[]),'<sorting>', 'exec'),ns)
field=ns['field'];smooth=ns['smooth'];grade=ns['grade'];old_terrain=ns['terrain'];old_sort=ns['sorting'];tint_ground=ns['tint_ground']
# Shared endpoints make a connected trunk, split/rejoin island, and tributaries.
paths=[([(-5.3,24),(-5.8,18),(-6.3,13),(-6.65,9.4)],.24,.043),([(-6.65,9.4),(-7.10,7.6),(-7.2,5.6)],.25,.055),([(-6.65,9.4),(-6.50,7.8),(-6.85,6.5),(-7.2,5.6)],.20,.051),([(-7.2,5.6),(-8.15,1),(-9.7,-2)],.48,.074),([(-4.05,7.8),(-4.50,7.2),(-5.3,6.8),(-6.2,6.2),(-7.2,5.6)],.17,.030),([(-4.3,15.6),(-4.9,14.7),(-5.5,13.8),(-6.3,13)],.18,.032),([(-4.15,26),(-4.65,25.1),(-5.3,24)],.15,.026)]
def channel_fields(x,y):
 x,y=np.broadcast_arrays(np.asarray(x),np.asarray(y));cut=np.zeros(x.shape);bar=np.zeros(x.shape);bank=np.zeros(x.shape)
 # Unequal right-side counterpart is farther along the road and shallower.
 xx=-np.abs(x);yy=y-np.where(x>0,11,0);strength=np.where(x>0,.64,1.)
 for ip,(points,width,depth) in enumerate(paths):
  for a,b in zip(points[:-1],points[1:]):
   ax,ay=a;bx,by=b;vx,vy=bx-ax,by-ay;length=math.hypot(vx,vy);t=np.clip(((xx-ax)*vx+(yy-ay)*vy)/(length*length),0,1);px=ax+t*vx;py=ay+t*vy;dx=xx-px;dy=yy-py;dist=np.sqrt(dx*dx+dy*dy);signed=(dx*(-vy)+dy*vx)/length
   irregular=1+.16*field(px,py,.27,128+ip)+.10*field(px,py,.083,164+ip)
   # One narrower bank gives an uneven crest; flat bottom with sharp slope break.
   half=width*.5*irregular*np.where(signed>0,1.0,.72);u=dist/np.maximum(half,.025)
   profile=1-smooth(.36,1,u);localcut=depth*profile*strength;cut=np.maximum(cut,localcut)
   pocket=np.clip(.48+.62*field(px,py,.8,304+ip),0,1);bar=np.maximum(bar,(1-smooth(.78,1.35,u))*smooth(.15,.55,u)*pocket*strength)
   bank=np.maximum(bank,(1-smooth(.83,1.15,u))*smooth(.48,.83,u)*strength)
 return cut,bar,bank

def landscape(x,y):
 x,y=np.broadcast_arrays(np.asarray(x),np.asarray(y));d=np.abs(x)-3.2;edit=smooth(.40,.75,d)*(1-smooth(13,19,d))*smooth(-4,-1,y)*(1-smooth(37,52,y))
 base=grade(y)+.072-np.clip(d,0,2)*.029-np.clip(d-2,0,7)*.006
 # Almost planar compacted interspaces. No blanket metre-scale wave field.
 base+=.006*field(x,y,12,581)
 for track in(.65,1.27):
  rut=(1-smooth(.055,.13,np.abs(d-track)))*np.clip(.40+field(x,y,3.7,610),0,1);base-=.013*rut
 cut,bar,bank=channel_fields(x,y);new=base-cut;old=old_terrain(x,y)+old_sort(x,y)[3]
 return old+edit*(new-old),edit,bar*edit,bank*edit,cut*edit

def delta(x,y):return landscape(x,y)[0]-(old_terrain(x,y)+old_sort(x,y)[3])
# Refine actual local geometry: old 17cm longitudinal sampling beyond y12 is
# insufficient for 15–48cm channels. Keep the fixed boundary interpolated exactly.
counts=[]
for ob in list(s.objects):
 if not ob.name.startswith('Graded shoulder and alluvial plain'):continue
 old=ob.data;oc=np.array([v.co[:] for v in old.vertices],dtype='f8');ys=np.unique(oc[:,1]);nx=len(oc)//len(ys);oc=oc.reshape(len(ys),nx,3);ys2=np.unique(np.r_[ys,np.arange(-3,40,.035)]);co=np.empty((len(ys2),nx,3),dtype='f8')
 for j in range(nx):co[:,j,0]=np.interp(ys2,ys,oc[:,j,0]);co[:,j,2]=np.interp(ys2,ys,oc[:,j,2])
 co[:,:,1]=ys2[:,None];x=co[:,:,0];y=co[:,:,1];newz,edit,bar,bank,cut=landscape(x,y);oldanalytic=old_terrain(x,y)+old_sort(x,y)[3];co[:,:,2]=co[:,:,2]*(1-edit)+newz-oldanalytic*(1-edit)
 q=(np.arange(len(ys2)-1)[:,None]*nx+np.arange(nx-1)[None,:]).ravel();f=np.stack((q,q+1,q+nx+1,q+nx),1)
 if ob.name.endswith('-1'):f=f[:,::-1]
 me=bpy.data.meshes.new(ob.name+' / resolved connected drainage');me.vertices.add(co.size//3);me.vertices.foreach_set('co',co.astype('f4').ravel());me.loops.add(f.size);me.loops.foreach_set('vertex_index',f.astype('i4').ravel());me.polygons.add(len(f));me.polygons.foreach_set('loop_start',np.arange(len(f),dtype='i4')*4);me.polygons.foreach_set('loop_total',np.full(len(f),4,dtype='i4'));me.polygons.foreach_set('use_smooth',np.ones(len(f),dtype=bool));me.update();me.materials.append(old.materials[0]);a=me.attributes.new('asphalt_share','FLOAT','POINT');a.data.foreach_set('value',np.zeros(len(me.vertices),dtype='f4'))
 tint=tint_ground(x,y);patch=field(x,y,2.9,804);comp=np.clip(.8*patch+.25*field(x,y,.65,805),-.5,.5);factors=np.ones(x.shape+(3,))+edit[...,None]*comp[...,None]*np.array([.10,.09,.06]);factors-=bar[...,None]*np.array([.24,.20,.13]);factors+=bank[...,None]*np.array([.05,.01,-.03]);tint[...,:3]*=factors;a=me.color_attributes.new(name='macro_tint',type='FLOAT_COLOR',domain='POINT');a.data.foreach_set('color',tint.astype('f4').ravel());ob.data=me;counts.append([ob.name,len(me.vertices),len(f)])
# Approved individual grain prototypes are unmodified; only their origins follow
# the broad terrain datum. Rock bodies below are translated as rigid components.
po=bpy.data.objects['True approved R5D near-camera grain geometry'];co=np.array([v.co[:] for v in po.data.vertices],dtype='f8');co[:,2]+=delta(co[:,0],co[:,1]);po.data.vertices.foreach_set('co',co.ravel());po.data.update()
def move_rigid_bodies(ob):
 me=ob.data;co=np.array([v.co[:] for v in me.vertices],dtype='f8');parent=np.arange(len(co),dtype='i4')
 def root(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 for p in me.polygons:
  ids=p.vertices;a=root(ids[0])
  for v in ids[1:]:b=root(v);parent[b]=a
 for i in range(len(parent)):parent[i]=root(i)
 roots,ids=np.unique(parent,return_inverse=True);ct=np.bincount(ids);cx=np.bincount(ids,weights=co[:,0])/ct;cy=np.bincount(ids,weights=co[:,1])/ct;co[:,2]+=delta(cx,cy)[ids];me.vertices.foreach_set('co',co.ravel());me.update();return len(roots)
moved=[]
for name in ('Sparse physical 7–31 mm roadside mineral lag','Gravel lag pockets beside shallow runoff arms'):
 ob=bpy.data.objects.get(name)
 if ob:moved.append([name,move_rigid_bodies(ob)])
plants=[ob for ob in s.objects if ob.name.startswith(('Scrub group /','Established irregular','Scrub patch /','Sparse dry straw'))];plant_xy=np.array([(o.location.x,o.location.y) for o in plants]);plant_delta=delta(plant_xy[:,0],plant_xy[:,1])
for ob,dz in zip(plants,plant_delta):ob.location.z+=float(dz)
print('RESOLVED_LANDSCAPE_AND_ROOTS',counts,flush=True)
# Extra bed-margin gravel is attached to this network, not an independent noise.
protos=json.loads((R.parent/'discrete_grains_r5/prototypes/fracture_solids.json').read_text());rng=np.random.default_rng(101017);verts=[];faces=[];cols=[];rough=[];placed=0
pal=np.array([[.30,.27,.22],[.47,.43,.35],[.18,.185,.18],[.30,.235,.17]])
candidates=[]
for k in range(7000):
 ip=int(rng.choice(len(paths),p=[.23,.13,.1,.24,.12,.11,.07]));points,width,depth=paths[ip];idx=int(rng.integers(len(points)-1));a=np.array(points[idx]);b=np.array(points[idx+1]);t=rng.uniform(0,1);p=a*(1-t)+b*t;v=b-a;perp=np.array([-v[1],v[0]])/np.linalg.norm(v);p+=perp*rng.uniform(-width*.64,width*.64);candidates.append(p)
candidates=np.array(candidates);cut,bar,bank=channel_fields(candidates[:,0],candidates[:,1]);keep=rng.random(len(candidates))<(.18+.82*bar);candidates=candidates[keep];zs=landscape(candidates[:,0],candidates[:,1])[0]
for (x,y),z in zip(candidates,zs):
 size=float(np.exp(rng.uniform(np.log(.006),np.log(.026))));pr=protos[int(rng.integers(len(protos)))];vv=np.array(pr['vertices']);vv[:,0]*=size;vv[:,1]*=size*rng.uniform(.4,.95);thickness=size*rng.uniform(.20,.42);vv[:,2]*=thickness;ang=rng.uniform(0,math.tau);vv[:,:2]=vv[:,:2]@np.array([[math.cos(ang),-math.sin(ang)],[math.sin(ang),math.cos(ang)]]).T;vv+=np.array([x,y,float(z)-thickness*rng.uniform(.3,.58)]);off=len(verts);verts.extend(vv);faces.extend(tuple(off+i for i in f) for f in pr['faces']);cc=np.ones((len(vv),4));cc[:,:3]=pal[int(rng.integers(len(pal)))]*rng.uniform(.9,1.12);cols.extend(cc);rough.extend([rng.uniform(.69,.85)]*len(vv));placed+=1
me=bpy.data.meshes.new('Channel-margin deposited mineral fragments');me.from_pydata(verts,[],faces);me.materials.append(bpy.data.objects['Gravel lag pockets beside shallow runoff arms'].data.materials[0]);a=me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');a.data.foreach_set('color',np.array(cols,dtype='f4').ravel());a=me.attributes.new('grain_roughness','FLOAT','POINT');a.data.foreach_set('value',np.array(rough,dtype='f4'));ob=bpy.data.objects.new('Connected drainage / margin gravel bars',me);s.collection.objects.link(ob)
s['scene_version']='R6 L connected shallow erosion and compacted interspaces';out=R/'preview/road_r6_l.blend';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(out),compress=True);receipt={'source_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scene_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'terrain_mesh_counts':counts,'local_longitudinal_mesh_spacing_m':.035,'channel_width_m':[.15,.48],'maximum_authored_incision_m':.074,'extra_channel_gravel_bodies':placed,'rigid_body_counts_repositioned':moved,'references':[{'url':'https://pubs.usgs.gov/of/2004/1007/fans.html','use':'Indexed USGS description of braided low corridors and desert-pavement islands; page 403 respected.'},{'url':'https://www.usgs.gov/media/images/lake-mead-incised-stream-channels-alluvial-fan-deposits','use':'Accessible USGS reference photo visually inspected in the cloud browser: distinct incised channels and irregular bank slope breaks; regional analogue, no measured scene scale.'}],'limits':'Art-directed shallow dimensions, not measured Victorville site reconstruction. No image pixels or scan assets used.','CPU_threads':2};(R/'receipts/erosion_network_l.json').write_text(json.dumps(receipt,indent=2));print('EROSION_NETWORK_READY',receipt,flush=True)
