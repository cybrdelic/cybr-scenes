#!/usr/bin/env python3
"""Bounded U shoulder specimen, derived only from immutable S. Never renders.

Run: blender -b -t 2 --python-exit-code 1 --python src/prepare_physical_lenses.py
Pure NumPy profile/contact tests can import this module without Blender.

Two interrupted millimetre-thick fine-sediment lenses and adjacent scours modify
EXISTING ground vertices. No extra ground sheets, image textures or shader edits.
The dimensions, sorting and partial burial are authored static exposure, not a
sediment-transport simulation or measured Victorville site reconstruction.
"""
from __future__ import annotations
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '2'
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'relief_correction/road_r6_s_coupled.blend'
OUTPUT = ROOT / 'preview/road_r6_u_physical_lenses.blend'
RECEIPT = ROOT / 'receipts/physical_lenses_u.json'
SOURCE_SHA256 = 'bc56aca669fe4fa01f4801a36aefe74d3f9eced5fdee4f32f01c470ab89706b6'
GROUND = 'Graded shoulder and alluvial plain -1'
ORIGINS = 'True approved R5D near-camera grain geometry'
RIGID = ('Sparse physical 7–31 mm roadside mineral lag',
         'Gravel lag pockets beside shallow runoff arms',
         'Connected drainage / margin gravel bars')
PLANT_PREFIXES = ('Scrub group /', 'Established irregular', 'Scrub patch /', 'Sparse dry straw')
# The actual T2 visible feeder; the two deposits are on its outward bank.
FEEDER = ((-3.55, 4.25), (-3.87, 3.20), (-3.94, 1.90), (-4.28, .10))
# centre XY, cross half-width, along half-length, downstream vector, phase, height
LENSES = (((-4.085, 2.94), .275, .48, (-.07, -1.30), .45, .0063),
          ((-4.205, 1.22), .320, .51, (-.34, -1.80), 2.20, .0073))
SCOURS = (((-3.885, 3.49), .105, .365, (-.07, -1.30), 1.10, .0083),
          ((-4.015, 1.84), .112, .335, (-.34, -1.80), 2.60, .0092))
EDIT_BOUNDS = (-4.70, -3.70, .60, 4.00)
PATCH_BOUNDS = (-4.90, -3.50, .38, 4.22)
SEED = 2610100216
MAX_NEW_GRAINS = 1500


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def smooth(a, b, value):
    t = np.clip((np.asarray(value) - a) / (b - a), 0., 1.)
    return t * t * (3. - 2. * t)


def in_bounds(xy, bounds=EDIT_BOUNDS, pad=0.):
    x0, x1, y0, y1 = bounds
    return ((xy[..., 0] >= x0-pad) & (xy[..., 0] <= x1+pad)
            & (xy[..., 1] >= y0-pad) & (xy[..., 1] <= y1+pad))


def shape_coordinates(x, y, spec):
    centre, width, half_length, direction, phase, _ = spec
    d = np.asarray(direction, dtype=float)
    d /= np.linalg.norm(d)
    outward = np.array((d[1], -d[0]))
    dx, dy = x-centre[0], y-centre[1]
    along = (dx*d[0] + dy*d[1]) / half_length
    cross = (dx*outward[0] + dy*outward[1]) / width
    angle = np.arctan2(along, cross)
    # A compact superellipse with irregular, shallowly scalloped edges. Its
    # plateau is explicitly constant; no radial Gaussian or blanket noise.
    irregular = 1 + .075*np.sin(3*angle+phase) + .038*np.sin(7*angle-phase)
    radius = (np.abs(along)**3.2 + np.abs(cross)**3.2)**(1/3.2) / irregular
    return radius, along, cross


def profile_fields(x, y):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    x0, x1, y0, y1 = EDIT_BOUNDS
    gate = (smooth(x0, x0+.07, x) * (1-smooth(x1-.07, x1, x))
            * smooth(y0, y0+.06, y) * (1-smooth(y1-.07, y1, y)))
    deposits, cuts = [], []
    lag = np.zeros(x.shape)
    for spec in LENSES:
        r, along, cross = shape_coordinates(x, y, spec)
        plateau = (1-smooth(.69, 1., r))*gate
        deposits.append(plateau)
        # An interrupted OUTWARD lag bench; avoid a decorative complete ring.
        margin = smooth(.72, .87, r)*(1-smooth(1.03, 1.22, r))
        side = smooth(-.08, .48, cross)
        broken = smooth(-.18, .46, np.sin(5.2*along+spec[4])+.30*np.sin(11*along))
        lag = np.maximum(lag, margin*side*broken*gate)
    dep = np.maximum.reduce(deposits)
    for spec in SCOURS:
        r, along, cross = shape_coordinates(x, y, spec)
        cut = (1-smooth(.38, 1., r))*gate*(1-dep)
        cuts.append(cut)
        lip = smooth(.70, .95, cross)*(1-smooth(1.1, 1.65, cross))
        reach = 1-smooth(.62, .95, np.abs(along))
        broken = smooth(-.25, .40, np.sin(5.8*along+spec[4]))
        lag = np.maximum(lag, lip*reach*broken*gate*(1-.75*dep))
    return deposits, cuts, np.clip(lag, 0, 1)


