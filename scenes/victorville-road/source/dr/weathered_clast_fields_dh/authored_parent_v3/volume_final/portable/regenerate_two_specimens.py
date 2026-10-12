"""Two bounded, source-pinned continuous weathered-clast specimens.
Authored representation only. No weathering time, sediment flux or source edits.
Run only under the common flock and existing process-tree resource guard.
"""
from pathlib import Path
import os, json, hashlib, math, time
os.environ['OPENBLAS_NUM_THREADS']='2';os.environ['OMP_NUM_THREADS']='2'
import numpy as np
from scipy.spatial import ConvexHull, cKDTree
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'inputs'

def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def vol(v,f):
 t=(v.astype(float)-v.mean(0))[f]
 return float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)
def ico(level):
 t=(1+math.sqrt(5))/2
 v=np.array([(0,a,b*t)for a in [-1,1]for b in [-1,1]]+[(a,b*t,0)for a in [-1,1]for b in [-1,1]]+[(b*t,0,a)for a in [-1,1]for b in [-1,1]],float)
 v/=np.linalg.norm(v,axis=1)[:,None];f=ConvexHull(v).simplices
 cross=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);rev=np.einsum('ij,ij->i',cross,v[f].mean(1))<0;f[rev]=f[rev][:,[0,2,1]]
 for _ in range(level):
  vv=list(v);cache={};ff=[]
  def mid(a,b):
   key=tuple(sorted((int(a),int(b))))
   if key not in cache:
    p=(v[a]+v[b]);p/=np.linalg.norm(p);cache[key]=len(vv);vv.append(p)
   return cache[key]
  for a,b,c in f:
   ab,bc,ca=mid(a,b),mid(b,c),mid(c,a);ff.extend([(a,ab,ca),(b,bc,ab),(c,ca,bc),(ab,bc,ca)])
  v=np.asarray(vv);f=np.asarray(ff,dtype='i4')
 return v,f

def first_hit(n,pv,pf,center,scale,counts=False):
 """Ray from declared interior center; use actual triangles, never convex hull."""
 verts=(pv-center)/scale;tri=verts[pf];best=np.full(len(n),np.inf);farthest=np.full(len(n),-np.inf)
 for a,b,c in tri:
  e1=b-a;e2=c-a;normal=np.cross(e1,e2);den=n@normal;num=float(a@normal)
  ids=np.flatnonzero((abs(den)>1e-12)&(num*den>0))
  if not len(ids):continue
  t=num/den[ids];x=n[ids]*t[:,None]-a
  aa=e1@e1;ab=e1@e2;bb=e2@e2;det=aa*bb-ab*ab
  if det<1e-24:continue
  xa=x@e1;xb=x@e2;u=(bb*xa-ab*xb)/det;w=(aa*xb-ab*xa)/det
  take=(u>=-1e-9)&(w>=-1e-9)&(u+w<=1+1e-9)
  chosen=ids[take];best[chosen]=np.minimum(best[chosen],t[take]);farthest[chosen]=np.maximum(farthest[chosen],t[take])
 assert np.isfinite(best).all(),'Ray has no surface hit: chosen center is invalid'
 return best,(farthest-best)>1e-7

def make_domains(lo,hi,spacing,seed):
 rng=np.random.default_rng(seed);axes=[np.arange(a-3*spacing,b+3.01*spacing,spacing)for a,b in zip(lo,hi)]
 grid=np.stack(np.meshgrid(*axes,indexing='ij'),-1).reshape(-1,3)
 points=grid+rng.uniform(-.49,.49,grid.shape)*spacing
 # Broad domain-size spread, with sparse weak minerals rather than eroding all boundaries.
 keep=rng.random(len(points))>.16;points=points[keep]
 labels=rng.choice(3,len(points),p=[.37,.56,.07]);sus=np.array([.07,.19,1.0])[labels]*rng.uniform(.8,1.08,len(points))
 radii=spacing*np.clip(rng.lognormal(np.log(1.55),.36,len(points)),.95,2.25)
 return points,labels,np.minimum(sus,1),cKDTree(points),radii

def field(x,domains,spacing):
 points,labels,sus,tree,radii=domains;d,idx=tree.query(x,k=96,workers=2)
 # A farthest queried neighbor beyond every support radius proves no omitted contribution.
 if np.any(d[:,-1]<radii.max()):
  d,idx=tree.query(x,k=192,workers=2)
 assert np.all(d[:,-1]>radii.max()),'Incomplete compact-support neighbor set'
 q=np.minimum(d/radii[idx],1);weights=(1-q)**4*(4*q+1)
 total=weights.sum(1);assert total.min()>1e-12,'Compact domains do not cover a surface point'
 weights/=total[:,None]
 susceptibility=(sus[idx]*weights).sum(1)
 weak=(weights*(labels[idx]==2)).sum(1)
 # Interfaces exist only around the authored 7% weak-mineral population, not every cell.
 boundary=4*weak*(1-weak)
 return susceptibility,boundary,idx[:,0],weights

