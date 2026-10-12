"""AT authored worked shoulder and shallow connected receiving wash.
The original approved grain recipes are unchanged. This changes broad scene
construction before the finite-inventory event, not numerical output smoothing.
Illustrative regional-inspired geometry; no survey/hydraulic calibration claim.
"""
from dataclasses import dataclass
import numpy as np
from scipy.interpolate import PchipInterpolator
from graded_shoulder_foundation_ah import smooth

@dataclass(frozen=True)
class FoundationSpec:
    crossfall:float=.030
    maximum_regrade_m:float=.120
    boundary_feather_m:float=.35
    boundary_zero_collar_m:float=.075
    contact_feather_m:float=.12
    worked_full_width_m:float=.50
    worked_transition_width_m:float=.90
    # x,y,full width,depth; one connected trunk and unequal tributaries.
    channels:tuple=(
      ((-3.62,7.7,.18,.005),(-3.88,6.48,.26,.008),(-4.13,5.31,.43,.011),(-4.67,3.55,.39,.016),(-5.51,1.67,.69,.021),(-6.10,.70,.82,.012)),
      ((-3.56,5.85,.12,.004),(-3.80,5.62,.21,.007),(-4.13,5.31,.43,.011)),
      ((-3.78,4.13,.16,.004),(-4.17,3.92,.26,.008),(-4.67,3.55,.39,.016)),
    )

def channel_incision(xy,spec=None):
    spec=spec or FoundationSpec();p=np.asarray(xy,float);q=p.reshape(-1,2);cut=np.zeros(len(q));bed=np.zeros(len(q))
    for chain in spec.channels:
        a=np.asarray(chain,float)[::-1];yi=np.clip(q[:,1],a[0,1],a[-1,1]);fx=PchipInterpolator(a[:,1],a[:,0]);cx=fx(yi);slope=fx.derivative()(yi)
        width=PchipInterpolator(a[:,1],a[:,2])(yi);depth=PchipInterpolator(a[:,1],a[:,3])(yi)
        # The world-y parameter is monotone. Near-normal distance keeps bank
        # width physical on diagonal reaches; endpoint distance gives round ends.
        signed=(q[:,0]-cx)/np.sqrt(1+slope*slope);outside=np.maximum(a[0,1]-q[:,1],0)+np.maximum(q[:,1]-a[-1,1],0);distance=np.hypot(signed,outside)
        # Unequal banks: broad receiving-side bank and narrower inside bank.
        half=width*np.where(signed<0,.58,.42);u=distance/np.maximum(half,1e-9)
        # Small bed (18% half-width), finite sloping banks, narrow weathered
        # crest/toe only. No circular deposit or repeated scallop centres.
        profile=np.clip((1-u)/.82,0,1);crest=smooth((1-u)/.10);toe=smooth((u-.13)/.08)
        profile=np.where(u>.90,profile*crest,profile);profile=np.where(u<.21,1-(1-profile)*toe,profile)
        cut=np.maximum(cut,depth*profile);bed=np.maximum(bed,(u<.18).astype(float))
    return cut.reshape(p.shape[:-1]),bed.reshape(p.shape[:-1])

def _fit(x,y,z):
    center=float(np.mean(y));scale=max(float(np.ptp(y)),1.)
    inner=np.polyfit((y-center)/scale,np.median(z[:,-3:],axis=1),2)
    outer=np.polyfit((y-center)/scale,np.median(z[:,:3],axis=1),2)
    return center,scale,inner,outer

def evaluate_mesh_target(xy,actual_vertex_z,x,y,sampled_source_z,spec=None):
    spec=spec or FoundationSpec();p=np.asarray(xy,float);z=np.asarray(actual_vertex_z,float);x=np.asarray(x,float);y=np.asarray(y,float);source=np.asarray(sampled_source_z,float)
    if source.shape!=(len(y),len(x)) or not np.isfinite(source).all():raise ValueError('Actual sampled source required')
    center,scale,fi,fo=_fit(x,y,source);v=(p[:,1]-center)/scale;inner=np.polyval(fi,v);outer=np.polyval(fo,v);distance=p[:,0]-x[0];fraction=distance/(x[-1]-x[0]);plane=outer+(inner-outer)*fraction
    road_distance=x[-1]-p[:,0];worked=1-smooth((road_distance-spec.worked_full_width_m)/spec.worked_transition_width_m)
    # The full planar regrade is confined to the worked inner strip. Existing
    # outer relief supplies the receiving landscape rather than being erased.
    base=z*(1-worked)+plane*worked;cut,_=channel_incision(p,spec);floor=outer+.001+.002*distance
    target=np.maximum(base-cut,np.minimum(base,floor))
    other=np.minimum.reduce((p[:,0]-x[0],p[:,1]-y[0],y[-1]-p[:,1]));gate=smooth((other-spec.boundary_zero_collar_m)/spec.boundary_feather_m)*smooth((x[-1]-p[:,0]-spec.boundary_zero_collar_m)/spec.contact_feather_m)
    delta=(target-z)*gate
    if not np.isfinite(delta).all() or np.max(np.abs(delta))>spec.maximum_regrade_m:raise ValueError('AT broad regrade exceeds finite metric bound')
    return delta,dict(role='Worked inner shoulder blended into existing outer relief, connected shallow asymmetric receiving wash',evaluation='Direct at actual mesh vertices before unchanged sediment event',datum_profile_coefficients=fi.tolist(),outer_datum_coefficients=fo.tolist(),datum_y_center_m=center,datum_y_scale_m=scale,worked_full_width_m=spec.worked_full_width_m,worked_transition_width_m=spec.worked_transition_width_m,channels=[[list(v) for v in c] for c in spec.channels],maximum_channel_depth_m=max(v[3] for c in spec.channels for v in c),boundary_zero_collar_m=spec.boundary_zero_collar_m,contact_feather_m=spec.contact_feather_m,vertex_delta_min_max_m=[float(delta.min()),float(delta.max())],outer_existing_relief_retained=True,no_post_transport_smoothing=True,conservation_claim=False,limits='Authored foundation, not measured site terrain or validated hydraulic prediction')

def construct(x,y,actual_z,spec=None):
    xx,yy=np.meshgrid(x,y);delta,report=evaluate_mesh_target(np.c_[xx.ravel(),yy.ravel()],np.asarray(actual_z).ravel(),x,y,actual_z,spec);return np.asarray(actual_z)+delta.reshape(xx.shape),report