def displacement(xyz, planes=None):
    deposits, cuts, lag = profile_fields(xyz[..., 0], xyz[..., 1])
    positives = []
    for i, (spec, weight) in enumerate(zip(LENSES, deposits)):
        thickness = np.full(weight.shape, spec[5])
        if planes is not None:
            plane = planes[i]
            top = xyz[..., 0]*plane[0] + xyz[..., 1]*plane[1] + plane[2] + spec[5]
            # Locally planar plateau; retain 4–8 mm bounds if an existing rut
            # prevents a completely flat top. Report that limitation explicitly.
            thickness = np.clip(top-xyz[..., 2], .004, .008)
        positives.append(weight*thickness)
    positive = np.maximum.reduce(positives)
    negative = np.maximum.reduce([w*spec[5] for w, spec in zip(cuts, SCOURS)])
    # A shallow connected feeder joins the deeper scour reaches beside the
    # interrupted deposits. Its flat-bottomed 0.10–0.16 m bed is continuous,
    # while the outer fine-sediment lenses remain separate on the lower bank.
    xy = xyz[..., :2]
    connected = np.zeros(negative.shape)
    for start, end in zip(FEEDER[:-1], FEEDER[1:]):
        a, b = np.asarray(start), np.asarray(end)
        direction = b-a
        t = np.clip(np.sum((xy-a)*direction, axis=-1)/np.dot(direction, direction), 0, 1)
        closest = a+t[..., None]*direction
        distance = np.linalg.norm(xy-closest, axis=-1)
        half_width = .070+.010*np.sin(4.1*closest[..., 1]+.7)
        profile = 1-smooth(.38, 1., distance/half_width)
        connected = np.maximum(connected, profile*.0035)
    x0, x1, y0, y1 = EDIT_BOUNDS
    connected *= (smooth(x0,x0+.07,xy[...,0])*(1-smooth(x1-.07,x1,xy[...,0]))
                  *smooth(y0,y0+.06,xy[...,1])*(1-smooth(y1-.07,y1,xy[...,1])))
    connected *= 1-np.maximum.reduce(deposits)
    negative = np.maximum(negative, connected)
    return positive-negative, deposits, cuts, lag


class TrianglePatch:
    """Small exact triangle interpolator with a bounded XY spatial hash.

    Input triangles come from Blender's ACTUAL loop tessellation before/after
    deformation. No analytical terrain function participates in contact queries.
    """
    def __init__(self, vertices, triangles, cell=.045):
        self.vertices = np.asarray(vertices, float)
        self.triangles = np.asarray(triangles, np.int32)
        self.cell = cell
        self.tri = self.vertices[self.triangles]
        # The retained L grid has coincident float32 Y rows at some overlapping
        # arange boundaries. Blender ignores their zero-footprint triangles.
        # They contribute no XY surface; skip them, never extrapolate a gap.
        a = self.tri[:, 1, :2]-self.tri[:, 0, :2]
        b = self.tri[:, 2, :2]-self.tri[:, 0, :2]
        valid = np.abs(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0]) > 1e-13
        self.discarded_zero_footprint_triangles = int(np.count_nonzero(~valid))
        self.triangles = self.triangles[valid]
        self.tri = self.tri[valid]
        if not len(self.tri):
            raise ValueError('Local patch has no nondegenerate XY surface triangles')
        self.bins = {}
        lo = np.floor(self.tri[:, :, :2].min(axis=1)/cell).astype(int)
        hi = np.floor(self.tri[:, :, :2].max(axis=1)/cell).astype(int)
        if np.any(hi-lo > 6):
            raise ValueError('Local shoulder grid unexpectedly coarse; do not guess contact')
        for index, (a, b) in enumerate(zip(lo, hi)):
            for ix in range(a[0], b[0]+1):
                for iy in range(a[1], b[1]+1):
                    self.bins.setdefault((ix, iy), []).append(index)
        self.bins = {k: np.asarray(v, np.int32) for k, v in self.bins.items()}

    def height(self, xy):
        shape = np.shape(xy)[:-1]
        p = np.asarray(xy, float).reshape(-1, 2)
        answer = np.full(len(p), np.nan)
        keys, inverse = np.unique(np.floor(p/self.cell).astype(np.int32), axis=0, return_inverse=True)
        for number, key in enumerate(keys):
            rows = np.flatnonzero(inverse == number)
            indices = self.bins.get(tuple(key))
            if indices is None:
                continue
            t = self.tri[indices]
            a, b, c = t[:, 0], t[:, 1], t[:, 2]
            v0, v1 = b[:, :2]-a[:, :2], c[:, :2]-a[:, :2]
            det = v0[:, 0]*v1[:, 1]-v0[:, 1]*v1[:, 0]
            if np.any(np.abs(det) < 1e-13):
                raise ValueError('Degenerate terrain triangle')
            q = p[rows, None, :]-a[None, :, :2]
            u = (q[..., 0]*v1[:, 1]-q[..., 1]*v1[:, 0])/det
            v = (v0[:, 0]*q[..., 1]-v0[:, 1]*q[..., 0])/det
            inside = (u >= -2e-7) & (v >= -2e-7) & (u+v <= 1+2e-7)
            z = a[:, 2] + u*(b[:, 2]-a[:, 2]) + v*(c[:, 2]-a[:, 2])
            # Shared edges agree to float tolerance. Highest hit is conservative.
            z[~inside] = -np.inf
            best = z.max(axis=1)
            answer[rows] = np.where(np.isfinite(best), best, np.nan)
        if not np.all(np.isfinite(answer)):
            raise ValueError(f'{np.count_nonzero(~np.isfinite(answer))} contact queries leave exact local triangle patch')
        return answer.reshape(shape)


