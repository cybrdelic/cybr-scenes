"""Explicit aggregate-foliage tier for the whole-area camera.

The facets represent groups of unresolved foliage, not metre-long individual
leaves. Source positions and the current vertical envelope are preserved. The
near-street plant meshes remain independent assets for closer views.
"""
from pathlib import Path
import hashlib
import json
import sys

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / 'geo-deps'), str(r / 'work/iv-component-runtime')]
import numpy as np
from iv_mesh_parts import Parts, leaf_mesh

out = r / 'evidence/full-iv-regional-vegetation'
audit = json.loads((out / 'SOURCE_TREE_AUDIT.json').read_text())
assert audit['passed']
parts = Parts(out / 'regional_vegetation.clm', 15400000)
trunk_material, leaf_material = 39, 42
records = []

def tube(a, b, ra, rb, sides=5):
    a, b = np.asarray(a, float), np.asarray(b, float)
    axis = (b - a) / np.linalg.norm(b - a)
    reference = np.array([0., 0., 1.]) if abs(axis[2]) < .95 else np.array([1., 0., 0.])
    u = np.cross(axis, reference)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    t = np.arange(sides) * 2 * np.pi / sides
    ring = np.cos(t)[:, None] * u + np.sin(t)[:, None] * v
    vertices = np.vstack([a + ra * ring, b + rb * ring])
    faces = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.extend([[i, j, sides + j], [i, sides + j, sides + i]])
    return vertices, np.asarray(faces)

def combine(items):
    vertices, faces = [], []
    offset = 0
    for v, f in items:
        vertices.append(v)
        faces.append(f + offset)
        offset += len(v)
    return np.concatenate(vertices), np.concatenate(faces)

def normals(v, f):
    n = np.zeros_like(v)
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for corner in range(3):
        np.add.at(n, f[:, corner], cross)
    length = np.linalg.norm(n, axis=1)
    assert np.all(length > 1e-12)
    return n / length[:, None]

