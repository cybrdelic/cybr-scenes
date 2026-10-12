"""DU whole-shoulder geometry and optical installation on recovered DR.
All field decisions are world-space. Inventory summaries separate foundation
cut/fill, finite retained fine cap, and unchanged solid-body inventory.
"""
from pathlib import Path
import hashlib,importlib.util,json,time,gc,sys
import numpy as np
import bpy
from field_du import Field

PLANTS=('Scrub group /','Established irregular','Scrub patch /','Sparse dry straw','AP layered scrub /','AQ layered scrub /','CK pocket /','CK matrix /')
POINTS=('True approved R5D near-camera grain geometry','U approved R5D density / projected chip and grit supplement','CZ current-view original sand instances','AP graded margin / exact metric lag instances','CG finite 18–60 mm historical gravel pockets')
RIGID=('Sparse physical 7–31 mm roadside mineral lag','Gravel lag pockets beside shallow runoff arms','Connected drainage / margin gravel bars')

def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def read(seq,p,w=1,d='f4'):
 a=np.empty((len(seq),w),d) if w>1 else np.empty(len(seq),d);seq.foreach_get(p,a.ravel());return a

def attr(me,name,v):
 a=me.attributes.get(name) or me.attributes.new(name,'FLOAT','POINT');a.data.foreach_set('value',np.asarray(v,'f4'))

def area_weights(me,co):
 me.calc_loop_triangles();tri=read(me.loop_triangles,'vertices',3,'i4');area=np.zeros(len(co),float)
 for at in range(0,len(tri),100000):
  t=tri[at:at+100000];q=co[t,:2].astype(float);a=q[:,1]-q[:,0];b=q[:,2]-q[:,0];v=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])/6
  for i in range(3):np.add.at(area,t[:,i],v)
 return area

def cap_redistribution(scene,cfg,out,field):
 f=np.load(cfg['cap']);me=scene.objects['Graded shoulder and alluvial plain -1'].data;ids=f['source_vertex_ids'];old=f['cap_m'];a=f['area'].astype(float);q=field.evaluate(f['co'][:,:2]);gate=f['gate'].astype(float)
 # Reassign only the pinned original static fine stock; all event arrays and
 # mixed reserves remain numerically untouched. No new fine stock is created.
 target=gate*(.12+1.3*q['opening']+.70*q['root']);volume=float(np.dot(a,old));new=target*(volume/np.dot(a,target));maximum=float(f['optical_layer_thickness_m'][0])*.96
 if new.max()>maximum:
  lo,hi=0.,1.
  while np.dot(a,np.minimum(target*hi,maximum))<volume:hi*=2
  for _ in range(80):
   mid=(lo+hi)/2
   if np.dot(a,np.minimum(target*mid,maximum))<volume:lo=mid
   else:hi=mid
  new=np.minimum(target*((lo+hi)/2),maximum)
 thick=f['optical_layer_thickness_m'];oldarea=(old/thick)*(-np.expm1(-thick/.00035));newarea=(new/thick)*(-np.expm1(-thick/.00035));v=read(me.attributes['ai_fine_coat'].data,'value');combined=v[ids].astype(float);parent=(combined-oldarea)/(1-oldarea)
 assert parent.min()>-2e-6 and parent.max()<1+2e-6,(parent.min(),parent.max())
 v[ids]=1-(1-np.clip(parent,0,1))*(1-newarea);attr(me,'ai_fine_coat',v)
 # Burial follows the same cap allocation, using existing finite support mesh.
 from context_mesh_refine_ab import SourceSampler
 sampler=SourceSampler(f['co'],f['tri'],np.arange(len(f['tri'])),max_triangles=500000,max_bin_entries=4000000)
 def sample(xy,values=None):
  xy=np.asarray(xy);v=np.zeros(len(xy));i=np.flatnonzero((xy[:,0]>=-7)&(xy[:,0]<=-3.36)&(xy[:,1]>=-.9)&(xy[:,1]<=18))
  i=i[np.lexsort((xy[i,1],np.floor(xy[i,0]/.045)))]
  for at in range(0,len(i),2048):
   ii=i[at:at+2048];v[ii]=sampler.sample(new-old if values is None else values,xy[ii])
  return v
 report={'old_bulk_m3':volume,'new_bulk_m3':float(np.dot(a,new)),'residual_m3':float(np.dot(a,new-old)),'new_cap_depth_quantiles_m':np.quantile(new,[0,.1,.5,.9,1]).tolist(),'old_mixed_reserves_sha256':digest(f['original_mixed_reserve']),'old_surviving_event_sha256':digest(f['surviving_event']),'same_class_stock':True,'model':'Authored initial cap redistribution only, no inferred wind/water transport.'}
 np.savez_compressed(Path(out)/'DU_FINE_CAP.npz',source_vertex_ids=ids,old_cap_m=old,new_cap_m=new,area=a)
 return sample,report

