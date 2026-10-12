"""AK: bounded historical substrate composition on the existing AH foundation.

This is explicitly authored, non-surveyed geomorphic chronology, not another
storm solve, conserved deposit, calibrated physics, new terrain height or color
noise. An older graded shoulder exposes heterogeneous parent material; three
unequal, connected old sheetflow reaches winnowed grit and left thin sandy
receiving cover. Final grading has erased most of their relief. The three newest
AH storms are deliberately NOT inputs to this model.

``substrate_fields(xy, ah_fields)`` is pure NumPy and returns SI metres plus
unitless fractions. ``prior_fine_cover_m`` is a pre-existing active surface skin
ALREADY WITHIN the ground, not a vertical displacement or inventory to add.
Apply it only to burial/exposure and surface representation of existing approved
prototypes. Preserve grain dimensions, material recipes and actual mesh contact.
"""
from dataclasses import dataclass, asdict
import numpy as np

UNIT_NAMES = ('armor_grit', 'compacted_fines', 'thin_sandy_cover')


@dataclass(frozen=True)
class HistorySpec:
    # Single nonperiodic grading-reach boundary: (world Y, outer blade reach X).
    # Unequal reaches describe one historical operation, not repeated tire ruts.
    grading_reach: tuple = ((-.6, -3.93), (.05, -3.76), (.70, -4.30),
                            (1.8, -4.63), (3.05, -4.29),
                            (4.4, -4.47), (8.2, -4.13))
    grading_transition_m: float = .46
    boundary_feather_m: float = .12
    maximum_prior_cover_m: float = .0025
    # (X,Y,half width m,settling opportunity). Tributaries terminate at exact
    # trunk nodes. Strong sand occurs on only selected widening reaches.
    # These old swales are illustrative signatures, not claims of extant rills.
    drainage_reaches: tuple = (
        ((-3.43,3.30,.080,.00),(-3.81,2.90,.160,.08),
         (-4.10,2.22,.240,.13),(-4.50,1.72,.390,.55),
         (-4.80,1.15,.570,.90),(-5.30,.60,.480,.40),
         (-6.02,.15,.320,.08)),
        ((-3.35,1.15,.070,.00),(-3.60,.83,.140,.12),
         (-4.03,.61,.340,.90),(-4.57,.38,.520,.98),
         (-5.00,.39,.420,.50),(-5.30,.60,.480,.40)),
        ((-3.46,2.14,.065,.00),(-3.60,1.92,.110,.08),
         (-3.96,1.70,.230,.36),(-4.50,1.72,.390,.55)),
    )


def _smooth(q):
    q = np.clip(np.asarray(q, dtype=float), 0., 1.)
    return q*q*(3.-2.*q)


def _inputs(fields):
    x = np.asarray(fields['x_m'], dtype=float)
    y = np.asarray(fields['y_m'], dtype=float)
    z = np.asarray(fields['foundation_z_m'], dtype=float)
    if (x.ndim != 1 or y.ndim != 1 or min(len(x),len(y)) < 3 or
            z.shape != (len(y),len(x)) or not np.isfinite(z).all() or
            not np.isfinite(x).all() or not np.isfinite(y).all() or
            np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0)):
        raise ValueError('Finite increasing AH axes and actual foundation grid required')
    return x, y, z


def _sample(a, p, x, y):
    """Bilinear scalar sampling, clipped only after caller's domain test."""
    i = np.clip(np.searchsorted(x,p[:,0])-1,0,len(x)-2)
    j = np.clip(np.searchsorted(y,p[:,1])-1,0,len(y)-2)
    u = np.clip((p[:,0]-x[i])/(x[i+1]-x[i]),0,1)
    v = np.clip((p[:,1]-y[j])/(y[j+1]-y[j]),0,1)
    return ((1-u)*a[j,i]+u*a[j,i+1])*(1-v) + ((1-u)*a[j+1,i]+u*a[j+1,i+1])*v


