"""Bounded scene-level sorting and scrub distribution pass over fixed-contact I.
All units metres. Approved R5D shader/prototypes and pavement are unchanged.
"""
import bpy,numpy as np,math,json,ast,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];source=R/'preview/road_r6_i.blend';bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene
wanted={'field','grade','edge_y','road_z','wash','terrain'};tree=ast.parse((R/'src/build_scene.py').read_text());env={'np':np};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[]),'<terrain>', 'exec'),env);field=env['field'];terrain=env['terrain'];wash=env['wash']
def smooth(a,b,x):
 t=np.clip((np.asarray(x)-a)/(b-a),0,1);return t*t*(3-2*t)
def sorting(x,y):
 x=np.asarray(x);y=np.asarray(y);d=np.abs(x)-3.2;side=np.sign(x)
 broad=field(x*.8,y,2.5,803);pocket=field(x,y,.43,808)
 lag=smooth(-.22,.46,broad+.44*pocket)
 # Irregular short cross-shoulder runoff arms, with lag beside shallow scours.
 scour=np.zeros(np.broadcast(x,y).shape);deposit=np.zeros_like(scour)
 for k,(cy,slant,width,depth) in enumerate([(2.8,.32,.085,.012),(5.6,.45,.075,.014),(10.9,-.31,.11,.020),(19.2,.58,.085,.016),(34.7,-.40,.13,.022),(58.2,.26,.17,.021)]):
  centre=cy+(d-.5)*slant+side*(.6+k*.19)+.13*field(x,y,.7,901+k)
  q=np.abs(y-centre)/(width+.035*np.maximum(d,0));arm=np.maximum(1-q,0)**1.5
  reach=smooth(.35,.7,d)*(1-smooth(2.4,4.2,d));scour=np.maximum(scour,depth*arm*reach)
  fan=np.maximum(1-np.abs(y-centre)/(.24+.13*np.maximum(d,0)),0)*smooth(1.15,2.2,d)*(1-smooth(3,5.2,d))
  deposit=np.maximum(deposit,fan)
 gate=smooth(.75,1.6,y)*(1-smooth(65,85,y))*smooth(.34,.66,d)*(1-smooth(9,14,d))
 lag=np.clip(lag+.45*scour/.022-.65*deposit,0,1)
 dz=gate*(-scour+.0035*deposit)
 return lag,deposit,gate,dz
# Resolved existing shoulder mesh receives shallow erosion and co-located tint.
changed=0;dzrange=[0,0]
for ob in list(s.objects):
 if not ob.name.startswith('Graded shoulder and alluvial plain'):continue
 me=ob.data;co=np.array([v.co[:] for v in me.vertices],dtype='f8');lag,dep,g,dz=sorting(co[:,0],co[:,1]);co[:,2]+=dz;me.vertices.foreach_set('co',co.ravel());me.update();ca=me.color_attributes['macro_tint'];c=np.empty(len(co)*4,dtype='f4');ca.data.foreach_get('color',c);c=c.reshape(-1,4)
 # Mineral-rich lag is cooler/darker; thin fine-sediment lenses are pale warm.
 factor=(1-g[:,None])+g[:,None]*((1-lag[:,None])*np.array([1.06,1.035,.97])+lag[:,None]*np.array([.73,.77,.82]))
 factor+=g[:,None]*dep[:,None]*np.array([.10,.06,.02]);c[:,:3]*=factor;ca.data.foreach_set('color',c.ravel());changed+=int(np.count_nonzero(g));dzrange=[min(dzrange[0],float(dz.min())),max(dzrange[1],float(dz.max()))]
