"""AU: bounded, view-aware replacement of the obsolete U point supplement.

Call apply(scene, config, out) AFTER AH and BEFORE AC/AL/AI. The required config
keys are camera_location, camera_target, lens, width and height. Only the existing
U object's point mesh is reassigned, after a complete validated in-memory plan.
No scene loading/saving, rendering, prototype editing, or camera mutation occurs.
The pure planner reuses the approved CameraProjection, PackingIndex, density and
pixel-LOD rules. It does not call restore_approved_density, whose creation-only
API cannot transactionally replace an existing supplement without a duplicate.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import gc
import hashlib
import json
import math
import time
import numpy as np
import approved_density_lod as lod
from context_mesh_refine_ab import SourceSampler, intersecting_triangles, _read, ATTRIBUTE_TYPES
from visible_shoulder_flow_ad import sample_field, _axis

MAX_INSTANCES = 294363
MAX_CELLS = 12000
GROUND = 'Graded shoulder and alluvial plain -1'
RIGID = ('Sparse physical 7–31 mm roadside mineral lag',
         'Gravel lag pockets beside shallow runoff arms',
         'Connected drainage / margin gravel bars')
_MISSING = ('Source query outside bounded support', 'Source query has a coverage gap',
            'Point is outside actual source triangles; no extrapolation',
            'contact queries leave exact local triangle patch')


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _height(surface, xy, *, missing=False):
    """Bounded exact triangle queries; only known geometric gaps become NaN."""
    xy = np.asarray(xy, float).reshape(-1, 2)
    out = np.empty(len(xy))
    order = np.lexsort((xy[:, 1], np.floor(xy[:, 0] / .045)))
    def sample(rows):
        try:
            out[rows] = np.asarray(surface.height(xy[rows])).reshape(-1)
        except ValueError as error:
            if not missing or not any(s in str(error) for s in _MISSING):
                raise
            if len(rows) == 1:
                out[rows] = np.nan
            else:
                cut = len(rows) // 2
                sample(rows[:cut]); sample(rows[cut:])
    for start in range(0, len(xy), 2048):
        sample(order[start:start+2048])
    _require(missing or np.isfinite(out).all(), 'Nonfinite triangle heights')
    return out


def validate_fields(fields):
    x, _ = _axis(fields['x_m'], 'x_m'); y, _ = _axis(fields['y_m'], 'y_m')
    _require(len(x) * len(y) <= 120000, 'AH field exceeds bounded allocation')
    for name, tail in [('sediment_delta_m', ()), ('lag', ()), ('surface_fraction', (3,)),
                       ('retained_deposit_by_class_m', (3,))]:
        a = np.asarray(fields[name])
        _require(a.shape == (len(y), len(x)) + tail and np.isfinite(a).all(),
                 'Invalid current AH field: ' + name)
    _require(np.all(fields['retained_deposit_by_class_m'] >= -1e-12), 'Negative retained stock')
    _require(np.all(fields['surface_fraction'] >= 0), 'Negative surface fraction')
    return x, y


def field_noise(x, y, spacing, seed):
    """Exact statistical source-scale field from prepare_runoff_shoulder_y."""
    xx, yy = np.asarray(x) / spacing, np.asarray(y) / spacing
    i, j = np.floor(xx), np.floor(yy); fx, fy = xx-i, yy-j
    fx, fy = fx*fx*(3-2*fx), fy*fy*(3-2*fy)
    def h(a, b):
        q = np.sin(a*127.1+b*311.7+seed*17.37)*43758.5453123
        return (q-np.floor(q))*2-1
    return (h(i,j)*(1-fx)+h(i+1,j)*fx)*(1-fy)+(h(i,j+1)*(1-fx)+h(i+1,j+1)*fx)*fy


def population_weights(xy, fields):
    """Y source-density weighting, with the CURRENT AH lag/class fractions."""
    xy = np.asarray(xy, float); px, py = xy[:, 0], xy[:, 1]
    x, y = fields['x_m'], fields['y_m']
    d = np.clip(.46+.32*field_noise(px,py,.031,8)+.16*field_noise(px,py,.008,28), .07, .94)
    lag = sample_field(fields['lag'], xy, x, y)
    frac = sample_field(fields['surface_fraction'], xy, x, y)
    inside = (px>=x[0]) & (px<=x[-1]) & (py>=y[0]) & (py<=y[-1])
    frac = np.where(inside[:, None], frac, np.array([.68, .24, .08]))
    chips = ((.10+.92*(1-d)**1.8)/.38)*np.clip(.60+5.*frac[:,2]+.55*lag, .25, 2.2)
    grit = ((.26+.78*(1-d))/.68)*np.clip(.58+1.9*frac[:,1], .35, 1.6)
    return np.stack((np.clip(chips,.08,2.5), np.clip(grit,.1,2.2)), -1)


class CurrentTriangleSurface:
    """Actual current triangles and the same per-vertex AH sediment increment.

    Barycentric sampling of per-vertex increments reconstructs the foundation
    datum on this topology, rather than using a bilinear height blanket. It is
    valid immediately after AH, before any later geometry-changing stages.
    """
    def __init__(self, sampler, sediment_at_vertices):
        self.sampler = sampler
        self.sediment_at_vertices = np.asarray(sediment_at_vertices, float)
    def height(self, xy):
        return self.sampler.height(xy)
    def sediment_delta(self, xy):
        return self.sampler.sample(self.sediment_at_vertices, xy)


def buried_origins(final_z, sediment_delta):
    """AH loose_shift: erosion follows surface; 85% of positive rise buries."""
    return np.asarray(final_z) - .85*np.maximum(np.asarray(sediment_delta), 0.)


def readonly_projection(scene, config):
    for name in ('camera_location', 'camera_target', 'lens', 'width', 'height'):
        _require(name in config, 'AU requires the actual requested view: ' + name)
    width, height = config['width'], config['height']
    _require(isinstance(width, int) and isinstance(height, int) and 0 < width <= 8192 and 0 < height <= 8192,
             'Invalid bounded projection resolution')
    location, target = np.asarray(config['camera_location'], float), np.asarray(config['camera_target'], float)
    _require(location.shape == target.shape == (3,) and np.isfinite([location, target]).all(), 'Invalid camera pose')
    direction = target-location
    _require(np.linalg.norm(direction) > 1e-8 and np.linalg.norm(direction[:2]) > 1e-8, 'Degenerate camera direction')
    _require(np.isfinite(config['lens']) and 1 <= config['lens'] <= 500, 'Invalid projection lens')
    projection = lod.CameraProjection(scene, width, height).with_pose(location, target, config['lens'])
    projection.name = 'AU actual requested view / read-only'
    return projection


def _counts(points, proto, projection, lower, step, shape, extra_views=()):
    nx, ny = shape
    cell = np.floor((points[:, :2]-lower)/step).astype(int)
    valid = ((cell[:,0]>=0) & (cell[:,0]<nx) & (cell[:,1]>=0) & (cell[:,1]<ny)
             & _visible(points, (projection,)+tuple(extra_views)))
    counts = np.zeros((nx*ny, 64), np.int32)
    np.add.at(counts, (cell[valid,1]*nx+cell[valid,0], proto[valid]), 1)
    return counts


def _visible(points, views):
    return np.logical_or.reduce([v.visible(points) for v in views])


def _frustum_counts(points, proto, projection, band):
    uv, _ = projection.project(points); visible = projection.visible(points)
    return {name: dict(all_points=int(np.count_nonzero(band[proto] == b)),
                      in_frustum=int(np.count_nonzero(visible & (band[proto] == b))),
                      lower40percent=int(np.count_nonzero(visible & (uv[:,1] <= .4*projection.height) & (band[proto] == b))))
            for name, b in [('chips',0), ('grit',1)]}


def _quotas(wanted, inventory, budget, rng):
    """Largest remainder per identity; no cell receives >ceil(physical demand)."""
    result = np.zeros(wanted.shape, np.int32)
    for k in range(64):
        demand = wanted[:,k]
        total = float(demand.sum())
        if total > inventory[k]:
            demand = demand*(inventory[k]/total)
        result[:,k] = np.floor(demand).astype(np.int32)
        target = min(int(inventory[k]), int(math.floor(float(demand.sum())+.5)))
        remaining = target-int(result[:,k].sum())
        if remaining:
            order = np.argsort(-(demand-result[:,k]), kind='stable')
            result[order[:remaining],k] += 1
    overflow = int(result.sum())-budget
    while overflow > 0:
        nonzero = np.flatnonzero(result.ravel())
        rows = rng.choice(nonzero, min(overflow, len(nonzero)), replace=False)
        result.ravel()[rows] -= 1; overflow -= len(rows)
    return result


@dataclass
class GrainPlan:
    points: np.ndarray
    prototype: np.ndarray
    yaw: np.ndarray
    source_rows: np.ndarray
    receipt: dict


def plan_reallocation(*, records, original_points, original_prototype, old_points,
                      old_prototype, old_yaw, surface, fields, projection,
                      bounds=None, max_instances=MAX_INSTANCES, cell_size=.12,
                      exclusion=None, seed=lod.SEED, extra_projections=()):
    """Pure bounded arrays only. Old supplement rows are a finite identity pool.

    No old row can be used twice. Its bank index and all yaw components survive
    bit-for-bit; only its world position can change. Unspent budget is allowed.
    """
    started = time.monotonic(); x, y = validate_fields(fields)
    _require(len(extra_projections)<=1, 'AU supports at most one additional read-only view')
    views=(projection,)+tuple(extra_projections)
    bounds = tuple((x[0],x[-1],y[0],y[-1]) if bounds is None else bounds)
    b = np.asarray(bounds, float)
    _require(b.shape == (4,) and np.isfinite(b).all() and b[0]<b[1] and b[2]<b[3], 'Invalid bounds')
    _require(b[0]>=x[0] and b[1]<=x[-1] and b[2]>=y[0] and b[3]<=y[-1], 'Allocation must stay inside current AH fields')
    _require(isinstance(max_instances, int) and 0 < max_instances <= MAX_INSTANCES, 'Invalid supplement cap')
    _require(.06 <= cell_size <= .30, 'Invalid density cell size')
    original_points = np.asarray(original_points); original_prototype = np.asarray(original_prototype)
    old_points = np.asarray(old_points); old_prototype = np.asarray(old_prototype); old_yaw = np.asarray(old_yaw)
    for p, pi in [(original_points,original_prototype), (old_points,old_prototype)]:
        _require(p.ndim==2 and p.shape[1]==3 and np.isfinite(p).all(), 'Invalid point coordinates')
        _require(pi.shape==(len(p),) and np.issubdtype(pi.dtype,np.integer) and np.all((pi>=0)&(pi<64)), 'Invalid bank indices')
    _require(old_yaw.shape==(len(old_points),3) and np.isfinite(old_yaw).all(), 'Invalid retained yaw')
    _require(len(old_points)>0 and len(old_points)<=MAX_INSTANCES, 'Unexpected original U supplement size')
    _require(len(records)==64 and tuple(r['source_id'] for r in records)==lod.VERIFIED_BANK_IDS, 'Changed approved 64-bank identity mapping')
    _require([r['index'] for r in records]==list(range(64)), 'Changed prototype index order')
    band = np.array([0 if r['band']=='chips' else 1 for r in records])
    _require(np.array_equal(np.bincount(band),[48,16]), 'Changed bank class membership')
    radius = np.array([r['radius'] for r in records])
    _require(np.isfinite(radius).all() and np.all((radius>0)&(radius<.008)), 'Invalid metric bank radii')
    cap = min(max_instances, len(old_points)); inventory = np.bincount(old_prototype,minlength=64)
    nx, ny = int(math.ceil((b[1]-b[0])/cell_size)), int(math.ceil((b[3]-b[2])/cell_size))
    _require(nx*ny<=MAX_CELLS, 'Density allocation grid exceeds bounded cap')
    step = np.array([(b[1]-b[0])/nx, (b[3]-b[2])/ny]); corner = b[[0,2]]
    gx, gy = np.meshgrid(np.arange(nx),np.arange(ny)); lower=corner+np.c_[gx.ravel(),gy.ravel()]*step
    centre = lower+.5*step; z = _height(surface,centre,missing=True); centre_ok=np.isfinite(z)
    offsets = np.array([(i,j) for i in (.125,.375,.625,.875) for j in (.125,.375,.625,.875)])
    sample_xy = (lower[:,None,:]+offsets[None,:,:]*step).reshape(-1,2)
    sample_z = _height(surface,sample_xy,missing=True); sample_ok=np.isfinite(sample_z)
    sample_world = np.c_[sample_xy,np.nan_to_num(sample_z)]
    sample_visible=(sample_ok & _visible(sample_world,views)).reshape(-1,16)
    # A cell without an actual triangle-supported centre receives no invented height.
    visible_area = sample_visible.mean(1)*np.prod(step)*centre_ok
    world = np.c_[centre,np.nan_to_num(z)]
    projected=np.zeros((len(centre),64))
    for view in views:
        jac=view.area_vectors(world)
        active=(sample_ok & view.visible(sample_world)).reshape(-1,16).any(1)&centre_ok
        for r in records:
            area=np.abs(jac@r['area_vectors'].T).sum(1)/8*active
            projected[:,r['index']]=np.maximum(projected[:,r['index']],area)
    eq=np.sqrt(np.maximum(projected,0)*4/math.pi)
    weights=population_weights(centre,fields)
    density=np.array([lod.DENSITIES[r['band']]/(48 if r['band']=='chips' else 16) for r in records])
    physical=visible_area[:,None]*density[None,:]*weights[:,band]
    original=_counts(original_points,original_prototype,projection,corner,step,(nx,ny),extra_projections)
    before=_counts(old_points,old_prototype,projection,corner,step,(nx,ny),extra_projections)
    def deficit(factor):
        d=np.maximum(physical*lod.lod_fraction(eq,factor)-original,0.)
        sums=d.sum(0); return d*np.minimum(1.,np.divide(inventory,sums,out=np.ones(64),where=sums>0))
    raw=deficit(1.); factor=1.
    if raw.sum()>cap:
        lo,hi=1.,2.
        while deficit(hi).sum()>cap: hi*=2
        for _ in range(24):
            mid=(lo+hi)*.5
            if deficit(mid).sum()>cap: lo=mid
            else: hi=mid
        factor=hi
    rng=np.random.default_rng(seed); quotas=_quotas(deficit(factor),inventory,cap,rng)
    # Exact retained originals plus coarse-first new disks, never the obsolete U positions.
    packing=lod.PackingIndex(float(radius.max()))
    pad=2*radius.max()
    inside=(original_points[:,0]>=b[0]-pad)&(original_points[:,0]<=b[1]+pad)&(original_points[:,1]>=b[2]-pad)&(original_points[:,1]<=b[3]+pad)
    for p,k in zip(original_points[inside],original_prototype[inside]): packing.add(p[:2],radius[k])
    pools=[rng.permutation(np.flatnonzero(old_prototype==k)) for k in range(64)]; cursor=np.zeros(64,int)
    positions=[]; rows=[]; cells=[]; achieved=np.zeros_like(quotas)
    attempted=rejected=unsupported=buried_outside_frustum=0
    for cl in (0,1):
        for cell in np.flatnonzero(quotas[:,band==cl].sum(1)):
            todo=[]
            for k in np.flatnonzero(band==cl):
                n=int(quotas[cell,k]); todo.extend(pools[k][cursor[k]:cursor[k]+n]); cursor[k]+=n
            todo=np.asarray(todo,int); rng.shuffle(todo)
            for _ in range(8):
                if not len(todo): break
                xy=(lower[cell]+rng.random((len(todo),2))*step).astype('f4').astype(float)
                heights=_height(surface,xy,missing=True); good=np.isfinite(heights)
                unsupported+=int((~good).sum())
                final=np.c_[xy,np.nan_to_num(heights)]; in_view=good&_visible(final,views)
                retry=[]
                for row,p,ok in zip(todo,final,in_view):
                    attempted+=1; k=old_prototype[row]
                    if not ok or not packing.clear(p[:2],radius[k]) or (exclusion is not None and not exclusion.clear(p[:2],radius[k])):
                        retry.append(row); rejected+=1; continue
                    packing.add(p[:2],radius[k]); positions.append(p); rows.append(row); cells.append(cell); achieved[cell,k]+=1
                todo=np.asarray(retry,int)
    points=np.asarray(positions,float).reshape(-1,3); rows=np.asarray(rows,np.int32); cells=np.asarray(cells,np.int32)
    if len(points):
        sediment=np.asarray(surface.sediment_delta(points[:,:2]),float)
        _require(sediment.shape==(len(points),) and np.isfinite(sediment).all(),'Invalid triangle-projected sediment increment')
        points[:,2]=buried_origins(points[:,2],sediment)
    else: sediment=np.empty(0)
    points=points.astype('f4'); pi=old_prototype[rows].copy(); yaw=old_yaw[rows].copy()
    # Stored-float boundary drift and burial may leave the view: remove, never move
    # or enlarge a grain to force it on screen. AI may subsequently change exposure.
    keep=_visible(points,views); buried_outside_frustum=int((~keep).sum())
    if not keep.all():
        np.add.at(achieved,(cells[~keep],pi[~keep]),-1)
        points,pi,yaw,rows,cells,sediment=points[keep],pi[keep],yaw[keep],rows[keep],cells[keep],sediment[keep]
    _require(len(points)<=cap and len(np.unique(rows))==len(rows),'Duplicate identities or budget overflow')
    _require(np.array_equal(pi,old_prototype[rows]) and np.array_equal(yaw,old_yaw[rows]),'Source identity/yaw changed')
    after=_counts(points,pi,projection,corner,step,(nx,ny),extra_projections); by_band={}
    old_frustum=_frustum_counts(old_points,old_prototype,projection,band); new_frustum=_frustum_counts(points,pi,projection,band)
    for name,cl in [('chips',0),('grit',1)]:
        mask=band==cl; target_area=float((physical[:,mask]*projected[:,mask]).sum())
        def proxy(counts):
            area=float((np.minimum(original[:,mask]+counts[:,mask],physical[:,mask])*projected[:,mask]).sum())
            return area/target_area if target_area else 0.
        by_band[name]=dict(source_density_per_m2=lod.DENSITIES[name],bank_count=int(mask.sum()),
            before=old_frustum[name],after=new_frustum[name],requested=int(quotas[:,mask].sum()),
            physical_target_count=float(physical[:,mask].sum()),retained_original_in_frustum=int(original[:,mask].sum()),
            projected_exposed_area_proxy_sum_px2=target_area,
            before_geometric_projected_area_proxy_retained_fraction=proxy(before),
            after_geometric_projected_area_proxy_retained_fraction=proxy(after),
            allocation_shortfall=int(quotas[:,mask].sum()-achieved[:,mask].sum()))
    receipt=dict(scope='AU current-view candidate reallocation; not measured optical coverage or a mass solver',
        before_count=len(old_points),after_count=len(points),maximum_instances=cap,unspent_budget=cap-len(points),
        requested_count=int(quotas.sum()),allocation_shortfall=int(quotas.sum())-len(points),bands=by_band,
        per_identity=[dict(index=k,approved_source_id=records[k]['source_id'],before=int(inventory[k]),after=int((pi==k).sum())) for k in range(64)],
        resolution=[projection.width,projection.height],
        projection_allocation='Union of supplied frusta, maximum visible-view projected area, one shared budget',
        view_count=len(views),per_view=[dict(index=i,resolution=[v.width,v.height],lens_mm=float(v.lens),
            inverse=np.asarray(v.inverse).tolist(),before=_frustum_counts(old_points,old_prototype,v,band),
            after=_frustum_counts(points,pi,v,band)) for i,v in enumerate(views)],
        projection_inverse=np.asarray(projection.inverse).tolist(),
        projection_focal_scale=np.asarray(projection.f).tolist(),projection_offset=np.asarray(projection.offset).tolist(),
        bounds_m=b.tolist(),spatial_cells=[nx,ny],cell_size_m=step.tolist(),projection_fraction_samples_per_cell=16,
        estimated_frustum_ground_area_m2=float(visible_area.sum()),unsupported_cell_centres=int((~centre_ok).sum()),
        unsupported_domain_samples=int((~sample_ok).sum()),unsupported_sampled_origins=unsupported,
        buried_or_float32_outside_frustum_removed=buried_outside_frustum,
        actual_attempts=attempted,packing_frame_or_support_rejections=rejected,
        population_weight_min_mean_max=[weights.min(0).tolist(),weights.mean(0).tolist(),weights.max(0).tolist()],
        population_rule='Exact Y statistical source-scale weighting, conditioned on current AH lag and surface_fraction',
        budget_threshold_multiplier=factor,lod_equivalent_diameter_transition_px=[.25*factor,factor],
        burial_rule='actual final triangle minus 0.85 * max(triangle-projected current AH sediment increment, 0)',
        additional_burial_range_m=[0.,float(.85*np.maximum(sediment,0).max(initial=0))],
        source_row_identity_sha256=hashlib.sha256(rows.tobytes()).hexdigest(),
        prototype_geometry_and_materials_unchanged=True,retained_identity_yaws_unchanged=True,instance_scale=[1,1,1],
        source_sand_density_per_m2=lod.DENSITIES['sand'],sand_geometry_added=0,
        later_AI_required=True,rendered=False,scene_saved=False,elapsed_seconds=time.monotonic()-started,
        limits=[
            'This is bounded candidate representation, not exact physical-density or mass calibration; no sediment mass is created or conserved by reallocating visual instances.',
            'Finite per-prototype source identity inventory, projected LOD and conservative packing can leave unspent budget. No physical cell target is inflated to spend it.',
            'Point frustum counts and four-yaw projected face-area sums are not terrain/vegetation occlusion, measured rendered coverage, or disjoint coverage unions.',
            'Source sand and unresolved grit remain in the existing bake; their exact parallax, shadows and interreflection are not restored.',
            'New world XY and current AH burial are reconstructed; obsolete individual positions and historical transported-exposure state are not preserved.',
            'AI must subsequently apply current finite-stock exposure/burial and lowest-vertex contact cap. AU does not prove rigid-body support or final beauty quality.'])
    return GrainPlan(points,pi,yaw,rows,receipt)


def _current_surface(ground, fields, bounds):
    _require(np.allclose(np.asarray(ground.matrix_world),np.eye(4),atol=1e-8), 'Ground must retain its metric unit transform')
    _require(len(ground.modifiers)==0 and ground.data.shape_keys is None, 'AU needs unevaluated actual AH triangles')
    _require(len(ground.data.vertices)<=1600000, 'Ground vertex read cap exceeded')
    co=_read(ground.data.vertices,'co',3)
    ground.data.calc_loop_triangles()
    _require(len(ground.data.loop_triangles)<=3000000, 'Ground triangle read cap exceeded')
    tri=_read(ground.data.loop_triangles,'vertices',3,np.int32)
    collar=(bounds[0]-.02,bounds[1]+.02,bounds[2]-.02,bounds[3]+.02)
    ids=intersecting_triangles(co,tri,collar)
    _require(0<len(ids)<=850000, 'Current triangle local cap exceeded')
    local=tri[ids]; used,inv=np.unique(local,return_inverse=True)
    localco=co[used].copy(); localtri=inv.reshape(-1,3).astype(np.int32)
    del co,tri,local,used,inv,ids; gc.collect()
    sampler=SourceSampler(localco,localtri,np.arange(len(localtri)),max_triangles=850000,max_bin_entries=3200000)
    delta=sample_field(fields['sediment_delta_m'],localco[:,:2],fields['x_m'],fields['y_m'])
    return CurrentTriangleSurface(sampler,delta)


def _check_rigid_counts(vertices, polygons):
    # Pinned Z's largest retained bank has 1,045,220 vertices / 2,036,376 faces.
    _require(0 <= vertices <= 1100000 and 0 <= polygons <= 2100000,
             'Rigid exclusion source-informed global read cap exceeded')


def _bounded_rigid_components(mesh, world, bounds):
    """Legacy connected-body extraction with explicit pre-union local caps."""
    x0,x1,y0,y1=bounds
    local=((world[:,0]>=x0-.15)&(world[:,0]<=x1+.15)&
           (world[:,1]>=y0-.15)&(world[:,1]<=y1+.15))
    count=_read(mesh.polygons,'loop_total',1,np.int32)
    _require(np.all(count==3), 'Rigid grains must retain source triangle topology')
    tri=_read(mesh.loops,'vertex_index',1,np.int32).reshape(-1,3)
    nearby=tri[np.any(local[tri],axis=1)]
    _require(len(nearby)<=650000, 'Rigid local-triangle cap exceeded')
    if not len(nearby): return []
    ids,inverse=np.unique(nearby,return_inverse=True)
    _require(len(ids)<=350000, 'Rigid local-vertex cap exceeded')
    parent=np.arange(len(ids),dtype=np.int32)
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]; i=parent[i]
        return i
    for a,b,c in inverse.reshape(-1,3):
        ra=root(a); parent[root(b)]=ra; parent[root(c)]=ra
    labels=np.array([root(i) for i in range(len(ids))]); order=np.argsort(labels)
    cuts=np.flatnonzero(np.diff(labels[order]))+1
    components=[ids[group] for group in np.split(order,cuts)]
    for component in components:
        q=world[component,:2]
        editable=((q[:,0]>=x0-.03)&(q[:,0]<=x1+.03)&(q[:,1]>=y0-.03)&(q[:,1]<=y1+.03))
        _require(not editable.any() or local[component].all(), 'Incomplete rigid body crosses exclusion collar')
    return [c for c in components if local[c].all()]


def _rigid_exclusion(scene, bounds):
    """Reuse established conservative clast disks with bounded local extraction."""
    from prepare_physical_lenses import DiskIndex
    disks=DiskIndex(); report=[]
    for name in RIGID:
        ob=scene.objects.get(name)
        _require(ob is not None and ob.type=='MESH' and not ob.modifiers and ob.data.shape_keys is None,
                 'Missing or evaluated retained rigid clasts: '+name)
        _check_rigid_counts(len(ob.data.vertices),len(ob.data.polygons))
        world=lod._world(ob,lod._co(ob.data)); count=0
        for ids in _bounded_rigid_components(ob.data,world,bounds):
            q=world[ids,:2]; centre=(q.min(0)+q.max(0))*.5
            radius=float(np.linalg.norm(q-centre,axis=1).max())
            if centre[0]+radius<bounds[0] or centre[0]-radius>bounds[1] or centre[1]+radius<bounds[2] or centre[1]-radius>bounds[3]:
                continue
            disks.add(centre,radius); count+=1
        report.append(dict(object=name,complete_bodies=count))
    return disks,report


def _point_arrays(ob, *, readonly=False):
    _require(ob.type=='MESH' and len(ob.data.edges)==0 and len(ob.data.polygons)==0 and ob.data.shape_keys is None,
             'Expected an ordinary point-only supplement mesh')
    _require(np.allclose(np.asarray(ob.matrix_world),np.eye(4),atol=1e-8), 'Point object must retain unit transform')
    attributes={}
    for attr in ob.data.attributes:
        if attr.name=='position': continue
        # The approved ORIGINS has empty FACE sharp_face despite zero faces.
        # It is read-only here, so leave that datablock untouched and skip it.
        if readonly and attr.domain!='POINT' and len(attr.data)==0: continue
        _require((attr.domain=='POINT' or len(attr.data)==0) and attr.data_type in ATTRIBUTE_TYPES,
                 'Unsupported point attribute: '+attr.name)
        prop,size,dtype,_=ATTRIBUTE_TYPES[attr.data_type]
        attributes[attr.name]=(attr.data_type,prop,_read(attr.data,prop,size,dtype),attr.domain)
    _require('prototype' in attributes and 'yaw' in attributes, 'Missing source point identity/yaw attributes')
    _require(attributes['prototype'][0]=='INT' and attributes['yaw'][0]=='FLOAT_VECTOR', 'Changed identity/yaw schema')
    return lod._co(ob.data),attributes


def _mesh_stamp(ob):
    from prepare_physical_lenses import data_digest
    mesh=ob.data
    return dict(object=ob.name,matrix=np.asarray(ob.matrix_world).tolist(),mesh=mesh.name,
        vertices=data_digest(mesh.vertices,'co',3,'f4'),loops=data_digest(mesh.loops,'vertex_index',1,'i4'),
        materials=[m.name if m else None for m in mesh.materials],
        attributes={a.name:[a.domain,a.data_type,data_digest(a.data,ATTRIBUTE_TYPES[a.data_type][0],
                    ATTRIBUTE_TYPES[a.data_type][1],ATTRIBUTE_TYPES[a.data_type][2])]
                    for a in mesh.attributes if a.name!='position' and a.data_type in ATTRIBUTE_TYPES})


def _validate_instance_graph(group):
    """Fail closed if the retained graph no longer has exact unit-scale inputs."""
    instances=[n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints']
    _require(len(instances)==1, 'Ambiguous source instance graph')
    node=instances[0]
    _require(not node.inputs['Scale'].is_linked and np.array_equal(np.asarray(node.inputs['Scale'].default_value),[1.,1.,1.]),
             'Source instances must use the approved unlinked unit scale')
    _require(node.inputs['Pick Instance'].default_value and not node.inputs['Pick Instance'].is_linked,
             'Source graph must pick exactly one approved instance per point')
    for socket,name in [('Instance Index','prototype'),('Rotation','yaw')]:
        links=node.inputs[socket].links
        _require(len(links)==1 and links[0].from_node.bl_idname=='GeometryNodeInputNamedAttribute',
                 'Source graph changed the '+name+' mapping')
        attr=links[0].from_node
        _require(attr.inputs['Name'].default_value==name and not attr.inputs['Name'].is_linked,
                 'Source graph changed the '+name+' attribute')


def _protected_stamp(scene, records, group):
    import bpy
    from prepare_physical_lenses import graph_signature
    protos=[bpy.data.objects[r['name']] for r in records]
    materials={m.name:m for ob in protos for m in ob.data.materials if m is not None}
    camera=scene.camera
    stamp=dict(origins=_mesh_stamp(scene.objects[lod.ORIGINS]),prototypes=[_mesh_stamp(ob) for ob in protos],
        graphs={m.name:graph_signature(m.node_tree) for m in materials.values()},group=graph_signature(group),
        camera_matrix=np.asarray(camera.matrix_world).tolist(),
        camera_data=[camera.data.type,camera.data.lens,camera.data.sensor_width,camera.data.sensor_height,
                     camera.data.shift_x,camera.data.shift_y,camera.data.clip_start,camera.data.clip_end,camera.data.sensor_fit],
        resolution=[scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage,
                    scene.render.pixel_aspect_x,scene.render.pixel_aspect_y])
    return hashlib.sha256(json.dumps(stamp,sort_keys=True).encode()).hexdigest()


def apply(scene, config, out):
    """Transactional scene adapter. Returns receipt; caller owns writing/saving.

    Refuses an already refreshed candidate. An exception before verified commit
    retains/restores the original U object and mesh. The old mesh is discarded
    only after the new mesh, protected assets and identity attributes validate.
    """
    import bpy
    started=time.monotonic(); path=Path(out)/'AH_FIELDS.npz'
    with np.load(path,allow_pickle=False) as archive: fields={k:archive[k] for k in archive.files}
    x,y=validate_fields(fields); bounds=tuple(config.get('bounds_m',(float(x[0]),float(x[-1]),float(y[0]),float(y[-1]))))
    projection=readonly_projection(scene,config)
    additional=config.get('additional_views',[])
    _require(isinstance(additional,(list,tuple)) and len(additional)<=1, 'Only one additional read-only view is supported')
    extra_projections=tuple(readonly_projection(scene,dict(config,**view)) for view in additional)
    old=scene.objects.get(lod.OUTPUT); origins=scene.objects.get(lod.ORIGINS)
    _require(old is not None and origins is not None, 'Expected the original pinned-Z U supplement and ORIGINS')
    _require(not old.get('au_view_refresh'), 'AU already applied; rebuild from the immutable source instead of duplicating refresh')
    _require(old.data.users==1 and len(old.users_scene)==1, 'Refuse a shared supplement mesh or multi-scene object')
    _require(abs(scene.unit_settings.scale_length-1.)<1e-8, 'AU requires unchanged SI scene scale')
    records,group,collection_name=lod._bank(origins)
    _validate_instance_graph(group)
    _require(len(old.modifiers)==1 and old.modifiers[0].type=='NODES' and old.modifiers[0].node_group==group,
             'Supplement does not share the approved unmodified instance graph')
    old_points,attributes=_point_arrays(old); original_points,origin_attributes=_point_arrays(origins,readonly=True)
    _require('au_source_row' not in attributes, 'Existing AU identity provenance requires rebuilding the source candidate')
    old_pi=attributes['prototype'][2]; old_yaw=attributes['yaw'][2]
    before_stamp=_protected_stamp(scene,records,group)
    surface=_current_surface(scene.objects[GROUND],fields,bounds)
    exclusion,rigid_report=_rigid_exclusion(scene,bounds)
    plan=plan_reallocation(records=records,original_points=original_points,
        original_prototype=origin_attributes['prototype'][2],old_points=old_points,
        old_prototype=old_pi,old_yaw=old_yaw,surface=surface,fields=fields,projection=projection,
        bounds=bounds,max_instances=config.get('max_instances',MAX_INSTANCES),
        cell_size=config.get('cell_size_m',.12),exclusion=exclusion,extra_projections=extra_projections)
    _require(len(plan.points)>0, 'New view has no supported source-scale allocation; old supplement retained')
    # Recheck after stored float32 coordinates, before touching the old object.
    actual=_height(surface,plan.points[:,:2]); delta=surface.sediment_delta(plan.points[:,:2])
    _require(np.max(np.abs(plan.points[:,2]-buried_origins(actual,delta)))<2e-6,
             'Stored float32 point no longer matches current triangle/burial datum')
    new=None; previous=old.data; assigned=False
    try:
        new=bpy.data.meshes.new(previous.name+' / AU view allocation')
        new.vertices.add(len(plan.points)); new.vertices.foreach_set('co',plan.points.ravel())
        for name,(kind,prop,values,domain) in attributes.items():
            attr=new.attributes.get(name) or new.attributes.new(name,kind,domain)
            _require(attr.data_type==kind and attr.domain==domain, 'Staging mesh attribute schema changed: '+name)
            selected=values[plan.source_rows] if domain=='POINT' else values
            attr.data.foreach_set(prop,np.ascontiguousarray(selected).ravel())
        identity=new.attributes.new('au_source_row','INT','POINT')
        identity.data.foreach_set('value',plan.source_rows)
        for material in previous.materials: new.materials.append(material)
        for key in previous.keys(): new[key]=previous[key]
        new.update()
        _require(np.array_equal(lod._co(new),plan.points),'New mesh point verification failed')
        _require(np.array_equal(_read(new.attributes['prototype'].data,'value',1,np.int32),plan.prototype), 'New mesh identity verification failed')
        _require(np.array_equal(_read(new.attributes['yaw'].data,'vector',3),plan.yaw), 'New mesh yaw verification failed')
        _require(_protected_stamp(scene,records,group)==before_stamp, 'Protected assets changed during planning')
        old.data=new; assigned=True
        _require(old.data==new and old.modifiers[0].node_group==group, 'Supplement mesh assignment verification failed')
        after_stamp=_protected_stamp(scene,records,group)
        _require(after_stamp==before_stamp, 'Protected assets changed during assignment')
        old['au_view_refresh']='Current-view source-identity reallocation; run AI afterward'
    except Exception:
        if assigned: old.data=previous
        if 'au_view_refresh' in old: del old['au_view_refresh']
        if new is not None and new.users==0: bpy.data.meshes.remove(new)
        raise
    # Commit is verified. Orphan cleanup is optional and cannot undo that commit.
    cleanup_error=None; old_mesh_removed=False
    try:
        if previous.users==0:
            bpy.data.meshes.remove(previous); old_mesh_removed=True
    except Exception as error:
        cleanup_error=str(error)
    report=plan.receipt
    report.update(object=old.name,prototype_collection=collection_name,
        camera=dict(location=list(config['camera_location']),target=list(config['camera_target']),lens_mm=float(config['lens'])),
        additional_requested_views=additional,read_only_camera_override=True,camera_and_render_settings_unchanged=True,
        protected_before_sha256=before_stamp,protected_after_sha256=after_stamp,
        original_origins_unchanged=True,existing_supplement_object_reused=True,new_supplement_objects=0,
        old_point_mesh_removed=old_mesh_removed,orphan_cleanup_error=cleanup_error,
        rigid_exclusion=rigid_report,current_actual_triangles=len(surface.sampler.triangles),
        AH_fields_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        rollback='Old mesh retained until verified assignment; precommit errors restore it',
        immutable_source_file_written=False,elapsed_seconds=time.monotonic()-started)
    del surface,exclusion,fields,plan; gc.collect()
    return report