class DiskIndex:
    """Conservative projected nonintersection, including buried source grains."""
    def __init__(self, cell=.025):
        self.cell, self.bins, self.count = cell, {}, 0

    def add(self, xy, radius):
        lo = np.floor((np.asarray(xy)-radius)/self.cell).astype(int)
        hi = np.floor((np.asarray(xy)+radius)/self.cell).astype(int)
        entry = (float(xy[0]), float(xy[1]), float(radius), self.count)
        self.count += 1
        for ix in range(lo[0], hi[0]+1):
            for iy in range(lo[1], hi[1]+1):
                self.bins.setdefault((ix, iy), []).append(entry)

    def clear(self, xy, radius, gap=.00035):
        reach = radius+gap
        lo = np.floor((np.asarray(xy)-reach)/self.cell).astype(int)
        hi = np.floor((np.asarray(xy)+reach)/self.cell).astype(int)
        seen = set()
        for ix in range(lo[0], hi[0]+1):
            for iy in range(lo[1], hi[1]+1):
                for x, y, r, index in self.bins.get((ix, iy), ()):
                    if index in seen:
                        continue
                    seen.add(index)
                    if (xy[0]-x)**2+(xy[1]-y)**2 < (radius+r+gap)**2:
                        return False
        return True


def read_coordinates(mesh):
    co = np.empty((len(mesh.vertices), 3), np.float32)
    mesh.vertices.foreach_get('co', co.ravel())
    return co


def world_coordinates(obj, co):
    m = np.asarray(obj.matrix_world, dtype=float)
    return np.asarray(co, float) @ m[:3, :3].T + m[:3, 3]


def write_world_z(obj, original_local, world_dz):
    # Rigid world translation per selected vertex, even for a transformed object.
    vector = np.linalg.inv(np.asarray(obj.matrix_world, float)[:3, :3]) @ np.array((0., 0., 1.))
    new = (original_local.astype(float) + np.asarray(world_dz)[:, None]*vector).astype('f4')
    obj.data.vertices.foreach_set('co', new.ravel())
    obj.data.update()
    return new


def exact_patch(obj, bounds=PATCH_BOUNDS, max_triangles=65000):
    """Only local triangles enter the interpolator, never a full-scene BVH.

    Blender tessellates this one existing mesh. A transient 3-int buffer reads
    its loop triangles, then is immediately reduced; peak Python buffers are
    bounded by this mesh, not evaluated particle instances or the whole scene.
    """
    co = read_coordinates(obj.data)
    world = world_coordinates(obj, co)
    local = in_bounds(world[:, :2], bounds, .045)
    obj.data.calc_loop_triangles()
    tris = np.empty((len(obj.data.loop_triangles), 3), np.int32)
    obj.data.loop_triangles.foreach_get('vertices', tris.ravel())
    tris = tris[np.any(local[tris], axis=1)]
    used, inverse = np.unique(tris, return_inverse=True)
    if len(tris) > max_triangles or len(tris) < 500:
        raise ValueError(f'Unexpected local patch triangle count {len(tris)}')
    return TrianglePatch(world[used], inverse.reshape(-1, 3))


def fit_plateaus(world):
    planes = []
    for spec in LENSES:
        r, _, _ = shape_coordinates(world[:, 0], world[:, 1], spec)
        points = world[r < .74]
        if len(points) < 40:
            raise ValueError('Insufficient existing vertices to resolve a lens plateau')
        design = np.column_stack((points[:, :2], np.ones(len(points))))
        planes.append(np.linalg.lstsq(design, points[:, 2], rcond=None)[0])
    return planes