def normals(v,f):
 cross=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);out=np.zeros(v.shape)
 for k in range(3):np.add.at(out,f[:,k],cross)
 out/=np.linalg.norm(out,axis=1)[:,None];return out

def support(v,f,z):
 tri=v[f];points=[]
 for i,j in [(0,1),(1,2),(2,0)]:
  a=tri[:,i];b=tri[:,j];hit=(a[:,2]<z)&(b[:,2]>=z)|(b[:,2]<z)&(a[:,2]>=z)
  a=a[hit];b=b[hit];t=(z-a[:,2])/(b[:,2]-a[:,2]);points.append((a+(b-a)*t[:,None])[:,:2])
 xy=np.concatenate(points);h=ConvexHull(xy)
 # True signed-tetrahedral volume centroid, valid for nonconvex closed surface.
 tri=v.astype(float)[f];six=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2]));centroid=(six[:,None]*tri.sum(1)/4).sum(0)/six.sum()
 distances=-(h.equations[:,:2]@centroid[:2]+h.equations[:,2])
 return {'datum_z_m':z,'lowest_z_m':float(v[:,2].min()),'buried_depth_m':float(z-v[:,2].min()),'cross_section_area_m2':float(h.volume),'cross_section_is_convex_hull_for_support_only':True,'volume_centroid_m':centroid.tolist(),'centroid_projected_support_margin_m':float(distances.min()),'stable_on_declared_horizontal_fixture':bool(distances.min()>0),'settling_translation_m':[0,0,0],'whole_road_contact_validated':False}

def audit(v,f,pv,pf,center,scale,burial):
 edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);un,inv,cnt=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
 assert np.all(cnt==2) and np.all(np.bincount(inv,weights=np.where(edges[:,0]<edges[:,1],1,-1))==0)
 assert len(v)-len(un)+len(f)==2
 areas=np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1)*.5
 assert areas.min()>1e-17
 assert np.all(v.min(0)>=pv.min(0)) and np.all(v.max(0)<=pv.max(0))
 vv=vol(v,f);pvvol=vol(pv,pf);assert vv>0 and pvvol>0
 el=np.linalg.norm(v[un[:,0]]-v[un[:,1]],axis=1)
 sr=support(v,f,burial);assert sr['buried_depth_m']>0 and sr['stable_on_declared_horizontal_fixture']
 return {'vertices':len(v),'triangles':len(f),'oriented_closed_two_face_edges':True,'euler_characteristic':2,'minimum_triangle_area_m2':float(areas.min()),'true_closed_volume_m3':vv,'parent_true_closed_volume_m3':pvvol,'representation_reserve_per_body_m3':pvvol-vv,'reserve_sign_policy':'Positive replenishes representation reserve; negative is a withdrawal requiring separate feasibility review before integration','removed_fraction':1-vv/pvvol,'dimensions_m':np.ptp(v,axis=0).tolist(),'parent_dimensions_m':np.ptp(pv,axis=0).tolist(),'edge_lengths_mm_percentiles':(np.percentile(el,[0,10,50,90,100])*1000).tolist(),'within_original_axis_aligned_metric_envelope':True,'support':sr}

