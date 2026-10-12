"""Conform all Sabado edge tops adjacent to the changed immutable cap.

Splits original edge quads at adjacent cap-facet breakpoints. Bottom lines,
mapped perimeter, source IDs and all other faces are retained. New float32
points on an original perimeter line are permitted only rounding-level drift.
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
from shapely.geometry import LineString, Point
from cybr_light import Meshlets
from verify_sabado_profile_v1 import Surface, DT


def canonical(a):
    a = np.asarray(a, dtype='<f4').copy()
    a[a == 0] = 0.
    return a.tobytes()


def rows(path):
    with path.open('rb') as stream:
        magic, total, packets = struct.unpack('<4sQI', stream.read(16))
        assert magic == b'CLM1'
        count = 0
        for _ in range(packets):
            nv, nt = struct.unpack('<HH', stream.read(4))
            vertices = np.frombuffer(stream.read(nv * 44), '<f4').reshape(nv, 11)
            triangles = np.frombuffer(stream.read(nt * 11), DT)
            q = vertices[triangles['indices']]
            a = np.zeros((nt, 36), '<f4')
            a[:, :9] = q[:, :, :3].reshape(nt, 9)
            a[:, 9:18] = q[:, :, 3:6].reshape(nt, 9)
            a[:, 18] = triangles['material']
            a[:, 19] = triangles['object']
            a[:, 20:26] = q[:, :, 6:8].reshape(nt, 6)
            a[:, 26:35] = q[:, :, 8:11].reshape(nt, 9)
            yield count, a
            count += nt
        assert count == total and not stream.read(1)


def local(path):
    selected, indices = [], []
    for first, a in rows(path):
        xyz = a[:, :9].reshape(-1, 3, 3)
        mask = ((a[:, 18] == 11) & (xyz[:, :, 0].max(1) >= 488) &
                (xyz[:, :, 0].min(1) <= 667) & (xyz[:, :, 1].max(1) >= -306) &
                (xyz[:, :, 1].min(1) <= -281))
        if mask.any():
            selected.append(a[mask])
            indices.append(np.flatnonzero(mask) + first)
    return np.concatenate(selected), np.concatenate(indices)


def triangle_row(xyz, uv, tint, material, object_id):
    xyz = np.asarray(xyz, '<f4')
    normal = np.cross(xyz[1].astype(float) - xyz[0], xyz[2].astype(float) - xyz[0])
    length = np.linalg.norm(normal)
    assert length > 1e-12, 'Refined edge triangle degenerated'
    uv = np.asarray(uv, float)
    uv -= np.floor(uv[0] / .256) * .256
    a = np.zeros(36, '<f4')
    a[:9] = xyz.ravel()
    a[9:18] = np.tile(normal / length, 3)
    a[18:20] = [material, object_id]
    a[20:26] = uv.ravel()
    a[26:35] = np.asarray(tint).ravel()
    return a


def refine_pair(pair, surface):
    p = pair[:, :9].reshape(2, 3, 3).astype(float)
    assert np.array_equal(p[0, 0], p[1, 0]) and np.array_equal(p[0, 2], p[1, 1])
    assert np.array_equal(p[0, 0, :2], p[1, 2, :2])
    assert np.array_equal(p[0, 1, :2], p[0, 2, :2])
    assert np.array_equal(pair[0, 18:20], pair[1, 18:20])
    a, b = p[0, 0, :2], p[0, 1, :2]
    direction = b - a
    length2 = direction @ direction
    assert length2 > 1e-10
    length = np.sqrt(length2)
    line = LineString([a, b])
    candidates = surface.tree.query(line.buffer(.0002))
    parameters = [0., 1.]
    for index in candidates:
        polygon = surface.polygons[index]
        intersection = line.intersection(polygon.boundary)
        coords = shapely.get_coordinates(intersection)
        if len(coords):
            parameters.extend(((coords - a) @ direction / length2).tolist())
        # Independent tessellations can round nominally collinear boundaries
        # by a few micrometres. Project their nearby vertices too.
        vertices = surface.triangles[index, :, :2]
        t = (vertices - a) @ direction / length2
        projection = a + t[:, None] * direction
        close = (np.linalg.norm(vertices - projection, axis=1) <= .0002) & (t > 0) & (t < 1)
        parameters.extend(t[close].tolist())
    parameters = sorted(np.clip(parameters, 0, 1))
    knots = []
    for t in parameters:
        xy = (a + t * direction).astype('<f4').astype(float)
        if not knots or np.linalg.norm(xy - knots[-1][1]) > 1e-7:
            knots.append((float(t), xy))
    assert np.array_equal(knots[0][1], a) and np.array_equal(knots[-1][1], b)
    xy = np.asarray([k[1] for k in knots])
    t = (xy - a) @ direction / length2
    drift = np.linalg.norm(xy - (a + t[:, None] * direction), axis=1)
    assert drift.max() < .00006, 'Perimeter deviation exceeds float32 rounding'
    top_z = surface.height(xy)
    assert np.isfinite(top_z).all(), ('No cap support for edge knot', xy[~np.isfinite(top_z)])
    bottom_z = p[0, 0, 2] * (1 - t) + p[0, 1, 2] * t
    assert np.all(top_z > bottom_z)
    bottom = np.c_[xy, bottom_z].astype('<f4')
    top = np.c_[xy, top_z].astype('<f4')
    uv0 = pair[0, 20:26].reshape(3, 2).astype(float)
    u = uv0[0, 0] + t * (uv0[1, 0] - uv0[0, 0])
    bottom_uv = np.c_[u, bottom[:, 2].astype(float) / 1.25]
    top_uv = np.c_[u, top[:, 2].astype(float) / 1.25]
    c = pair[:, 26:35].reshape(2, 3, 3).astype(float)
    bottom_tint = c[0, 0] * (1 - t[:, None]) + c[0, 1] * t[:, None]
    top_tint = c[1, 2] * (1 - t[:, None]) + c[0, 2] * t[:, None]
    material, object_id = map(int, pair[0, 18:20])
    result = []
    for j in range(len(knots) - 1):
        for points, uv, tint in [
            ([bottom[j], bottom[j + 1], top[j + 1]], [bottom_uv[j], bottom_uv[j + 1], top_uv[j + 1]], [bottom_tint[j], bottom_tint[j + 1], top_tint[j + 1]]),
            ([bottom[j], top[j + 1], top[j]], [bottom_uv[j], top_uv[j + 1], top_uv[j]], [bottom_tint[j], top_tint[j + 1], top_tint[j]])]:
            result.append(triangle_row(points, uv, tint, material, object_id))
    # The 17-point independent verifier will still test the actual output;
    # this local preflight catches a chord spanning a missed cap breakpoint.
    maximum_gap = 0.
    for j in range(len(top) - 1):
        weights = np.linspace(0, 1, 9)[:, None]
        points = top[j] * (1 - weights) + top[j + 1] * weights
        z = surface.height(points[:, :2])
        assert np.isfinite(z).all()
        maximum_gap = max(maximum_gap, float(np.max(abs(points[:, 2] - z))))
    assert maximum_gap < .002, ('Missed cap facet breakpoint', a, b, maximum_gap)
    provenance = {'material': material, 'object': object_id, 'source_xy_endpoints_m': [a.tolist(), b.tolist()],
                  'source_bottom_z_endpoints_m': [float(p[0, 0, 2]), float(p[0, 1, 2])],
                  'source_top_z_endpoints_m': [float(p[1, 2, 2]), float(p[0, 2, 2])],
                  'parameter_knots': t.tolist(), 'output_piece_count': len(knots) - 1,
                  'maximum_xy_rounding_drift_m': float(drift.max()),
                  'preflight_maximum_cap_gap_m': maximum_gap,
                  'source_pair_canonical_sha256': hashlib.sha256(canonical(pair)).hexdigest()}
    return np.asarray(result, '<f4'), provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=R / 'evidence/sabado-profile-v1/contact.clm')
    parser.add_argument('--output-dir', type=Path, default=R / 'evidence/sabado-profile-closed-v2')
    args = parser.parse_args()
    target = args.output_dir / 'contact.clm'
    assert args.source.resolve() != target.resolve()
    recovered = R / 'evidence/full-iv-path-uv-rebased/contact.clm'
    profile_receipt = json.loads((args.source.parent / 'PROFILE_RECEIPT.json').read_text())
    assert profile_receipt['passed']
    with args.source.open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert source_hash == profile_receipt['output_sha256']
    contact = json.loads((R / 'evidence/full-iv-contact/CONTACT_RECEIPT.json').read_text())
    edge_ids = {p['object'] for p in contact['parts'] if p['name'].endswith('_closed_edges')}
    before, before_indices = local(recovered)
    profiled, indices = local(args.source)
    assert np.array_equal(before_indices, indices) and before.shape == profiled.shape
    assert np.array_equal(before[:, 18:20], profiled[:, 18:20])
    edge = np.isin(profiled[:, 19].astype(int), list(edge_ids))
    surface = Surface(profiled[~edge, :9].reshape(-1, 3, 3).astype(float))
    original_cap = before[~edge, :9].reshape(-1, 3, 3)
    profiled_cap = profiled[~edge, :9].reshape(-1, 3, 3)
    cap_changed = np.any(original_cap != profiled_cap, axis=(1, 2))
    changed_surface = Surface(profiled_cap[cap_changed].astype(float))
    edge_local = np.flatnonzero(edge)
    assert len(edge_local) % 2 == 0
    replacements, deleted, provenance = {}, set(), []
    for j in range(0, len(edge_local), 2):
        pair_local = edge_local[j:j + 2]
        pair_indices = indices[pair_local]
        assert pair_indices[1] == pair_indices[0] + 1
        original_pair, profile_pair = before[pair_local], profiled[pair_local]
        endpoints_changed = not np.array_equal(original_pair[:, :9], profile_pair[:, :9])
        pair_xyz = profile_pair[:, :9].reshape(2, 3, 3).astype(float)
        line = LineString(pair_xyz[1, [2, 1], :2])
        candidates = changed_surface.tree.query(line.buffer(.00015))
        adjacent_changed_cap = any(changed_surface.polygons[k].distance(line) <= .00015 for k in candidates)
        if not endpoints_changed and not adjacent_changed_cap:
            continue
        replacement, record = refine_pair(profile_pair, surface)
        record['selection'] = {'profile_changed_endpoint': endpoints_changed, 'adjacent_changed_cap': bool(adjacent_changed_cap)}
        record['source_triangle_indices'] = pair_indices.tolist()
        replacements[int(pair_indices[0])] = (replacement, record)
        deleted.add(int(pair_indices[1]))
        provenance.append(record)
    assert replacements
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'EDGE_ADAPTER_SOURCE_SNAPSHOT.py').write_bytes(Path(__file__).read_bytes())
    expected, unchanged_before, nonedge_before = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    expected_unchanged, count_before, count_after = 0, 0, 0
    with Meshlets(target) as writer:
        for first, a in rows(args.source):
            count_before += len(a)
            unchanged = np.ones(len(a), dtype=bool)
            pieces = []
            cursor = 0
            for k in range(len(a)):
                index = first + k
                if index not in replacements and index not in deleted:
                    continue
                if k > cursor:
                    pieces.append(a[cursor:k])
                unchanged[k] = False
                if index in replacements:
                    replacement, record = replacements[index]
                    record['output_triangle_start'] = count_after + sum(len(p) for p in pieces)
                    record['output_triangle_count'] = len(replacement)
                    pieces.append(replacement)
                cursor = k + 1
            if cursor < len(a):
                pieces.append(a[cursor:])
            output = np.concatenate(pieces) if pieces else np.empty((0, 36), '<f4')
            unchanged_before.update(canonical(a[unchanged]))
            expected_unchanged += int(unchanged.sum())
            nonedge_before.update(canonical(a[~np.isin(a[:, 19].astype(int), list(edge_ids))]))
            if len(output):
                expected.update(canonical(output))
                writer.add(output)
                count_after += len(output)
    actual, unchanged_after, nonedge_after = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    ranges = [(p['output_triangle_start'], p['output_triangle_start'] + p['output_triangle_count']) for p in provenance]
    actual_unchanged = 0
    for first, a in rows(target):
        actual.update(canonical(a))
        selected = np.ones(len(a), dtype=bool)
        for lo, hi in ranges:
            if hi > first and lo < first + len(a):
                selected[max(0, lo - first):min(len(a), hi - first)] = False
        unchanged_after.update(canonical(a[selected]))
        actual_unchanged += int(selected.sum())
        nonedge_after.update(canonical(a[~np.isin(a[:, 19].astype(int), list(edge_ids))]))
    assert expected.digest() == actual.digest(), 'Serialized float values changed'
    assert nonedge_before.digest() == nonedge_after.digest(), 'Cap or non-edge payload changed'
    assert unchanged_before.digest() == unchanged_after.digest() and actual_unchanged == expected_unchanged
    assert writer.triangles == count_after
    with args.source.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == source_hash, 'Input profile changed'
    with target.open('rb') as stream:
        output_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    record = {'passed': True, 'source': str(args.source), 'target': str(target),
              'source_sha256': source_hash, 'output_sha256': output_hash,
              'source_triangles': count_before, 'output_triangles': count_after,
              'reconciled_original_segments': len(provenance),
              'nonedge_payload_order_canonical_sha256': nonedge_before.hexdigest(),
              'unchanged_faces_canonical_sha256': unchanged_before.hexdigest(),
              'serialized_all_fields_canonical_sha256': actual.hexdigest(),
              'immutable_cap_and_nonedge_faces': True, 'immutable_source_profile': True,
              'semantic_source_ids_preserved': True, 'source_terrain_untouched': True,
              'provenance': provenance,
              'limits': 'Only local path edge quads changed by the profile or adjacent to a changed cap triangle are replaced. All cap and other faces retain every deindexed float value and order. Refined perimeter and bottom-line interpolation allow float32 rounding only; mapped source footprints and widths are not edited. Signed zero is canonicalized for exact float-value hashing.'}
    (args.output_dir / 'EDGE_RECONCILIATION_RECEIPT.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k != 'provenance'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