def ground_edit(obj):
    if obj.modifiers or obj.data.shape_keys or obj.data.users != 1:
        raise ValueError('Ground is shared or has evaluated deformation; source-surface contact requires explicit support')
    co = read_coordinates(obj.data)
    world = world_coordinates(obj, co)
    select = in_bounds(world[:, :2])
    ids = np.flatnonzero(select)
    local = world[ids]
    planes = fit_plateaus(local)
    dz, deps, cuts, lag = displacement(local, planes)
    full_dz = np.zeros(len(co))
    full_dz[ids] = dz
    before = exact_patch(obj)
    new = write_world_z(obj, co, full_dz)
    if not np.array_equal(co[~select], new[~select]):
        raise AssertionError('Geometry outside bounded shoulder footprint changed')
    after = exact_patch(obj)
    plateau_records = []
    for spec, weight, plane in zip(LENSES, deps, planes):
        core = weight > .999
        requested = local[core, 0]*plane[0] + local[core, 1]*plane[1] + plane[2]+spec[5]-local[core, 2]
        plateau_records.append(dict(centre=list(spec[0]),target_height_m=spec[5],
                                    plane_coefficients=plane.tolist(),core_vertices=int(core.sum()),
                                    clipped_core_fraction=float(np.mean((requested < .004) | (requested > .008)))))
    report = dict(object=obj.name,total_vertices=len(co),changed_vertices=int(np.count_nonzero(full_dz)),
                  existing_topology_unchanged=True,extra_ground_sheets=0,bounds_xy_m=EDIT_BOUNDS,
                  vertex_displacement_min_max_m=[float(dz.min()), float(dz.max())],
                  source_patch_triangles=len(before.triangles),final_patch_triangles=len(after.triangles),
                  ignored_zero_footprint_triangles=[before.discarded_zero_footprint_triangles, after.discarded_zero_footprint_triangles],
                  plateaus=plateau_records,outside_bounds_coordinate_bytes_unchanged=True,
                  macro_tint_and_material_unchanged=True)
    return before, after, report


def loose_shift(delta):
    # Eroded particles settle with the exact final triangle datum. Fine sediment
    # covers existing grains: only 15% of positive datum rise moves their body.
    # Geometry and metric sizes remain rigid and exact.
    return np.minimum(delta, 0.) + .15*np.maximum(delta, 0.)


def local_components(mesh, world):
    """Find complete nearby disconnected grain bodies, without a global graph."""
    local = in_bounds(world[:, :2], PATCH_BOUNDS, -.015)
    counts = np.empty(len(mesh.polygons), np.int32)
    mesh.polygons.foreach_get('loop_total', counts)
    if not np.all(counts == 3):
        raise ValueError('Rigid grain mesh must retain triangular fracture topology')
    loops = np.empty(len(mesh.loops), np.int32)
    mesh.loops.foreach_get('vertex_index', loops)
    triangles = loops.reshape(-1, 3)
    nearby = triangles[np.any(local[triangles], axis=1)]
    if not len(nearby):
        return []
    ids, inverse = np.unique(nearby, return_inverse=True)
    parent = np.arange(len(ids), dtype=np.int32)
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b, c in inverse.reshape(-1, 3):
        ra = root(a)
        parent[root(b)] = ra
        parent[root(c)] = ra
    labels = np.array([root(i) for i in range(len(ids))])
    order = np.argsort(labels)
    cuts = np.flatnonzero(np.diff(labels[order]))+1
    components = [ids[group] for group in np.split(order, cuts)]
    # A body cut at the extraction collar cannot touch the edit footprint. Refuse
    # instead of accidentally moving only some vertices of a source prototype.
    for component in components:
        if np.any(in_bounds(world[component, :2], EDIT_BOUNDS, .03)) and not np.all(local[component]):
            raise ValueError('Editable rigid body crosses bounded component extraction collar')
    return [c for c in components if np.all(local[c])]


