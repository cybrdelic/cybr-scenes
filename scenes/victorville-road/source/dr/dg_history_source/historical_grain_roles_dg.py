"""DG: prior-support grains and finite-stock surface representatives.
Only the existing rebuilt CZ point-bank Z coordinates change, after DA.
No new transport, input ledger edits, XY changes, enlargement or recoloring.
"""
from pathlib import Path
import gc,hashlib,json,time
import numpy as np
from history_budget_dg import reconcile,retained_cover
from transported_grain_exposure_dg import allocate_transported_grains,ExposureConfig
NAMES=('U approved R5D density / projected chip and grit supplement','CZ current-view original sand instances')
BOUNDS=(-7.,-3.36,-.9,18.)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(seq,key,n,d='f4'):
 a=np.empty((len(seq),n),d);seq.foreach_get(key,a.ravel());return a

def apply(scene,cfg,out):
 import approved_density_lod as a
 from context_mesh_refine_ab import SourceSampler
 from visible_shoulder_flow_ad import sample_field
 start=time.monotonic();out=Path(out);assert cfg['revision']==1
 for key in ('payload','historical_fields','sand_bank','datums'):assert sha(cfg[key])==cfg[key+'_sha256']
 with np.load(cfg['payload'])as f:p={k:f[k]for k in f.files}
 with np.load(cfg['historical_fields'])as f:h={k:f[k]for k in f.files}
 co=p['source_coordinates'].copy();co[:,2]+=p['delta'];tri=p['tri'];sampler=SourceSampler(co,tri,np.arange(len(tri)),max_triangles=500000,max_bin_entries=4000000)
 def current_sample(values,xy):
  ans=np.zeros((len(xy),)+np.asarray(values).shape[1:]);inside=(xy[:,0]>=BOUNDS[0])&(xy[:,0]<=BOUNDS[1])&(xy[:,1]>=BOUNDS[2])&(xy[:,1]<=BOUNDS[3]);ii=np.flatnonzero(inside);ii=ii[np.lexsort((xy[ii,1],np.floor(xy[ii,0]/.045)))]
  for st in range(0,len(ii),2048):
   ids=ii[st:st+2048];ans[ids]=sampler.sample(values,xy[ids])
  return ans,inside
 def historical(values,xy):
  ans=np.zeros((len(xy),)+np.asarray(values).shape[2:]);inside=(xy[:,0]>=h['x_m'][0])&(xy[:,0]<=h['x_m'][-1])&(xy[:,1]>=h['y_m'][0])&(xy[:,1]<=h['y_m'][-1]);ans[inside]=sample_field(values,xy[inside],h['x_m'],h['y_m']);return ans
 # Reuse the old allocator at its original 5cm representation-cell scale.
 # This grid is only a display-budget quadrature; it does not alter terrain.
 x=np.arange(-6.975,-3.36,.05);y=np.arange(-.875,18.,.05);xx,yy=np.meshgrid(x,y);grid=np.c_[xx.ravel(),yy.ravel()]
 rem,_=current_sample(p['removed'],grid);dep,_=current_sample(p['deposited'],grid);prior=historical(h['retained_deposit_by_class_m'],grid);recon=reconcile(prior,rem,dep);available=recon['available'].reshape(len(y),len(x),3)
 net,_=current_sample(p['sediment'],grid);priornet=historical(h['sediment_delta_m'],grid);cover_grid=retained_cover(priornet,net).reshape(len(y),len(x))
 records,_,_=a._bank(scene.objects[a.ORIGINS]);protos=[]
 for r in records:
  import bpy
  me=bpy.data.objects[r['name']].data;me.calc_loop_triangles();tt=read(me.loop_triangles,'vertices',3,'i4');protos.append({'vertices':r['vertices'],'tri':tt,'diameter':r['diameter'],'footprint':r['footprint_area'],'class':2 if r['band']=='chips'else 1,'offset':0.})
 bank=json.loads(Path(cfg['sand_bank']).read_text());dt=json.loads(Path(cfg['datums']).read_text());offsets={r['source_id']:r['bed_reference_offset_m']for r in dt['records']}
 for q in bank['particles']:
  v=np.asarray(q['vertices'],float);tt=np.asarray(q['faces'],'i4');diam=float(np.sqrt(np.max(np.sum((v[:,None,:2]-v[None,:,:2])**2,axis=-1))));protos.append({'vertices':v,'tri':tt,'diameter':diam,'footprint':a._hull_area(v[:,:2]),'class':0,'offset':offsets[q['source_id']]})
 volume=[];minimum=[];maximum=[];bottom=[]
 for r in protos:
  v=r['vertices'];t=r['tri'];assert t.ndim==2 and t.shape[1]==3
  edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);_,count=np.unique(edges,axis=0,return_counts=True);assert np.all(count==2),'Open prototype cannot spend a solid-volume budget'
  tv=v[t];vol=abs(float(np.einsum('ij,ij->i',tv[:,0],np.cross(tv[:,1],tv[:,2])).sum()/6));assert 0<vol<1e-6;volume.append(vol);minimum.append(v[:,2].min()-r['offset']);maximum.append(v[:,2].max()-r['offset']);bottom.append(v[np.argmin(v[:,2])])
 volume=np.array(volume);minimum=np.array(minimum);maximum=np.array(maximum);bottom=np.array(bottom);diam=np.array([r['diameter']for r in protos]);foot=np.array([r['footprint']for r in protos]);classes=np.array([r['class']for r in protos]);offs=np.array([r['offset']for r in protos]);rows=[];parts=[];protected=hashlib.sha256(a._co(scene.objects[a.ORIGINS].data).tobytes()).hexdigest()
 for k,name in enumerate(NAMES):
  ob=scene.objects[name];assert np.array_equal(np.asarray(ob.matrix_world),np.eye(4));before=read(ob.data.vertices,'co',3);pi=read(ob.data.attributes['prototype'].data,'value',1,'i4').ravel();yaw=read(ob.data.attributes['yaw'].data,'vector',3);identity=hashlib.sha256(before[:,:2].tobytes()+pi.tobytes()+yaw.tobytes()).hexdigest();idx=pi+k*64;parts.append((ob,before,pi,yaw,identity,idx))
 before=np.concatenate([p1[1]for p1 in parts]);idx=np.concatenate([p1[5]for p1 in parts]);xy=before[:,:2].astype(float);ce,inside=current_sample(p['sediment'],xy);ah=historical(h['sediment_delta_m'],xy);cover=retained_cover(ah,ce)
 final=before[:,2].astype(float)+offs[idx]
 # Numerically confirm that the rebuilt DA bank really is on current terrain.
 true_z,_=current_sample(co[:,2],xy);err=np.max(abs(true_z[inside]-final[inside]),initial=0);assert err<2e-7,('Unsupported baseline point datum',err)
 allocation=allocate_transported_grains(xy_m=xy,flow_class=classes[idx],solid_volume_m3=volume[idx],diameter_m=diam[idx],footprint_area_m2=foot[idx],local_z_bounds_m=np.c_[minimum,maximum][idx],final_surface_m=final,x_m=x,y_m=y,retained_deposit_by_class_m=available,net_deposit_m=cover_grid,local_net_deposit_m=cover,config=ExposureConfig(availability_mode='surviving_deposit_stock'))
 selected=allocation.transported&inside;after=before.copy();after[:,2]=(before[:,2].astype(float)-cover).astype('f4');after[selected,2]=(before[selected,2].astype(float)-allocation.extra_embedment_m[selected]).astype('f4')
 # All selected surface representatives retain the intrinsic source embedding.
 assert np.all(after[:,2]<=before[:,2]+1e-9);assert np.array_equal(after[:,:2],before[:,:2]);assert np.all(allocation.selected_solid_volume_by_cell_class_m3<=allocation.solid_budget_by_cell_class_m3)
 # Validate each moved body's actual lowest vertex against the final triangles.
 yaw=np.concatenate([p1[3]for p1 in parts])[:,2];b=bottom[idx];bx=b[:,0]*np.cos(yaw)-b[:,1]*np.sin(yaw);by=b[:,0]*np.sin(yaw)+b[:,1]*np.cos(yaw);bxy=xy+np.c_[bx,by];changed=abs(after[:,2]-before[:,2])>1e-9;test=np.flatnonzero(changed&inside);tests=test[np.unique(np.linspace(0,len(test)-1,min(1024,len(test)),dtype=int))]if len(test)else test
 terrain_all=a._height(sampler,bxy[test],allow_missing=True);valid_all=np.isfinite(terrain_all);valid_ids=test[valid_all];old_z=after[valid_ids,2].astype(float).copy();cap=terrain_all[valid_all]-b[valid_ids,2]-.000020
 after[valid_ids,2]=np.minimum(old_z,cap).astype('f4');contact_cap_shift=old_z-after[valid_ids,2];terrain_b=a._height(sampler,bxy[tests],allow_missing=True);valid=np.isfinite(terrain_b);contact=after[tests,2].astype(float)+b[tests,2]-terrain_b;assert np.max(contact[valid],initial=-1)<.000021,('Floating candidate lowest vertex',contact[valid].max())
 cur=0
 for ob,old,pi,yaw,identity,ii in parts:
  n=len(old);new=after[cur:cur+n];ob.data.vertices.foreach_set('co',new.ravel());ob.data.update();assert identity==hashlib.sha256(read(ob.data.vertices,'co',3)[:,:2].tobytes()+pi.tobytes()+yaw.tobytes()).hexdigest();sel=selected[cur:cur+n];cv=cover[cur:cur+n];rows.append({'object':ob.name,'count':n,'identity_XY_prototype_yaw_sha256':identity,'surface_representatives':int(sel.sum()),'static_origins_buried':int(((cv>1e-9)&~sel).sum()),'newly_below_reference_plane':int(((maximum[ii]>0)&(maximum[ii]-(old[:,2]-new[:,2])<=0)).sum()),'before_position_sha256':hashlib.sha256(old.tobytes()).hexdigest(),'after_position_sha256':hashlib.sha256(new.tobytes()).hexdigest()});cur+=n
 assert protected==hashlib.sha256(a._co(scene.objects[a.ORIGINS].data).tobytes()).hexdigest()
 for key in ('payload','historical_fields','sand_bank','datums'):assert sha(cfg[key])==cfg[key+'_sha256']
 np.savez_compressed(out/'DG_EXACT_ROLE_AND_Z_CHANGE.npz',point_id=np.arange(len(before),dtype='i4'),before_z=before[:,2],after_z=after[:,2],class_id=classes[idx].astype('i1'),surface_representative=selected,static_cover_m=cover.astype('f4'),budget=allocation.solid_budget_by_cell_class_m3,selected_volume=allocation.selected_solid_volume_by_cell_class_m3)
 report={'revision':'DG historical support and class-stock display allocation','objects':rows,'input_pins':{k:cfg[k+'_sha256']for k in ('payload','historical_fields','sand_bank','datums')},'static_rule':'Same CI current-terrain minus max(max(AH net,0)+CE signed redistribution,0).','surface_role':'Existing finite proxy instances selected against surviving AH deposited classes after class-wise CE erosion-first debit, plus CE retained deposits. The old bounded allocator is unchanged except accepting original fine-sand class0.','reconciliation':'min(AH deposited, CE removed) is charged to the prior retained class first. This is a conservative representation assumption; vertical stratigraphy and particle trajectories are not solved.','allocation':allocation.receipt,'maximum_initial_contact_datum_error_m':float(err),'contact_cap_rule':'Original AI minimum20um embedding at the actual lowest prototype vertex, applied to every moved supported body; unsupported boundary contacts reported.', 'contact_cap_body_count':int((contact_cap_shift>1e-9).sum()),'maximum_additional_contact_cap_m':float(contact_cap_shift.max(initial=0)),'unsupported_lowest_vertex_contacts':int((~valid_all).sum()),'lowest_vertex_contact_samples':len(tests),'valid_contact_samples':int(valid.sum()),'maximum_lowest_vertex_contact_m':float(contact[valid].max())if valid.any()else None,'geometry_source_sizes_materials_XY_yaw_ids_counts_and_ledger_unchanged':True,'new_solver_mass':0,'limits':['Grain roles describe display proxies, not tracked physical transport trajectories.','New budget grid samples original fields; it is a representation quadrature, not a newly conservative transport solve. Input ledgers remain byte-exact.','Subpixel population and original normal/color bakes still overlap statistically; no exact disjoint no-double-counting optical claim.','Origin-cell volume caps and bounded lowest-vertex contact tests do not prove every footprint collision.','The original physical grain sizes and material endpoints are unchanged.'],'elapsed_seconds':time.monotonic()-start};(out/'HISTORICAL_GRAIN_ROLES_DG.json').write_text(json.dumps(report,indent=2)+'\n');print('DG_ROLES',json.dumps(report),flush=True);del p,h,sampler,co,tri,parts,after,before;gc.collect();return report
