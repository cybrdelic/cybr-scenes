"""Bounded, explicitly authored crossfall on the mapped north Sabado walk.

Source terrain and mapped XY/widths are unchanged. This is a presentation-level
construction estimate, not measured curb engineering or an accessibility claim.
Ordinary walk sections follow the source centerline height with 2% transverse
fall toward the street. Only mapped driveway crossings receive local ramps.
"""
from pathlib import Path
import hashlib,json,struct,sys
import numpy as np
import shapely
from shapely.geometry import shape,box
from shapely.ops import unary_union
from cybr_light import Meshlets
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/'whole-iv-vendor'),str(R/'work')]
from iv_shared_ground import SharedGround
OUT=R/'evidence/sabado-profile-v1';OUT.mkdir(exist_ok=True)
(OUT/'PROFILE_SOURCE_SNAPSHOT.py').write_bytes(Path(__file__).read_bytes())
source=R/'evidence/full-iv-path-uv-rebased/contact.clm';target=OUT/'contact.clm'
state=R/'evidence/full-iv-roofs/measured-terrain-state.npz'
source_geo=R/'evidence/full-iv-roofs/normalized.geojson'
receipt=json.loads((R/'evidence/full-iv-contact/CONTACT_RECEIPT.json').read_text())
widths={x['source_id']:x for x in receipt['widths']}
features=json.loads(source_geo.read_text())['features'];byid={f['id']:f for f in features}
walk_id='osm:way:592214516';road_id='osm:way:16262054'
walk=shape(byid[walk_id]['geometry']);road=shape(byid[road_id]['geometry'])
assert widths[walk_id]['width_m']==1.8 and widths[road_id]['width_m']==7.
roi=box(490,-305,665,-282)
walk_part=walk.intersection(roi);assert walk_part.geom_type=='LineString'
footprint=walk_part.buffer(.9,cap_style='flat',join_style='round')
driveways=[];driveway_ids=[]
for f in features:
 p=f['properties'];tags=p['source_properties']
 if p['category']=='road' and tags.get('service')=='driveway':
  line=shape(f['geometry'])
  if line.intersects(roi):
   w=widths[f['id']]['width_m'];driveways.append(line.buffer(w/2,cap_style='flat',join_style='round'));driveway_ids.append(f['id'])