def authored_primary(n,scale,kind):
 def raw(nn):
  x,y,z=nn.T
  radius=.99+.085*x-.06*y+.04*z+.08*x*y-.07*x*z-.035*(3*z*z-1)+.045*(3*y*y-1)
  radius+=.047*np.exp((nn@np.array([-.70,.26,.665])-1)/.32)
  radius-=.063*np.exp((nn@np.array([.21,.80,-.56])-1)/.40)
  return radius
 # Calibrate each analytic body axis to the original aspect class without creating six box faces.
 rawradius=raw(n);axis_factors=.978/np.max(abs(n*rawradius[:,None]),axis=0)
 nn=n/axis_factors;length=np.linalg.norm(nn,axis=1);radius=raw(nn/length[:,None])/length
 if kind=='CG':
  planes=np.array([[.18,-.28,.94,.67],[-.72,-.62,.30,.77],[.92,.23,-.11,.82],[-.25,.93,.30,.79]],float);weather_width=.00022
 else:
  planes=np.array([[.80,-.22,.56,.78],[-.15,-.88,.45,.77],[-.64,.51,.58,.76],[.32,.91,.28,.89]],float);weather_width=.00065
 planes[:,:3]/=np.linalg.norm(planes[:,:3],axis=1)[:,None]
 pair=planes[:,:3]@planes[:,:3].T;assert np.min(pair)>-.90,'Near-opposed plane pair'
 L=np.linalg.norm(n*scale,axis=1);metric_radius=radius*L
 for p in planes:
  den=n@p[:3];active=den>1e-8
  cap=np.full(len(n),100.);cap[active]=p[3]*L[active]/den[active]
  # Narrow physical transition at unequal fracture/parent intersections, never bevel bands.
  metric_radius=.5*(metric_radius+cap-np.sqrt((metric_radius-cap)**2+weather_width**2))
 return metric_radius/L,{'planes_in_normalized_metric_envelope_coordinates':planes.tolist(),'edge_weathering_transition_m':weather_width,'intrinsic_body_axis_envelope_factors':axis_factors.tolist(),'old_parent_radius_used_for_new_shape':False,'minimum_pair_normal_dot':float(pair.min())}

def overlap_estimate(n,f,v,pv,pf,center,scale):
 """Separate gain/loss via common-ray intersection samples; not an exact Boolean claim."""
 source,hits=first_hit(n,pv,pf,center,scale);candidate=np.linalg.norm((v-center)/scale,axis=1)
 parent_volume=vol(pv,pf);candidate_volume=vol(v,f);rows=[]
 def row(nn,ff,src,can,label):
  intersection=vol(center+nn*np.minimum(src,can)[:,None]*scale,ff)
  return {'sampling_level':label,'sample_directions':len(nn),'intersection_volume_estimate_m3':intersection,'added_representation_volume_estimate_m3':candidate_volume-intersection,'removed_representation_volume_estimate_m3':parent_volume-intersection,'net_reserve_from_exact_closed_mesh_volumes_m3':parent_volume-candidate_volume,'net_accounting_residual_m3':(parent_volume-intersection)-(candidate_volume-intersection)-(parent_volume-candidate_volume)}
 rows.append(row(n,f,source,candidate,6));n7,f7=ico(7);assert np.array_equal(n7[:len(n)],n)
 d,ij=cKDTree(n).query(n7[len(n):],k=2,workers=2)
 # Fine directions are coarse chart-edge midpoints; lift onto the actual coarse planar triangles.
 edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1);edge_codes=np.unique(edges[:,0].astype('i8')*len(n)+edges[:,1]);sorted_ij=np.sort(ij,axis=1);assert np.isin(sorted_ij[:,0].astype('i8')*len(n)+sorted_ij[:,1],edge_codes).all()
 mids=np.linalg.norm(n[ij[:,0]]+n[ij[:,1]],axis=1)/(1/candidate[ij[:,0]]+1/candidate[ij[:,1]])
 candidate7=np.r_[candidate,mids];lifted_volume=vol(center+n7*candidate7[:,None]*scale,f7);assert abs(lifted_volume-candidate_volume)<candidate_volume*1e-6
 source7,hits7=first_hit(n7,pv,pf,center,scale);rows.append(row(n7,f7,source7,candidate7,7))
 assert all(r['added_representation_volume_estimate_m3']>=0 and r['removed_representation_volume_estimate_m3']>=0 for r in rows)
 return {'method':'Common-direction radial intersection of the actual parent triangles and the actual candidate polyhedron; two angular sampling densities. Candidate edge lifting preserves the level6 planar mesh, rather than re-evaluating the authored surface.','measurements':rows,'intersection_resolution_change_m3':abs(rows[1]['intersection_volume_estimate_m3']-rows[0]['intersection_volume_estimate_m3']),'sampling_difference_is_not_rigorous_error_bound':True,'sampled_source_nonstar_directions_level7':int(hits7.sum()),'candidate_polyhedron_edge_lift_volume_error_m3':lifted_volume-candidate_volume,'local_added_solid_is_representation_redistribution_not_physical_growth':True}

