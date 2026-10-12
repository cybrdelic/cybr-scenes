"""AQ new finite-film event on the final continuous physical bank/road.
No reuse of old Z stock; retains its archived ledger. Uses the already-tested
AO downhill/wet contact restriction, with its unchanged erosion approximation.
12.5 mm centres over a declared larger domain. This is an illustrative new
post-storm state, not a validated everyday dust history or convergence claim.
"""
from pathlib import Path
import time,json,hashlib,gc
from dataclasses import asdict
import numpy as np
from sample_final_surface_an import (SampleConfig,_mesh_sampler,_sample_tiles,include_section_support,select_topmost,coverage_diagnostics,GROUND,ROAD,SECTION)
from refined_film_event_an import initial_inventory,validate_balances,concentration_metrics
from flow_sediment_model_ao import FlowConfig,simulate_shoulder

BOUNDS=(-3.8,-2.7,-.4,15.6);SPACING=.0125

def apply(scene,config,out):
 import bpy
 from road_film_shader_z import apply as install_film
 start=time.monotonic();out=Path(out)
 cfg=SampleConfig(bounds_m=BOUNDS,spacing_m=SPACING,stage_label='AQ actual continuous contact after AP scene composition')
 x=BOUNDS[0]+np.arange(89)*SPACING;y=BOUNDS[2]+np.arange(1281)*SPACING;xx,yy=np.meshgrid(x,y);xy=np.stack((xx,yy),-1)
 assert xy.shape==(1281,89,2) and np.allclose([x[-1],y[-1]],[BOUNDS[1],BOUNDS[3]])
 reports=[]
 ground=_mesh_sampler(scene.objects.get(GROUND),BOUNDS,cfg,.05);zg=ground.height(xy);reports.append(ground.report);del ground;gc.collect()
 road=_mesh_sampler(scene.objects.get(ROAD),BOUNDS,cfg,.05);zr=road.height(xy);edge=road.left_edge(y);reports.append(road.report);del road;gc.collect()
 assert np.isfinite(edge).all()
 zr,road_owner,tiles=_sample_tiles(scene,xy,zr)
 section=[]
 for layer in (0,1):
  s=_mesh_sampler(scene.objects.get(SECTION),BOUNDS,cfg,.025,section_layer=layer);section.append(s.height(xy));reports.append(s.report);del s;gc.collect()
 soil,road,so,ro=include_section_support(zg,zr,road_owner,*section);coverage=coverage_diagnostics(xy,soil,road)
 if coverage['missing_xy_count']:
  (out/'AQ_FILM_SOURCE_GAPS.json').write_text(json.dumps(coverage,indent=2));raise ValueError('AQ final current surface has gaps; no invented support permitted')
 z,p,owner=select_topmost(soil,road,ro,so)
 source=out/'AQ_FINAL_SURFACE.npz';np.savez_compressed(source,x_m=x,y_m=y,actual_surface_z_m=z,pavement=p,owner=owner,road_edge_x_m=edge,surface_schema=np.array('AQ_CURRENT_PHYSICAL_V1'))
 source_sha=hashlib.sha256(source.read_bytes()).hexdigest();del zg,zr,soil,road,section,so,ro,xy,xx,yy;gc.collect()
 initial,caps,feed=initial_inventory(x,y,p,edge)
 conf=FlowConfig(rainfall_m=(.010,),event_duration_s=1200.,upstream_width_m=1.2,max_erosion_m=.001,max_event_erosion_m=.001,max_deposition_m=.001)
 print('AQ_FILM_START',{'shape':z.shape,'bounds':BOUNDS,'spacing':SPACING},flush=True)
 flow=simulate_shoulder(x,y,z,conf,initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
 ledger=validate_balances(flow,initial,caps,SPACING,SPACING);stock=flow.remaining_initial_mobile_class_thickness_m+flow.retained_deposit_by_class_m
 road=np.where(p[...,None],stock,0);soil=stock-road;assert np.array_equal(road+soil,stock)
 dest=out/'AQ_CURRENT_FILM.npz';np.savez_compressed(dest,x_m=x,y_m=y,actual_surface_z_m=z,pavement=p,owner=owner,road_edge_x_m=edge,initial_mobile_class_thickness_m=initial,remaining_initial_mobile_class_thickness_m=flow.remaining_initial_mobile_class_thickness_m,retained_deposit_by_class_m=flow.retained_deposit_by_class_m,remaining_mobile_class_thickness_m=stock,pavement_owned_class_thickness_m=road,soil_owned_class_thickness_m=soil,source_fields_sha256=np.array(source_sha),event_schema=np.array('AQ_NEW_CONTINUOUS_CONTACT_EVENT_V1'))
 data=np.ones(p.shape+(4,),np.float32);data[:,:,0]=road[:,:,0];data[:,:,1]=initial[:,:,0]*p;data[:,:,2]=p
 image=bpy.data.images.new('AQ final-contact pavement-owned film / metres',width=len(x),height=len(y),float_buffer=True,alpha=True);image.colorspace_settings.name='Non-Color';image.alpha_mode='CHANNEL_PACKED';image.pixels.foreach_set(data.ravel());image.update();image.pack()
 shader=install_film(scene,image,(x,y))
 receipt={'scope':'New illustrative finite-stock event on final actual AQ contact; not a visual acceptance or calibrated hydrology claim','bounds_m':BOUNDS,'spacing_m':SPACING,'source_sha256':source_sha,'fields_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'actual_surface_objects':reports,'native_tiles':tiles,'coverage':coverage,'flow_config':asdict(conf),'class_ledger':ledger,'model':flow.receipt,'stock_metrics':concentration_metrics(stock,p,x,y,(-3.7,-2.8,.1,15.2)),'shader':shader,'historical_Z_stock_modified':False,'old_pavement_grid_reused':False,'geometry_modified_by_film':False,'opacity_scale_modified':False,'elapsed_seconds':time.monotonic()-start,'limitations':['AO deposition is restricted to downhill wet contacts, while erosion retains its earlier symmetric wetted footprint.','Open rectangular rim and undeveloped external catchment; not a site prediction.','Centre ownership and12.5mm sampling do not resolve all aggregate relief or subcell mixed ownership.','The exact ledger includes soil/grit/chip stocks that this pavement-only film shader does not separately realize as geometry.','Virtual event height is not added to the existing scene; this thin-film candidate only visualizes the pavement matrix stock.','Linear image filtering and80um extinction remain uncalibrated; no exact rendered-volume claim.','This is a post-storm candidate. It may be too clean for a long dry dust-accumulation history.']}
 (out/'AQ_CURRENT_FILM.json').write_text(json.dumps(receipt,indent=2));print('AQ_FILM_READY',receipt['stock_metrics']['pavement_matrix'],flush=True)
 del flow,initial,caps,stock,road,soil,data;gc.collect();return receipt