# Preserve existing near-camera extra lag. Suppress its uniformly scattered
# middle-distance portion; the new particles below use the same physical grade.
old=bpy.data.objects['Sparse physical 7–31 mm roadside mineral lag'];me=old.data
co=np.array([v.co[:] for v in me.vertices]);keep=[tuple(p.vertices) for p in me.polygons if max(co[i,1] for i in p.vertices)<1.0];used=np.unique(np.array(keep).ravel());remap=np.full(len(co),-1,dtype='i4');remap[used]=np.arange(len(used));new=bpy.data.meshes.new('Preserved foreground roadside lag');new.from_pydata(co[used].tolist(),[],[tuple(remap[list(f)]) for f in keep]);new.materials.append(me.materials[0]);cols=np.empty(len(co)*4,dtype='f4');me.color_attributes['mineral'].data.foreach_get('color',cols);a=new.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');a.data.foreach_set('color',cols.reshape(-1,4)[used].ravel());rough=np.empty(len(co),dtype='f4');me.attributes['grain_roughness'].data.foreach_get('value',rough);a=new.attributes.new('grain_roughness','FLOAT','POINT');a.data.foreach_set('value',rough[used]);old.data=new
protos=json.loads((R.parent/'discrete_grains_r5/prototypes/fracture_solids.json').read_text());rng=np.random.default_rng(261010);verts=[];faces=[];colors=[];rough=[];nbody=0
palette=np.array([[.32,.27,.205],[.47,.425,.34],[.19,.185,.175],[.29,.235,.17],[.12,.125,.125]])
# Dense spots at true grain size, with broad sparse/bare interspaces.
for k in range(76000):
 side=-1 if k<61000 else 1;x=side*rng.uniform(3.65,10);y=rng.uniform(.85,60);lag,dep,g,dz=sorting(x,y);prob=(.018+.43*float(lag)**2)*(1-.8*float(dep))*float(g)
 if rng.random()>prob:continue
 diameter=float(np.exp(rng.uniform(np.log(.006),np.log(.028))));pr=protos[int(rng.integers(len(protos)))];vv=np.array(pr['vertices']);vv[:,0]*=diameter;vv[:,1]*=diameter*rng.uniform(.38,.94);thick=diameter*rng.uniform(.18,.36);vv[:,2]*=thick;angle=rng.uniform(0,math.tau);c,si=math.cos(angle),math.sin(angle);vv[:,:2]=vv[:,:2]@np.array([[c,-si],[si,c]]).T;vv+=np.array([x,y,float(terrain(x,y)+dz)-thick*rng.uniform(.40,.72)]);off=len(verts);verts.extend(vv);faces.extend(tuple(off+i for i in f) for f in pr['faces']);cc=np.ones((len(vv),4));cc[:,:3]=palette[int(rng.choice(5,p=[.26,.24,.17,.24,.09]))]*rng.uniform(.88,1.14);cc[:,:3]=cc[:,:3]*.80+np.array([.29,.231,.16])*.20;colors.extend(cc);rough.extend([rng.uniform(.69,.86)]*len(vv));nbody+=1
mm=bpy.data.meshes.new('Sorted metric lag bodies');mm.from_pydata(verts,[],faces);mm.materials.append(old.data.materials[0]);a=mm.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');a.data.foreach_set('color',np.array(colors,dtype='f4').ravel());a=mm.attributes.new('grain_roughness','FLOAT','POINT');a.data.foreach_set('value',np.array(rough,dtype='f4'));ob=bpy.data.objects.new('Gravel lag pockets beside shallow runoff arms',mm);s.collection.objects.link(ob)
# Replace the uniform independent middle-distance shrub scatter with groups
# around discontinuous wetting/sediment pockets. Leave large connected gaps.
from types import SimpleNamespace
meshes={o.data.name:o.data for o in s.objects if o.name.startswith('Scrub patch / rooted')};bank=[SimpleNamespace(name=name,data=data) for name,data in meshes.items()];assert len(bank)==12,len(bank)
removed=0
for ob in list(s.objects):
 if ob.name.startswith('Scrub patch / rooted') and abs(ob.location.x)<40 and -2<ob.location.y<155:
  bpy.data.objects.remove(ob,do_unlink=True);removed+=1
