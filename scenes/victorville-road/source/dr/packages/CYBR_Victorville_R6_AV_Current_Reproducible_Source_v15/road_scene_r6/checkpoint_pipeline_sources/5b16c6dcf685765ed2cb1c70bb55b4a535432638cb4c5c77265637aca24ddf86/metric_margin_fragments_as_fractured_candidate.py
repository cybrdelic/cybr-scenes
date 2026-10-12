"""Unapproved AS morphology candidate: asymmetric bulk fracture and edge spall.

Only the baseline's dimensional draws and linked mineral field are reused. Each
new mass is authored from 17 unequal fracture support sites: staggered lower
corners and shoulders plus an off-centre roof ridge. Their convex envelope is
cut back by bounded 0.55--1.8 mm true face setbacks at dihedral edges. Two or
three finite-depth polyhedral spalls remove exposed outer corners; the new
scars are fresh angular fractures, not a noise/displacement shell or a socket
punched in a broad top. All boundaries are explicit planar solid geometry.

Physical dimensions are assigned once while authoring the new unapproved
coarse body. No approved R5D grain, instance scale, shader, placement, camera or
lighting changes. The stable AS module stays runnable and untouched. Regional
observation supplies qualitative hierarchy only, never scan/texture/metric data.
"""
from dataclasses import dataclass, replace
import math
import numpy as np
from scipy.spatial import ConvexHull, HalfspaceIntersection
from metric_margin_fragments_as import Fragment, build_fragment as build_stock

_EPS = 2e-10

@dataclass(frozen=True)
class FracturedFragment(Fragment):
    spalls: tuple
    stock_dimensions_m: np.ndarray
    stock_volume_m3: float
    macro_fractures: tuple
    new_edge_setbacks_m: tuple
    stock_coordinate_offset_m: np.ndarray
    retained_blank_planes: np.ndarray


def _unit(x):
    return x / np.linalg.norm(x)


def _basis(normal):
    u = _unit(np.cross(normal, [0., 0., 1.] if abs(normal[2]) < .9 else [1., 0., 0.]))
    return u, np.cross(normal, u)


def _area(poly):
    if len(poly) < 3:
        return 0.
    return float(np.linalg.norm(np.cross(poly, np.roll(poly, -1, axis=0)).sum(0)) * .5)


def _convex_boundary(points):
    """Outward polygon loops, preserving real planes and eliminating diagonals."""
    hull = ConvexHull(points)
    planes = []
    polygons = []
    for eq in hull.equations:
        if any(np.linalg.norm(eq[:3] - p[:3]) < 2e-8 and abs(eq[3] - p[3]) < 2e-9 for p in planes):
            continue
        planes.append(eq)
        ids = np.flatnonzero(abs(points @ eq[:3] + eq[3]) < 2e-9)
        p = points[ids]
        center = p.mean(0)
        u, v = _basis(eq[:3])
        order = np.argsort(np.arctan2((p - center) @ v, (p - center) @ u))
        polygons.append(p[order])
    return np.array(planes), polygons


def _clip(poly, plane):
    """Retain a closed convex polygon's plane <= 0 side."""
    if len(poly) < 3:
        return np.empty((0, 3))
    ds = poly @ plane[:3] + plane[3]
    result = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        a, b = ds[i], ds[(i + 1) % len(poly)]
        if a <= 0:
            result.append(p)
        if (a < 0 and b > 0) or (a > 0 and b < 0):
            result.append(p + (q - p) * (a / (a - b)))
    if len(result) < 3:
        return np.empty((0, 3))
    out = []
    for p in result:
        if not out or np.linalg.norm(p - out[-1]) > _EPS:
            out.append(p)
    if len(out) > 1 and np.linalg.norm(out[0] - out[-1]) < _EPS:
        out.pop()
    return np.array(out) if len(out) >= 3 else np.empty((0, 3))


def _subtract(poly, cutter):
    """A convex polygon minus a convex cutter, as disjoint convex pieces."""
    outside = []
    inside = poly
    for plane in cutter:
        if len(inside) < 3:
            break
        ds = inside @ plane[:3] + plane[3]
        if ds.max() <= _EPS:
            continue
        if ds.min() >= -_EPS:
            outside.append(inside)
            inside = np.empty((0, 3))
            break
        piece = _clip(inside, -plane)
        if _area(piece) > _EPS ** 2:
            outside.append(piece)
        inside = _clip(inside, plane)
    return outside


def _subtract_all(polygons, cutters):
    for cutter in cutters:
        polygons = [p for poly in polygons for p in _subtract(poly, cutter)]
    return polygons


