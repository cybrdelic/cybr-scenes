"""AF authored earthwork before weathering: crossfall and a connected shallow wash.
This constructs a scene's broad shape, not a conservation claim or site survey.
The subsequent finite-stock sediment solve is a separate numerical operation.
No periodic rut/tread waveform, Gaussian pile, or output smoothing is applied.
"""
from dataclasses import dataclass
import numpy as np

def smooth(x):
    q=np.clip(np.asarray(x),0,1);return q*q*(3-2*q)

@dataclass(frozen=True)
class FoundationSpec:
    crossfall:float=.030
    maximum_regrade_m:float=.120
    boundary_feather_m:float=.35
    boundary_zero_collar_m:float=.075
    contact_feather_m:float=.12
    # Shared endpoints form one outward draining trunk and two short tributaries.
    # (worldX,worldY,full top width,incision depth), in metres.
    channels:tuple=(
      ((-3.62,7.7,.14,.012),(-3.86,6.4,.18,.023),(-4.18,5.15,.23,.035),(-4.70,3.35,.31,.047),(-5.54,1.60,.39,.055),(-6.10,.70,.44,.056)),
      ((-3.56,5.85,.10,.008),(-3.82,5.51,.13,.016),(-4.18,5.15,.23,.035)),
      ((-3.78,4.13,.11,.010),(-4.16,3.82,.16,.021),(-4.70,3.35,.31,.047)),
    )

def channel_incision(xy,spec=None):
    spec=spec or FoundationSpec();p=np.asarray(xy,float);q=p.reshape(-1,2);cut=np.zeros(len(q));bed=np.zeros(len(q))
    for chain in spec.channels:
        for va,vb in zip(chain[:-1],chain[1:]):
            a,b=np.array(va[:2]),np.array(vb[:2]);d=b-a;length2=np.dot(d,d);t=np.clip((q-a)@d/length2,0,1);center=a+t[:,None]*d
            width=va[2]+t*(vb[2]-va[2]);depth=va[3]+t*(vb[3]-va[3]);dist=np.linalg.norm(q-center,axis=1);side=((q[:,0]-center[:,0])*(-d[1])+(q[:,1]-center[:,1])*d[0])>=0
            # Unequal but finite planar banks, with narrow rounded weathering
            # transitions at crest/toe. This creates a connected trough, no berm.
            signed=((q[:,0]-center[:,0])*(-d[1])+(q[:,1]-center[:,1])*d[0])/np.sqrt(length2)
            # Continuous lateral width and round caps; no hard head-side jump.
            blend=smooth((signed/np.maximum(width*.12,1e-9)+1)*.5)
            half=.5*width*(.76+.24*blend);u=dist/half
            profile=np.clip((1-u)/.70,0,1)
            crest=smooth((1-u)/.08);toe=smooth((u-.20)/.10)
            profile=np.where(u>.92,profile*crest,profile)
            profile=np.where(u<.30,1-(1-profile)*toe,profile)
            cut=np.maximum(cut,depth*profile);bed=np.maximum(bed,(u<.30).astype(float))
    return cut.reshape(p.shape[:-1]),bed.reshape(p.shape[:-1])