added=0
for side in(-1,1):
 centres=[]
 for k in range(62):
  cy=rng.uniform(-1,160);cx=side*rng.uniform(5.0,34)
  if field(cx,cy,12,771)<-.08 and rng.random()<.86:continue
  centres.append((cx,cy,rng.uniform(.65,2.4)))
 for cx,cy,spread in centres:
  for k in range(int(rng.integers(2,9))):
   x=cx+rng.normal(0,spread);y=cy+rng.normal(0,spread*1.3)
   if abs(x)<4.9:continue
   # Low spreading shrubs dominate; a few tall, airy individuals punctuate.
   candidates=[o for o in bank if ('young' in o.name.lower() or 'low' in o.name.lower() or 'spreading' in o.name.lower())] if rng.random()<.73 else bank
   base=candidates[int(rng.integers(len(candidates)))];ob=bpy.data.objects.new('Scrub group / sediment wetting pocket',base.data);s.collection.objects.link(ob);dz=sorting(x,y)[3];ob.location=(x,y,float(terrain(x,y)+dz));ob.rotation_euler=(rng.uniform(-.10,.10),rng.uniform(-.10,.10),rng.uniform(0,math.tau));scale=rng.uniform(.65,1.28);ob.scale=(scale*rng.uniform(.85,1.20),scale*rng.uniform(.85,1.2),scale*rng.uniform(.78,1.05));added+=1
# A few established groups occupy the camera-visible near/middle corridor,
# rather than accidentally deleting all nearby plants during re-clustering.
for cx,cy,number in [(-5.45,8.5,5),(-6.7,18.5,5),(-5.8,32,4),(5.8,8.0,4),(6.6,17,5),(8.8,31,4)]:
 for k in range(number):
  x=cx+rng.normal(0,.48);y=cy+rng.normal(0,.65)
  candidates=[o for o in bank if ('low' in o.name.lower() or 'spreading' in o.name.lower())]
  if k==0 and cx>0:candidates=[o for o in bank if 'upright' in o.name.lower()]
  base=candidates[int(rng.integers(len(candidates)))];ob=bpy.data.objects.new('Established irregular roadside scrub group',base.data);s.collection.objects.link(ob);ob.location=(x,y,float(terrain(x,y)+sorting(x,y)[3]));ob.rotation_euler=(rng.uniform(-.10,.10),rng.uniform(-.10,.10),rng.uniform(0,math.tau));scale=rng.uniform(.65,1.1);ob.scale=(scale*rng.uniform(.85,1.2),scale*rng.uniform(.85,1.2),scale*rng.uniform(.8,1.05));added+=1
# Move instance origins with the tiny ground datum change; prototype geometry,
# physical sizes, mineral assignments and micro-materials stay identical.
points=bpy.data.objects['True approved R5D near-camera grain geometry'].data
co=np.array([v.co[:] for v in points.vertices],dtype='f8');co[:,2]+=sorting(co[:,0],co[:,1])[3];points.vertices.foreach_set('co',co.ravel());points.update()
# Existing grasses track the edited terrain where present.
for ob in s.objects:
 if ob.name.startswith('Sparse dry straw tufts'):ob.location.z+=float(sorting(ob.location.x,ob.location.y)[3])
s['scene_version']='R6 K sorted middle-distance shoulder and grouped scrub';out=R/'preview/road_r6_k.blend';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(out),compress=True)
receipt={'source_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scene_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'shoulder_vertices_in_sorting_field':changed,'relief_delta_m':dzrange,'additional_sorted_clast_bodies':nbody,'clast_diameter_m':[.006,.028],'shrubs_removed':removed,'grouped_shrubs_added':added,'unchanged':'Approved R5D prototype shapes, materials and metric sizes; instance origins follow the broad ground datum. Road, same-surface contact, cameras and lighting unchanged.','CPU_threads':2};(R/'receipts/sediment_patches_k.json').write_text(json.dumps(receipt,indent=2));print('SEDIMENT_PATCHES_READY',receipt,flush=True)