def main():
 out=Path(os.environ.get('DH_OUTPUT_DIR',str(ROOT/'output')));out.mkdir(parents=True,exist_ok=True);reports=[];pins=json.loads((ROOT/'SOURCE_PINS.json').read_text())
 for name,sha in pins['inputs'].items():assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==sha,'Pinned parent input changed'
 specs=[{'kind':'CG','index':146,'file':'prototype_146.npz','burial':.002527210690024928,'grain_spacing':.0017,'depth_range':[.000035,.00017],'boundary_depth':.00002,'rare_weak_depth':.00022,'seed':261011146},{'kind':'AS','index':39,'file':'as_prototype_039.npz','burial':.025811180133229472,'grain_spacing':.0028,'depth_range':[.000075,.00036],'boundary_depth':.00004,'rare_weak_depth':.00042,'seed':261011039}]
 for sp in specs:
  t0=time.monotonic();src=np.load(SOURCE/sp['file']);pv=src['parent_v'];pf=src['parent_f'];lo=pv.min(0).astype(float);hi=pv.max(0).astype(float);center=(lo+hi)/2;scale=(hi-lo)/2
  n,f=ico(6);radius,shape=authored_primary(n,scale,sp['kind']);primary=center+n*radius[:,None]*scale
  normal=normals(primary,f);direction=n*scale;direction/=np.linalg.norm(direction,axis=1)[:,None];incidence=np.maximum(np.einsum('ij,ij->i',normal,direction),.30)
  domains=make_domains(lo,hi,sp['grain_spacing'],sp['seed']);sus,boundary,domain,w=field(primary,domains,sp['grain_spacing']);a,b=sp['depth_range'];depth=a+(b-a)*sus+sp['rare_weak_depth']*sus**3+sp['boundary_depth']*boundary
  v=(primary-direction*(depth/incidence)[:,None]).astype('f4');assert np.all(np.einsum('ij,ij->i',v-center,direction)>0)
  pre_volume=vol(v,f);factor=min(1,(vol(pv,pf)*.9999/pre_volume)**(1/3))
  v=((v-center)*factor+center).astype('f4');primary=((primary.astype('f4')-center)*factor+center).astype('f4');depth=depth.astype('f4');depth*=factor
  check=audit(v,f,pv,pf,center,scale,sp['burial']);check['primary_no_relief_volume_m3']=vol(primary,f);check['mineral_relief_volume_difference_m3']=vol(primary,f)-vol(v,f);check['actual_normal_relief_mm_percentiles']=(np.percentile(depth,[0,10,50,90,100])*1000).tolist()
  accounting=overlap_estimate(n,f,v,pv,pf,center,scale)
  dist,idx=cKDTree(pv).query(v,k=4,workers=2);weights=1/np.maximum(dist,1e-12);weights/=weights.sum(1)[:,None]
  arrays={'v':v,'f':f,'parent_v':pv,'parent_f':pf,'attribute_parent_index':idx.astype('i4'),'attribute_parent_weight':weights,'weathering_susceptibility':sus.astype('f4'),'grain_boundary_factor':boundary.astype('f4'),'grain_domain_index':domain.astype('i4'),'grain_normal_depth_m':depth.astype('f4'),'primary_v':primary.astype('f4')}
  path=out/sp['file'];np.savez_compressed(path,**arrays)
  report={'source_kind':sp['kind'],'prototype_index':sp['index'],'source_file_sha256':hashlib.sha256((SOURCE/sp['file']).read_bytes()).hexdigest(),'parent_coordinates_sha256':digest(pv),'parent_faces_sha256':digest(pf),'candidate_coordinates_sha256':digest(v),'npz_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'parameters':sp,'primary_authorship':shape,'level6':check,'representation_overlap':accounting,'material_policy':'Current live original-parent mineral and grain_roughness attributes are interpolated using four-neighbor convex weights, including new space outside the old solid. This is an authored transfer, not a claim that old internal pigment was measured. CN graph stays unchanged.','old_silhouette_used':False,'old_parent_envelope_and_attribute_sources_retained':True,'new_and_old_transform_identical':True,'whole_road_contact_validated':False,'old_CI_exposure_baseline_only':True,'full_road_or_bank_pass_run':False,'limits':['New authored primary shape, not a geometry-only weathering simulation of the old body.','Dimensions, body lobes, fracture planes, grain field and relief are authored and uncalibrated. No physical time or sediment-transport claim.','Exact final and old closed polyhedral volumes; local gain/loss overlap is a two-density sampled measurement with its observed resolution change, not an exact Boolean or a rigorous bound.','No new mesh-convergence sweep. The two densities measure local overlap of the same actual level6 candidate mesh.','Horizontal fixture support only; actual terrain contact must be checked before integration.'],'uniform_volume_calibration_linear_factor':factor,'generation_elapsed_seconds':time.monotonic()-t0}
  (out/sp['file'].replace('.npz','.json')).write_text(json.dumps(report,indent=2)+'\n');reports.append(report);print(sp['kind'],json.dumps(report),flush=True)
 (out/'NUMERICAL_SUMMARY.json').write_text(json.dumps(reports,indent=2)+'\n')
if __name__=='__main__':main()
