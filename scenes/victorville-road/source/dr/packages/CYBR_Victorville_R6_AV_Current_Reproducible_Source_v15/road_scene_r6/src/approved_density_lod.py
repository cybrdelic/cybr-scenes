"""Bounded, source-only R5D density restoration for the U shoulder specimen.

Call restore_approved_density(scene, after_patch, before_surface=before_patch,
                             burial_shift=loose_shift, max_instances=320000).
Patches must expose height(Nx2) over bounds plus a 1 cm collar. No scene opening,
rendering, evaluated dependency graph, BVH, prototype edits, or shader edits.
Only a new point mesh/object/modifier is made; it shares the approved GN tree.

Counts are from source_checkpoint/receipts/geometry_d.json, not an artistically
chosen coarse-rock density. Screen-area LOD is explicitly an approximation:
unresolved particles retain the existing source bake, not geometric occlusion.
"""
from __future__ import annotations
import math
import re
import time
import numpy as np

ORIGINS = 'True approved R5D near-camera grain geometry'
OUTPUT = 'U approved R5D density / projected chip and grit supplement'
DENSITIES = {'chips': 297/.18**2, 'grit': 8859/.18**2, 'sand': 64577/.18**2}
SEED = 2610100225
# Measured from Blender4.3.2 evaluated Collection Info instances, not assumed
# lexical sorting. IDs are the exact retained approved particle bank.
VERIFIED_BANK_IDS = (13, 23, 26, 32, 35, 36, 50, 52, 61, 62, 63, 64, 70, 78, 79, 83, 88, 90, 93, 98, 108, 116, 117, 129, 136, 143, 149, 151, 167, 168, 172, 179, 199, 206, 210, 211, 222, 226, 230, 247, 250, 256, 261, 265, 266, 273, 278, 292, 328, 784, 2934, 3077, 3821, 4243, 4744, 4975, 5933, 6351, 6454, 7589, 7649, 8453, 9012, 9033)


def _co(mesh):
    a = np.empty((len(mesh.vertices), 3), np.float32)
    mesh.vertices.foreach_get('co', a.ravel())
    return a


def _world(obj, co):
    m = np.asarray(obj.matrix_world, float)
    return co @ m[:3, :3].T + m[:3, 3]


def _height(surface, xy, block=2048, allow_missing=False):
    """Spatial ordering keeps U's exact hash sampler bounded and quick."""
    xy = np.asarray(xy, float).reshape(-1, 2)
    if not len(xy):
        return np.empty(0)
    order = np.lexsort((xy[:, 1], np.floor(xy[:, 0]/.045)))
    out = np.empty(len(xy))
    def sample(ids):
        try:
            out[ids] = np.asarray(surface.height(xy[ids])).reshape(-1)
        except ValueError as error:
            if not allow_missing or 'contact queries leave exact local triangle patch' not in str(error):
                raise
            if len(ids) == 1:
                out[ids] = np.nan
            else:
                mid = len(ids)//2
                sample(ids[:mid]); sample(ids[mid:])
    for start in range(0, len(xy), block):
        sample(order[start:start+block])
    if not allow_missing and not np.isfinite(out).all():
        raise ValueError('Exact surface sampler returned nonfinite contact heights')
    return out


def _hull_area(points):
    """2-D convex hull area, for a tiny source-prototype cross section."""
    p = sorted(set(map(tuple, np.asarray(points, float))))
    if len(p) < 3:
        return 0.
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def chain(seq):
        out = []
        for v in seq:
            while len(out) > 1 and cross(out[-2], out[-1], v) <= 0:
                out.pop()
            out.append(v)
        return out
    h = np.asarray(chain(p)[:-1]+chain(reversed(p))[:-1])
    return abs(float(np.sum(h[:, 0]*np.roll(h[:, 1], -1)-h[:, 1]*np.roll(h[:, 0], -1))))*.5


