"""Read-only camera subsets of the frozen compact world and unchanged macro.

Packing and role allocation are forbidden here. Source contact is a pure
candidate-ID/XY/prototype/yaw/role calculation before any final pixel selection.
Conservative interval culling only avoids evaluating surely invisible bodies.
"""
from pathlib import Path
import sys,json,math,hashlib,gc,time,dataclasses
import numpy as np
O=Path(__file__).resolve().parent;sys.path[:0]=[str(O),str(O/'core'),str(O/'roles')]
from stream_compact import Reader,c,ref
from support_context import Support
import transported_grain_exposure_dq as role

def interval_candidates(xy,zlo,zhi,proj,diameter,height,ids):
 """Conservative linear-frustum + monotone LOD upper bound over a Z interval."""
 q0=np.c_[xy,zlo]@proj.inverse[:3,:3].T+proj.inverse[:3,3];q1=np.c_[xy,zhi]@proj.inverse[:3,:3].T+proj.inverse[:3,3]
 d0=-q0[:,2];d1=-q1[:,2];ok=np.maximum(d0,d1)>proj.near
 for axis,size in [(0,proj.width),(1,proj.height)]:
  l0=q0[:,axis]*proj.f[axis]+proj.offset[axis]*d0;l1=q1[:,axis]*proj.f[axis]+proj.offset[axis]*d1
  h0=q0[:,axis]*proj.f[axis]+(proj.offset[axis]-size)*d0;h1=q1[:,axis]*proj.f[axis]+(proj.offset[axis]-size)*d1
  ok&=(np.maximum(l0,l1)>=-1e-9)&(np.minimum(h0,h1)<=1e-9)
 mindepth=np.maximum(proj.near,np.minimum(d0,d1));px=(diameter+height/math.tan(math.radians(22)))*proj.f[0]/mindepth
 ok&=ref._uniform(ids,'lod')<ref.lod_fraction(px)
 return ok

def cell_height_bounds(s,cells,step):
 """Conservative bounds from every source triangle overlapping each cell+collar."""
 sampler=s.sampler;bounds=[];co=s.co;tri=s.tri
 # Includes grain XY radius, float32 roundoff and support minimum-vertex query.
 collar=max(q['radius'] for q in json.loads((O/'ACTUAL_CATALOG.json').read_text())['provenance']['prototypes'])+.00001
 margin=max(np.max(abs(s.arr('offset'))+np.maximum(s.arr('maximum'),0)),abs(s.arr('bottom')[:,2]).max())+abs(s.sediment).max()+abs(s.h['sediment_delta_m']).max()+abs(s.cap).max()+.0001
 for cell in cells:
  a=cell*step-collar;b=(cell+1)*step+collar;lo=np.floor(a/sampler.cell).astype('i8')-sampler.origin;hi=np.floor(b/sampler.cell).astype('i8')-sampler.origin;lo=np.maximum(lo,0);hi=np.minimum(hi,sampler.shape-1);parts=[]
  for yy in range(lo[1],hi[1]+1):
   keys=np.arange(lo[0],hi[0]+1)+yy*sampler.shape[0]
   for key in keys:
    i=np.searchsorted(sampler.keys,key,'left');j=np.searchsorted(sampler.keys,key,'right');parts.append(sampler.entries[i:j])
  assert parts and sum(map(len,parts)),'Missing source cell support'
  ids=sampler.triangle_ids[np.unique(np.concatenate(parts))];z=co[tri[ids],2];bounds.append([z.min()-margin,z.max()+margin])
 return np.array(bounds)

def effective_depth(ids,xy,pi,roles,budget,s,cover):
 x,dx=role._axis(budget['x'],'x');y,dy=role._axis(budget['y'],'y');inside=(xy[:,0]>=x[0])&(xy[:,0]<=x[-1])&(xy[:,1]>=y[0])&(xy[:,1]<=y[-1]);config=role.ExposureConfig(availability_mode='surviving_deposit_stock');dep=role._bilinear(budget['available'],xy,x,y,dx,dy,inside);_,effective,_=role.retained_top_proxy(dep,config.active_layer_m,config.top_availability_by_class);effective=np.where(np.isfinite(cover),effective,0)
 return role.keyed_extra_embedment_m(candidate_ids=ids,local_effective_deposit_m=effective,diameter_m=s.arr('diameter')[pi],local_z_bounds_m=np.c_[s.arr('minimum'),s.arr('maximum')][pi],transported=roles,config=config)