def construct(x,y,actual_z,spec=None):
    spec=spec or FoundationSpec();x=np.asarray(x,float);y=np.asarray(y,float);z=np.asarray(actual_z,float)
    if z.shape!=(len(y),len(x)) or not np.isfinite(z).all():raise ValueError('Actual sampled terrain is required')
    if not .015<=spec.crossfall<=.045 or spec.maximum_regrade_m>.15:raise ValueError('Unqualified broad grading range')
    xx,yy=np.meshgrid(x,y);center=float(np.mean(y));scale=max(float(np.ptp(y)),1.)
    # Datum is fitted to the existing compacted road-contact strip. The fit is
    # an authored grading profile, not a filter applied after sediment transport.
    datum=np.median(z[:,-3:],axis=1);fit=np.polyfit((y-center)/scale,datum,2)
    grade=np.polyval(fit,(yy-center)/scale)
    outer_fit=np.polyfit((y-center)/scale,np.median(z[:,:3],axis=1),2)
    outer_datum=np.polyval(outer_fit,(yy-center)/scale)
    distance=xx-x[0];fraction=distance/(x[-1]-x[0])
    # The receiving outer terrain constrains broad grading. A constant 3%
    # crossfall was rejected: it excavated below the actual locked outlet.
    target=outer_datum+(grade-outer_datum)*fraction
    cut,bed=channel_incision(np.stack((xx,yy),-1),spec)
    receiving_floor=outer_datum+.001+.002*distance
    target=np.maximum(target-cut,receiving_floor)
    edge=np.minimum.reduce((xx-x[0],x[-1]-xx,yy-y[0],y[-1]-yy));gate=smooth((edge-spec.boundary_zero_collar_m)/spec.boundary_feather_m)
    requested=(target-z)*gate
    if np.max(np.abs(requested))>spec.maximum_regrade_m:raise ValueError('Broad reconstruction exceeds explicit metric bound')
    result=z+requested
    return result,dict(role='Authored broad road grading before finite sediment weathering',datum_profile_coefficients=fit.tolist(),datum_y_center_m=center,datum_y_scale_m=scale,crossfall_requested=spec.crossfall,actual_crossfall_range=[float(((grade-outer_datum)/(x[-1]-x[0])).min()),float(((grade-outer_datum)/(x[-1]-x[0])).max())],outer_datum_coefficients=outer_fit.tolist(),outlet_policy='Incision capped above fitted actual receiving terrain plus 1 mm and 0.2% outward grade',channels=[[list(p) for p in chain] for chain in spec.channels],maximum_channel_depth_m=max(p[3] for chain in spec.channels for p in chain),geometry_delta_min_max_m=[float(requested.min()),float(requested.max())],source_shape=z.shape,no_periodic_displacement=True,no_post_transport_smoothing=True,conservation_claim=False,limits='Illustrative shallow runoff/road-earthwork arrangement, not measured Victorville topography')


def evaluate_mesh_target(xy,actual_vertex_z,x,y,sampled_source_z,spec=None):
    """Evaluate authored grading directly at vertices, before transport sampling.
    The zero collar covers the 7cm maximum triangle edge without an extra
    model-grid interpolation collar. True road contact lies outside this domain.
    """
    spec=spec or FoundationSpec();p=np.asarray(xy);z=np.asarray(actual_vertex_z)
    _,report=construct(x,y,sampled_source_z,spec)
    center=report['datum_y_center_m'];scale=report['datum_y_scale_m'];v=(p[:,1]-center)/scale
    inner=np.polyval(report['datum_profile_coefficients'],v);outer=np.polyval(report['outer_datum_coefficients'],v)
    distance=p[:,0]-x[0];fraction=distance/(x[-1]-x[0]);cut,_=channel_incision(p,spec)
    target=np.maximum(outer+(inner-outer)*fraction-cut,outer+.001+.002*distance)
    other=np.minimum.reduce((p[:,0]-x[0],p[:,1]-y[0],y[-1]-p[:,1]))
    gate=smooth((other-spec.boundary_zero_collar_m)/spec.boundary_feather_m)*smooth((x[-1]-p[:,0]-spec.boundary_zero_collar_m)/spec.contact_feather_m)
    delta=(target-z)*gate
    if np.max(np.abs(delta))>spec.maximum_regrade_m:raise ValueError('Authored mesh regrade exceeds bound')
    report.update(evaluation='Direct at actual mesh vertices; AE input resampled from these actual triangles',boundary_zero_collar_m=spec.boundary_zero_collar_m,contact_feather_m=spec.contact_feather_m,vertex_delta_min_max_m=[float(delta.min()),float(delta.max())])
    return delta,report