def _mesh(polygons):
    """Weld, split every T-junction, then centroid-fan each convex patch.

    Splitting happens before triangulation, so independently clipped boundaries
    have matching directed halfedges even when a cutter crosses stock bevels.
    """
    vertices = []
    key_to_id = {}
    loops = []
    for poly in polygons:
        if _area(poly) <= 1e-16:
            continue
        loop = []
        for p in poly:
            key = tuple(np.round(p / _EPS).astype(np.int64))
            if key not in key_to_id:
                # Neighbouring rounding cells can contain the same intersection.
                found = next((i for i, q in enumerate(vertices) if np.linalg.norm(p - q) < 4 * _EPS), None)
                if found is None:
                    found = len(vertices)
                    vertices.append(p)
                key_to_id[key] = found
            i = key_to_id[key]
            if not loop or loop[-1] != i:
                loop.append(i)
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        if len(set(loop)) >= 3:
            loops.append(loop)
    points = np.array(vertices)
    splits = []
    for loop in loops:
        split = []
        for ia, ib in zip(loop, loop[1:] + loop[:1]):
            a, b = points[ia], points[ib]
            edge = b - a
            ll = edge @ edge
            t = (points - a) @ edge / ll
            dist = np.linalg.norm(points - (a + t[:, None] * edge), axis=1)
            ids = np.flatnonzero((t >= -1e-10) & (t < 1 - 1e-10) & (dist < 5 * _EPS))
            split.extend(ids[np.argsort(t[ids])].tolist())
        clean = []
        for i in split:
            if not clean or i != clean[-1]:
                clean.append(i)
        splits.append(clean)
    triangles = []
    for loop in splits:
        center = points[loop].mean(0)
        ci = len(vertices)
        vertices.append(center)
        for a, b in zip(loop, loop[1:] + loop[:1]):
            if np.linalg.norm(np.cross(points[a] - center, points[b] - center)) > 1e-17:
                triangles.append([ci, a, b])
    return np.array(vertices), np.array(triangles, dtype=np.int32)


def _spall(q, direction, depth, radius, rng):
    """Irregular open fracture wedge, with a tiny sloping broken floor.

    All side planes open outwards; depth is explicitly bounded in metres.
    Width and depth are event dimensions, not grain/grit noise wavelengths.
    """
    axis = _unit(direction)
    u, v = _basis(axis)
    tip = q - axis * depth
    n = int(rng.integers(4, 7))
    phase = rng.uniform(0, math.tau)
    planes = []
    for j in range(n):
        a = phase + j * math.tau / n + rng.uniform(-.20, .20)
        tangent = np.cos(a) * u + np.sin(a) * v
        # Unequal sides produce a fracture wedge, rather than a regular socket.
        normal = _unit(tangent - axis * (radius / depth) * rng.uniform(.73, 1.28))
        offset = depth * rng.uniform(.025, .095)
        planes.append([*normal, -normal @ tip - offset])
    floor_normal = _unit(-axis + u * rng.uniform(-.25, .25) + v * rng.uniform(-.25, .25))
    planes.append([*floor_normal, -floor_normal @ tip])
    witness = tip + axis * depth * .15
    return np.array(planes), witness, axis