def move_existing(scene, before, after, disks):
    records = []
    obj = scene.objects.get(ORIGINS)
    if obj is None:
        raise ValueError('Approved R5D instance origins are missing')
    co = read_coordinates(obj.data)
    world = world_coordinates(obj, co)
    # Origins outside the edited footprint have exactly zero displacement.
    # Do not query an expanded collar that may cross the real asphalt boundary.
    mask = in_bounds(world[:, :2], EDIT_BOUNDS)
    ids = np.flatnonzero(mask)
    delta = after.height(world[ids, :2])-before.height(world[ids, :2])
    shifts = np.zeros(len(co)); shifts[ids] = loose_shift(delta)
    write_world_z(obj, co, shifts)
    # Conservative maximum source-prototype projected radius, including its
    # origin offset. No evaluation or scaling of the approved geometry occurs.
    collections = [n.inputs['Collection'].default_value for m in obj.modifiers if m.type == 'NODES'
                   for n in m.node_group.nodes if n.bl_idname == 'GeometryNodeCollectionInfo']
    if len(collections) != 1 or collections[0] is None:
        raise ValueError('Cannot verify approved grain instance source')
    radii = []
    for proto in collections[0].objects:
        v = read_coordinates(proto.data)
        scale = np.max(np.linalg.svd(np.asarray(proto.matrix_world)[:2, :2], compute_uv=False))
        radii.append(float(np.linalg.norm(v[:, :2], axis=1).max()*scale))
    radius = max(radii)
    for p in world[mask, :2]:
        disks.add(p, radius)
    records.append(dict(object=obj.name,moved_origins=int(np.count_nonzero(shifts)),
                        deposition_burial_increase_max_m=float(np.maximum(delta, 0).max(initial=0)*.85),
                        conservative_instance_exclusion_radius_m=radius,prototype_geometry_changed=False))
    color_bank = []
    for name in RIGID:
        obj = scene.objects.get(name)
        if obj is None:
            raise ValueError(f'Expected retained source grain object is missing: {name}')
        if obj.modifiers or obj.data.shape_keys or obj.data.users != 1:
            raise ValueError(f'Cannot safely edit shared/evaluated rigid grains: {name}')
        co = read_coordinates(obj.data); world = world_coordinates(obj, co)
        components = local_components(obj.data, world)
        shifts = np.zeros(len(co)); changed = 0
        for component in components:
            v = world[component]
            centre = (v[:, :2].min(axis=0)+v[:, :2].max(axis=0))*.5
            radius = float(np.linalg.norm(v[:, :2]-centre, axis=1).max())
            if in_bounds(centre[None], EDIT_BOUNDS, .07)[0]:
                disks.add(centre, radius)
            if in_bounds(centre[None])[0]:
                delta = float(after.height(centre)-before.height(centre))
                shift = float(loose_shift(delta))
                if abs(shift) > 1e-10:
                    shifts[component] = shift; changed += 1
            if name == RIGID[1]:
                index = int(component[0])
                color_bank.append((tuple(obj.data.color_attributes['mineral'].data[index].color),
                                   float(obj.data.attributes['grain_roughness'].data[index].value)))
        if np.any(shifts):
            write_world_z(obj, co, shifts)
        records.append(dict(object=name,nearby_complete_rigid_components=len(components),moved_bodies=changed,
                            geometry_action='One uniform world-Z translation per complete component'))
    # The local strip may have very few original K clasts. Their exact stored
    # mineral/roughness pairs are sampled globally in that case, never recolored.
    bank_obj = scene.objects[RIGID[1]]
    if len(color_bank) < 32:
        for index in np.linspace(0, len(bank_obj.data.vertices)-1, 96, dtype=int):
            color_bank.append((tuple(bank_obj.data.color_attributes['mineral'].data[int(index)].color),
                               float(bank_obj.data.attributes['grain_roughness'].data[int(index)].value)))
    roots = []
    for obj in scene.objects:
        if not obj.name.startswith(PLANT_PREFIXES):
            continue
        p = np.array(obj.matrix_world.translation, float)
        if in_bounds(p[None, :2])[0]:
            delta = float(after.height(p[:2])-before.height(p[:2]))
            if abs(delta) > 1e-10:
                matrix = obj.matrix_world.copy(); matrix.translation.z += delta; obj.matrix_world = matrix
                roots.append(dict(object=obj.name,world_z_translation_m=delta))
    return records, roots, color_bank, bank_obj.data.materials[0]


