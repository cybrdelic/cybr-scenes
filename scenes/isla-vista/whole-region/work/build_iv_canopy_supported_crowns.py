"""Authored crown construction constrained by dated classified canopy support.

Mapped roots and current height envelopes stay fixed. The map constrains lateral
foliage support only; association, branches, heights within the envelope and
aggregate leaf groups remain estimates. Unassociated canopy is not filled here.
"""
from pathlib import Path
import hashlib
import json
import sys

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / 'geo-deps'), str(r / 'work/iv-component-runtime')]
import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt, label
from scipy.spatial import cKDTree
from iv_mesh_parts import Parts, leaf_mesh

out = r / 'evidence/full-iv-canopy-supported-crowns'
out.mkdir(exist_ok=True)
support = r / 'evidence/full-iv-canopy-support'
audit = json.loads((support / 'CANOPY_SUPPORT_AUDIT.json').read_text())
assert audit['passed']
source = json.loads((r / 'evidence/full-iv-regional-vegetation/SOURCE_TREE_AUDIT.json').read_text())
regional = json.loads((r / 'evidence/full-iv-regional-vegetation/REGIONAL_VEGETATION_RECEIPT.json').read_text())
rows = source['sources']
points = np.load(support / 'source_support_assignments.npz')
assert list(points['source_ids']) == [x['source_id'] for x in rows]
xy = points['classified_local_xy_m']
yy, xx = points['native_row'], points['native_column']
nearest = points['nearest_source_index']
eligible = points['eligible_radius_rule']
roots = np.array([x['source_xy_m'] for x in rows])
root_distance, root_pixel = cKDTree(xy).query(roots, workers=2)
with rasterio.open(r / 'data/urban-canopy-2022/iv_canopy_2022_native_060m.tif') as ds:
    mask = ds.read(1) == 1
    labels, components = label(mask, structure=np.ones((3, 3), dtype='uint8'))
    clearance = distance_transform_edt(mask, sampling=.6).astype('f4')
same_component = labels[yy, xx] == labels[yy[root_pixel[nearest]], xx[root_pixel[nearest]]]
selected_indices = np.flatnonzero(eligible & same_component)
selected_indices = selected_indices[np.argsort(nearest[selected_indices], kind='stable')]
sorted_roots = nearest[selected_indices]
starts = np.searchsorted(sorted_roots, np.arange(len(rows)), side='left')
ends = np.searchsorted(sorted_roots, np.arange(len(rows)), side='right')
parts = Parts(out / 'canopy_supported_crowns.clm', 16000000)
records, replaced_sources = [], set()

def tube(a, b, ra, rb, sides=4):
    a, b = np.asarray(a, float), np.asarray(b, float)
    axis = b - a
    axis /= np.linalg.norm(axis)
    ref = np.array([0., 0., 1.]) if abs(axis[2]) < .95 else np.array([1., 0., 0.])
    u = np.cross(axis, ref);u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    angles = np.arange(sides) * 2 * np.pi / sides
    ring = np.cos(angles)[:, None] * u + np.sin(angles)[:, None] * v
    vertices = np.vstack([a + ra * ring, b + rb * ring])
    faces = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.extend([[i, j, sides + j], [i, sides + j, sides + i]])
    return vertices, np.asarray(faces)