def _exposed_area_vectors(v, triangles):
    """Clip source triangles at its stored soil datum, keeping stored burial.

    For a convex closed solid, half the absolute projected face-area sum is its
    silhouette area. Fracture concavity can make this a conservative upper proxy;
    it is NOT presented as an exact rendered coverage or occlusion measurement.
    """
    normals, boundary = [], []
    for triangle in triangles:
        polygon = []
        points = v[triangle]
        for a, b in zip(points, np.roll(points, -1, axis=0)):
            if a[2] >= 0:
                polygon.append(a)
            if (a[2] >= 0) != (b[2] >= 0):
                hit = a + (b-a)*(-a[2]/(b[2]-a[2]))
                polygon.append(hit)
                boundary.append(hit[:2])
        for i in range(1, len(polygon)-1):
            normals.append(np.cross(polygon[i]-polygon[0], polygon[i+1]-polygon[0])*.5)
    if boundary:
        normals.append(np.array((0., 0., -_hull_area(boundary))))
    return np.asarray(normals, float).reshape(-1, 3)


def _bank(obj):
    mods = [m for m in obj.modifiers if m.type == 'NODES']
    if len(mods) != 1 or len(obj.modifiers) != 1:
        raise ValueError('Expected exactly the approved point-instance modifier')
    nodes = [n for n in mods[0].node_group.nodes if n.bl_idname == 'GeometryNodeCollectionInfo']
    if len(nodes) != 1:
        raise ValueError('Ambiguous approved prototype collection')
    node = nodes[0]
    if not node.inputs['Separate Children'].default_value or not node.inputs['Reset Children'].default_value:
        raise ValueError('Approved collection must separate/reset children')
    collection = node.inputs['Collection'].default_value
    if collection is None or len(collection.children):
        raise ValueError('Nested or missing approved prototype collection')
    # Blender uses natural numeric sorting for this bank. Ordinary lexical
    # string sorting incorrectly mapped fine-grit indices onto larger chips.
    objects = sorted(collection.objects, key=lambda o: int(re.fullmatch(r'Approved particle (\d+)(?:\.\d+)?', o.name).group(1)))
    if tuple(int(o.name.split()[2].split('.')[0]) for o in objects) != VERIFIED_BANK_IDS:
        raise ValueError('Actual approved bank no longer matches the64-identity evaluated contract')
    if len(objects) != 64:
        raise ValueError('Expected the exact 64-object approved bank')
    records = []
    for index, proto in enumerate(objects):
        match = re.fullmatch(r'Approved particle (\d+)(?:\.\d+)?', proto.name)
        if not match or proto.type != 'MESH' or proto.modifiers:
            raise ValueError('Unrecognized or modified approved prototype: '+proto.name)
        particle_id = int(match.group(1))
        band = 'chips' if particle_id < 297 else 'grit'
        if not 0 <= particle_id < 297+8859:
            raise ValueError('Source particle does not belong to the approved chip/grit bank')
        v = _co(proto.data).astype(float)
        if not np.allclose(np.asarray(proto.matrix_world), np.eye(4), atol=1e-8):
            raise ValueError('Prototype transform is not the approved unit transform')
        proto.data.calc_loop_triangles()
        tri = np.empty((len(proto.data.loop_triangles), 3), np.int32)
        proto.data.loop_triangles.foreach_get('vertices', tri.ravel())
        diameter = float(np.sqrt(np.max(np.sum((v[:, None, :2]-v[None, :, :2])**2, axis=-1))))
        if not 0 < diameter < .008:
            raise ValueError('Source metric grain dimensions are outside the expected millimetre bank')
        vectors = _exposed_area_vectors(v, tri)
        # Four orientations avoid privileging an elongated source chip's old yaw.
        rotated = []
        for angle in np.arange(4)*math.pi/4:
            c, s = math.cos(angle), math.sin(angle)
            rotated.append(vectors @ np.array(((c, -s, 0), (s, c, 0), (0, 0, 1))).T)
        records.append(dict(index=index, name=proto.name, source_id=particle_id, band=band,
                            vertices=v, area_vectors=np.concatenate(rotated),
                            radius=float(np.linalg.norm(v[:, :2], axis=1).max()),
                            diameter=diameter, footprint_area=_hull_area(v[:, :2])))
    if [sum(r['band'] == b for r in records) for b in ('chips', 'grit')] != [48, 16]:
        raise ValueError('Approved 48-chip / 16-grit bank membership changed')
    return records, mods[0].node_group, collection.name