def add_grit(scene, patch, disks, color_bank, material):
    import bpy
    rng = np.random.default_rng(SEED)
    prototype_file = ROOT.parent/'discrete_grains_r5/prototypes/fracture_solids.json'
    prototypes = json.loads(prototype_file.read_text())
    candidates = rng.uniform([EDIT_BOUNDS[0], EDIT_BOUNDS[2]], [EDIT_BOUNDS[1], EDIT_BOUNDS[3]], (28000, 2))
    deposits, cuts, lag = profile_fields(candidates[:, 0], candidates[:, 1])
    dep = np.maximum.reduce(deposits)
    # No uniform background term. Real fragments occupy only bounded connected
    # lag benches, and their coarser tail increases toward the bench crest.
    keep = (lag > .08) & (rng.random(len(lag)) < .40*lag**1.45*(1-.8*dep))
    indices = np.flatnonzero(keep)
    vertices, faces, colors, roughness, diameters, burials, gaps = [], [], [], [], [], [], []
    rejected = 0
    for index in indices:
        if len(diameters) >= MAX_NEW_GRAINS:
            break
        xy = candidates[index]; strength = lag[index]
        diameter = float(np.clip(rng.lognormal(np.log(.00415+.00045*strength), .34), .002, .011))
        prototype = prototypes[int(rng.integers(len(prototypes)))]
        v = np.asarray(prototype['vertices'], float).copy()
        v[:, :2] -= (v[:, :2].max(axis=0)+v[:, :2].min(axis=0))*.5
        v[:, 1] *= rng.uniform(.56, .90)
        # Calibrate the actual maximum footprint pair-distance, rather than
        # pretending the nominal X multiplier is a physical particle diameter.
        span = np.sqrt(np.max(np.sum((v[:, None, :2]-v[None, :, :2])**2, axis=-1)))
        v[:, :2] *= diameter/span
        angle = rng.uniform(0, math.tau); c, s = math.cos(angle), math.sin(angle)
        v[:, :2] = v[:, :2] @ np.array(((c, -s), (s, c))).T
        thickness = diameter*rng.uniform(.25, .42)
        v[:, 2] = (v[:, 2]-v[:, 2].min())/np.ptp(v[:, 2])*thickness
        radius = float(np.linalg.norm(v[:, :2], axis=1).max())
        if not disks.clear(xy, radius):
            rejected += 1; continue
        v[:, :2] += xy
        surface_z = patch.height(v[:, :2])
        burial = rng.uniform(.34, .60)
        v[:, 2] += float(np.max(surface_z-v[:, 2]))-burial*thickness
        # Contact is sampled at every final footprint vertex, after float32
        # storage quantization. The rigid solid crosses the real surface.
        v = v.astype('f4')
        contact = v[:, 2]-patch.height(v[:, :2])
        if not (contact.min() < -.0001 and contact.max() > .0001):
            rejected += 1; continue
        disks.add(xy, radius)
        offset = len(vertices); vertices.extend(v.tolist())
        faces.extend(tuple(offset+i for i in face) for face in prototype['faces'])
        color, rough = color_bank[int(rng.integers(len(color_bank)))]
        colors.extend([color]*len(v)); roughness.extend([rough]*len(v))
        diameters.append(diameter); burials.append(burial); gaps.append([float(contact.min()), float(contact.max())])
    if len(diameters) < 80:
        raise ValueError(f'Only {len(diameters)} conservative new fragments fit; inspect scene, do not weaken contacts')
    mesh = bpy.data.meshes.new('U bounded 2–11 mm angular shoulder lag')
    mesh.from_pydata(vertices, [], faces); mesh.materials.append(material); mesh.update()
    attr = mesh.color_attributes.new(name='mineral', type='FLOAT_COLOR', domain='POINT')
    attr.data.foreach_set('color', np.asarray(colors, 'f4').ravel())
    attr = mesh.attributes.new(name='grain_roughness', type='FLOAT', domain='POINT')
    attr.data.foreach_set('value', np.asarray(roughness, 'f4'))
    obj = bpy.data.objects.new('U physical lenses / sorted angular lag margins', mesh)
    scene.collection.objects.link(obj)
    d = np.asarray(diameters)
    return dict(object=obj.name,count=len(d),candidate_count=len(indices),overlap_or_contact_rejections=rejected,
                actual_footprint_diameter_mm_min_median_max=(1000*np.array([d.min(), np.median(d), d.max()])).tolist(),
                diameter_quantiles_mm=(1000*np.quantile(d, [.1, .25, .5, .75, .9])).tolist(),
                grain_thickness_to_diameter=[.25, .42],authored_burial_fraction_range=[min(burials), max(burials)],
                stored_vertex_contact_offsets_m=[float(np.min(gaps)), float(np.max(gaps))],
                prototype_file=str(prototype_file.relative_to(ROOT.parent)),prototype_sha256=sha256(prototype_file),
                material=material.name,mineral_and_roughness_source=RIGID[1],source_attribute_pairs_copied_exactly=True,
                added_image_textures=0,minimum_projected_clearance_m=.00035,
                nonoverlap='Conservative enclosing disks against retained local clasts, approved grain instances and new grit')


def data_digest(collection, prop, size, dtype):
    arr = np.empty(len(collection)*size, dtype=dtype)
    collection.foreach_get(prop, arr)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def stable_value(value):
    """Serialize shader values without process-local RNA pointer addresses."""
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    rna = getattr(value, 'bl_rna', None)
    if rna is not None:
        kind = rna.identifier
        if kind == 'ColorRamp':
            return dict(type=kind, color_mode=value.color_mode,
                        interpolation=value.interpolation,
                        hue_interpolation=value.hue_interpolation,
                        elements=[dict(position=float(e.position), color=list(e.color))
                                  for e in value.elements])
        if kind == 'CurveMapping':
            return dict(type=kind, black_level=list(value.black_level),
                        white_level=list(value.white_level),
                        clip_min_x=value.clip_min_x, clip_min_y=value.clip_min_y,
                        clip_max_x=value.clip_max_x, clip_max_y=value.clip_max_y,
                        use_clip=value.use_clip, extend=value.extend, tone=value.tone,
                        curves=[[dict(location=list(p.location), handle_type=p.handle_type)
                                 for p in curve.points] for curve in value.curves])
        if kind == 'ImageUser':
            names = ('frame_current', 'frame_duration', 'frame_offset', 'frame_start',
                     'multilayer_layer', 'multilayer_pass', 'multilayer_view', 'tile',
                     'use_auto_refresh', 'use_cyclic')
            return dict(type=kind, **{name: stable_value(getattr(value, name)) for name in names})
        if kind in {'TexMapping', 'ColorMapping'}:
            fields = dict(type=kind)
            for prop in rna.properties:
                if prop.identifier == 'rna_type':
                    continue
                scalar = prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}
                ramp = kind == 'ColorMapping' and prop.identifier == 'color_ramp' and prop.type == 'POINTER'
                if not (scalar or ramp):
                    raise ValueError(f'Unsupported fingerprint property: {kind}.{prop.identifier}/{prop.type}')
                fields[prop.identifier] = stable_value(getattr(value, prop.identifier))
            return fields
        # A name alone does not make an RNA struct an ID datablock. Inspect its
        # RNA ancestry without importing bpy, so pure source tests stay usable.
        base = rna
        while base is not None:
            if base.identifier == 'ID':
                return ('ID', value.name)
            base = getattr(base, 'base', None)
        raise ValueError('Unsupported non-ID RNA pointer in fingerprint: '+kind)
    try:
        return [stable_value(item) for item in value]
    except TypeError:
        raise ValueError('Unsupported fingerprint value: '+type(value).__name__) from None