def _fractured_blank(stock, rng):
    """Build the primary mass from a sparse asymmetric fracture support set.

    Unequal foot corners, staggered shoulders and an off-centre high ridge
    define entire centimetre-scale fracture planes. These 17--20 support sites
    are the bulk body, not a noisy shell over the previous box. Metric targets
    come from the same AS dimensional draw; only this unapproved tier changes.
    """
    dims = np.ptp(stock.vertices, axis=0)
    phase = rng.uniform(0,math.tau)
    slope_dir = np.array([np.cos(phase+.9),np.sin(phase+.9)])
    sites=[]
    # No aligned upper/lower rings: unequal azimuths and heights eliminate the
    # repeated vertical extrusion responsible for the AS cut-block impression.
    for count, zlo, zhi, rlo, rhi, shift in ((6,.0,.16,.65,1.,0.),(8,.36,.80,.58,1.,.37)):
        for j in range(count):
            angle=phase+shift+j*math.tau/count+rng.uniform(-.25,.25)
            radial=rng.uniform(rlo,rhi)
            xy=np.array([np.cos(angle),np.sin(angle)])*radial*.5
            z=rng.uniform(zlo,zhi)+float(xy@slope_dir)*.15
            sites.append([*xy,z])
    # Three non-collinear, unequal high points form a broken off-centre ridge.
    ridge_center=np.array([rng.uniform(-.20,.14),rng.uniform(-.18,.15)])
    for j in range(3):
        xy=ridge_center+np.array([rng.uniform(-.15,.15),rng.uniform(-.14,.14)])
        sites.append([*xy,rng.uniform(.81,1.)])
    points=np.array(sites)
    lo,hi=points.min(0),points.max(0)
    # One-time authored physical dimensions; no instance/LOD/grain scaling.
    points=(points-lo)/(hi-lo)*dims
    points[:,:2]-=dims[:2]*.5
    center=points.mean(0)
    original_hull=ConvexHull(points)
    blank_volume=float(original_hull.volume)
    planes,polygons=_convex_boundary(points)
    extra=planes.tolist()
    all_planes=planes
    # Narrow physical weathering only at new bulk-fracture edges. The setback
    # along either supporting face is bounded, even for shallow dihedrals.
    hull=ConvexHull(points)
    cuts=[]; setbacks=[]; seen=set()
    for fi,face in enumerate(hull.simplices):
        for ni in hull.neighbors[fi]:
            key=tuple(sorted((fi,int(ni))))
            if key in seen: continue
            seen.add(key)
            a,b=hull.equations[fi,:3],hull.equations[ni,:3]
            dot=float(a@b)
            if dot > .995: continue
            new_edge=any(np.linalg.norm(a-np.array(e[:3]))<2e-7 or np.linalg.norm(b-np.array(e[:3]))<2e-7 for e in extra)
            if not new_edge: continue
            edge=list(set(face).intersection(hull.simplices[ni]))
            if len(edge)!=2: continue
            normal=_unit(a+b)
            setback=float(rng.uniform(.00055, stock.weathering_width_m))
            cut=setback*math.sqrt((1-dot)*.5)
            support=float(normal@points[edge].mean(0)-cut)
            if support-normal@center <= dims[2]*.04: continue
            cuts.append([*normal,-support]); setbacks.append(setback)
    if cuts:
        points=HalfspaceIntersection(np.vstack([all_planes,cuts]),center).intersections
    return points, tuple(dict(plane=e) for e in extra), tuple(setbacks), blank_volume


def _events(stock, planes, polygons, rng):
    center = stock.vertices.mean(0)
    dims = np.ptp(stock.vertices, axis=0)
    phase = rng.uniform(0, math.tau)
    sites = []
    count = 3 if stock.family in ('block', 'broken_lump') else 2
    for j in range(count):
        angle = phase + j * math.tau / count + rng.uniform(-.25, .25)
        support = np.array([np.cos(angle), np.sin(angle), rng.uniform(.30, .60)]) / dims
        radial = np.linalg.norm(stock.vertices[:, :2] / dims[:2], axis=1)
        eligible = np.flatnonzero((radial > .43) & (stock.vertices[:, 2] > dims[2] * .28))
        if len(eligible) < 3:
            eligible = np.flatnonzero(radial > .40)
        q = stock.vertices[eligible[int(np.argmax(stock.vertices[eligible] @ support))]]
        sites.append(('open_ridge_spall', q, _unit(q - center), rng.uniform(.14,.21), rng.uniform(.20,.29)))
    cutters, records = [], []
    for name, q, direction, depth_fraction, radius_fraction in sites:
        depth = min(float(dims[2] * depth_fraction), .025)
        radius = float(min(dims[:2]) * radius_fraction)
        c, witness, axis = _spall(q, direction, depth, radius, rng)
        assert np.all(witness @ planes[:, :3].T + planes[:, 3] < -1e-10)
        cutters.append(c)
        records.append(dict(kind=name, axis=axis.tolist(), site_m=q.tolist(), depth_m=depth,
                            opening_radius_m=radius, cutter_planes=c.tolist(), witness_m=witness.tolist()))
    return cutters, records