assert driveways
drives=unary_union(driveways);ground=SharedGround(state)
edges={p['object'] for p in receipt['parts'] if p['name'].endswith('_closed_edges')}
DT=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
def rows(path):
 with path.open('rb') as stream:
  magic,total,packets=struct.unpack('<4sQI',stream.read(16));assert magic==b'CLM1'
  for _ in range(packets):
   nv,nt=struct.unpack('<HH',stream.read(4));v=np.frombuffer(stream.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(stream.read(nt*11),DT);q=v[t['indices']]
   a=np.zeros((nt,36),'<f4');a[:,:9]=q[:,:,:3].reshape(nt,9);a[:,9:18]=q[:,:,3:6].reshape(nt,9);a[:,18]=t['material'];a[:,19]=t['object'];a[:,20:26]=q[:,:,6:8].reshape(nt,6);a[:,26:35]=q[:,:,8:11].reshape(nt,9)
   yield a
  assert not stream.read(1)
def value_bytes(a):
 # Meshlet np.unique may merge equal +0/-0 records. No other value is changed.
 q=a.copy();q[q==0]=0
 return q.tobytes()
def smooth(t):
 t=np.clip(t,0,1);return t*t*(3-2*t)
def centerline_frame(points):
 pp=shapely.points(points);station=shapely.line_locate_point(walk_part,pp)
 q=shapely.get_coordinates(shapely.line_interpolate_point(walk_part,station))
 a=shapely.get_coordinates(shapely.line_interpolate_point(walk_part,np.maximum(station-.001,0)))
 b=shapely.get_coordinates(shapely.line_interpolate_point(walk_part,np.minimum(station+.001,walk_part.length)))
 tangent=b-a;tangent/=np.linalg.norm(tangent,axis=1)[:,None]
 outward=np.c_[-tangent[:,1],tangent[:,0]]
 street=shapely.get_coordinates(shapely.line_interpolate_point(road,shapely.line_locate_point(road,shapely.points(q))))
 outward*=np.where(np.einsum("ij,ij->i",outward,q-street)>=0,1.,-1.)[:,None]
 return q,outward
def profile(points,oldz):
 pp=shapely.points(points);selected=shapely.distance(footprint,pp)<.00012
 q,outward=centerline_frame(points)
 across=np.einsum('ij,ij->i',points-q,outward)
 ordinary=ground.height(q)+.14+.02*across
 d=shapely.distance(drives,pp);ramp=smooth(d/1.2)
 authored=(ground.height(points)+.018)*(1-ramp)+ordinary*ramp
 blend=smooth((points[:,0]-490)/10)*smooth((665-points[:,0])/10)*selected
 return oldz+(authored-oldz)*blend,blend,ramp,across
# Independent analytic cross-section checks, away from driveway transitions.
sections=[]
for x in [523.23,550.,580.,630.]:
 qq,nn=centerline_frame(np.array([[x,-292.5]]));q=qq[0];outward=nn[0]
 pts=q+np.array([-.85,0.,.85])[:,None]*outward
 z,blend,ramp,across=profile(pts,ground.height(pts)+.14)
 row={'center_m':q.tolist(),'crossfall':float((z[2]-z[0])/1.7),'minimum_clearance_m':float(np.min(z-ground.height(pts))),'ordinary':bool(np.all(ramp==1) and np.all(blend==1))}
 if row['ordinary']:assert abs(row['crossfall']-.02)<2e-5,row
 sections.append(row)
assert sum(s['ordinary'] for s in sections)>=2
invariant_before=hashlib.sha256();invariant_after=hashlib.sha256();unchanged_before=hashlib.sha256();unchanged_after=hashlib.sha256()
expected_output=hashlib.sha256()
count=0;changed_faces=0;changed_vertices=0;minimum_clearance=1e9;maximum_displacement=0.;top_count=0;edge_count=0
# XY, IDs, tint, triangle order and all fields on untouched faces are invariants.
invariant_columns=[0,1,3,4,6,7,18,19,*range(26,35)]
with Meshlets(target) as writer:
 for a in rows(source):
  before=a.copy();xyz=a[:,:9].reshape(-1,3,3)
  near=(a[:,18]==11)&np.any((xyz[:,:,0]>489)&(xyz[:,:,0]<666)&(xyz[:,:,1]>-305)&(xyz[:,:,1]<-282),axis=1)
  for index in np.flatnonzero(near):
   old=xyz[index].copy();xy=old[:,:2].astype(float);terrain=ground.height(xy)
   # Source closed-edge bottoms stay buried; only construction top vertices move.
   edge=int(a[index,19]) in edges;top=old[:,2]>terrain-.02
   newz,blend,ramp,across=profile(xy,old[:,2].astype(float));active=top&(blend>0)
   if not active.any():continue
   xyz[index,active,2]=newz[active].astype('<f4')
   delta=xyz[index,:,2].astype(float)-old[:,2]
   if not np.any(delta):continue
   clearance=xyz[index,active,2].astype(float)-terrain[active]
   assert np.min(clearance)>.001,('authored walk would penetrate retained terrain',xy.tolist(),clearance.tolist())
   minimum_clearance=min(minimum_clearance,float(clearance.min()));maximum_displacement=max(maximum_displacement,float(abs(delta).max()))
   cross=np.cross(xyz[index,1].astype(float)-xyz[index,0],xyz[index,2].astype(float)-xyz[index,0]);length=np.linalg.norm(cross)
   assert length>1e-12,('changed face degenerated',index)
   a[index,9:18]=np.tile(cross/length,3)
   if edge:
    # Retain authored physical U arclength; update V only by the physical delta.
    uv=a[index,20:26].reshape(3,2).astype(float);uv[:,1]+=delta/1.25
    uv[:,1]-=np.floor(uv[0,1]/.256)*.256
    a[index,20:26]=uv.reshape(6).astype('<f4');edge_count+=1
   else:top_count+=1
   changed_vertices+=int(np.count_nonzero(delta))
  altered=np.any(a!=before,axis=1);changed_faces+=int(altered.sum());count+=len(a)
  invariant_before.update(np.ascontiguousarray(before[:,invariant_columns]).tobytes());invariant_after.update(np.ascontiguousarray(a[:,invariant_columns]).tobytes())
  unchanged_before.update(np.ascontiguousarray(before[~altered]).tobytes());unchanged_after.update(np.ascontiguousarray(a[~altered]).tobytes())
  expected_output.update(value_bytes(a));writer.add(a)
serialized_output=hashlib.sha256()
for a in rows(target):serialized_output.update(value_bytes(a))
assert serialized_output.digest()==expected_output.digest(), "Meshlet serialization changed authored deindexed data"
assert invariant_before.digest()==invariant_after.digest() and unchanged_before.digest()==unchanged_after.digest()
assert writer.triangles==count==2383698 and changed_faces>0
record={'passed':True,'profile_author_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
 'source_terrain_sha256':hashlib.sha256(state.read_bytes()).hexdigest(),'normalized_source_geojson_sha256':hashlib.sha256(source_geo.read_bytes()).hexdigest(),
 'source_sidewalk':walk_id,'source_main_road':road_id,'driveway_source_ids':driveway_ids,'mapped_walk_width_m':1.8,
 'authored_estimates':{'crossfall':.02,'centerline_top_above_unchanged_source_ground_m':.14,'driveway_top_offset_m':.018,'driveway_transition_m':1.2,'longitudinal_blend_m':10,'x_interval_m':[490,665]},
 'triangles':count,'changed_faces':changed_faces,'changed_top_faces':top_count,'changed_closed_edge_faces':edge_count,'changed_deindexed_vertices':changed_vertices,
 'minimum_changed_top_clearance_m':minimum_clearance,'maximum_vertex_height_displacement_m':maximum_displacement,
 'xy_material_object_tint_and_order_sha256':invariant_before.hexdigest(),'untouched_faces_sha256':unchanged_before.hexdigest(),
 'source_terrain_and_xy_footprints_unchanged':True,'serialized_all_fields_sha256':serialized_output.hexdigest(),'serialization_qualification':'Every deindexed float value is exact; signed zero is canonicalized because meshlet deduplication treats +0 and -0 as equal.','analytic_cross_sections':sections,
 'limits':'Bounded authored north-sidewalk construction profile; no terrain grading, widening, source GIS edit, survey claim, or accessibility qualification. Existing triangulation approximates the local smooth driveway blend. No material or lighting changes.'}
(OUT/'PROFILE_RECEIPT.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2),flush=True)
