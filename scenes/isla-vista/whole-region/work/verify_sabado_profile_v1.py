"""Read-only geometric checks of the serialized local Sabado construction.

Does not import/evaluate the authoring profile. Streams both CLMs, retaining
only the local path faces, and writes a standalone verification JSON.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

R = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(R / 'geo-deps'), str(R / 'whole-iv-vendor'), str(R / 'work')]
import numpy as np
import shapely
from shapely.geometry import shape, box, Point
from shapely.ops import unary_union
from iv_shared_ground import SharedGround

DT = np.dtype([('indices', 'u1', (3,)), ('material', '<u4'), ('object', '<u4')])


def local_faces(path):
    """Packet-bounded scan; no whole-mesh allocation or mutation."""
    geometry, labels = [], []
    count = 0
    with path.open('rb') as stream:
        magic, total, packets = struct.unpack('<4sQI', stream.read(16))
        assert magic == b'CLM1'
        for _ in range(packets):
            nv, nt = struct.unpack('<HH', stream.read(4))
            vertices = np.frombuffer(stream.read(nv * 44), '<f4').reshape(nv, 11)
            triangles = np.frombuffer(stream.read(nt * 11), DT)
            count += nt
            selected = triangles['material'] == 11
            if not selected.any():
                continue
            triangles = triangles[selected]
            q = vertices[triangles['indices']]
            xy = q[:, :, :2]
            selected = ((xy[:, :, 0].max(1) >= 488) &
                        (xy[:, :, 0].min(1) <= 667) &
                        (xy[:, :, 1].max(1) >= -306) &
                        (xy[:, :, 1].min(1) <= -281))
            if selected.any():
                geometry.append(q[selected].astype(float))
                labels.append(triangles[selected][['material', 'object']].copy())
        assert not stream.read(1)
    assert count == total and geometry, (count, total)
    return np.concatenate(geometry), np.concatenate(labels), count


class Surface:
    def __init__(self, triangles):
        e1 = triangles[:, 1, :2] - triangles[:, 0, :2]
        e2 = triangles[:, 2, :2] - triangles[:, 0, :2]
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        keep = abs(det) > 1e-12
        self.triangles = triangles[keep]
        self.polygons = shapely.polygons(self.triangles[:, :, :2])
        self.tree = shapely.STRtree(self.polygons)

    def height(self, points, xy_tolerance=0.00015):
        """Planar interpolation; tolerance only accommodates float32 boundaries."""
        z = np.full(len(points), np.nan)
        for i, xy in enumerate(points):
            point = Point(xy)
            indices = self.tree.query(point.buffer(xy_tolerance))
            candidates = []
            for j in indices:
                distance = self.polygons[j].distance(point)
                if distance > xy_tolerance:
                    continue
                triangle = self.triangles[j]
                matrix = np.column_stack((triangle[1, :2] - triangle[0, :2],
                                          triangle[2, :2] - triangle[0, :2]))
                weights = np.linalg.solve(matrix, xy - triangle[0, :2])
                value = triangle[0, 2] + weights @ (triangle[1:, 2] - triangle[0, 2])
                # Prefer interior support over a nearby edge extrapolation.
                candidates.append((distance, -min(*weights, 1 - weights.sum()), value))
            if candidates:
                z[i] = min(candidates)[2]
        return z


def walk_frame(walk, road, x):
    """Independent exact mapped-segment normal; road determines sign only."""
    point = Point(x, -292.5)
    station = walk.project(point)
    center = np.asarray(walk.interpolate(station).coords)[0]
    coords = np.asarray(walk.coords)
    segments = np.diff(coords, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    segment = min(np.searchsorted(np.cumsum(lengths), station, side='right'), len(lengths) - 1)
    tangent = segments[segment] / lengths[segment]
    normal = np.array([-tangent[1], tangent[0]])
    street = np.asarray(road.interpolate(road.project(Point(center))).coords)[0]
    if normal @ (center - street) < 0:
        normal *= -1
    return center, normal


def summarize(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    return None if not len(values) else {
        'min': float(values.min()), 'median': float(np.median(values)),
        'p95': float(np.quantile(values, .95)), 'max': float(values.max())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, default=R / 'evidence/sabado-profile-v1/contact.clm')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--crossfall-tolerance', type=float, default=.005,
                        help='Absolute slope tolerance: default 0.5 percentage points.')
    parser.add_argument('--edge-tolerance-m', type=float, default=.002)
    args = parser.parse_args()
    source = R / 'evidence/full-iv-path-uv-rebased/contact.clm'
    output = args.output or args.target.parent / 'SERIALIZED_SURFACE_VERIFICATION.json'
    ground_path = R / 'evidence/full-iv-roofs/measured-terrain-state.npz'
    ground = SharedGround(ground_path)
    contact = json.loads((R / 'evidence/full-iv-contact/CONTACT_RECEIPT.json').read_text())
    edge_ids = {p['object'] for p in contact['parts'] if p['name'].endswith('_closed_edges')}
    widths = {item['source_id']: item['width_m'] for item in contact['widths']}
    features = json.loads((R / 'evidence/full-iv-roofs/normalized.geojson').read_text())['features']
    byid = {item['id']: item for item in features}
    roi = box(490, -305, 665, -282)
    walk = shape(byid['osm:way:592214516']['geometry']).intersection(roi)
    road = shape(byid['osm:way:16262054']['geometry'])
    driveways = []
    for feature in features:
        properties = feature['properties']
        if properties['category'] != 'road' or properties['source_properties'].get('service') != 'driveway':
            continue
        line = shape(feature['geometry'])
        if line.intersects(roi):
            driveways.append(line.buffer(widths[feature['id']] / 2, cap_style='flat', join_style='round'))
    drives = unary_union(driveways)
    before, ids_before, total_before = local_faces(source)
    after, ids_after, total_after = local_faces(args.target)
    assert before.shape == after.shape and total_before == total_after
    assert np.array_equal(ids_before, ids_after)
    assert np.array_equal(before[:, :, :2], after[:, :, :2]), 'Mapped XY changed'
    edge = np.isin(ids_after['object'], list(edge_ids))
    changed = np.any(before[:, :, :3] != after[:, :, :3], axis=(1, 2))
    top_changed = changed & ~edge
    assert top_changed.any(), 'No changed top faces'
    old_surface = Surface(before[~edge, :, :3])
    new_surface = Surface(after[~edge, :, :3])

    # A barycentric lattice includes all vertices, edges, and interior samples.
    subdivisions = 8
    barycentric = np.array([[i, j, subdivisions - i - j]
                            for i in range(subdivisions + 1)
                            for j in range(subdivisions + 1 - i)], float) / subdivisions
    samples = np.einsum('ij,tjk->tik', barycentric, after[top_changed, :, :3]).reshape(-1, 3)
    clearance = samples[:, 2] - ground.height(samples[:, :2])
    worst = int(np.argmin(clearance))
    support = {'changed_top_faces': int(top_changed.sum()), 'samples_per_face': len(barycentric),
               'sample_count': len(samples), 'clearance_m': summarize(clearance),
               'minimum_sample_xyz_m': samples[worst].tolist(),
               'passed': bool(clearance.min() >= .001)}

    sections = []
    for x in [523.23, 550., 580., 630.]:
        center, normal = walk_frame(walk, road, x)
        offsets = np.linspace(-.85, .85, 35)
        xy = center + offsets[:, None] * normal
        ordinary = bool(np.all((xy[:, 0] >= 500) & (xy[:, 0] <= 655)) and
                        np.min(shapely.distance(drives, shapely.points(xy))) >= 1.2)
        old = old_surface.height(xy)
        new = new_surface.height(xy)
        covered = bool(np.isfinite(new).all() and np.isfinite(old).all())
        section = {'requested_x_m': x, 'center_xy_m': center.tolist(), 'ordinary': ordinary,
                   'sample_count': len(xy), 'covered': covered}
        if covered:
            slope = float((new[-1] - new[0]) / 1.7)
            section.update(before_full_width_crossfall=float((old[-1] - old[0]) / 1.7),
                           after_full_width_crossfall=slope,
                           after_fitted_crossfall=float(np.polyfit(offsets, new, 1)[0]),
                           after_local_crossfall=summarize(np.diff(new) / np.diff(offsets)),
                           minimum_clearance_m=float(np.min(new - ground.height(xy))),
                           passed=bool(not ordinary or abs(slope - .02) <= args.crossfall_tolerance))
        else:
            section['passed'] = not ordinary
        sections.append(section)

    # Edge and cap meshes have independent tessellation. Probe edge top lines
    # against actual adjacent top faces, including original baseline mismatch.
    seam_before, seam_after, seam_growth, seam_locations = [], [], [], []
    missing = []
    segments = 0
    for index in np.flatnonzero(changed & edge):
        old = before[index, :, :3]
        new = after[index, :, :3]
        is_top = old[:, 2] > ground.height(old[:, :2]) - .02
        if is_top.sum() != 2:
            continue  # One of each quad's two faces has the complete top edge.
        segments += 1
        old_ends, new_ends = old[is_top], new[is_top]
        t = np.linspace(0, 1, 17)[:, None]
        old_points = old_ends[0] * (1 - t) + old_ends[1] * t
        new_points = new_ends[0] * (1 - t) + new_ends[1] * t
        old_z = old_surface.height(old_points[:, :2])
        new_z = new_surface.height(new_points[:, :2])
        valid = np.isfinite(old_z) & np.isfinite(new_z)
        missing.extend(new_points[~valid, :2].tolist())
        a = abs(old_points[valid, 2] - old_z[valid])
        b = abs(new_points[valid, 2] - new_z[valid])
        seam_before.extend(a.tolist())
        seam_after.extend(b.tolist())
        seam_growth.extend((b - a).tolist())
        seam_locations.extend(new_points[valid].tolist())
    seam_after = np.asarray(seam_after)
    seam_worst = int(np.argmax(seam_after)) if len(seam_after) else None
    closure = {'changed_top_segments': segments, 'matched_samples': len(seam_after),
               'unmatched_samples': len(missing), 'unmatched_xy_examples': missing[:5],
               'baseline_abs_gap_m': summarize(seam_before), 'output_abs_gap_m': summarize(seam_after),
               'gap_increase_m': summarize(seam_growth),
               'maximum_gap_xyz_m': seam_locations[seam_worst] if seam_worst is not None else None,
               'tolerance_m': args.edge_tolerance_m,
               'passed': bool(len(seam_after) and not missing and seam_after.max() <= args.edge_tolerance_m)}

    triangle = after[changed, :, :3]
    geometric = np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0])
    lengths = np.linalg.norm(geometric, axis=1)
    assert np.all(lengths > 1e-12), 'Changed face degeneracy'
    geometric /= lengths[:, None]
    normal_error = np.max(abs(after[changed, :, 3:6] - geometric[:, None, :]))
    ordinary_count = sum(section['ordinary'] for section in sections)
    failures = []
    if not support['passed']:
        failures.append('Changed top surface clearance below 1 mm')
    if ordinary_count < 2 or not all(section['passed'] for section in sections):
        failures.append('Serialized ordinary transverse crossfall is unverified or outside tolerance')
    if not closure['passed']:
        failures.append('Closed edge tops do not match adjacent serialized top within tolerance')
    if normal_error > 1e-5:
        failures.append('Changed face normals do not match geometric normals')
    record = {'passed': not failures, 'failures': failures, 'source': str(source), 'target': str(args.target),
              'source_sha256': hashlib.file_digest(source.open('rb'), 'sha256').hexdigest(),
              'target_sha256': hashlib.file_digest(args.target.open('rb'), 'sha256').hexdigest(),
              'terrain_sha256': hashlib.file_digest(ground_path.open('rb'), 'sha256').hexdigest(),
              'total_triangles': total_after, 'local_faces_retained': len(after),
              'changed_local_faces': int(changed.sum()), 'mapped_xy_unchanged': True,
              'support': support, 'crossfall_tolerance': args.crossfall_tolerance,
              'cross_sections': sections, 'edge_closure': closure,
              'maximum_changed_normal_component_error': float(normal_error),
              'limits': 'Checks actual serialized piecewise-planar geometry. Clearance and edge closure are dense bounded samples, not a formal continuum proof. Source terrain and all meshes are read-only. The 1.8 m width and construction dimensions are authored estimates; no surveyed or accessibility claim.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
