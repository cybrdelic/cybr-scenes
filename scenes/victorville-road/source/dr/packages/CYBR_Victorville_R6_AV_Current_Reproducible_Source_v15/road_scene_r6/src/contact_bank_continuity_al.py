"""AL physical bank continuity after AH/AC, before AI presentation.

Bury the inherited 0--55 mm soil incursion under unchanged asphalt, continuing
actual AH foundation crossfall and net bed change. No extra sheet, remeshing,
edge noise, material edit, or sediment mass claim. Pure planning imports without
Blender. The apply adapter never opens/saves a scene or renders.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
import gc
import hashlib
import time
import numpy as np
from context_mesh_refine_ab import SourceSampler, intersecting_triangles
from metric_edge_strip_aa import TriangleSampler
from runoff_edge_support_ai import EdgeSupportSpec, build_edge_support

GROUND = 'Graded shoulder and alluvial plain -1'
ROAD = 'Crowned asphalt crust / longitudinal rise'


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _smooth(t):
    t = np.clip(np.asarray(t, float), 0., 1.)
    return t*t*t*(t*(6*t-15)+10)


@dataclass(frozen=True)
class BankSpec:
    y_min_m: float = 2.
    y_max_m: float = 8.2
    onset_m: float = .20
    end_fade_m: float = .30
    outer_x_m: float = -3.75
    full_x_m: float = -3.45
    right_x_m: float = -3.04
    max_movement_m: float = .030
    sampler_collar_m: float = .075
    max_local_triangles: int = 240_000
    # Same AI profile/limits. Its default 20 cm anchor span exceeds its 10%
    # grade guard at one far row; this allowed 30 cm span stays below 8.1%.
    # Neither source filtering nor safety-limit relaxation is needed.
    support: EdgeSupportSpec = field(default_factory=lambda: EdgeSupportSpec(
        outer_anchor_x_m=-3.75, inner_anchor_x_m=-3.45))

    def validate(self):
        self.support.validate()
        _require(self.y_min_m == 2. and self.y_max_m == 8.2,
                 'AL is bounded to y=2..8.2 m; existing AC is unchanged')
        _require(.12 <= self.onset_m <= .30 and .20 <= self.end_fade_m <= .50,
                 'Use short smooth onset and bounded far-domain fade')
        _require(self.outer_x_m == self.support.outer_anchor_x_m and
                 self.full_x_m == self.support.inner_anchor_x_m and
                 self.full_x_m < self.right_x_m <= -3.04,
                 'Bank mask must use the actual support anchors')
        _require(0 < self.max_movement_m <= .030,
                 'Physical bank movement is bounded to 30 mm')
        _require(.05 <= self.sampler_collar_m <= .10 and
                 1 <= self.max_local_triangles <= 300_000,
                 'Keep the actual triangle neighborhood bounded')
        return self

    @property
    def bounds(self):
        return self.outer_x_m, self.right_x_m, self.y_min_m, self.y_max_m


def bank_gate(xy, spec=None):
    """Exact zero at/outside bounds, including all good y<=2 AC contact."""
    spec = (spec or BankSpec()).validate()
    p = np.asarray(xy, float)
    _require(p.shape[-1] == 2 and np.isfinite(p).all(), 'Finite XY required')
    x, y = p[..., 0], p[..., 1]
    g = (_smooth((x-spec.outer_x_m)/(spec.full_x_m-spec.outer_x_m))
         * _smooth((y-spec.y_min_m)/spec.onset_m)
         * _smooth((spec.y_max_m-y)/spec.end_fade_m))
    return np.where(x < spec.right_x_m, g, 0.)


def actual_road_profile(road_co, road_triangles, spec=None):
    """Actual left triangle-union edge at every original longitudinal knot."""
    spec = (spec or BankSpec()).validate()
    co, tri = np.asarray(road_co), np.asarray(road_triangles)
    ids = intersecting_triangles(co, tri,
        (spec.outer_x_m, -2.95, spec.y_min_m-1e-5, spec.y_max_m+1e-5))
    t = tri[ids]; q = co[t, :2].astype(float)
    u, v = q[:, 1]-q[:, 0], q[:, 2]-q[:, 0]
    t = t[np.abs(u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0]) > 1e-13]
    used, inverse = np.unique(t, return_inverse=True)
    sampler = TriangleSampler(co[used], inverse.reshape(-1, 3), cell=.05,
                              max_bucket_entries=500_000)
    ys = co[used, 1].astype(float)
    ys = np.unique(np.r_[spec.y_min_m,
        ys[(ys > spec.y_min_m) & (ys < spec.y_max_m)], spec.y_max_m])
    _require(len(ys) <= 10_000, 'Actual boundary exceeds bounded sample cap')
    xy = np.c_[sampler.left_edge(ys), ys]
    return np.c_[xy, sampler.sample(sampler.co[:, 2], xy)], sampler


def support_from_fields(fields, actual_edge, spec=None):
    spec = (spec or BankSpec()).validate()
    return build_edge_support(*(fields[k] for k in (
        'x_m', 'y_m', 'foundation_z_m', 'sediment_delta_m',
        'retained_deposit_by_class_m', 'flow_strength')),
        actual_edge, spec=spec.support)


def bank_vertex_delta(coordinates, profile, road_sampler, spec=None):
    """Continue actual crossfall; carry net bed delta once; change only Z.

    A smooth constraint transfer reaches the shared profile's bank datum at
    the actual road edge. Under-pavement soil is capped below actual triangles.
    """
    spec = (spec or BankSpec()).validate(); co = np.asarray(coordinates)
    _require(co.ndim == 2 and co.shape[1] == 3 and np.isfinite(co).all(),
             'Finite actual terrain coordinates required')
    gate = bank_gate(co[:, :2], spec); rows = np.flatnonzero(gate > 0.)
    dz = np.zeros(len(co), float)
    if not len(rows):
        return dz, dict(eligible_vertices=0, movement_cap_clipped_vertices=0)
    q = co[rows].astype(float); p = profile.sample(q[:, 1])
    edge_x = np.interp(q[:, 1], profile.y_m, profile.base_edge_xyz[:, 0])
    dx = q[:, 0]-edge_x
    raw = p['raw_bank_top_z_m']+p['foundation_grade']*dx
    transfer = _smooth((q[:, 0]-spec.full_x_m)/(edge_x-spec.full_x_m))
    target = raw+(p['bank_top_z_m']-p['raw_bank_top_z_m'])*transfer
    under_road = dx >= 0.
    if np.any(under_road):
        road_z = road_sampler.sample(road_sampler.co[:, 2], q[under_road, :2])
        target[under_road] = np.minimum(target[under_road],
                                       road_z-p['exposure_m'][under_road])
    requested = target-q[:, 2]
    bounded = np.clip(requested, -spec.max_movement_m, spec.max_movement_m)
    dz[rows] = gate[rows]*bounded
    return dz, dict(eligible_vertices=len(rows),
        under_pavement_vertices=int(under_road.sum()),
        movement_cap_clipped_vertices=int(np.count_nonzero(requested != bounded)),
        unblended_requested_movement_range_m=[float(requested.min()), float(requested.max())],
        vertex_movement_range_m=[float(dz.min(initial=0)), float(dz.max(initial=0))])


def contained_vertex_mask(co, triangles, bounds):
    """Pin vertices of triangles crossing the boundary to prevent AC leakage.

    This topology-local zero collar also contains far-end/outer interpolation.
    It does not protect arbitrary weak terrain inside the physical bank.
    """
    co, t = np.asarray(co), np.asarray(triangles); a, b, c, d = bounds
    inside = ((co[:, 0] >= a) & (co[:, 0] <= b) &
              (co[:, 1] >= c) & (co[:, 1] <= d))
    allowed = inside.copy()
    for start in range(0, len(t), 32768):
        batch = t[start:start+32768]
        allowed[np.unique(batch[~np.all(inside[batch], axis=1)])] = False
    return allowed


def audit_triangle_clearance(after, triangles, road_sampler, profile, spec=None):
    """Bounded triangle-interior clearance samples in the full-strength span.

    Vertices, edge midpoints, and centroid check the actual final facets against
    actual road facets. This is a finite sampling audit, not an intersection
    certificate; partial onset/fade regions are explicitly excluded.
    """
    spec = (spec or BankSpec()).validate()
    co = np.asarray(after); tri = np.asarray(triangles)
    bary = np.array([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.],
                     [.5, .5, 0.], [0., .5, .5], [.5, 0., .5], [1/3, 1/3, 1/3]])
    count = 0; clearance_min = np.inf; near_coplanar = penetrations = 0
    for first in range(0, len(tri), 2048):
        q = np.einsum('ki,nij->nkj', bary, co[tri[first:first+2048]]).reshape(-1, 3)
        core = ((q[:, 1] >= spec.y_min_m+spec.onset_m) &
                (q[:, 1] <= spec.y_max_m-spec.end_fade_m) &
                (q[:, 0] >= spec.full_x_m) & (q[:, 0] < spec.right_x_m))
        q = q[core]
        if not len(q):
            continue
        edge_x = np.interp(q[:, 1], profile.y_m, profile.base_edge_xyz[:, 0])
        q = q[q[:, 0] >= edge_x+1e-9]
        if not len(q):
            continue
        top = road_sampler.sample(road_sampler.co[:, 2], q[:, :2])
        clearance = top-q[:, 2]; count += len(q)
        clearance_min = min(clearance_min, float(clearance.min()))
        near_coplanar += int(np.count_nonzero(clearance < .0001))
        penetrations += int(np.count_nonzero(clearance < -1e-7))
    return dict(sampled_full_strength_under_pavement_points=count,
        sampled_minimum_clearance_m=clearance_min if count else None,
        sampled_clearance_below_0_1mm=near_coplanar,
        sampled_penetrations=penetrations,
        sample_locations='Every local triangle vertex, edge midpoint, and centroid',
        finite_sample_audit_not_complete_intersection_proof=True,
        partial_onset_and_far_fade_excluded=True)


@dataclass
class BankPlan:
    before: np.ndarray
    after: np.ndarray
    delta_m: np.ndarray
    local_triangles: np.ndarray
    sampler: SourceSampler
    profile: object
    spec: BankSpec
    report: dict

    def height_shift(self, xy):
        """Actual final-minus-old triangle height; NaN outside real soil.

        Existing origins beyond the soil boundary are not assigned invented
        nearest support. Reuse the existing bounded missing-contact helper.
        """
        import approved_density_lod as lod
        plan = self
        class DeltaSurface:
            def height(self, q):
                try:
                    return plan.sampler.sample(plan.delta_m, q)
                except ValueError as error:
                    if any(s in str(error) for s in ('outside bounded support',
                        'coverage gap', 'outside actual source triangles')):
                        raise ValueError('contact queries leave exact local triangle patch') from error
                    raise
        return lod._height(DeltaSurface(), xy, allow_missing=True)


def plan_bank(ground_co, ground_triangles, road_co, road_triangles, fields, *, spec=None):
    """Pure actual post-AH/AC geometry plan; all input arrays stay unchanged."""
    spec = (spec or BankSpec()).validate()
    co, tri = np.asarray(ground_co), np.asarray(ground_triangles)
    _require(co.ndim == 2 and co.shape[1] == 3 and np.issubdtype(co.dtype, np.floating) and len(co) <= 2_000_000,
             'Ground source allocation cap exceeded')
    _require(tri.ndim == 2 and tri.shape[1] == 3 and
             np.issubdtype(tri.dtype, np.integer) and len(tri) <= 3_600_000,
             'Actual bounded ground loop triangles required')
    _require(len(tri) and tri.min() >= 0 and tri.max() < len(co),
             'Ground triangle indices are invalid')
    edge, road_sampler = actual_road_profile(road_co, road_triangles, spec)
    profile = support_from_fields(fields, edge, spec)
    dz, report = bank_vertex_delta(co, profile, road_sampler, spec)
    contained = contained_vertex_mask(co, tri, spec.bounds)
    report['boundary_straddling_vertices_pinned'] = int(np.count_nonzero((dz != 0) & ~contained))
    dz[~contained] = 0.
    after = co.copy(); after[:, 2] = np.asarray(co[:, 2], float)+dz
    # Match actual storage precision; grains follow the geometry Blender gets.
    dz = after[:, 2].astype(float)-co[:, 2]
    a, b, c, d = spec.bounds; margin = spec.sampler_collar_m
    ids = intersecting_triangles(co, tri, (a-margin, b+margin, c-margin, d+margin))
    local = tri[ids]
    _require(len(local) <= spec.max_local_triangles, 'Local ground triangle cap exceeded')
    sampler = SourceSampler(co, local, np.arange(len(local)), cell_m=.075,
                            max_triangles=spec.max_local_triangles,
                            max_bin_entries=1_500_000)
    moved = np.any(dz[local] != 0., axis=1); q = co[local[moved]].astype(float)
    u, v = q[:, 1, :2]-q[:, 0, :2], q[:, 2, :2]-q[:, 0, :2]
    area = .5*np.abs(u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0])
    volume = float(np.sum(area*dz[local[moved]].mean(axis=1)))
    max_edge = (float(np.linalg.norm(q[:, [1, 2, 0], :2]-q[:, [0, 1, 2], :2],
                                    axis=2).max()) if len(q) else 0.)
    clearance = audit_triangle_clearance(after, local, road_sampler, profile, spec)
    _require(clearance['sampled_penetrations'] == 0,
             'Actual full-strength bank still penetrates pavement triangles')
    from contact_triangle_clearance_al import exact_clearance
    exact=exact_clearance(after,local,road_sampler,(spec.full_x_m,spec.right_x_m,spec.y_min_m+spec.onset_m,spec.y_max_m-spec.end_fade_m))
    _require(exact['penetrating_overlap_polygons']==0,'Exact bank/road intersection audit found penetration')
    report.update(exact_triangle_clearance=exact,clearance=clearance, model='Bounded actual AH-derived far bank support reconstruction',
        bounds_xy_m=list(spec.bounds), onset_m=spec.onset_m, end_fade_m=spec.end_fade_m,
        support=profile.report, changed_vertices=int(np.count_nonzero(dz)),
        final_vertex_movement_range_m=[float(dz.min(initial=0)), float(dz.max(initial=0))],
        maximum_moving_triangle_xy_edge_m=max_edge, local_sampler_triangles=len(local),
        signed_earthwork_volume_m3=volume, sediment_mass_conservation_claim=False,
        grain_movement_policy='Full actual final-minus-old triangle datum for earthwork; no sediment burial multiplier',
        existing_topology_unchanged=True, world_xy_unchanged=True, original_asphalt_unchanged=True,
        exact_zero_below_y_2=True, triangle_boundary_leakage=False,
        new_ground_sheets=0, new_particles=0, material_or_recipe_changes=False,
        periodic_or_random_edge_pattern=False,
        limits='Bounded geometric earthwork/support, not a new erosion solve or conserved sediment. '
               'Original protruding soil XY stays beneath pavement. Onset/fade retain partial old support. '
               'Triangle/crown clearance and visual acceptance need scene review.')
    return BankPlan(co, after, dz, local, sampler, profile, spec, report)


def move_retained(scene, plan):
    """Translate retained origins/complete bodies at unchanged XY and identity."""
    import prepare_physical_lenses as legacy
    records = []; a, b, c, d = plan.spec.bounds
    def in_bank(p):
        return (p[..., 0] > a) & (p[..., 0] < b) & (p[..., 1] > c) & (p[..., 1] < d)
    for name in (legacy.ORIGINS, 'U approved R5D density / projected chip and grit supplement'):
        obj = scene.objects.get(name)
        if obj is None:
            continue
        co = legacy.read_coordinates(obj.data); world = legacy.world_coordinates(obj, co)
        rows = np.flatnonzero(in_bank(world[:, :2])); shift = np.zeros(len(co))
        delta = plan.height_shift(world[rows, :2]); valid = np.isfinite(delta)
        shift[rows[valid]] = delta[valid]
        if np.any(shift):
            new = legacy.write_world_z(obj, co, shift)
            _require(np.array_equal(new[shift == 0], co[shift == 0]),
                     'Unchanged retained origin bytes moved')
        records.append(dict(object=name, moved_origins=int(np.count_nonzero(shift)),
            outside_actual_soil_support=int((~valid).sum()),
            shift_range_m=[float(shift.min(initial=0)), float(shift.max(initial=0))],
            prototype_identity_xy_scale_materials_unchanged=True))
    # Restore explicit helper bounds, including its captured function defaults.
    saved = (legacy.EDIT_BOUNDS, legacy.PATCH_BOUNDS, legacy.in_bounds.__defaults__)
    try:
        legacy.EDIT_BOUNDS = plan.spec.bounds
        legacy.PATCH_BOUNDS = (a-.10, b+.10, c-.10, d+.10)
        legacy.in_bounds.__defaults__ = (plan.spec.bounds, 0.)
        for name in legacy.RIGID:
            obj = scene.objects.get(name)
            if obj is None:
                continue
            co = legacy.read_coordinates(obj.data); world = legacy.world_coordinates(obj, co)
            components = legacy.local_components(obj.data, world)
            shift = np.zeros(len(co)); moved = 0
            for component in components:
                q = world[component, :2]; center = (q.min(axis=0)+q.max(axis=0))*.5
                if not in_bank(center):
                    continue
                dz = plan.height_shift(center[None])[0]
                if np.isfinite(dz) and abs(dz) > 1e-12:
                    shift[component] = dz; moved += 1
            if np.any(shift):
                legacy.write_world_z(obj, co, shift)
            records.append(dict(object=name, moved_complete_bodies=moved,
                                rigid_shape_xy_materials_unchanged=True))
    finally:
        legacy.EDIT_BOUNDS, legacy.PATCH_BOUNDS, legacy.in_bounds.__defaults__ = saved
    roots = []
    for obj in scene.objects:
        if not obj.name.startswith(legacy.PLANT_PREFIXES):
            continue
        p = np.asarray(obj.matrix_world.translation, float)
        if in_bank(p[:2]):
            dz = plan.height_shift(p[None, :2])[0]
            if np.isfinite(dz) and abs(dz) > 1e-12:
                matrix = obj.matrix_world.copy(); matrix.translation.z += dz
                obj.matrix_world = matrix; roots.append(dict(object=obj.name, delta_m=float(dz)))
    return records, roots


def apply(scene, config=None, output_directory=None):
    """After AH/AC, before AI. config fields_path defaults to out/AH_FIELDS.npz.

    Optional config['spec'] is a BankSpec. Return a serializable report; the
    caller owns persistence. There are no shared pipeline edits or file writes.
    """
    from context_mesh_refine_ab import _read
    from terrain_normal_transfer_ah import update_normals
    started = time.monotonic(); config = config or {}; spec = config.get('spec') or BankSpec()
    path = Path(config['fields_path']) if config.get('fields_path') else Path(output_directory)/'AH_FIELDS.npz'
    with np.load(path, allow_pickle=False) as archive:
        fields = {k: archive[k] for k in archive.files}
    ground, road = scene.objects[GROUND], scene.objects[ROAD]
    _require(not ground.modifiers and ground.data.shape_keys is None and ground.data.users == 1,
             'Ground must be a singly owned unevaluated mesh')
    for ob in (ground, road):
        _require(np.allclose(np.asarray(ob.matrix_world), np.eye(4), atol=1e-9, rtol=0),
                 'Actual coordinates require identity terrain/road transforms')
    mesh = ground.data; before = _read(mesh.vertices, 'co', 3)
    mesh.calc_loop_triangles(); triangles = _read(mesh.loop_triangles, 'vertices', 3, np.int32)
    road_co = _read(road.data.vertices, 'co', 3)
    road.data.calc_loop_triangles(); road_triangles = _read(road.data.loop_triangles, 'vertices', 3, np.int32)
    plan = plan_bank(before, triangles, road_co, road_triangles, fields, spec=spec)
    # Preserve decoded vectors BEFORE geometry-dependent normal encoding changes.
    normals = _read(mesh.corner_normals, 'vector', 3)
    mesh.vertices.foreach_set('co', plan.after.astype('f4').ravel()); mesh.update()
    normal_report = update_normals(mesh, SimpleNamespace(triangles=plan.local_triangles),
                                   before, plan.after, plan.delta_m, normals)
    movement, roots = move_retained(scene, plan)
    _require(np.array_equal(_read(road.data.vertices, 'co', 3), road_co),
             'AL must not change a road vertex')
    report = dict(plan.report, normals=normal_report, moved_existing=movement,
        moved_roots=roots, source_field_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scene_assigned=True, elapsed_seconds=time.monotonic()-started)
    del fields, plan, before, triangles, road_co, road_triangles, normals
    gc.collect(); print('AL_BANK_ASSEMBLED', report, flush=True)
    return report