for index, row in enumerate(audit['sources']):
    source = row['source_id']
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256((source + ':regional-foliage-v1').encode()).digest()[:8], 'little'))
    xy = np.asarray(row['source_xy_m'], float)
    old_low, old_high = np.asarray(row['original_bounds_m'])
    height = row['retained_height_parameter_m']
    origin = np.r_[xy, old_low[2]]
    stem, foliage = [], []
    if row['form'] in {'fan palm', 'pinnate palm'}:
        crown = np.array([0., 0., height * .9])
        stem.append(tube([0, 0, 0], crown, max(.10, height * .024), max(.08, height * .018), 6))
        if row['form'] == 'fan palm':
            for j in range(14):
                az = j * 2.39996323 + rng.uniform(-.12, .12)
                elevation = np.interp((j + .5) / 14, [0, 1], [1.12, -.7])
                radial = np.array([np.cos(az), np.sin(az), 0.])
                axis = radial * np.cos(elevation) + np.array([0, 0, np.sin(elevation)])
                side = np.array([-radial[1], radial[0], 0.])
                n = np.cross(side, axis)
                hub = crown + axis * min(1.4, height * .10)
                stem.append(tube(crown, hub, .025, .012, 3))
                radius = min(1.2, height * .095)
                vertices, faces = [], []
                angles = np.linspace(-1.25, 1.25, 13)
                for a, b in zip(angles[:-1], angles[1:]):
                    middle = (a + b) * .5
                    def point(angle, distance, ridge=0.):
                        return hub + (axis * np.cos(angle) + side * np.sin(angle)) * radius * distance + n * (radius * .12 * distance ** 2 + ridge)
                    start = len(vertices)
                    vertices.extend([hub, point(a, .95), point(middle, 1., .025), point(b, .95)])
                    faces.extend((np.array([[0, 1, 2], [0, 2, 3]]) + start).tolist())
                foliage.append((np.asarray(vertices), np.asarray(faces)))
            representation = 'Source-genus fan form; reduced folded fan sectors retain aggregate blade coverage.'
        else:
            for j in range(22):
                az = j * 2.39996323 + rng.uniform(-.1, .1)
                axis = np.array([np.cos(az), np.sin(az), 0.])
                side = np.array([-axis[1], axis[0], 0.])
                reach = height * rng.uniform(.24, .31)
                age = (j + .5) / 22
                lift = reach * np.interp(age, [0, 1], [.75, .16])
                drop = reach * np.interp(age, [0, 1], [.18, .85])
                vertices, faces = [], []
                for k, t in enumerate(np.linspace(0, 1, 6)):
                    center = crown + axis * reach * t + [0, 0, lift * np.sin(np.pi * t * .72) - drop * t * t]
                    width = max(.015, (.15 + .63 * np.sin(np.pi * t)) * min(1.3, reach / 2.5) * .72)
                    vertices.extend([center - side * width, center + [0, 0, width * .07], center + side * width])
                    if k:
                        a, b = (k - 1) * 3, k * 3
                        faces.extend([[a, a + 1, b + 1], [a, b + 1, b], [a + 1, a + 2, b + 2], [a + 1, b + 2, b + 1]])
                foliage.append((np.asarray(vertices), np.asarray(faces)))
            representation = 'Coalesced pinnate-frond coverage; ribbons represent unresolved leaflet groups. Family-only palm form remains illustrative.'
    else:
        radius = height * .27
        crown = np.array([0., 0., height * .66])
        stem.append(tube([0, 0, 0], [0, 0, height * .55], max(.10, height * .018), .05, 6))
        centers, axes, lengths, widths, rolls = [], [], [], [], []
        for branch in range(8):
            az = branch * 2.39996323
            zz = -.65 + 1.3 * (branch + .5) / 8
            direction = np.array([np.cos(az) * np.sqrt(1 - zz * zz), np.sin(az) * np.sqrt(1 - zz * zz), zz])
            end = crown + direction * [radius * .72, radius * .72, height * .23]
            root = np.array([0., 0., height * (.34 + .10 * rng.random())])
            stem.append(tube(root, end, .047, .018, 4))
            for shoot in range(3):
                delta = rng.normal(size=3)
                delta /= np.linalg.norm(delta)
                cluster = end + delta * radius * .13
                for patch in range(5):
                    a = rng.normal(size=3)
                    a[2] *= .4
                    a /= np.linalg.norm(a)
                    center = cluster + rng.normal(size=3) * np.array([radius * .10, radius * .10, height * .025])
                    length = radius * rng.uniform(.49, .65)
                    centers.append(center)
                    axes.append(a)
                    lengths.append(length)
                    widths.append(length * rng.uniform(.52, .68))
                    rolls.append(rng.uniform(-1.1, 1.1))
        v, f = leaf_mesh(centers, axes, lengths, widths, folded=True, rolls=rolls)
        foliage.append((v, f))
        representation = 'Branch-supported aggregate foliage facets with inter-cluster holes. Facets represent unresolved leaf groups, not individual enlarged leaves or an opaque crown shell.'
    sv, sf = combine(stem)
    fv, ff = combine(foliage)
    all_vertices = np.vstack([sv, fv])
    # Fit the existing visible envelope around the same root point. This
    # changes representation, not geographic placement or tree height.
    scaling = np.ones(3)
    for axis in [0, 1]:
        left = xy[axis] - old_low[axis]
        right = old_high[axis] - xy[axis]
        negative = max(1e-9, -all_vertices[:, axis].min())
        positive = max(1e-9, all_vertices[:, axis].max())
        scaling[axis] = min(left / negative, right / positive)
        assert scaling[axis] > 0
    scaling[2] = (old_high[2] - old_low[2]) / all_vertices[:, 2].max()
    sv = sv * scaling + origin
    fv = fv * scaling + origin
    actual = np.vstack([sv, fv])
    assert np.all(actual.min(0) >= old_low - 1e-8)
    assert np.all(actual.max(0) <= old_high + 1e-8)
    assert abs(actual[:, 2].max() - old_high[2]) < 1e-8
    start = parts.writer.triangles
    estimate = 'Mapped source root and prior height envelope retained; fixed overview aggregation of authored foliage. Detailed near-street geometry remains a separate asset.'
    parts.mesh(source.replace(':', '_') + '_regional_stem', sv, sf, trunk_material, source, estimate, normals=normals(sv, sf))
    parts.mesh(source.replace(':', '_') + '_regional_foliage', fv, ff, leaf_material, source, estimate, normals=normals(fv, ff))
    t = fv[ff]
    surface_area = float(np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() * .5)
    records.append({'source_id': source, 'source_xy_m': xy.tolist(),
        'source_genus': row['source_genus'], 'source_family': row['source_family'],
        'retained_height_parameter_m': height, 'original_visible_height_m': row['original_visible_height_m'],
        'form': row['form'], 'representation': representation,
        'geometry_scale_to_existing_envelope': scaling.tolist(),
        'original_bounds_m': row['original_bounds_m'], 'candidate_bounds_m': [actual.min(0).tolist(), actual.max(0).tolist()],
        'aggregate_foliage_surface_area_m2': surface_area,
        'triangles': parts.writer.triangles - start, 'previous_visible_triangles': row['original_visible_triangles']})
    if (index + 1) % 500 == 0:
        print('REGIONAL_TREES', index + 1, parts.writer.triangles, flush=True)
report = parts.close()
report.update(source_trees=len(records), trees=records, material_count=0,
    material_reuse={'trunk': trunk_material, 'leaf_reflection_transmission_blend': leaf_material},
    replace_meshes=audit['meshes'], original_visible_tree_triangles=audit['visible_tree_triangles'],
    source_audit_sha256=hashlib.sha256((out / 'SOURCE_TREE_AUDIT.json').read_bytes()).hexdigest(),
    selection='Explicit fixed regional view tier. No dynamic screen-error selector or streaming implementation.',
    limits='Aggregate geometry approximation, not transport-equivalent simplification or individual leaf reconstruction. Crown coverage, leaf-group geometry and taxonomy-dependent form remain authored. Existing source root points and visible height bounds are retained. Actual visual and memory comparisons are required. The detailed street assets remain unchanged for their original views.')
(out / 'REGIONAL_VEGETATION_RECEIPT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'trees': len(records), 'triangles': report['triangles'], 'meshlets': report['meshlets'],
    'previous_tree_triangles': audit['visible_tree_triangles']}), flush=True)