for index, row in enumerate(rows):
    # Leaf-form-specific palm/conifer tiers need their own correspondence gate.
    if row['form'] != 'broadleaf' or root_distance[index] > 3.:
        continue
    ids = selected_indices[starts[index]:ends[index]]
    if len(ids) * .36 < 10.:
        continue
    old_low, old_high = np.asarray(row['original_bounds_m'])
    root = roots[index]
    height = old_high[2] - old_low[2]
    relative = xy[ids] - root
    # A 1.2 m regional sampling lattice selects original classified cell
    # centres. The mask is never enlarged or converted into a surface texture.
    bins = np.floor(relative / 1.2).astype('i4')
    unique, inverse = np.unique(bins, axis=0, return_inverse=True)
    chosen = []
    for group, cell in enumerate(unique):
        candidates = ids[inverse == group]
        target = root + (cell + .5) * 1.2
        chosen.append(candidates[np.argmin(np.linalg.norm(xy[candidates] - target, axis=1))])
    chosen = np.asarray(chosen)
    # EDT measures centre-to-centre distance. Subtract half the native cell
    # diagonal plus 5 mm before using it as a conservative in-mask radius.
    radii = np.minimum(1.05, np.maximum(0., clearance[yy[chosen], xx[chosen]] - .6 / np.sqrt(2) - .005)) * .995
    keep = radii >= .14
    chosen, radii = chosen[keep], radii[keep]
    if len(chosen) < 8:
        continue
    centers_xy = xy[chosen]
    radial = np.linalg.norm(centers_xy - root, axis=1)
    reach = max(float(radial.max()), 1.)
    crown_z = old_low[2] + height * (.54 + .34 * np.sqrt(np.maximum(0, 1 - (radial / (reach * 1.03)) ** 2)))
    seed = int.from_bytes(hashlib.sha256((row['source_id'] + ':canopy-supported-v1').encode()).digest()[:8], 'little')
    rng = np.random.default_rng(seed)
    leaf_centers, axes, lengths, widths, rolls, shoot_roots = [], [], [], [], [], []
    stems = [tube(np.r_[root, old_low[2]], np.r_[root, old_low[2] + height * .52], max(.10, height * .018), .065, 6)]
    for point, z, radius in zip(centers_xy, crown_z, radii):
        tip = np.r_[point, z - height * .07]
        stems.append(tube(np.r_[root, old_low[2] + height * .46], tip, .025, .006))
        for layer in range(2):
            angle = rng.uniform(0, 2 * np.pi)
            axis = np.array([np.cos(angle), np.sin(angle), rng.uniform(-.28, .28)])
            axis /= np.linalg.norm(axis)
            leaf_centers.append(np.r_[point, z - layer * height * .12])
            axes.append(axis)
            lengths.append(radius * 2)
            widths.append(radius * 1.65)
            rolls.append(rng.uniform(-.5, .5))
            shoot_roots.append(tip)
    fv, ff = leaf_mesh(leaf_centers, axes, lengths, widths, rolls=rolls)
    for leaf_index, shoot_root in enumerate(shoot_roots):
        stems.append(tube(shoot_root, fv[leaf_index * 5 + 4], .006, .0025, 3))
    # Match the previous visible top without moving any horizontal support.
    factor = height / (fv[:, 2].max() - old_low[2])
    fv[:, 2] = old_low[2] + (fv[:, 2] - old_low[2]) * factor
    wood_vertices, wood_faces, offset = [], [], 0
    for v, f in stems:
        v[:, 2] = old_low[2] + (v[:, 2] - old_low[2]) * factor
        wood_vertices.append(v);wood_faces.append(f + offset);offset += len(v)
    sv, sf = np.concatenate(wood_vertices), np.concatenate(wood_faces)
    # A tube's radial cap can extend slightly above its endpoint. Keep the
    # supporting wood inside the same source height envelope as the foliage.
    sv[:, 2] = np.clip(sv[:, 2], old_low[2], old_high[2])
    total_before = parts.writer.triangles
    estimate = 'Source root and prior visible height retained. Crown support follows associated 2022 classified cells; branch form and vertical foliage distribution are authored. Foliage facets aggregate unresolved leaves.'
    parts.mesh(row['source_id'].replace(':', '_') + '_supported_wood', sv, sf, 39, row['source_id'], estimate)
    parts.mesh(row['source_id'].replace(':', '_') + '_supported_foliage', fv, ff, 42, row['source_id'], estimate)
    replaced_sources.add(row['source_id'])
    records.append({'source_id': row['source_id'], 'source_xy_m': row['source_xy_m'],
        'source_genus': row['source_genus'], 'source_family': row['source_family'],
        'previous_bounds_m': row['original_bounds_m'],
        'candidate_bounds_m': [np.minimum(sv.min(0), fv.min(0)).tolist(), np.maximum(sv.max(0), fv.max(0)).tolist()],
        'prior_visible_height_m': height, 'source_height_tag_m': row['source_height_tag_m'],
        'root_to_nearest_classified_cell_m': float(root_distance[index]),
        'associated_native_cell_area_m2': len(ids) * .36,
        'foliage_group_centres': len(chosen), 'triangles': parts.writer.triangles - total_before,
        'association': 'Nearest mapped root within the same connected classified component; maximum radius follows the audited authored height-based rule.'})
    if len(records) % 500 == 0:
        print('SUPPORTED_CROWNS', len(records), parts.writer.triangles, flush=True)
assert records
report = parts.close()
report.update(trees=records, source_tree_count=len(records), material_count=0,
    replaced_regional_objects=[x['object'] for x in regional['parts'] if x['source'] in replaced_sources],
    classified_source_year=2022, native_source_subset_sha256=hashlib.sha256((r / 'data/urban-canopy-2022/iv_canopy_2022_native_060m.tif').read_bytes()).hexdigest(),
    association_is_authored=True, unmapped_stems_added=0, source_roots_moved=0,
    coordinate_operation_advertised_accuracy_m=audit['coordinate_operation_advertised_accuracy_m'],
    positional_uncertainty='The retained EPSG:3310-to-EPSG:32611 NAD83/WGS84 operation advertises 4 m accuracy in this evaluated environment. The 3 m nearest-canopy selection is an authored rule, not a correspondence confidence bound or sub-metre survey claim.',
    original_material_ids=[39, 42], cluster_spacing_m=1.2,
    limits='Dated 2D classification constrains horizontal support; it does not provide tree identities, height, species, branches, leaf density or current ecological state. This first pass changes eligible existing broadleaf crowns only. Palms, conifers, unassociated source trees and unassigned classified canopy remain unchanged. No photographic texture or scan mesh is used. Validation and actual matched rendering remain required.')
(out / 'CANOPY_SUPPORTED_CROWNS_RECEIPT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'trees': len(records), 'triangles': report['triangles'], 'meshlets': report['meshlets']}), flush=True)