class CameraProjection:
    """Read-only camera projection; avoids evaluating all particle instances."""
    def __init__(self, scene, width=2048, height=1365):
        camera = scene.camera
        if camera is None or camera.data.type != 'PERSP':
            raise ValueError('Density LOD currently requires the approved perspective camera')
        self.width, self.height = int(width), int(height)
        self.inverse = np.linalg.inv(np.asarray(camera.matrix_world, float))
        frame = np.asarray(camera.data.view_frame(scene=scene), float)
        tangents = frame[:, :2]/(-frame[:, 2, None])
        lo, hi = tangents.min(axis=0), tangents.max(axis=0)
        # Preserve the camera's existing fit/shift, with only the tiny native
        # aspect-ratio correction. This does not touch any camera/render setting.
        source_ratio = (hi[0]-lo[0])/(hi[1]-lo[1])
        desired_ratio = width*scene.render.pixel_aspect_x/(height*scene.render.pixel_aspect_y)
        if camera.data.sensor_fit == 'VERTICAL':
            centre = (hi[0]+lo[0])*.5
            half = (hi[0]-lo[0])*.5*desired_ratio/source_ratio
            lo[0], hi[0] = centre-half, centre+half
        else:
            centre = (hi[1]+lo[1])*.5
            half = (hi[1]-lo[1])*.5*source_ratio/desired_ratio
            lo[1], hi[1] = centre-half, centre+half
        self.f = np.array((width, height))/(hi-lo)
        self.offset = -lo*self.f
        self.near = max(float(camera.data.clip_start), 1e-5)
        self.name = camera.name
        self.lens = float(camera.data.lens)

    def with_pose(self, location, target, lens):
        other = object.__new__(CameraProjection)
        other.__dict__.update(self.__dict__)
        location, target = np.asarray(location, float), np.asarray(target, float)
        forward = target-location; forward /= np.linalg.norm(forward)
        right = np.cross(forward, (0., 0., 1.)); right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        other.inverse = np.eye(4)
        other.inverse[:3, :3] = np.stack((right, up, -forward))
        other.inverse[:3, 3] = -other.inverse[:3, :3] @ location
        other.f = self.f*(float(lens)/self.lens)
        other.name = 'Read-only lens diagnostic projection'
        other.lens = float(lens)
        return other

    def project(self, world):
        q = np.asarray(world) @ self.inverse[:3, :3].T + self.inverse[:3, 3]
        depth = -q[:, 2]
        safe = np.maximum(depth, self.near)
        uv = q[:, :2]/safe[:, None]*self.f+self.offset
        return uv, depth

    def visible(self, world, margin=0.):
        uv, depth = self.project(world)
        return ((depth > self.near) & (uv[:, 0] >= -margin) & (uv[:, 0] <= self.width+margin)
                & (uv[:, 1] >= -margin) & (uv[:, 1] <= self.height+margin))

    def area_vectors(self, world):
        q = np.asarray(world) @ self.inverse[:3, :3].T+self.inverse[:3, 3]
        d = np.maximum(-q[:, 2], self.near)
        j = np.zeros((len(q), 2, 3))
        j[:, 0, 0] = self.f[0]/d
        j[:, 1, 1] = self.f[1]/d
        j[:, 0, 2] = self.f[0]*q[:, 0]/d**2
        j[:, 1, 2] = self.f[1]*q[:, 1]/d**2
        j = j @ self.inverse[:3, :3]
        return np.cross(j[:, 0], j[:, 1])


class PackingIndex:
    """Actual enclosing footprint disks, no geometry enlargement or BVH."""
    def __init__(self, largest_radius):
        self.cell = max(2*largest_radius, .001)
        self.bins = {}

    def add(self, xy, radius):
        key = tuple(np.floor(np.asarray(xy)/self.cell).astype(int))
        self.bins.setdefault(key, []).append((float(xy[0]), float(xy[1]), float(radius)))

    def clear(self, xy, radius):
        ix, iy = np.floor(np.asarray(xy)/self.cell).astype(int)
        for i in range(ix-1, ix+2):
            for j in range(iy-1, iy+2):
                for x, y, r in self.bins.get((i, j), ()):
                    if (xy[0]-x)**2+(xy[1]-y)**2 < (radius+r)**2:
                        return False
        return True


