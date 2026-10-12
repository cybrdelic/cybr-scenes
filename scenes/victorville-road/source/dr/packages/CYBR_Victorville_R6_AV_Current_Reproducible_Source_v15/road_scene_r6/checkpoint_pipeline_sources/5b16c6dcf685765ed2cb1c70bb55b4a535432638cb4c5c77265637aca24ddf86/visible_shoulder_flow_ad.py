"""AD: visible-shoulder finite-overburden adapter around the tested Z inventory solver.

SOURCE ONLY. No Blender import, scene edits, new ground sheets, material tint,
image/scan inputs, arbitrary stones, or alternate terrain function. The caller
supplies actual terrain-triangle heights and applies the returned vertical
movement to its existing/refined triangle surface. Z retains Y's nonvalidated,
stage-limited, connected-wet contact physics; this is not measured hydrology.

Suggested integration (do not add initial stock to the mesh a second time)::

    spec = ContextSpec()
    x, y = context_axes(spec)
    z = sample_triangle_grid(actual_triangle_patch.height, x, y)
    result = solve_context(x, y, z, spec=spec)
    delta = sample_displacement(result, world_vertices[:, :2])
    # If the irregular ground edge leaves contact-grid gaps, query the actual
    # topmost ground/road triangles there; do not fill missing Z analytically.
    # Apply delta to world Z on existing ground; follow actual triangle contact
    # for existing movable grains/roots OUTSIDE the protected near patch only.
    # Leave approved source grains, intrinsic materials and road contact intact.

The continuous outer shoulder is solved as ONE domain. Protected cells remain
in its hydraulic graph and can pass water/load, but have zero initial mobile
stock and zero retained-deposit capacity. A smooth interface limits the actual
inventory BEFORE transport, never masks or blurs the completed height field.
No analytical channel centres, periodic rakes/combs, or conical piles are added.

Important: the existing scene is ~17/18 cm triangulated in parts of this region.
A 5 cm simulation grid cannot restore missing mesh bandwidth. Subdivide that
existing surface to <=5 cm in affected flow areas before applying the field,
interpolating original material attributes and triangle Z exactly. Otherwise
reject the projection or explicitly use broad >=0.5 m features there. Protect
existing Y geometry/grain placements; never rebuild a second height blanket.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import math
import numpy as np
from flow_sediment_model_z import FlowConfig, FlowResult, simulate_shoulder


@dataclass(frozen=True)
class ContextSpec:
    bounds_m: tuple[float, float, float, float] = (-10.0, -3.2, 0.0, 40.0)
    spacing_m: float = 0.05
    # Includes the wider Y grain restoration domain as well as its terrain patch.
    protected_bounds_m: tuple[float, float, float, float] = (-6.25, -3.15, -0.7, 8.35)
    # Preserve the shoulder immediately under/beside the current Z pavement.
    protected_contact_x_min_m: float = -3.45
    transition_m: float = 0.30
    # Additional pre-transport support guard for linear triangle projection.
    # Must be at least the maximum moving mesh edge at protected interfaces.
    mesh_guard_m: float = 0.07
    loose_layer_m: float = 0.018
    retained_deposit_cap_m: float = 0.014
    max_grid_samples: int = 120_000
    flow: FlowConfig = field(default_factory=lambda: FlowConfig(
        seed=73109, exchange_diameter_m=0.15, boundary_band_m=0.20,
        max_erosion_m=0.018, max_deposition_m=0.018,
        max_event_erosion_m=0.0045))


@dataclass
class ContextResult:
    x_m: np.ndarray
    y_m: np.ndarray
    source_z_m: np.ndarray
    flow: FlowResult
    mobility: np.ndarray
    spec: ContextSpec
    receipt: dict


def _axis(a, name):
    a = np.asarray(a, dtype=np.float64)
    if a.ndim != 1 or len(a) < 3 or not np.isfinite(a).all():
        raise ValueError(name + ' must have at least three finite coordinates')
    d = np.diff(a)
    if np.any(d <= 0) or not np.allclose(d, d[0], atol=1e-10, rtol=1e-6):
        raise ValueError(name + ' must increase uniformly')
    return a, float(d[0])


def _smooth(v):
    v = np.clip(v, 0.0, 1.0)
    return v * v * (3.0 - 2.0 * v)


def _validate_spec(spec):
    for name in ('spacing_m', 'transition_m', 'mesh_guard_m', 'loose_layer_m', 'retained_deposit_cap_m'):
        if not np.isfinite(getattr(spec, name)) or getattr(spec, name) <= 0:
            raise ValueError(name + ' must be finite and positive')
    for name in ('bounds_m', 'protected_bounds_m'):
        b = np.asarray(getattr(spec, name), dtype=float)
        if b.shape != (4,) or not np.isfinite(b).all() or b[0] >= b[1] or b[2] >= b[3]:
            raise ValueError(name + ' must be finite (xmin,xmax,ymin,ymax)')
    if not np.isfinite(spec.protected_contact_x_min_m):
        raise ValueError('Contact protection must be finite')
    if not 0.010 <= spec.loose_layer_m <= 0.080:
        raise ValueError('Context loose stock must stay between 10 and 80 mm')
    if spec.retained_deposit_cap_m > 0.040:
        raise ValueError('Context retained deposits must stay at or below 40 mm')
    if not isinstance(spec.max_grid_samples, int) or spec.max_grid_samples < 9:
        raise ValueError('max_grid_samples must be an integer of at least 9')


def context_axes(spec: ContextSpec | None = None):
    spec = spec or ContextSpec()
    _validate_spec(spec)
    x0, x1, y0, y1 = spec.bounds_m
    counts = [round((b-a)/spec.spacing_m) for a, b in ((x0,x1),(y0,y1))]
    if any(not np.isclose(n * spec.spacing_m, b-a, atol=1e-9)
           for n, (a,b) in zip(counts, ((x0,x1),(y0,y1)))):
        raise ValueError('Bounds must be an integral number of requested grid intervals')
    if (counts[0]+1)*(counts[1]+1) > spec.max_grid_samples:
        raise ValueError('Context grid exceeds the explicit allocation limit')
    return np.linspace(x0,x1,counts[0]+1), np.linspace(y0,y1,counts[1]+1)


def sample_triangle_grid(height: Callable, x_m, y_m, batch_size=16_384):
    """Bound query memory; height(xy) must query actual triangles, not a formula.

    The last contact columns can cross the irregular shoulder edge. The caller
    must provide actual topmost road/ground triangle coverage there, or choose a
    fully covered grid. Missing heights fail rather than being extrapolated.
    """
    x, _ = _axis(x_m, 'x_m'); y, _ = _axis(y_m, 'y_m')
    if not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError('batch_size must be a positive integer')
    z = np.empty(len(x)*len(y), dtype=np.float64)
    for start in range(0, len(z), batch_size):
        ii = np.arange(start, min(start+batch_size, len(z)))
        query = np.column_stack((x[ii % len(x)], y[ii // len(x)]))
        sample = np.asarray(height(query), dtype=np.float64)
        if sample.shape != (len(ii),) or not np.isfinite(sample).all():
            raise ValueError('Actual triangle sampler returned gaps/nonfinite heights')
        z[start:start+len(ii)] = sample
    return z.reshape(len(y), len(x))


def inventory_mobility(x_m, y_m, spec: ContextSpec | None = None):
    """Metric C1 initial-inventory guard for grid AND linear-mesh interpolation.

    A one-cell guard alone only protects sampled points: a triangle straddling
    a non-grid-aligned protected edge can still interpolate movement inside it.
    Add mesh_guard_m before transport so every triangle of edge length at most
    that guard crossing a protected boundary has only zero-displacement corners.
    No completed height field is masked, blurred, or volume-corrected here.
    """
    spec = spec or ContextSpec(); _validate_spec(spec)
    x, dx = _axis(x_m, 'x_m'); y, dy = _axis(y_m, 'y_m')
    xx, yy = np.meshgrid(x,y)
    a,b,c,d = spec.protected_bounds_m
    ox = np.maximum(np.maximum(a-xx, xx-b), 0.)
    oy = np.maximum(np.maximum(c-yy, yy-d), 0.)
    # Chebyshev distance makes the whole interpolation support zero along every
    # protected edge, including diagonal approaches to rectangle corners.
    guard = (max(dx,dy) + spec.mesh_guard_m) * (1.0 + 1e-9)
    near_gate = _smooth((np.maximum(ox,oy)-guard)/spec.transition_m)
    road_gate = _smooth((spec.protected_contact_x_min_m-xx-guard)/spec.transition_m)
    # Keep a complete grid+mesh support collar immobile at the rectangular
    # projection boundary BEFORE transport. The boundary still routes water
    # and suspended load; only its erodible stock and retained capacity vanish.
    outer_distance = np.minimum.reduce((xx-x[0],x[-1]-xx,yy-y[0],y[-1]-yy))
    outer_gate = _smooth((outer_distance-guard)/spec.transition_m)
    return near_gate * road_gate * outer_gate


def solve_context(x_m, y_m, triangle_z_m, *, spec: ContextSpec | None = None,
                  flow_config: FlowConfig | None = None):
    """Solve finite stock on actual terrain. Does not modify its inputs or files."""
    spec = spec or ContextSpec(); _validate_spec(spec)
    x, dx = _axis(x_m, 'x_m'); y, dy = _axis(y_m, 'y_m')
    z = np.asarray(triangle_z_m, dtype=np.float64)
    if z.shape != (len(y),len(x)) or not np.isfinite(z).all():
        raise ValueError('triangle_z_m must contain finite actual terrain samples')
    if z.size > spec.max_grid_samples:
        raise ValueError('Context grid exceeds the explicit allocation limit')
    cfg = flow_config or spec.flow
    if cfg.max_erosion_m > .060 or cfg.max_deposition_m > .040:
        raise ValueError('Context solver height bounds must remain <=60mm erosion /40mm deposition')
    mobility = inventory_mobility(x,y,spec)
    initial = mobility[...,None] * spec.loose_layer_m * np.asarray(cfg.substrate_fractions)
    cap = mobility * spec.retained_deposit_cap_m
    flow = simulate_shoulder(x,y,z,cfg,
        initial_mobile_class_thickness_m=initial,
        maximum_deposited_thickness_m=cap)
    locked = mobility == 0
    if np.any(flow.height_delta_m[locked] != 0):
        raise AssertionError('Protected cells changed')
    if np.any(flow.retained_deposit_by_class_m < 0) or np.any(flow.remaining_initial_mobile_class_thickness_m < 0):
        raise AssertionError('Negative context inventory')
    if np.max(flow.final_deposit_m-cap) > 1e-12:
        raise AssertionError('Context retained-deposit cap exceeded')
    for name in ('net_bed_plus_export_error_m3', 'sediment_balance_error_m3', 'water_balance_error_m3'):
        if not np.isfinite(flow.receipt[name]) or abs(flow.receipt[name]) > 1e-9:
            raise AssertionError('Absolute context conservation failed: '+name)
    receipt = dict(
        model='Z finite-inventory adapter with preserved Y/road-contact interface',
        status='NONVALIDATED ART-DIRECTED PHYSICS; conservation is not visual or hydraulic validation',
        source='Caller-supplied actual triangle heights; initial stock is already part of those heights',
        bounds_m=[float(x[0]),float(x[-1]),float(y[0]),float(y[-1])],
        shape_yx=list(z.shape), spacing_xy_m=[dx,dy],
        protected_bounds_m=list(spec.protected_bounds_m),
        protected_contact_x_min_m=spec.protected_contact_x_min_m,
        interpolation_grid_guard_m=max(dx,dy), mesh_projection_guard_m=spec.mesh_guard_m,
        interpolation_guard_m=max(dx,dy)+spec.mesh_guard_m, interface_transition_m=spec.transition_m,
        protected_cells=int(locked.sum()), protected_cells_unchanged=True,
        model_cell_center_area_m2=dx*dy,
        model_integration='Cell-centre areas include rim samples; verify triangle projection separately',
        inventory_layer_m=spec.loose_layer_m, retained_cap_m=spec.retained_deposit_cap_m,
        no_additional_height_sheets=True, no_material_or_grain_edits=True,
        solver=flow.receipt)
    return ContextResult(x.copy(),y.copy(),z.copy(),flow,mobility,spec,receipt)


def sample_field(field, xy_m, x_m, y_m, outside=0.):
    """NumPy bilinear sampling for scalar or class fields. No SciPy dependency."""
    x, dx = _axis(x_m,'x_m'); y, dy = _axis(y_m,'y_m')
    a = np.asarray(field); p = np.asarray(xy_m, dtype=np.float64)
    if a.shape[:2] != (len(y),len(x)) or p.shape[-1:] != (2,):
        raise ValueError('Expected field (ny,nx,...) and points (...,2)')
    shape = p.shape[:-1]; p = p.reshape(-1,2)
    good = np.isfinite(p).all(axis=1) & (p[:,0]>=x[0]) & (p[:,0]<=x[-1]) & (p[:,1]>=y[0]) & (p[:,1]<=y[-1])
    tail = a.shape[2:]; out = np.full((len(p),)+tail, outside, dtype=np.result_type(a,float))
    q = p[good]; fx = (q[:,0]-x[0])/dx; fy=(q[:,1]-y[0])/dy
    i=np.clip(np.floor(fx).astype(int),0,len(x)-2); j=np.clip(np.floor(fy).astype(int),0,len(y)-2)
    fx=np.clip(fx-i,0,1).reshape((-1,)+(1,)*len(tail)); fy=np.clip(fy-j,0,1).reshape((-1,)+(1,)*len(tail))
    out[good]=(a[j,i]*(1-fx)+a[j,i+1]*fx)*(1-fy)+(a[j+1,i]*(1-fx)+a[j+1,i+1]*fx)*fy
    return out.reshape(shape+tail)


def sample_displacement(result: ContextResult, xy_m):
    """Return existing-ground Z movement; preservation checked, not post-masked."""
    p=np.asarray(xy_m,dtype=np.float64)
    delta=sample_field(result.flow.height_delta_m,p,result.x_m,result.y_m)
    a,b,c,d=result.spec.protected_bounds_m
    locked=((p[...,0]>=a)&(p[...,0]<=b)&(p[...,1]>=c)&(p[...,1]<=d)) | (p[...,0]>=result.spec.protected_contact_x_min_m)
    if np.any(delta[locked] != 0):
        raise AssertionError('Protected triangle/grain position would move; enlarge interpolation guard')
    return delta


def sample_surface_state(result: ContextResult, xy_m):
    """Use actual sediment stock for existing source-sized grain placement/LOD.

    Fractions/exposure are descriptive; they never authorize a color wash or
    extra solid volume. Newly visible grains require class-volume allocation,
    unchanged source prototypes, and actual final-triangle contact checking.
    """
    f=result.flow; x=result.x_m; y=result.y_m
    return {name:sample_field(getattr(f,name),xy_m,x,y) for name in (
        'height_delta_m','retained_deposit_by_class_m',
        'remaining_initial_mobile_class_thickness_m','surface_fraction',
        'lag_exposure','flow_strength','cumulative_erosion_m')}


def projection_diagnostics(result: ContextResult, vertices_m, triangles,
                           vertex_delta_m, batch_size=8192):
    """Exact linear-triangle signed volume and bandwidth, never a mass fix-up.

    Provide ONLY triangles within the solved rectangle. Boundary-spanning
    triangles are rejected, so off-domain corners cannot hide a seam. All input
    vertices may be supplied, but triangle indices must refer to those vertices.
    A large projection error needs mesh refinement or rerunning at suitable
    bandwidth, never a uniform offset/height blanket to force the total.
    """
    v=np.asarray(vertices_m,float); tri=np.asarray(triangles,dtype=np.int64)
    dz=np.asarray(vertex_delta_m,float)
    if v.ndim!=2 or v.shape[1]!=3 or tri.ndim!=2 or tri.shape[1]!=3 or dz.shape!=(len(v),):
        raise ValueError('Expected vertices(N,3), triangles(M,3), delta(N)')
    if not np.isfinite(v).all() or not np.isfinite(dz).all() or not len(tri):
        raise ValueError('Finite nonempty triangle projection required')
    volume=0.; area_sum=0.; coarse_area=0.; max_edge=0.; min_xy=np.array([result.x_m[0],result.y_m[0]]); max_xy=np.array([result.x_m[-1],result.y_m[-1]])
    threshold=max(result.x_m[1]-result.x_m[0],result.y_m[1]-result.y_m[0])*math.sqrt(2)*1.05
    for start in range(0,len(tri),batch_size):
        ids=tri[start:start+batch_size]; q=v[ids,:2]
        if np.any(q<min_xy-1e-7) or np.any(q>max_xy+1e-7):
            raise ValueError('Projection triangles must be clipped/subdivided at grid bounds')
        a=q[:,1]-q[:,0]; b=q[:,2]-q[:,0]
        area=.5*np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])
        edge=np.maximum.reduce((np.linalg.norm(a,axis=1),np.linalg.norm(b,axis=1),np.linalg.norm(q[:,2]-q[:,1],axis=1)))
        moved=np.max(np.abs(dz[ids]),axis=1)>1e-12
        volume+=float(np.dot(area,np.mean(dz[ids],axis=1)))
        area_sum+=float(area.sum()); coarse_area+=float(area[moved&(edge>threshold)].sum())
        max_edge=max(max_edge,float(edge.max()))
    grid_volume=float(result.flow.height_delta_m.sum()*(result.x_m[1]-result.x_m[0])*(result.y_m[1]-result.y_m[0]))
    gross=float(result.flow.receipt['cumulative_erosion_m3']+result.flow.receipt['cumulative_deposition_m3'])
    rectangle_area=float(np.prod(max_xy-min_xy))
    return dict(triangle_area_m2=area_sum,rectangle_area_m2=rectangle_area,
        area_difference_m2=area_sum-rectangle_area,triangle_signed_volume_m3=volume,
        solver_signed_volume_m3=grid_volume,projection_volume_error_m3=volume-grid_volume,
        projection_relative_to_gross_exchange=abs(volume-grid_volume)/max(gross,1e-30),
        coarse_moving_triangle_area_m2=coarse_area,maximum_triangle_edge_m=max_edge,
        field_diagonal_resolution_m=threshold,
        needs_refinement=bool(coarse_area>1e-10),
        note='No displacement changed by this audit; grid conservation does not prove triangle projection conservation')
