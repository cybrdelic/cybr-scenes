"""AI surface representation from AH finite sediment inventories, SI units.
No geometric terrain/noise field, photos, or added solver mass. The field
mapping is a declared visual proxy, not a calibrated sediment optical model.
"""
from dataclasses import dataclass,asdict
import numpy as np
from visible_shoulder_flow_ad import sample_field
from transported_grain_exposure import retained_top_proxy

@dataclass(frozen=True)
class SurfaceSpec:
    include_net_eroded_retained:bool=False
    include_substrate_history:bool=False
    fine_optical_depth_m:float=.00035
    lag_active_depth_m:float=.0010
    base_coarse_fraction:float=.08
    coarse_fraction_for_full_lag:float=.30
    maximum_lift_fraction_of_buried_depth:float=.55

def surface_fields(xy,fields,spec=None):
    spec=spec or SurfaceSpec();x=fields['x_m'];y=fields['y_m'];xy=np.asarray(xy,float)
    dep=sample_field(fields['retained_deposit_by_class_m'],xy,x,y)
    net=sample_field(fields['sediment_delta_m'],xy,x,y)
    mix=sample_field(fields['surface_fraction'],xy,x,y)
    scour=np.maximum(-net,0)
    # The mobile coarse fraction increases when fines leave the donor. Bound
    # lag visibility by actual erosion depth rather than arbitrary island masks.
    enrichment=np.clip((mix[:,2]-spec.base_coarse_fraction)/(spec.coarse_fraction_for_full_lag-spec.base_coarse_fraction),0,1)
    lag=enrichment*(-np.expm1(-scour/spec.lag_active_depth_m))
    # Fine fraction retained in the top, not gross cumulative through-flow.
    top,_,_=retained_top_proxy(dep)
    fine_depth=top[:,0] if spec.include_net_eroded_retained else np.minimum(dep[:,0],np.maximum(net,0))
    coat=-np.expm1(-fine_depth/spec.fine_optical_depth_m)
    historical_matrix=np.zeros(len(xy));compaction=np.zeros(len(xy));remaining_skin=np.zeros(len(xy))
    if spec.include_substrate_history:
        initial=sample_field(fields['initial_mobile_class_thickness_m'],xy,x,y)
        bed=sample_field(fields['remaining_initial_mobile_class_thickness_m'],xy,x,y)
        true_scour=np.maximum((initial-bed).sum(-1),0)
        prior=sample_field(fields['historical_prior_fine_cover_m'],xy,x,y)
        remaining_skin=np.maximum(prior-true_scour,0)
        coat=1-(1-coat)*np.exp(-remaining_skin/spec.fine_optical_depth_m)
        armor=sample_field(fields['historical_armor_exposure'],xy,x,y)
        lag=np.maximum(lag,.55*armor)*(1-coat)
        base=np.divide(bed,bed.sum(-1,keepdims=True),out=np.zeros_like(bed),where=bed.sum(-1,keepdims=True)>0)
        # Where the initial inventory guard has zero mobile stock, the authored
        # parent mixture is still a material property, not new mobile mass.
        fallback=sample_field(fields['initial_class_fractions'],xy,x,y)
        base=np.where((bed.sum(-1)>0)[:,None],base,fallback)
        historical_matrix=np.clip((base[:,0]-.68)/.16,0,1)
        compaction=sample_field(fields['historical_compaction'],xy,x,y)*np.exp(-true_scour/.020)
    return dict(lag=lag,fine_coat=coat,net_m=net,scour_m=scour,retained_m=dep,top_proxy_m=top,mixture=mix,historical_matrix=historical_matrix,historical_compaction=compaction,remaining_prior_skin_m=remaining_skin)

def retained_grain_lift(fields,local_minz_m,spec=None):
    spec=spec or SurfaceSpec();buried=np.maximum(-np.asarray(local_minz_m,float),0)
    # Earthwork/bed movement already happened in AH. Retain a fraction of each
    # finite grain's embedded body where donor fines departed; no grain scaling.
    deposit_burial=(1-fields['fine_coat']) if spec.include_net_eroded_retained else 1.
    return np.minimum(fields['scour_m'],buried*spec.maximum_lift_fraction_of_buried_depth)*fields['lag']*deposit_burial

def summary(fields,x,y,spec=None):
    spec=spec or SurfaceSpec();xx,yy=np.meshgrid(x,y);v=surface_fields(np.c_[xx.ravel(),yy.ravel()],fields,spec)
    area=float((x[1]-x[0])*(y[1]-y[0]));return dict(spec=asdict(spec),lag_above_half_area_m2=float((v['lag']>.5).sum()*area),fine_coat_above_half_area_m2=float((v['fine_coat']>.5).sum()*area),retained_bulk_by_class_m3=(fields['retained_deposit_by_class_m'].sum((0,1))*area).tolist(),maximum_fine_optical_depth_m=float((v['top_proxy_m'][:,0] if spec.include_net_eroded_retained else np.minimum(v['retained_m'][:,0],np.maximum(v['net_m'],0))).max()),limits='Nonvalidated surface optics/retention proxy. Top fractions are solver mixtures without vertical stratigraphy; no new sediment is created.')