def build_fragment(index, seed=2610100905):
    stock = build_stock(index, seed)
    rng = np.random.default_rng(np.random.SeedSequence([seed, index, 73041]))
    blank_points, macro_records, setbacks, blank_volume = _fractured_blank(stock, rng)
    blank = replace(stock, vertices=blank_points)
    planes, polygons = _convex_boundary(blank_points)
    cutters, records = _events(blank, planes, polygons, rng)
    surface = _subtract_all(polygons, cutters)
    for i, cutter in enumerate(cutters):
        witness = np.array(records[i]['witness_m'])
        intersection = HalfspaceIntersection(np.vstack([planes, cutter]), witness).intersections
        cap_planes, cap_polys = _convex_boundary(intersection)
        caps = []
        for p, poly in zip(cap_planes, cap_polys):
            if any(np.linalg.norm(p[:3] - c[:3]) < 2e-7 and abs(p[3] - c[3]) < 2e-8 for c in cutter):
                caps.append(poly[::-1])  # Cavity normals point into removed volume.
        surface.extend(_subtract_all(caps, [c for j, c in enumerate(cutters) if j != i]))
    points, faces = _mesh(surface)
    # The original vertical mineral/dust field is evaluated at the new boundary.
    # It is quadratic in height in AS; no new material or independent color noise.
    old_t = stock.vertices[:, 2] / np.ptp(stock.vertices[:, 2])
    new_t = points[:, 2] / np.ptp(stock.vertices[:, 2])
    old_basis = np.c_[np.ones(len(old_t)), old_t, old_t ** 2]
    new_basis = np.c_[np.ones(len(new_t)), new_t, new_t ** 2]
    color = new_basis @ np.linalg.lstsq(old_basis, stock.color, rcond=None)[0]
    color[:, 3] = 1.
    rough = new_basis @ np.linalg.lstsq(old_basis, stock.roughness, rcond=None)[0]
    datum = np.r_[(points[:, :2].min(0) + points[:, :2].max(0)) * .5, points[:, 2].min()]
    points -= datum
    return FracturedFragment(points, faces, stock.mineral, np.clip(color, 0, 1), rough,
                             stock.nominal_length_m, stock.weathering_width_m, stock.family,
                             tuple(records), np.ptp(stock.vertices, axis=0), blank_volume, macro_records, setbacks, datum, planes)


def audit_fragment(f):
    faces, points = f.faces, f.vertices
    tri = points[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    areas = np.linalg.norm(cross, axis=1) * .5
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    unique_edges, inv, count = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    assert np.all(count == 2), ('nonmanifold edges', unique_edges[count != 2])
    signs = np.where(edges[:, 0] < edges[:, 1], 1, -1)
    assert np.all(np.bincount(inv, weights=signs) == 0), 'inconsistent directed edges'
    assert len(points) - len(unique_edges) + len(faces) == 2, 'not a single genus-zero shell'
    volume = float(np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6)
    assert volume > 0 and np.all(areas > 1e-17)
    assert np.isfinite(points).all() and np.isfinite(f.color).all() and np.isfinite(f.roughness).all()
    assert np.all((f.color >= 0) & (f.color <= 1)) and np.all((f.roughness >= .45) & (f.roughness <= .9))
    dims = np.ptp(points, axis=0)
    assert np.all(dims <= f.stock_dimensions_m + 2e-8), 'stock inflated'
    assert np.all(dims >= f.stock_dimensions_m * .70), 'excessive dimension loss'
    assert abs(points[:, 2].min()) < 1e-10
    assert .00055 <= f.weathering_width_m <= .0018
    assert .035 <= f.nominal_length_m <= .225
    convex_volume = float(ConvexHull(points).volume)
    missing = (convex_volume - volume) / convex_volume
    assert missing > .0001 and volume < f.stock_volume_m3, 'no genuine concavity/material loss'
    normals = cross / (2 * areas[:, None])
    # This is the analytical boundary of an actual solid, rather than merely a
    # closed triangle soup: inward/outward samples must straddle the CSG body.
    def solid(samples):
        inside = np.all(samples @ f.retained_blank_planes[:, :3].T + f.retained_blank_planes[:, 3] <= 0., axis=1)
        for event in f.spalls:
            cutter = np.array(event['cutter_planes'])
            inside &= ~np.all(samples @ cutter[:, :3].T + cutter[:, 3] <= 0., axis=1)
        return inside
    centers = tri.mean(1) + f.stock_coordinate_offset_m
    epsilon = min(dims) * 2e-7
    assert np.all(solid(centers - normals * epsilon)), 'wrong inward solid membership'
    assert not np.any(solid(centers + normals * epsilon)), 'wrong outward solid membership'
    assert all(.00055 <= w <= .0018 for w in f.new_edge_setbacks_m)
    upper = normals[:, 2] > .25
    return dict(family=f.family, vertices=len(points), triangles=len(faces), dimensions_m=dims.tolist(),
                solid_volume_m3=volume, stock_volume_m3=f.stock_volume_m3, stock_coordinate_offset_m=f.stock_coordinate_offset_m.tolist(),
                removed_volume_fraction=1 - volume / f.stock_volume_m3,
                convex_deficit_fraction=missing, narrow_edge_weathering_m=f.weathering_width_m,
                mineral_index=f.mineral, spall_count=len(f.spalls), primary_fracture_face_count=len(f.macro_fractures),
                maximum_new_edge_face_setback_m=max(f.new_edge_setbacks_m, default=0.),
                maximum_spall_depth_m=max(e['depth_m'] for e in f.spalls),
                upward_surface_area_m2=float(areas[upper].sum()),
                directed_edge_manifold=True, analytical_solid_boundary_verified=True, euler_characteristic=2, exact_stock_envelope_retained=bool(np.max(abs(dims - f.stock_dimensions_m)) < 2e-8))
