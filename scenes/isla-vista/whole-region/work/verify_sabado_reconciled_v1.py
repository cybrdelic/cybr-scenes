"""Independent verification of the split-edge Sabado mesh.

Reads serialized geometry; does not import the adapter or authoring profile.
Provenance is checked against both meshes, not treated as proof by itself.
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
from shapely.geometry import shape, box
from shapely.ops import unary_union
from iv_shared_ground import SharedGround
from verify_sabado_profile_v1 import Surface, DT, local_faces, walk_frame, summarize


def canonical(a):
    a = np.asarray(a, dtype='<f4').copy()
    a[a == 0] = 0.
    return a.tobytes()


def inspect(path, edge_ids, ranges):
    """Hash all unaffected rows and collect only bounded local/provenance rows."""
    cap_hash, unchanged_hash = hashlib.sha256(), hashlib.sha256()
    local, selected = [], {}
    spans = sorted(ranges)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    span_index = 0
    count = 0
    with path.open('rb') as stream:
        magic, total, packets = struct.unpack('<4sQI', stream.read(16))
        assert magic == b'CLM1'
        for _ in range(packets):
            nv, nt = struct.unpack('<HH', stream.read(4))
            vertices = np.frombuffer(stream.read(nv * 44), '<f4').reshape(nv, 11)
            triangles = np.frombuffer(stream.read(nt * 11), DT)
            q = vertices[triangles['indices']]
            a = np.zeros((nt, 36), '<f4')
            a[:, :9] = q[:, :, :3].reshape(nt, 9)
            a[:, 9:18] = q[:, :, 3:6].reshape(nt, 9)
            a[:, 18:20] = np.c_[triangles['material'], triangles['object']]
            a[:, 20:26] = q[:, :, 6:8].reshape(nt, 6)
            a[:, 26:35] = q[:, :, 8:11].reshape(nt, 9)
            nonedge = ~np.isin(triangles['object'], list(edge_ids))
            cap_hash.update(canonical(a[nonedge]))
            untouched = np.ones(nt, bool)
            while span_index < len(spans) and spans[span_index][1] <= count:
                span_index += 1
            j = span_index
            while j < len(spans) and spans[j][0] < count + nt:
                lo, hi = spans[j]
                for k in range(max(0, lo - count), min(nt, hi - count)):
                    selected[count + k] = a[k].copy()
                    untouched[k] = False
                j += 1
            unchanged_hash.update(canonical(a[untouched]))
            xy = q[:, :, :2]
            mask = ((triangles['material'] == 11) & (xy[:, :, 0].max(1) >= 488) &
                    (xy[:, :, 0].min(1) <= 667) & (xy[:, :, 1].max(1) >= -306) &
                    (xy[:, :, 1].min(1) <= -281))
            if mask.any():
                local.append(a[mask])
            count += nt
        assert count == total and not stream.read(1)
    assert len(selected) == sum(hi - lo for lo, hi in spans)
    return cap_hash.hexdigest(), unchanged_hash.hexdigest(), np.concatenate(local), selected, total


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, default=R / 'evidence/sabado-profile-closed-v1/contact.clm')
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    receipt_path = args.receipt or args.target.parent / 'EDGE_RECONCILIATION_RECEIPT.json'
    output = args.output or args.target.parent / 'SERIALIZED_SURFACE_VERIFICATION.json'
    receipt = json.loads(receipt_path.read_text())
    assert receipt['passed']
    source = Path(receipt['source'])
    assert source.resolve() != args.target.resolve()
    assert file_hash(source) == receipt['source_sha256']
    target_hash = file_hash(args.target)
    assert target_hash == receipt['output_sha256']
    contact = json.loads((R / 'evidence/full-iv-contact/CONTACT_RECEIPT.json').read_text())
    edge_ids = {p['object'] for p in contact['parts'] if p['name'].endswith('_closed_edges')}
    provenance = receipt['provenance']
    source_ranges = [(p['source_triangle_indices'][0], p['source_triangle_indices'][1] + 1) for p in provenance]
    output_ranges = [(p['output_triangle_start'], p['output_triangle_start'] + p['output_triangle_count']) for p in provenance]
    cap_before, other_before, local_before, old_rows, before_count = inspect(source, edge_ids, source_ranges)
    cap_after, other_after, local_after, new_rows, after_count = inspect(args.target, edge_ids, output_ranges)
    assert cap_before == cap_after, 'Cap or another non-edge payload/order changed'
    assert other_before == other_after, 'Unrelated face payload/order changed'
    assert before_count == receipt['source_triangles'] and after_count == receipt['output_triangles']
    target_top = local_after[~np.isin(local_after[:, 19].astype(int), list(edge_ids)), :9].reshape(-1, 3, 3).astype(float)
    profile_top = local_before[~np.isin(local_before[:, 19].astype(int), list(edge_ids)), :9].reshape(-1, 3, 3).astype(float)
    assert np.array_equal(target_top, profile_top)
    surface = Surface(target_top)
    ground_path = R / 'evidence/full-iv-roofs/measured-terrain-state.npz'
    ground = SharedGround(ground_path)
    recovered = R / 'evidence/full-iv-path-uv-rebased/contact.clm'
    original, ids, _ = local_faces(recovered)
    original_top = original[~np.isin(ids['object'], list(edge_ids)), :, :3]
    assert original_top.shape == target_top.shape
    assert np.array_equal(original_top[:, :, :2], target_top[:, :, :2])
    changed = np.any(original_top != target_top, axis=(1, 2))
    bary = np.array([[i, j, 8 - i - j] for i in range(9) for j in range(9 - i)], float) / 8
    samples = np.einsum('ij,tjk->tik', bary, target_top[changed]).reshape(-1, 3)
    clearance = samples[:, 2] - ground.height(samples[:, :2])
    support = {'changed_top_faces': int(changed.sum()), 'sample_count': len(samples),
               'clearance_m': summarize(clearance), 'passed': bool(clearance.min() >= .001)}

    features = json.loads((R / 'evidence/full-iv-roofs/normalized.geojson').read_text())['features']
    byid = {f['id']: f for f in features}
    widths = {p['source_id']: p['width_m'] for p in contact['widths']}
    roi = box(490, -305, 665, -282)
    walk = shape(byid['osm:way:592214516']['geometry']).intersection(roi)
    road = shape(byid['osm:way:16262054']['geometry'])
    driveways = []
    for f in features:
        p = f['properties']
        if p['category'] == 'road' and p['source_properties'].get('service') == 'driveway':
            line = shape(f['geometry'])
            if line.intersects(roi):
                driveways.append(line.buffer(widths[f['id']] / 2, cap_style='flat', join_style='round'))
    drives = unary_union(driveways)
    old_surface = Surface(original_top)
    sections = []
    for x in [523.23, 550., 580., 630.]:
        center, normal = walk_frame(walk, road, x)
        offsets = np.linspace(-.85, .85, 35)
        xy = center + offsets[:, None] * normal
        old, new = old_surface.height(xy), surface.height(xy)
        ordinary = bool(np.all((xy[:, 0] >= 500) & (xy[:, 0] <= 655)) and
                        np.min(shapely.distance(drives, shapely.points(xy))) >= 1.2)
        covered = bool(np.isfinite(old).all() and np.isfinite(new).all())
        item = {'requested_x_m': x, 'center_xy_m': center.tolist(), 'ordinary': ordinary, 'covered': covered}
        if covered:
            slope = float((new[-1] - new[0]) / 1.7)
            item.update(before_full_width_crossfall=float((old[-1] - old[0]) / 1.7),
                        after_full_width_crossfall=slope, after_local_crossfall=summarize(np.diff(new) / np.diff(offsets)),
                        passed=bool(not ordinary or abs(slope - .02) <= .005))
        else:
            item['passed'] = not ordinary
        sections.append(item)

    gaps, perimeter, bottom_errors, normal_errors = [], [], [], []
    missing, uv_failures = 0, 0
    segment_pieces = 0
    worst_gap = {'gap_m': 0.}
    for item in provenance:
        source_indices = item['source_triangle_indices']
        assert source_indices[1] == source_indices[0] + 1
        old = np.stack([old_rows[i] for i in source_indices])
        assert hashlib.sha256(canonical(old)).hexdigest() == item['source_pair_canonical_sha256']
        old_xyz = old[:, :9].reshape(2, 3, 3).astype(float)
        a, b = old_xyz[0, 0, :2], old_xyz[0, 1, :2]
        assert np.array_equal([a, b], item['source_xy_endpoints_m'])
        assert np.array_equal(old[:, 18:20], np.tile([item['material'], item['object']], (2, 1)))
        assert item['object'] in edge_ids and item['material'] == 11
        lo = item['output_triangle_start']
        count = item['output_triangle_count']
        assert count == 2 * item['output_piece_count'] and count % 2 == 0
        actual = np.stack([new_rows[i] for i in range(lo, lo + count)])
        assert np.array_equal(actual[:, 18:20], np.tile(old[0, 18:20], (count, 1)))
        xyz = actual[:, :9].reshape(-1, 3, 3).astype(float)
        direction = b - a
        length2 = direction @ direction
        points = xyz[:, :, :2].reshape(-1, 2)
        t = (points - a) @ direction / length2
        assert t.min() >= -1e-6 and t.max() <= 1 + 1e-6
        drift = np.linalg.norm(points - (a + t[:, None] * direction), axis=1)
        perimeter.extend(drift.tolist())
        normal = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
        lengths = np.linalg.norm(normal, axis=1)
        assert np.all(lengths > 1e-12)
        normal /= lengths[:, None]
        normal_errors.extend(abs(actual[:, 9:18].reshape(-1, 3, 3) - normal[:, None, :]).ravel().tolist())
        uv = actual[:, 20:26].reshape(-1, 3, 2).astype(float)
        d1, d2 = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
        det = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]
        uv_failures += int((abs(det) <= 1e-14).sum())
        assert np.array_equal(xyz[0, 0, :2], a) and np.array_equal(xyz[-2, 1, :2], b)
        for j in range(0, count, 2):
            first, second = xyz[j], xyz[j + 1]
            assert np.array_equal(first[0], second[0]) and np.array_equal(first[2], second[1])
            assert np.array_equal(first[0, :2], second[2, :2]) and np.array_equal(first[1, :2], first[2, :2])
            if j + 2 < count:
                assert np.array_equal(first[1], xyz[j + 2, 0])
                assert np.array_equal(first[2], xyz[j + 3, 2])
            bottom = first[:2]
            bt = (bottom[:, :2] - a) @ direction / length2
            expected_bottom = old_xyz[0, 0, 2] * (1 - bt) + old_xyz[0, 1, 2] * bt
            bottom_errors.extend(abs(bottom[:, 2] - expected_bottom).tolist())
            top = second[[2, 1]]
            weights = np.linspace(0, 1, 17)[:, None]
            edge_points = top[0] * (1 - weights) + top[1] * weights
            cap_z = surface.height(edge_points[:, :2])
            valid = np.isfinite(cap_z)
            missing += int((~valid).sum())
            errors = abs(edge_points[valid, 2] - cap_z[valid])
            gaps.extend(errors.tolist())
            if len(errors) and errors.max() > worst_gap['gap_m']:
                k = int(np.argmax(errors))
                worst_gap = {'gap_m': float(errors[k]), 'xyz_m': edge_points[valid][k].tolist(),
                             'source_triangle_indices': source_indices}
            segment_pieces += 1
    closure = {'source_segments': len(provenance), 'refined_segments': segment_pieces,
               'matched_samples': len(gaps), 'unmatched_samples': missing,
               'absolute_gap_m': summarize(gaps), 'worst': worst_gap,
               'tolerance_m': .002, 'passed': bool(gaps and not missing and max(gaps) <= .002)}
    geometry = {'maximum_perimeter_rounding_drift_m': max(perimeter),
                'maximum_bottom_line_interpolation_error_m': max(bottom_errors),
                'maximum_normal_component_error': max(normal_errors), 'degenerate_uv_faces': uv_failures,
                'passed': bool(max(perimeter) < .00006 and max(bottom_errors) < .000002 and
                               max(normal_errors) < .00001 and uv_failures == 0)}
    failures = []
    if not support['passed']:
        failures.append('Top clearance below 1 mm')
    if sum(p['ordinary'] for p in sections) < 2 or not all(p['passed'] for p in sections):
        failures.append('Actual ordinary crossfall outside 2% +/- 0.5 percentage points or uncovered')
    if not closure['passed']:
        failures.append('Edge-to-cap closure exceeds 2 mm or has missing support')
    if not geometry['passed']:
        failures.append('Refined perimeter, bottom lines, normals or UV charts fail')
    record = {'passed': not failures, 'failures': failures, 'source': str(source), 'target': str(args.target),
              'source_sha256': file_hash(source), 'target_sha256': target_hash,
              'terrain_sha256': file_hash(ground_path), 'total_triangles': after_count,
              'all_cap_and_nonedge_payload_order_exact': True, 'all_unrelated_face_payload_order_exact': True,
              'nonedge_payload_order_canonical_sha256': cap_after, 'unchanged_faces_canonical_sha256': other_after,
              'semantic_source_ids_preserved': True, 'support': support, 'cross_sections': sections,
              'edge_closure': closure, 'refined_edge_geometry': geometry,
              'limits': 'Independently reads actual serialized triangles. Cap and unrelated payloads compare exactly, allowing signed-zero equivalence only. Refined XY perimeter and bottom lines allow float32 rounding; no mapped source/width or terrain changes. Sampled closure and support are bounded numerical checks, not surveyed engineering or accessibility certification.'}
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