def graph_signature(tree):
    if tree is None:
        return None
    nodes = []
    for node in tree.nodes:
        props = []
        for prop in node.bl_rna.properties:
            if prop.identifier in {'rna_type', 'location', 'dimensions', 'select', 'inputs', 'outputs', 'internal_links', 'parent'}:
                continue
            if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM', 'POINTER'}:
                try:
                    value = getattr(node, prop.identifier)
                except (AttributeError, TypeError):
                    continue
                # Serialization failures must not silently omit protected data.
                props.append((prop.identifier, stable_value(value)))
        sockets = [(side, sock.identifier, stable_value(sock.default_value))
                   for side, sequence in [('in', node.inputs), ('out', node.outputs)]
                   for sock in sequence if hasattr(sock, 'default_value')]
        nodes.append((node.name, node.bl_idname, props, sockets))
    links = [(l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier) for l in tree.links]
    return hashlib.sha256(json.dumps([nodes, links], sort_keys=True).encode()).hexdigest()


def protected_snapshot(bpy, existing_objects, mutable_meshes, movable_roots):
    """One-mesh-at-a-time fingerprints; never evaluates source grain instances."""
    objects, meshes = {}, {}
    schema = {'FLOAT': ('value', 1, 'f4'), 'INT': ('value', 1, 'i4'), 'BOOLEAN': ('value', 1, bool),
              'FLOAT_VECTOR': ('vector', 3, 'f4'), 'FLOAT_COLOR': ('color', 4, 'f4'), 'BYTE_COLOR': ('color', 4, 'f4'),
              'FLOAT2': ('vector', 2, 'f4'), 'INT8': ('value', 1, 'i4')}
    for obj in existing_objects:
        matrix = np.asarray(obj.matrix_world).copy()
        if obj.name in movable_roots:
            matrix[2, 3] = 0
        objects[obj.name] = [obj.type, getattr(obj.data, 'name', None), matrix.tolist(),
                             obj.hide_render, obj.hide_viewport]
        if obj.type != 'MESH' or obj.data.name in meshes:
            continue
        mesh = obj.data
        record = dict(vertices=len(mesh.vertices),polygons=len(mesh.polygons),
                      loops=data_digest(mesh.loops, 'vertex_index', 1, 'i4'),
                      starts=data_digest(mesh.polygons, 'loop_start', 1, 'i4'),
                      counts=data_digest(mesh.polygons, 'loop_total', 1, 'i4'),
                      smooth=data_digest(mesh.polygons, 'use_smooth', 1, bool),
                      material_indices=data_digest(mesh.polygons, 'material_index', 1, 'i4'),
                      materials=[m.name if m else None for m in mesh.materials],attributes={})
        if mesh.name not in mutable_meshes:
            record['coordinates'] = data_digest(mesh.vertices, 'co', 3, 'f4')
        for attr in mesh.attributes:
            if attr.name == 'position':
                continue
            if attr.data_type in schema:
                prop, size, dtype = schema[attr.data_type]
                record['attributes'][attr.name] = [attr.domain, attr.data_type, data_digest(attr.data, prop, size, dtype)]
            elif not attr.name.startswith('.'):
                raise ValueError(f'Cannot certify unsupported retained attribute {attr.name}/{attr.data_type}')
        meshes[mesh.name] = record
    graphs = {f'material/{m.name}': graph_signature(m.node_tree) for m in bpy.data.materials}
    graphs.update({f'group/{g.name}': graph_signature(g) for g in bpy.data.node_groups})
    graphs.update({f'world/{w.name}': graph_signature(w.node_tree) for w in bpy.data.worlds})
    images = {im.name: dict(size=list(im.size),source=im.source,colorspace=im.colorspace_settings.name,
                           packed_sha256=hashlib.sha256(im.packed_file.data).hexdigest() if im.packed_file else None)
              for im in bpy.data.images}
    cameras = {c.name: [c.type, c.lens, c.sensor_width, c.sensor_height, c.shift_x, c.shift_y,
                        c.clip_start, c.clip_end] for c in bpy.data.cameras}
    lights = {l.name: [l.type, l.energy, list(l.color), getattr(l, 'angle', None)] for l in bpy.data.lights}
    return dict(objects=objects, meshes=meshes, graphs=graphs, images=images, cameras=cameras, lights=lights)


