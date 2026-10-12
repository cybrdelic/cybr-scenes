"""CI historical gravel stays beneath retained overburden, never rides atop it.
Only existing CH body's Z datum changes. Exact IDs, XY, shape and solid budget
remain fixed; all18–60mm gravel here is pre-existing, none is event-transported.
"""
from pathlib import Path
import time,json,hashlib,gc
import numpy as np
import bpy
from context_mesh_refine_ab import _read,SourceSampler
from visible_shoulder_flow_ad import sample_field
from weather_metric_gravel_ch import bank
from gravel_exposure_estimate_ci import estimate_exposure
NAME='CG finite 18–60 mm historical gravel pockets'

def apply(scene,cfg,out):
 start=time.monotonic();assert cfg['revision']==1
 def pin(p,wanted):assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==wanted
 pin(cfg['terrain_payload'],cfg['terrain_sha256']);pin(cfg['historical_fields'],cfg['historical_fields_sha256'])
 ob=scene.objects[NAME];before=_read(ob.data.vertices,'co',3);pi=_read(ob.data.attributes['prototype'].data,'value',1,np.int32);yaw=_read(ob.data.attributes['yaw'].data,'vector',3);assert np.max(abs(yaw[:,:2]))==0 and np.array_equal(np.asarray(ob.matrix_world),np.eye(4))
 identity=hashlib.sha256(before[:,:2].tobytes()+pi.tobytes()+yaw.tobytes()).hexdigest();p=np.load(cfg['terrain_payload']);co=p['source_coordinates'].astype(float);co[:,2]+=p['delta'];tri=p['tri'];sampler=SourceSampler(co,tri,np.arange(len(tri)),max_triangles=500000,max_bin_entries=4000000);ids,weights=sampler.weights(before[:,:2]);t=tri[ids];ground=(co[t,2]*weights).sum(1);ce_net=(p['sediment'][t]*weights).sum(1);v=co[t];normal=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]);gradient=-normal[:,:2]/normal[:,2,None];assert np.isfinite(gradient).all()
 h=np.load(cfg['historical_fields']);assert np.max(abs(h['sediment_delta_m']-(h['retained_deposit_by_class_m'].sum(2)-(h['initial_mobile_class_thickness_m']-h['remaining_initial_mobile_class_thickness_m']).sum(2))))<1e-12
 q=before[:,:2];inside=(q[:,0]>=h['x_m'][0])&(q[:,0]<=h['x_m'][-1])&(q[:,1]>=h['y_m'][0])&(q[:,1]<=h['y_m'][-1]);ah_net=np.zeros(len(q));ah_net[inside]=sample_field(h['sediment_delta_m'],q[inside],h['x_m'],h['y_m'])
 # A later erosion pass first consumes retained cover; summing the positive
 # deposits of both events would double-count the cover that was then removed.
 prior_cover=np.maximum(ah_net,0);cover=np.maximum(prior_cover+ce_net,0)
 fixed_support=ground-cover;after=before.copy();after[:,2]=(before[:,2].astype(float)-cover).astype('f4')
 preserved_offset=before[:,2].astype(float)-ground;offset_after=after[:,2].astype(float)-fixed_support;err=float(np.max(abs(preserved_offset-offset_after)));assert err<2e-8
 assert np.all(after[:,2]<=before[:,2]+1e-9);ob.data.vertices.foreach_set('co',after.ravel());ob.data.update();assert hashlib.sha256(_read(ob.data.vertices,'co',3)[:,:2].tobytes()+_read(ob.data.attributes['prototype'].data,'value',1,np.int32).tobytes()+_read(ob.data.attributes['yaw'].data,'vector',3).tobytes()).hexdigest()==identity
 # The origin's actual terrain triangle supplies a local-plane approximation.
 # Exposed area/volume are optical/geometric estimates, NOT the solid ledger.
 records=bank(cfg['fractured_prototypes']);exposure=estimate_exposure(records,pi,yaw[:,2],before[:,2],after[:,2],ground,gradient,resolution=32,batch_size=512)
 assert np.all(exposure['after']['exposed_footprint_area_m2']<=exposure['before']['exposed_footprint_area_m2']+1e-15)
 assert np.all(exposure['after']['exposed_volume_m3']<=exposure['before']['exposed_volume_m3']+1e-15)
 ledger=np.load(Path(out)/'CH_WEATHERED_STOCK_PARTITION.npz');assert np.isclose(sum(records[int(k)]['volume']for k in pi),float(ledger['explicit_new_solid'].sum()),rtol=1e-10)
 report=dict(revision='CI',bodies=len(before),preexisting_historical_gravel=len(before),event_transported_gravel=0,exact_identity_xy_yaw_sha256=identity,geometry_material_scale_and_xy_unchanged=True,body_solid_inventory_m3=float(ledger['explicit_new_solid'].sum()),body_solid_inventory_changed=False,retained_fine_and_chip_ledger_changed=False,terrain_geometry_and_material_changed=False,support_formula='Current terrain minus max(max(AH net retained cover,0)+CE signed redistribution,0). CE erosion consumes prior cover before exposing the older gravel datum.',earthwork_assumption='Authored CE grading carries the declared historical gravel/cover together onto its new foundation. This reconstructs a static support horizon, not a verified old hydraulic trajectory.',outside_AH_policy='No invented earlier cover outside the retained finite AH domain; only CE signed redistribution contributes.',maximum_overburden_m=float(cover.max()),bodies_lowered_over_0p1mm=int((cover>.0001).sum()),bodies_lowered_over_1mm=int((cover>.001).sum()),maximum_support_offset_float32_error_m=err,exposure=exposure['aggregate'],exposure_method=exposure['method'],exposure_limits=exposure['limitations'],solid_ledger={k:v for k,v in exposure['solid_ledger'].items()if not isinstance(v,np.ndarray)},quadrature={k:v for k,v in exposure['quadrature_diagnostic'].items()if not isinstance(v,np.ndarray)},predeposition_embedding='The existing CH embed offset is held unchanged to isolate datum correction. It remains an authored historical-placement offset; no rigid-body settling is solved.',elapsed_seconds=time.monotonic()-start)
 arrays=dict(before=before,after=after,prototype=pi,yaw=yaw,actual_ground_height=ground,actual_ground_gradient=gradient,actual_ground_triangle_id=ids,ah_net=ah_net,ce_net=ce_net,retained_cover=cover,fixed_support_z=fixed_support)
 for section in ('solid_ledger','quadrature_diagnostic'):
  for name,value in exposure[section].items():
   if isinstance(value,np.ndarray):arrays[section+'_'+name]=value
 for phase in ('before','after'):
  for name,value in exposure[phase].items():arrays[phase+'_'+name]=value
 np.savez_compressed(Path(out)/'CI_FIXED_SUPPORT_AND_EXPOSURE.npz',**arrays);(Path(out)/'FIXED_GRAVEL_SUPPORT_CI.json').write_text(json.dumps(report,indent=2)+'\n');print('CI_FIXED_SUPPORT',json.dumps(report),flush=True)
 p.close();h.close();ledger.close();del sampler,co,records,exposure;gc.collect();return report