def _validate(spec):
    if (not np.isfinite(spec.maximum_prior_cover_m) or
            not 0 < spec.maximum_prior_cover_m <= .003 or
            not .04 <= spec.boundary_feather_m <= .5 or
            not .15 <= spec.grading_transition_m <= 1.):
        raise ValueError('History must retain millimetric skin and metric feather bounds')
    r = np.asarray(spec.grading_reach,float)
    if (r.ndim != 2 or r.shape[1] != 2 or len(r) < 2 or
            not np.isfinite(r).all() or np.any(np.diff(r[:,0]) <= 0)):
        raise ValueError('Grading reach must be finite and ordered in world Y')
    if not spec.drainage_reaches:
        raise ValueError('Explicit connected drainage chronology is required')
    trunk = np.asarray(spec.drainage_reaches[0],float)
    for k,reach in enumerate(spec.drainage_reaches):
        a = np.asarray(reach,float)
        if (a.ndim != 2 or a.shape[1] != 4 or len(a) < 2 or
                not np.isfinite(a).all() or np.any(a[:,2] < .04) or
                np.any(a[:,2] > 1.) or np.any(a[:,3] < 0) or
                np.any(a[:,3] > 1) or
                np.any(np.linalg.norm(np.diff(a[:,:2],axis=0),axis=1) < 1e-8)):
            raise ValueError('Finite metric drainage geometry and bounded settling required')
        if k and not np.any(np.linalg.norm(trunk[:,:2]-a[-1,:2],axis=1) < 1e-9):
            raise ValueError('Every old tributary must terminate at a trunk node')


def _grading(p, spec):
    r = np.asarray(spec.grading_reach,float)
    i = np.clip(np.searchsorted(r[:,0],p[:,1])-1,0,len(r)-2)
    t = _smooth((p[:,1]-r[i,0])/(r[i+1,0]-r[i,0]))
    edge = (1-t)*r[i,1]+t*r[i+1,1]
    return _smooth(.5+(p[:,0]-edge)/spec.grading_transition_m)


def _drainage(p, gx, gy, spec):
    """Union of unequal reaches; finite smooth banks, no islands/no RNG.

    Each segment carries its interpolated width and settling history.
    A channel core is not painted a fixed material: expansion, along-path slope
    and lateral velocity opportunity jointly select winnowing versus cover.
    """
    wash = np.zeros(len(p)); scour = wash.copy(); sand = wash.copy()
    for reach in spec.drainage_reaches:
        a = np.asarray(reach,float)
        for va,vb in zip(a[:-1],a[1:]):
            d = vb[:2]-va[:2]; length = float(np.linalg.norm(d))
            t = np.clip(((p[:,0]-va[0])*d[0]+(p[:,1]-va[1])*d[1])/(length*length),0,1)
            c = va[:2]+t[:,None]*d
            width = va[2]+t*(vb[2]-va[2])
            q = np.linalg.norm(p-c,axis=1)/width
            envelope = _smooth((1-q)/np.clip(.07/width,.13,.75))
            down = -(gx*d[0]+gy*d[1])/length
            # Actual foundation suppresses steep receivers and locally uphill
            # routes; it does not create a depression or relocate the ground.
            downhill = _smooth((down+.002)/.010)
            rapid = _smooth((down-.012)/.030)
            settling = (va[3]+t*(vb[3]-va[3]))*(1-.55*rapid)*(.70+.30*downhill)
            core = _smooth((.72-q)/.50)
            exposure = envelope*(.38+.62*core)*(1-.78*settling)*downhill
            cover = envelope*settling*(.72+.28*_smooth(q/.75))
            # Max unions of continuous per-segment effects avoid a discontinuous
            # nearest-segment attribute switch at unequal-width bends.
            wash = np.maximum(wash,envelope)
            scour = np.maximum(scour,exposure)
            sand = np.maximum(sand,cover)
    return wash,scour,sand