def main():
    started = time.monotonic()
    if OUTPUT.exists() or RECEIPT.exists():
        raise FileExistsError('Refusing to overwrite existing U scene or metric receipt')
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    actual_source_sha256 = sha256(SOURCE)
    import argparse, sys
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-fingerprint', type=Path, help='Portable rebuild only: bundled structural S fingerprint; never skip source validation')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if actual_source_sha256 != SOURCE_SHA256 and not args.source_fingerprint:
        raise ValueError('Immutable S byte checksum mismatch; a rebuilt S requires its locked structural fingerprint')
    import bpy
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    scene.render.threads_mode = 'FIXED'; scene.render.threads = 2
    if hasattr(scene, 'cycles'):
        scene.cycles.device = 'CPU'
    existing = list(bpy.data.objects)
    required = [GROUND, ORIGINS, *RIGID]
    if any(scene.objects.get(n) is None for n in required):
        raise ValueError('Required S ground/particle source object missing')
    mutable = {scene.objects[n].data.name for n in required}
    roots = {o.name for o in scene.objects if o.name.startswith(PLANT_PREFIXES)}
    protected = protected_snapshot(bpy, existing, mutable, roots)
    source_structure = dict(protected=protected,
        mutable_coordinates={scene.objects[n].data.name: data_digest(scene.objects[n].data.vertices, 'co', 3, 'f4') for n in required},
        root_matrices={n: np.asarray(scene.objects[n].matrix_world).tolist() for n in sorted(roots)})
    source_fingerprint = hashlib.sha256(json.dumps(source_structure, sort_keys=True).encode()).hexdigest()
    if actual_source_sha256 != SOURCE_SHA256:
        expected = json.loads(args.source_fingerprint.read_text())['source_scene_structural_sha256']
        if source_fingerprint != expected:
            raise ValueError('Rebuilt S structural fingerprint differs from the source used for the actual U render')
    print('U_SOURCE_VERIFIED', actual_source_sha256, source_fingerprint, flush=True)
    density_bounds = (-6.2, -3.20, -.65, 5.0)
    density_patch_bounds = (-6.23, -3.17, -.68, 5.03)
    density_before = exact_patch(scene.objects[GROUND], density_patch_bounds, 110000)
    before, after, ground_report = ground_edit(scene.objects[GROUND])
    disks = DiskIndex()
    movement, root_movement, colors, material = move_existing(scene, before, after, disks)
    grit_report = add_grit(scene, after, disks, colors, material)
    import sys
    sys.path.insert(0, str(ROOT/'src'))
    from approved_density_lod import restore_approved_density
    density_after = exact_patch(scene.objects[GROUND], density_patch_bounds, 110000)
    density_report = restore_approved_density(scene, density_after, before_surface=density_before,
        burial_shift=loose_shift, bounds=density_bounds, max_instances=320000, exclusion=disks)
    verified = protected_snapshot(bpy, existing, mutable, roots)
    if protected != verified:
        different = [key for key in protected if protected[key] != verified[key]]
        raise AssertionError(f'Protected S scene data changed: {different}')
    if OUTPUT.exists() or RECEIPT.exists():
        raise FileExistsError('Output appeared during generation; refusing overwrite')
    scene['scene_version'] = 'R6 U physical lenses/scours, source-fracture lag and approved projected particle density over immutable S'
    scene['physical_lenses_limit'] = 'Authored static exposure/burial, not simulated transport or surveyed Victorville soil'
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
    if sha256(SOURCE) != actual_source_sha256:
        raise AssertionError('Immutable source file changed')
    report = dict(source_scene=str(SOURCE.relative_to(ROOT)),source_sha256=actual_source_sha256,
                  source_scene_structural_sha256=source_fingerprint,
                  output_scene=str(OUTPUT.relative_to(ROOT)),output_sha256=sha256(OUTPUT),
                  generator_sha256=sha256(Path(__file__)),ground=ground_report,new_grit=grit_report,
                  density_restoration=density_report,density_helper_sha256=sha256(ROOT/'src/approved_density_lod.py'),
                  existing_grain_movement=movement,plant_roots=root_movement,
                  source_feeder_xy_m=FEEDER,connecting_feeder_depth_m=.0035,connecting_feeder_width_m=[.12,.16],CPU_threads=2,render_device='CPU',rendered=False,
                  protected_S_data_unchanged=True,protected_snapshot_sha256=hashlib.sha256(json.dumps(protected,sort_keys=True).encode()).hexdigest(),
                  preserved='Original asphalt/paint/shared dust geometry and shader graphs, approved R5D prototypes/maps, all existing mineral/roughness attributes, cameras, daylight, distant landscape',
                  existing_loose_grain_rule='Actual final-minus-source triangle elevation; negative changes fully followed, only 15% of positive change followed, giving 85% authored deposit burial',
                  contact_method='Bounded actual Blender source/final loop-triangle patch, exact barycentric XY interpolation; no analytic-height placement or full-scene BVH',
                  limits=['Art-directed dimensions and source-fracture shape analogues, not measured site reconstruction',
                          'Fines retain approved R5D shader/maps; composition reads through small rigid-grain burial and local real lag',
                          'Plateau targets local fitted planes, clamped to 4–8 mm thickness where pre-existing relief prevents perfect planarity',
                          'Old support offsets are preserved through erosion; old particle-ground errors are not silently repaired',
                          'Conservative projected disks avoid new overlaps but do not certify old clast intersections',
                          'Saved scene needs independent reload and matched-camera visual review; no improvement claim before render'],
                  elapsed_seconds=time.monotonic()-started)
    RECEIPT.write_text(json.dumps(report, indent=2)+'\n')
    print('PHYSICAL_LENSES_READY', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
