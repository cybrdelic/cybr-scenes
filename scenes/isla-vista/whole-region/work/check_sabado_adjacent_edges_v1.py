"""Check every edge touching a changed cap, including unchanged endpoints."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
R = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(R / 'geo-deps'), str(R / 'whole-iv-vendor'), str(R / 'work')]
import numpy as np
import shapely
from shapely.geometry import LineString
from verify_sabado_profile_v1 import local_faces, Surface, summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, default=R / 'evidence/sabado-profile-closed-v1/contact.clm')
    args = parser.parse_args()
    receipt = json.loads((R / 'evidence/full-iv-contact/CONTACT_RECEIPT.json').read_text())
    edges = {p['object'] for p in receipt['parts'] if p['name'].endswith('_closed_edges')}
    old, old_ids, _ = local_faces(R / 'evidence/full-iv-path-uv-rebased/contact.clm')
    new, new_ids, _ = local_faces(args.target)
    old_top = old[~np.isin(old_ids['object'], list(edges)), :, :3]
    new_top = new[~np.isin(new_ids['object'], list(edges)), :, :3]
    assert old_top.shape == new_top.shape
    assert np.array_equal(old_top[:, :, :2], new_top[:, :, :2])
    changed = np.any(old_top != new_top, axis=(1, 2))
    changed_surface, surface = Surface(new_top[changed]), Surface(new_top)
    edge_faces = new[np.isin(new_ids['object'], list(edges)), :, :3]
    assert len(edge_faces) % 2 == 0
    checked, missing, gaps = 0, 0, []
    worst = {'gap_m': 0.}
    for j in range(0, len(edge_faces), 2):
        first, second = edge_faces[j:j + 2]
        assert np.array_equal(first[0], second[0]) and np.array_equal(first[2], second[1])
        top = second[[2, 1]]
        line = LineString(top[:, :2])
        candidates = changed_surface.tree.query(line.buffer(.00015))
        if not any(changed_surface.polygons[k].distance(line) <= .00015 for k in candidates):
            continue
        checked += 1
        weights = np.linspace(0, 1, 17)[:, None]
        points = top[0] * (1 - weights) + top[1] * weights
        heights = surface.height(points[:, :2])
        valid = np.isfinite(heights)
        missing += int((~valid).sum())
        error = abs(points[valid, 2] - heights[valid])
        gaps.extend(error.tolist())
        if len(error) and error.max() > worst['gap_m']:
            k = int(np.argmax(error))
            worst = {'gap_m': float(error[k]), 'xyz_m': points[valid][k].tolist(),
                     'edge_xy_endpoints_m': top[:, :2].tolist()}
    with args.target.open('rb') as stream:
        target_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    record = {'passed': bool(checked and not missing and max(gaps) <= .002),
              'target': str(args.target), 'target_sha256': target_hash,
              'scope': 'Every local path edge adjacent to any changed cap triangle, including unchanged endpoint pairs.',
              'adjacent_edge_segments': checked, 'matched_samples': len(gaps), 'unmatched_samples': missing,
              'absolute_gap_m': summarize(gaps), 'worst': worst, 'tolerance_m': .002}
    output = args.target.parent / 'ADJACENT_CAP_EDGE_SCOPE_VERIFICATION.json'
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2), flush=True)
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