def lod_fraction(diameter_px, factor=1.):
    """Full geometry at >=1 equivalent pixel; continuous .25–1 pixel transition."""
    t = np.clip((np.asarray(diameter_px)/factor-.25)/.75, 0., 1.)
    return t*t*(3-2*t)


def restore_approved_density(scene, surface, *, before_surface=None, burial_shift=None,
                             bounds=(-6.2, -3.20, -.65, 5.0), max_instances=320000,
                             width=2048, height=1365, cell_size=.12, exclusion=None, population_weights=None,
                             diagnostic_view=((-4.65, .40, .47), (-4.02, 1.65, .06), 55.)):
    """Add a budgeted density deficit, returning a JSON-serializable receipt.

    exclusion, if provided, is U's existing DiskIndex with clear(xy, radius), used
    to avoid retained larger clasts and newly authored lag bodies. before_surface
    and burial_shift implement exactly the same exposure rule as U's old grains.
    Re-running against a scene already containing OUTPUT is refused.
    """
    import bpy
    started = time.monotonic()
    if bpy.data.objects.get(OUTPUT) is not None:
        raise ValueError('Density supplement already exists; refuse duplicate restoration')
    if max_instances <= 0 or max_instances > 320000 or cell_size < .06:
        raise ValueError('Invalid bounded density budget/grid')
    obj = scene.objects.get(ORIGINS)
    if obj is None or not np.allclose(np.asarray(obj.matrix_world), np.eye(4), atol=1e-8):
        raise ValueError('Approved source origins missing or unexpectedly transformed')
    records, group, collection_name = _bank(obj)
    rng = np.random.default_rng(SEED)
    projection = CameraProjection(scene, width, height)
    views = [projection]
    if diagnostic_view is not None:
        views.append(projection.with_pose(*diagnostic_view))
    def visible(world, margin=0.):
        return np.logical_or.reduce([view.visible(world, margin) for view in views])
    x0, x1, y0, y1 = map(float, bounds)
    nx, ny = int(math.ceil((x1-x0)/cell_size)), int(math.ceil((y1-y0)/cell_size))
    dx, dy = (x1-x0)/nx, (y1-y0)/ny
    gx, gy = np.meshgrid(np.arange(nx), np.arange(ny))
    lower = np.column_stack((x0+gx.ravel()*dx, y0+gy.ravel()*dy))
    centre = lower+np.array((dx, dy))*.5
    heights = _height(surface, centre)
    world = np.column_stack((centre, heights))
    # Sixteen deterministic subcell samples estimate the screen-clipped area.
    offsets = np.array([(i, j) for i in (.125, .375, .625, .875) for j in (.125, .375, .625, .875)])
    sample_xy = lower[:, None, :]+offsets[None, :, :]*np.array((dx, dy))
    samples = np.concatenate((sample_xy, np.broadcast_to(heights[:, None, None], (len(heights), 16, 1))), axis=2)
    visible_fraction = visible(samples.reshape(-1, 3)).reshape(-1, 16).mean(axis=1)
    visible_area = visible_fraction*dx*dy
    projected = np.zeros((len(centre), 64))
    for view in views:
        area_jacobian = view.area_vectors(world)
        view_visible = view.visible(samples.reshape(-1, 3), margin=2.).reshape(-1, 16).any(axis=1)
        for r in records:
            # 0.5 Cauchy projected area, then average the four yaw samples.
            area = np.abs(area_jacobian @ r['area_vectors'].T).sum(axis=1)/8
            projected[:, r['index']] = np.maximum(projected[:, r['index']], area*view_visible)
    eq_diameter = np.sqrt(np.maximum(projected, 0)*4/math.pi)
    band = np.array([0 if r['band'] == 'chips' else 1 for r in records])
    densities = np.array([DENSITIES[r['band']]/(48 if r['band'] == 'chips' else 16) for r in records])
    physical_counts = visible_area[:, None]*densities[None, :]
    population_report = None
    if population_weights is not None:
        weights = np.asarray(population_weights(centre), float)
        if weights.shape != (len(centre), 2) or not np.isfinite(weights).all() or np.any(weights < 0):
            raise ValueError('Population weights must be finite nonnegative chip/grit columns')
        physical_counts *= weights[:, band]
        population_report = dict(weight_min_mean_max=[weights.min(0).tolist(),weights.mean(0).tolist(),weights.max(0).tolist()], meaning='Flow and original-scale deposit-conditioned scene population; intrinsic geometry/material unchanged')
    original = _world(obj, _co(obj.data))
    proto = np.empty(len(original), np.int32)
    obj.data.attributes['prototype'].data.foreach_get('value', proto)
    if np.any((proto < 0) | (proto >= 64)):
        raise ValueError('Existing source point prototype index is outside the approved bank')
    xx = np.floor((original[:, 0]-x0)/dx).astype(int)
    yy = np.floor((original[:, 1]-y0)/dy).astype(int)
    inside = ((xx >= 0) & (xx < nx) & (yy >= 0) & (yy < ny))
    existing = np.zeros_like(physical_counts, dtype=np.int32)
    valid = inside & visible(original)
    np.add.at(existing, (yy[valid]*nx+xx[valid], proto[valid]), 1)
    raw_target = physical_counts*lod_fraction(eq_diameter)
    def deficit(factor):
        return np.maximum(physical_counts*lod_fraction(eq_diameter, factor)-existing, 0.)
    raw_deficit = deficit(1.)
    factor = 1.
    if raw_deficit.sum() > max_instances:
        lo, hi = 1., 2.
        while deficit(hi).sum() > max_instances:
            hi *= 2
        for _ in range(24):
            middle = (lo+hi)*.5
            if deficit(middle).sum() > max_instances:
                lo = middle
            else:
                hi = middle
        factor = hi
    wanted_float = deficit(factor)
    quotas = np.floor(wanted_float).astype(np.int32)
    quotas += rng.random(quotas.shape) < wanted_float-quotas
    # Hard cap after unbiased stochastic integer rounding, without scaling bodies.
    overflow = int(quotas.sum())-int(max_instances)
    if overflow > 0:
        candidates = np.flatnonzero(quotas.ravel())
        for i in rng.choice(candidates, overflow, replace=False):
            quotas.ravel()[i] -= 1
    index = PackingIndex(max(r['radius'] for r in records))
    padded = ((original[:, 0] >= x0-.01) & (original[:, 0] <= x1+.01)
              & (original[:, 1] >= y0-.01) & (original[:, 1] <= y1+.01))
    for p, k in zip(original[padded], proto[padded]):
        index.add(p[:2], records[int(k)]['radius'])
    added_xy, added_proto, added_cell, yaws = [], [], [], []
    attempted = rejected = 0
    achieved = np.zeros_like(quotas)
    # Coarse-first hierarchy like the approved patch. Exact physical prototypes
    # have no size multiplier; resolvable grit has its own much larger quota.
    for b in (0, 1):
        for cell in np.flatnonzero(quotas[:, band == b].sum(axis=1)):
            todo = np.repeat(np.flatnonzero(band == b), quotas[cell, band == b])
            rng.shuffle(todo)
            for iteration in range(8):
                if not len(todo):
                    break
                candidates = lower[cell]+rng.random((len(todo), 2))*np.array((dx, dy))
                candidate_world = np.column_stack((candidates, np.full(len(todo), heights[cell])))
                in_frame = visible(candidate_world, margin=2.)
                retry = []
                for xy, k, in_view in zip(candidates, todo, in_frame):
                    attempted += 1
                    radius = records[int(k)]['radius']
                    clear = in_view and index.clear(xy, radius)
                    if clear and exclusion is not None:
                        clear = exclusion.clear(xy, radius)
                    if not clear:
                        retry.append(k); rejected += 1; continue
                    index.add(xy, radius)
                    added_xy.append(xy); added_proto.append(k); added_cell.append(cell)
                    yaws.append(rng.uniform(0, math.tau)); achieved[cell, k] += 1
                todo = np.asarray(retry, np.int32)
    xy = np.asarray(added_xy, float).reshape(-1, 2)
    pi = np.asarray(added_proto, np.int32)
    cell_ids = np.asarray(added_cell, np.int32)
    z_after = _height(surface, xy, allow_missing=True)
    supported = np.isfinite(z_after)
    unsupported = int(np.count_nonzero(~supported))
    # The true shoulder has a meandering asphalt boundary. Discard out-of-mesh
    # origins rather than analytically inventing soil over the pavement.
    if unsupported:
        np.add.at(achieved, (cell_ids[~supported], pi[~supported]), -1)
        xy, pi, cell_ids, z_after = xy[supported], pi[supported], cell_ids[supported], z_after[supported]
        yaws = np.asarray(yaws)[supported]
    if before_surface is not None:
        z_before = _height(before_surface, xy)
        delta = z_after-z_before
        shift = np.asarray(burial_shift(delta) if burial_shift else np.minimum(delta, 0)+.15*np.maximum(delta, 0))
        z = z_before+shift
    else:
        z_before = z_after.copy(); delta = np.zeros(len(xy)); z = z_after
    points = np.column_stack((xy, z)).astype('f4')
    rotation = np.zeros((len(points), 3), np.float32)
    rotation[:, 2] = np.asarray(yaws, np.float32)
    # Bounded contact audit uses final stored coordinates and every source vertex
    # for at most 256 bodies. Deliberately buried lens grains are retained.
    audit = []
    audit_boundary_vertices = 0
    if len(points):
        ids = np.unique(np.linspace(0, len(points)-1, min(256, len(points)), dtype=int))
        for i in ids:
            v = records[int(pi[i])]['vertices'].copy()
            c, s = math.cos(float(rotation[i, 2])), math.sin(float(rotation[i, 2]))
            v[:, :2] = v[:, :2] @ np.array(((c, -s), (s, c))).T
            v += points[i]
            contact = v[:, 2]-_height(surface, v[:, :2], allow_missing=True)
            audit_boundary_vertices += int(np.count_nonzero(~np.isfinite(contact)))
            contact = contact[np.isfinite(contact)]
            if len(contact):
                audit.append((float(contact.min()), float(contact.max())))
    # No old mesh is reassigned or modified. No new material, graph, image, or
    # prototype object is needed; shared GN instances stay unrealized.
    mesh = bpy.data.meshes.new(OUTPUT)
    mesh.vertices.add(len(points)); mesh.vertices.foreach_set('co', points.ravel())
    attribute = mesh.attributes.new('prototype', 'INT', 'POINT')
    attribute.data.foreach_set('value', pi)
    attribute = mesh.attributes.new('yaw', 'FLOAT_VECTOR', 'POINT')
    attribute.data.foreach_set('vector', rotation.ravel()); mesh.update()
    supplement = bpy.data.objects.new(OUTPUT, mesh); scene.collection.objects.link(supplement)
    modifier = supplement.modifiers.new('Exact approved metric R5D instances', 'NODES'); modifier.node_group = group
    bands = {}
    for name, b in (('chips', 0), ('grit', 1)):
        mask = band == b
        physical = float(physical_counts[:, mask].sum())
        lod_target = float(raw_target[:, mask].sum())
        old = int(existing[:, mask].sum()); new = int(achieved[:, mask].sum())
        accounted = np.minimum(existing[:, mask]+achieved[:, mask], physical_counts[:, mask])
        required_area = float((physical_counts[:, mask]*projected[:, mask]).sum())
        retained_area = float((accounted*projected[:, mask]).sum())
        d = np.array([r['diameter'] for r in records if r['band'] == name])*1000
        footprint = np.array([r['footprint_area'] for r in records if r['band'] == name])
        bands[name] = dict(source_density_per_m2=DENSITIES[name],bank_count=int(mask.sum()),
                           actual_bank_footprint_diameter_mm_min_median_max=[float(d.min()), float(np.median(d)), float(d.max())],
                           full_source_count_in_estimated_visible_area=physical,
                           full_density_world_footprint_area_sum_per_m2=float(DENSITIES[name]*footprint.mean()),
                           unbudgeted_projected_lod_target_count=lod_target,
                           existing_visible_count=old,requested_additions=int(quotas[:, mask].sum()),
                           added_count=new,packing_shortfall=int(quotas[:, mask].sum())-new,
                           source_count_fraction_bake_only=float(max(0., 1-accounted.sum()/physical)) if physical else 0.,
                           projected_exposed_area_proxy_sum_px2=required_area,
                           geometric_projected_area_proxy_retained_fraction=retained_area/required_area if required_area else 0.,
                           local_nominal_count_deficit_after=float(np.maximum(physical_counts[:, mask]-existing[:, mask]-achieved[:, mask], 0).sum()))
    audit = np.asarray(audit, float).reshape(-1, 2)
    return dict(object=OUTPUT,added_instances=len(points),maximum_additional_instances=max_instances,
                native_projection_resolution=[width, height],camera=projection.name,bounds_xy_m=list(bounds),
                diagnostic_readonly_projection=diagnostic_view,projection_allocation='Union of both frusta; maximum visible-view particle area, no camera datablock changes',
                actual_shoulder_boundary_rejected_origins=unsupported,
                spatial_cells=[nx, ny],estimated_screen_visible_ground_area_m2=float(visible_area.sum()),
                projection_grid_cell_m=[dx, dy],projection_fraction_samples_per_cell=16,
                lod_equivalent_diameter_transition_px=[.25*factor, 1.*factor],
                budget_threshold_multiplier=float(factor),unbudgeted_addition_expectation=float(raw_deficit.sum()),
                actual_attempts=attempted,packing_or_frame_rejections=rejected,
                bands=bands,population_sorting=population_report,prototype_collection=collection_name,prototype_index_order='Natural numeric child-name order, verified from all64 evaluated Blender instances',
                prototype_geometry_and_materials_unchanged=True,instance_scale=[1, 1, 1],
                old_objects_and_node_graphs_unchanged=True,new_materials=0,new_images=0,
                source_sand_count_per_m2=DENSITIES['sand'],sand_geometry_added=0,
                baked_source_resolution_px=1024,baked_source_extent_m=.18,bake_texel_world_mm=.18/1024*1000,
                source_conservative_occupied_mask_fraction=.35925725,
                compensation='None: no arbitrary AO, darkening, material tint, larger grain substitution, or shader redesign',
                burial_rule='Source triangle datum plus supplied U loose_shift(final minus source datum)',
                additional_burial_min_max_m=[float((z_after-z).min(initial=0)), float((z_after-z).max(initial=0))],
                contact_audited_bodies=len(audit),contact_audit_outside_shoulder_vertices=audit_boundary_vertices,contact_audit_fully_buried=int(np.sum(audit[:, 1] < 0)),
                contact_audit_floating_over_20um=int(np.sum(audit[:, 0] > .00002)),
                contact_audit_min_max_m=[float(audit[:, 0].min(initial=0)), float(audit[:, 1].max(initial=0))],
                larger_clast_exclusion_supplied=exclusion is not None,
                limits=['Full source count is restored only where projected LOD and finite packing budget permit; this is not all-grain geometric equivalence.',
                        'Projected face-area sum is a first-order four-yaw convex silhouette proxy; concavities can overestimate it, and it is not a measured render occlusion fraction.',
                        'Visibility is camera-frustum clipping only, not terrain/road/vegetation occlusion; some conservative instances can be hidden.',
                        'Source 1024 bake retains unresolved sand/grit appearance but cannot reproduce their cast shadows, parallax, interreflection, or displaced silhouette.',
                        'The source occupied mask fraction includes all three classes; prototype area sums are not a disjoint coverage union and must not be equated to that mask.',
                        'Circumscribed disks conservatively pack new instances against retained exact grains; source overlaps are not repaired.',
                        'Only the existing 48 chips and 16 grit prototypes represent their respective source populations; no source sand prototypes are synthesized.',
                        'Burial and surface slopes can further reduce visible grain area; the reported LOD retention is an allocation proxy, not rendered visibility.'],
                elapsed_seconds=time.monotonic()-started)