def select_world(proj,cfg):
 start=time.monotonic();reader=Reader();s=Support();bud=np.load(O/'WORLD_ROLE_BUDGET.npz');roles_path=O/'roles/WORLD_ROLES.npz';roles_receipt=json.loads(roles_path.with_suffix('.json').read_text());roles=np.load(roles_path);bits=roles['role1'];macro=np.load(O/'ACTUAL_CATALOG.npz');rows=s.rows;bounds=cell_height_bounds(s,reader.map.cells,reader.spec.cell_size)
 # File/data pins are checked by the installer job; additionally insist on the
 # complete world receipt here rather than accepting a view-derived role set.
 assert roles_receipt['roles_ready'] and roles_receipt['schema']=='dq-full-virtual-serial-role1-v1'
 assert roles_receipt['keyed_role_version']=='dq-stock-role-v1'
 assert roles_receipt['config']==json.loads(json.dumps(dataclasses.asdict(role.ExposureConfig(availability_mode='surviving_deposit_stock')))), 'Unreviewed role config change'
 assert hashlib.sha256(roles_path.read_bytes()).hexdigest()==roles_receipt['output_npz_sha256']
 assert hashlib.sha256(bits.tobytes()).hexdigest()==roles_receipt['role_sha256']
 for name,h in roles_receipt['input_sha256'].items():assert hashlib.sha256((O/name).read_bytes()).hexdigest()==h,name
 assert s.pins==roles_receipt['field_pins']
 diameter=s.arr('diameter');maxheight=np.maximum(s.arr('maximum'),0);sandheight=np.where(np.arange(len(rows))>=64,maxheight,0);kept=[None,None];tested=0;sampled=0
 def append(data):
  nonlocal kept
  for band in range(2):
   pi=data['prototype'];take=(pi>=64)==bool(band);ii=np.flatnonzero(take)
   if not len(ii):continue
   d={k:v[ii]for k,v in data.items()};old=kept[band]
   if old is not None:d={k:np.concatenate((old[k],v))for k,v in d.items()}
   budget=int(cfg.get('sand_budget',85000)if band else cfg.get('grit_budget',135000))
   if len(d['id'])>budget:
    rank=ref._mix64(d['id']^np.uint64(0xCBBB9D5DC1059ED8));order=np.lexsort((d['id'],rank))[:budget];d={k:v[order]for k,v in d.items()}
   kept[band]=d
 def exact_select(data):
  pi=data['prototype'];world=np.c_[data['xy'],data['z']];uv,depth=proj.project(world);px=(diameter[pi]+sandheight[pi]/math.tan(math.radians(22)))*proj.f[0]/np.maximum(depth,.001);ok=proj.visible(world,margin=0)&(ref._uniform(data['id'],'lod')<ref.lod_fraction(px));append({k:v[ok]for k,v in data.items()})
 exact_select({k:macro[k]for k in ['id','xy','prototype','yaw','precap_z','z','role','cover','static_cap']})
 for first in range(0,reader.map.virtual_count,131072):
  serial=np.arange(first,min(first+131072,reader.map.virtual_count),dtype='u4');serial=serial[reader.status_at(serial)==1]
  if not len(serial):continue
  ids,xy,slots,cells,ordinal=c._decode(reader.map,serial,reader.spec.cell_size);pi=reader.proto[slots];group=np.searchsorted(reader.map.prefix,serial,side='right')-1;ci=reader.map.group_cell[group];xy=xy.astype('f4').astype('f8');tested+=len(ids);ok=interval_candidates(xy,bounds[ci,0],bounds[ci,1],proj,diameter[pi],sandheight[pi],ids)
  if not ok.any():continue
  serial,ids,xy,pi=serial[ok],ids[ok],xy[ok],pi[ok];yaw=(ref._uniform(ids,'yaw')*math.tau).astype('f4');is_role=((bits[serial//8]>>(serial%8))&1).astype(bool);height,cover,cap=s.local_fields(xy);extra=effective_depth(ids,xy,pi,is_role,bud,s,cover);pre,z,cover,cap=s.placement(xy,pi,yaw,is_role,extra);sampled+=len(ids)
  assert np.all(z>=bounds[ci[ok],0])and np.all(z<=bounds[ci[ok],1]),'Placement exceeded conservative interval'
  exact_select(dict(id=ids,xy=xy,prototype=pi.astype('u1'),yaw=yaw,precap_z=pre,z=z,role=is_role,cover=cover.astype('f4'),static_cap=cap.astype('f4')))
 template={k:macro[k]for k in ['id','xy','prototype','yaw','precap_z','z','role','cover','static_cap']};data={k:(np.concatenate([d[k]for d in kept if d is not None])if any(d is not None for d in kept)else v[:0].copy())for k,v in template.items()};order=np.argsort(data['id']);data={k:v[order]for k,v in data.items()};assert len(np.unique(data['id']))==len(data['id'])
 rep={'status':'World IDs and frozen roles selected read-only for one view','tested_world_bodies':tested,'contact_evaluated':sampled,'selected':len(data['id']),'elapsed_seconds':time.monotonic()-start,'no_view_dependent_allocation_or_packing':True,'source_world_status_sha256':reader.report['status_file_sha256'],'frozen_macro_sha256':hashlib.sha256((O/'ACTUAL_CATALOG.npz').read_bytes()).hexdigest(),'limits':['Contact is lazily evaluated from fixed terrain and already frozen role/ID; it is not recomputed from selected competitors.','Origin-based culling is inherited: grains partly crossing a frame edge are not guaranteed retained. Pixel culling and fixed rank budget affect only membership. Statistical map/particle optical overlap remains unresolved.']}
 return data,rep