def substrate_fields(xy, fields, spec=None):
    """Return historical fractions at (...,2) world-metre coordinates.

    Outside the supplied AH foundation domain all outputs are exactly zero.
    Unit weights sum to the boundary strength, and to one in the interior.
    When mapping initial inventories, blend the unassigned boundary remainder
    with the original baseline composition instead of renormalizing it.
    World coordinates and full AH sampling make chunk/crop query invariant.
    Recent storm fields, seed/noise textures and external files are never read.
    """
    spec=spec or HistorySpec(); _validate(spec)
    x,y,z = _inputs(fields)
    p = np.asarray(xy,dtype=float)
    if p.shape[-1:] != (2,) or not np.isfinite(p).all():
        raise ValueError('Finite points (...,2) required')
    shape=p.shape[:-1]; p=p.reshape(-1,2)
    gy,gx=np.gradient(z,y,x,edge_order=2)
    gpx=_sample(gx,p,x,y); gpy=_sample(gy,p,x,y)
    edge=np.minimum.reduce((p[:,0]-x[0],x[-1]-p[:,0],p[:,1]-y[0],y[-1]-p[:,1]))
    strength=_smooth(edge/spec.boundary_feather_m)
    grade=_grading(p,spec)
    wash,scour,sand=_drainage(p,gpx,gpy,spec)
    # A unit is a mixture, never a hard painted polygon. Roadward graded fines
    # become interrupted by old wash; away from grading, armor is the parent.
    sandy=_smooth((sand-.12)/.76)*.94
    compact=grade*(1-.78*scour)*(1-sandy)
    armor=np.clip(1-sandy-compact,0,1)
    weights=np.stack((armor,compact,sandy),axis=-1)
    # Fine matrix in exposed armor is only tens of microns; compacted fines are
    # a thin pre-existing crust, not a 1 mm blanket. Low-mm sand is local.
    compact_depth=.00008+.00013*grade
    sand_depth=.00045+.00205*np.power(np.clip(sand,0,1),1.6)
    cover=armor*.000025+compact*compact_depth+sandy*sand_depth
    cover=np.minimum(cover,spec.maximum_prior_cover_m)*strength
    exposure=np.clip(.72*armor+.13*compact+.07*sandy+.27*scour*(1-sandy),0,1)*strength
    compaction=np.clip(.30*armor+.91*compact+.22*sandy+.10*grade*(1-sandy),0,1)*strength
    result=dict(prior_fine_cover_m=cover,armor_exposure=exposure,compaction=compaction,
                unit_weights=weights*strength[:,None],historical_wash=wash*strength,
                historical_winnowing=scour*strength,historical_sand_opportunity=sand*strength,
                grading_strength=grade*strength,domain_strength=strength,
                foundation_slope=np.hypot(gpx,gpy)*strength)
    return {k:v.reshape(shape+v.shape[1:]) for k,v in result.items()}


def summary(fields, spec=None):
    """Area quadrature uses actual axis rectangle cells, never endpoint stock."""
    spec=spec or HistorySpec();x,y,z=_inputs(fields)
    xx,yy=np.meshgrid((x[:-1]+x[1:])*.5,(y[:-1]+y[1:])*.5)
    xy=np.stack((xx,yy),axis=-1);v=substrate_fields(xy,fields,spec)
    area=np.diff(y)[:,None]*np.diff(x)[None,:]
    near=(xx>=-4.8)&(xx<=-3.6)&(yy>=0)&(yy<=4)
    def coverage(mask):
        a=area*mask
        return dict(area_m2=float(a.sum()),
                    cover_above_m2={str(t):float(a[v['prior_fine_cover_m']>t].sum()) for t in (.0002,.0006,.0015)},
                    armor_above_half_m2=float(a[v['armor_exposure']>.5].sum()),
                    unassigned_boundary_baseline_fraction=float((a*(1-v['domain_strength'])).sum()/max(a.sum(),1e-30)),
                    dominant_unit_m2={name:float(a[np.argmax(v['unit_weights'],axis=-1)==k].sum()) for k,name in enumerate(UNIT_NAMES)},
                    unit_composition_mean={name:float((a*v['unit_weights'][...,k]).sum()/max(a.sum(),1e-30)) for k,name in enumerate(UNIT_NAMES)})
    routes=[]
    for reach in spec.drainage_reaches:
        a=np.asarray(reach,float);p=np.concatenate([va[:2]+np.linspace(0,1,33)[:,None]*(vb[:2]-va[:2]) for va,vb in zip(a[:-1],a[1:])])
        zz=_sample(z,p,x,y); dz=np.diff(zz)
        routes.append(dict(start_xy_m=a[0,:2].tolist(),end_xy_m=a[-1,:2].tolist(),
                           net_foundation_drop_m=float(zz[0]-zz[-1]),
                           maximum_local_uphill_increment_m=float(max(0.,dz.max())),
                           note='Centerline samples on present graded AH, not reconstructed historical topography'))
    return dict(model='AK illustrative historical substrate units',spec=asdict(spec),
                units=list(UNIT_NAMES),whole_domain=coverage(np.ones(xx.shape,bool)),
                near_visible_world_roi=coverage(near),
                prior_fine_cover_min_max_m=[float(v['prior_fine_cover_m'].min()),float(v['prior_fine_cover_m'].max())],
                drainage_routes=routes,geometry_height_added_m=0.,recent_storm_inputs_used=False,
                conservation_claim=False,calibrated_physics=False,surveyed_history=False,
                interpretation='A graded pre-existing parent skin, older connected winnowing and thin receiving sand; no new sediment inventory or terrain displacement.',
                limits='Non-surveyed art-directed chronology; width and settling are authored, gradients use actual AH foundation. Unit membership is a visual/exposure proxy, not a validated geomorphic reconstruction.')
