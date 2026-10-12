"""Exact radius-tier broad phase for compact packing; no candidate/order changes.

Separate coarse/grit/sand hash grids avoid scanning a coarse-radius bin full of
fine sand. Each query conservatively visits every bin within radius + tier max.
Narrow phase and strict < overlap predicate are unchanged. Source diagnostic,
not qualified until parity tests and an actual retained macro pass.
"""
import math,time
import numpy as np
import compact_catalog as c
CHECKPOINT=None
_KERNELS=None
_ORIGINAL_PACK=c._pack_records

def _init(blockers,bucket,low,cell,nx,ny,offset,head,nxt):
 for j in range(len(blockers)):
  k=bucket[j];gx=min(nx[k]-1,max(0,int(math.floor((blockers[j,0]-low[0])/cell[k]))));gy=min(ny[k]-1,max(0,int(math.floor((blockers[j,1]-low[1])/cell[k]))));idx=offset[k]+gy*nx[k]+gx;nxt[j]=head[idx];head[idx]=j

def _pack(xy,slots,serials,radii,proto_tier,blockers,lower,cells,nx,ny,offset,max_radius,oh,on,ah,an,axy,api,count,status,counts):
 for i in range(len(xy)):
  radius=radii[slots[i]];code=1
  for stage in range(2):
   hit=False
   for k in range(len(cells)):
    reach=radius+max_radius[k]+1e-12
    xlo=max(0,int(math.floor((xy[i,0]-reach-lower[0])/cells[k])));xhi=min(nx[k]-1,int(math.floor((xy[i,0]+reach-lower[0])/cells[k])))
    ylo=max(0,int(math.floor((xy[i,1]-reach-lower[1])/cells[k])));yhi=min(ny[k]-1,int(math.floor((xy[i,1]+reach-lower[1])/cells[k])))
    for yy in range(ylo,yhi+1):
     for xx in range(xlo,xhi+1):
      cell=offset[k]+yy*nx[k]+xx;j=oh[cell] if stage==0 else ah[cell]
      while j>=0:
       bx=blockers[j,0] if stage==0 else axy[j,0];by=blockers[j,1] if stage==0 else axy[j,1];br=blockers[j,2] if stage==0 else radii[api[j]];dx=xy[i,0]-bx;dy=xy[i,1]-by
       if dx*dx+dy*dy<(radius+br)**2:hit=True;break
       j=on[j] if stage==0 else an[j]
      if hit:break
     if hit:break
    if hit:break
   if hit:code=stage+2;break
  if code==1:
   k=proto_tier[slots[i]];gx=min(nx[k]-1,max(0,int(math.floor((xy[i,0]-lower[0])/cells[k]))));gy=min(ny[k]-1,max(0,int(math.floor((xy[i,1]-lower[1])/cells[k]))));idx=offset[k]+gy*nx[k]+gx
   axy[count,0]=xy[i,0];axy[count,1]=xy[i,1];api[count]=slots[i];an[count]=ah[idx];ah[idx]=count;count+=1
  serial=int(serials[i]);status[serial>>2]|=np.uint8(code<<((serial&3)*2));counts[slots[i],code-1]+=1
 return count

def pack_records(spec,serial_map,records,original_blockers,low,high,max_r,backend):
 global _KERNELS
 if spec.max_grid_bins<3:return _ORIGINAL_PACK(spec,serial_map,records,original_blockers,low,high,max_r,backend)
 status=np.zeros((serial_map.virtual_count+3)//4,np.uint8);counts=np.zeros((len(serial_map.prototypes),3),np.int64)
 if not len(records):return status,counts,dict(backend=backend,grid_bins=0,relevant_original_blockers=0)
 delta=np.maximum(np.maximum(low-original_blockers[:,:2],original_blockers[:,:2]-high),0);blockers=original_blockers[np.sum(delta*delta,axis=1)<(original_blockers[:,2]+max_r)**2]
 radii=np.array([p.radius for p in serial_map.prototypes]);largest=max(max_r,float(blockers[:,2].max())if len(blockers)else 0.)
 # Geometric tiers, not altered material/prototype labels. All radii supported.
 cut=np.array([largest/8,largest/3]);pt=np.searchsorted(cut,radii,side='right').astype('i1');bt=np.searchsorted(cut,blockers[:,2],side='right').astype('i1');mr=np.array([max(np.max(radii[pt==k],initial=0),np.max(blockers[bt==k,2],initial=0))for k in range(3)])
 lower=np.minimum(low,blockers[:,:2].min(0))if len(blockers)else low;upper=np.maximum(high,blockers[:,:2].max(0))if len(blockers)else high;span=upper-lower
 cells=np.maximum(2*mr,largest/32)
 def shapes():return np.floor(span[None,:]/cells[:,None]).astype('i8')+1
 shapes_=shapes()
 while int(np.prod(shapes_,axis=1).sum())>spec.max_grid_bins:
  k=int(np.argmax(np.prod(shapes_,axis=1)));cells[k]*=math.sqrt(2);shapes_=shapes()
 nx=shapes_[:,0];ny=shapes_[:,1];offset=np.r_[0,np.cumsum(nx*ny)[:-1]];bins=int((nx*ny).sum());oh=np.full(bins,-1,'i4');ah=oh.copy();on=np.empty(len(blockers),'i4');an=np.empty(len(records),'i4');axy=np.empty((len(records),2),'f8');api=np.empty(len(records),'u1'if len(radii)<=256 else'u2')
 if backend=='numpy':init,pack=_init,_pack
 elif backend=='numba':
  if _KERNELS is None:
   from numba import njit
   _KERNELS=njit(cache=False,fastmath=False)(_init),njit(cache=False,fastmath=False)(_pack)
  init,pack=_KERNELS
 else:raise ValueError(backend)
 init(blockers,bt,lower,cells,nx,ny,offset,oh,on);count=0;last_checkpoint=time.monotonic()
 for band,first,last in serial_map.band_ranges:
  for start in range(0,len(records),spec.chunk_size):
   block=records[start:start+spec.chunk_size];member=(block['serial']>=first)&(block['serial']<last)
   if not np.any(member):continue
   serial,ids=block['serial'][member],block['id'][member];_,xy,slots,_,_=c._decode(serial_map,serial,spec.cell_size,known_ids=ids);count=pack(xy,slots,serial,radii,pt,blockers,lower,cells,nx,ny,offset,mr,oh,on,ah,an,axy,api,count,status,counts)
   if CHECKPOINT is not None and time.monotonic()-last_checkpoint>=60:
    CHECKPOINT(status,counts,{'band':int(band),'record_chunk_start':int(start),'accepted_count':int(count),'complete':False});last_checkpoint=time.monotonic()
  if CHECKPOINT is not None:CHECKPOINT(status,counts,{'band':int(band),'band_complete':True,'accepted_count':int(count),'complete':False});last_checkpoint=time.monotonic()
  print('PACK_RADIUS_TIER_BAND_DONE',band,'accepted_total',count,flush=True)
 assert count==int(counts[:,0].sum())
 return status,counts,dict(backend=backend,grid_bins=bins,grid_shapes=shapes_.tolist(),grid_cell_sizes=cells.tolist(),relevant_original_blockers=len(blockers),broadphase='conservative three-radius-tier grid; unchanged strict squared-distance predicate')