def geometry(scene,cfg,out):
 start=time.monotonic();out=Path(out);roots=[];rootnames=[]
 for ob in scene.objects:
  if ob.hide_render or not ob.name.startswith(PLANTS):continue
  x,y,z=ob.matrix_world.translation
  if abs(x)<43 and -8<y<132:
   # Use actual existing crown width to anchor a small, low support apron.
   mw=np.asarray(ob.matrix_world);b=np.asarray(ob.bound_box)@mw[:3,:3].T+mw[:3,3];diam=max(float(np.ptp(b[:,0])),float(np.ptp(b[:,1])));scale=np.clip(diam,.30,2.5)
   roots.append((x,y,scale));rootnames.append(ob.name)
 field=Field(roots);(out/'DU_ROOTS.json').write_text(json.dumps({'roots':roots,'names':rootnames},indent=2)+'\n')
 cap_sample,cap_report=cap_redistribution(scene,cfg,out,field)
 terrain=[];offsets={}
 for sign in (-1,1):
  ob=scene.objects['Graded shoulder and alluvial plain '+str(sign)];me=ob.data;co=read(me.vertices,'co',3);assert np.array_equal(np.asarray(ob.matrix_world),np.eye(4));weights=area_weights(me,co);q=field.evaluate(co[:,:2]);g=q['gate'];mean=float(np.dot(weights*g,q['raw_height'])/np.dot(weights,g));delta=g*(q['raw_height']-mean);offsets[sign]=mean
  new=co.copy();new[:,2]=(co[:,2].astype(float)+delta).astype('f4');actual=new[:,2].astype(float)-co[:,2].astype(float)
  me.vertices.foreach_set('co',new.ravel());me.update();me.normals_split_custom_set(np.zeros((len(me.loops),3),'f4'));me.update()
  attr(me,'du_opening',q['opening']);attr(me,'du_shelter',q['root']);attr(me,'du_rough',q['rough']);attr(me,'du_compact',q['compact']);attr(me,'du_gate',g)
  # Compaction is structure, not a new sediment mass. It now varies at the same
  # geographic scale as broad relief and gravel exposure.
  for name,value in [('ak_historical_compaction',q['compact'])]:
   if me.attributes.get(name):
    old=read(me.attributes[name].data,'value');attr(me,name,old*(1-g)+value*g)
  row={'object':ob.name,'vertices':len(co),'pre_co_sha256':digest(co),'post_co_sha256':digest(new),'foundation_cut_m3':float(np.dot(weights,np.maximum(-actual,0))),'foundation_fill_m3':float(np.dot(weights,np.maximum(actual,0))),'foundation_net_f32_m3':float(np.dot(weights,actual)),'foundation_net_f64_m3':float(np.dot(weights,delta)),'height_range_m':[float(actual.min()),float(actual.max())],'mean_correction_m':mean,'xy_and_topology_unchanged':True,'modified_area_m2':float(weights[g>.01].sum())}
  assert abs(row['foundation_net_f64_m3'])<1e-9
  terrain.append(row);del co,new,q,weights,g,delta,actual;gc.collect()
 def shifts(xy,coarse_radius=0.):
  xy=np.asarray(xy,float);q=field.evaluate(xy);mean=np.where(xy[:,0]<0,offsets[-1],offsets[1]);h=q['gate']*(q['raw_height']-mean)
  if coarse_radius:
   for dx,dy in [(coarse_radius,0),(-coarse_radius,0),(0,coarse_radius),(0,-coarse_radius)]:
    qq=field.evaluate(xy+np.array([dx,dy]));h=np.minimum(h,qq['gate']*(qq['raw_height']-mean))
  return h,q
 bodies=[]
 for name in POINTS:
  ob=scene.objects.get(name)
  if not ob:continue
  co=read(ob.data.vertices,'co',3);mw=np.asarray(ob.matrix_world);assert np.array_equal(mw,np.eye(4));radius=.0009 if 'sand' in name else (.0035 if name.startswith(('True','U ')) else (.010 if name.startswith('AP ') else .033));h,q=shifts(co[:,:2],radius)
  radius_burial=0. if ('sand' in name or name.startswith(('True','U '))) else .011
  burial=radius_burial*np.minimum(q['opening']**3+.12*np.maximum((q['root']-.75)/.25,0),1)*q['gate'];cap_delta=cap_sample(co[:,:2]) if ('sand' not in name and not name.startswith(('True','U '))) else 0
  dz=h-burial-cap_delta;new=co.copy();new[:,2]=(co[:,2].astype(float)+dz).astype('f4');ob.data.vertices.foreach_set('co',new.ravel());ob.data.update()
  before_attrs={a.name:digest(read(a.data,'vector',3)if a.data_type=='FLOAT_VECTOR' else read(a.data,'value',1,'i4')) for a in ob.data.attributes if a.name in ['prototype','yaw','grain_id_lo','grain_id_hi']}
  assert np.array_equal(new[:,:2],co[:,:2]);bodies.append({'object':name,'bodies':len(co),'xy_sha256':digest(co[:,:2]),'identity_prototype_yaw':before_attrs,'z_delta_range_m':[float(dz.min()),float(dz.max())],'grain_sizes_meshes_ids_and_xy_unchanged':True,'maximum_additional_intrinsic_embedding_m':radius_burial,'support_footprint_radius_m':radius,'finite_surface_representatives_not_additionally_buried':name.startswith(('True','U '))or 'sand' in name})
  np.savez_compressed(out/('DU_BODY_'+str(len(bodies))+'.npz'),old_xyz=co,new_xyz=new)
  del co,new,h,q,dz;gc.collect()
 # Rigid existing bodies move as intact solids; no new minerals, rescaling,
 # deletion, hidden instances or stochastic reseeding.
 import prepare_physical_lenses as legacy
 oldbounds=legacy.PATCH_BOUNDS;legacy.PATCH_BOUNDS=(-42.,42.,-7.,130.)
 try:
  for name in RIGID:
   ob=scene.objects.get(name)
   if not ob:continue
   co=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,co);parts=legacy.local_components(ob.data,world);dz=np.zeros(len(co));moved=0
   for ii in parts:
    h,q=shifts(world[ii,:2]);bury=.018*np.minimum(q['opening']**3+.12*np.maximum((q['root']-.75)/.25,0),1)*q['gate'];d=float((h-bury).min());dz[ii]=d;moved+=abs(d)>1e-7
   legacy.write_world_z(ob,co,dz);bodies.append({'object':name,'connected_bodies':len(parts),'moved_bodies':int(moved),'rigid_translation_only':True,'solid_volume_unchanged':True,'z_delta_range_m':[float(dz.min()),float(dz.max())]});del co,world,parts,dz;gc.collect()
 finally:legacy.PATCH_BOUNDS=oldbounds
 movedroots=[]
 for ob in scene.objects:
  if ob.hide_render:continue
  if ob.name.startswith(PLANTS):
   xyz=np.asarray(ob.matrix_world.translation,float);h,q=shifts(xyz[None,:2]);d=float(h[0]-q['basal'][0]*q['gate'][0]-.016*q['root'][0]*q['gate'][0]);kind='root support anchored below irregular conserved soil collar'
  elif ob.name.startswith('AS sparse outer fragment /'):
   mw=np.asarray(ob.matrix_world);co=read(ob.data.vertices,'co',3);world=co@mw[:3,:3].T+mw[:3,3];h,q=shifts(world[:,:2]);d=float(np.min(h-.014*np.minimum(q['opening']**3+.12*np.maximum((q['root']-.75)/.25,0),1)*q['gate']));kind='unchanged rigid fragment';del co,world
  else:continue
  if abs(d)<1e-8:continue
  m=ob.matrix_world.copy();m.translation.z+=d;ob.matrix_world=m;movedroots.append({'name':ob.name,'z_shift_m':d,'kind':kind})
 bpy.context.view_layer.update()
 from root_contact_du import apply as root_contact
 root_report=root_contact(scene,out)
 from exposure_du import apply as expose_source_grains
 exposure=expose_source_grains(scene,cfg,out,field,cap_sample,offsets)
 for index,name in enumerate(POINTS,1):
  file=out/('DU_BODY_'+str(index)+'.npz')
  if not file.exists():continue
  original=np.load(file)['old_xyz'];final=read(scene.objects[name].data.vertices,'co',3)
  assert np.array_equal(original[:,:2],final[:,:2])
  np.savez_compressed(file,old_xyz=original,new_xyz=final,stage='DU5 final after exposure')
  for row in bodies:
   if row['object']==name:row['z_delta_range_m']=[float((final[:,2]-original[:,2]).min()),float((final[:,2]-original[:,2]).max())];row['final_stored_xyz_sha256']=digest(final)
 report={'root_contact':root_report,'exposure':exposure,'revision':'DU5','source_field_sha256':hashlib.sha256(Path(__file__).with_name('field_du.py').read_bytes()).hexdigest(),'root_count':len(roots),'terrain':terrain,'finite_fine_cap':cap_report,'bodies':bodies,'roots_and_rigid_instances':movedroots,'camera_independent':True,'same_AV_mountains_CN_palette_CO22_daylight':True,'changes':'Connected compacted openings, irregular rough margins and low shrub-base accumulation. No engineered parallel ditch.','limits':['Static authored reconstruction, no surveyed ground model or validated sediment transport.','Foundation cut/fill is area-lumped and zero net in float64; float32 storage residual separately reported.','Finite cap total is conserved. Initial intrinsic clast embedding is reassigned geographically; no new burial sediment is claimed.','Rigid shifts use conservative minimum field over footprints; full packing/collision simulation is not performed.','Existing DQ finite foreground-world particle catalog is retained; distant ground is a continuous substrate recipe, not fully resolved physical particles.'],'elapsed_seconds':time.monotonic()-start}
 (out/'DU_GEOMETRY.json').write_text(json.dumps(report,indent=2)+'\n');print('DU_GEOMETRY',json.dumps({'elapsed':report['elapsed_seconds'],'terrain':terrain,'cap':cap_report,'roots':len(roots)}),flush=True)
 return report

def material(scene,cfg,out):
 from matrix_du import install
 return install(scene,cfg,out)
