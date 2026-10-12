"""Compare dated geographic canopy support with current mapped-tree envelopes.

Bounding boxes are deliberately treated as an upper bound, not as the actual
projected leaf coverage. This diagnostic does not infer tree identity or height.
"""
from pathlib import Path
import hashlib
import json
import sys

r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(r / 'geo-deps'))
import numpy as np
import rasterio
from rasterio.features import geometry_mask, rasterize
from rasterio.warp import transform_geom
from scipy.spatial import cKDTree
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

out = r / 'evidence/full-iv-canopy-support'
out.mkdir(exist_ok=True)
ref = r / 'references/urban-canopy-2022'
native_input = r / 'data/urban-canopy-2022/iv_canopy_2022_native_060m.tif'
input_receipt = json.loads((ref / 'IV_NATIVE_SUBSET_RECEIPT.json').read_text())
assert hashlib.sha256(native_input.read_bytes()).hexdigest() == input_receipt['subset_sha256']
origin = np.array([237001.80699345336, 3811663.448398269])
to_albers = Transformer.from_crs(32611, 3310, always_xy=True)
to_utm = Transformer.from_crs(3310, 32611, always_xy=True)
from_wgs = Transformer.from_crs(4326, 3310, always_xy=True)
audit = json.loads((r / 'evidence/full-iv-regional-vegetation/SOURCE_TREE_AUDIT.json').read_text())
roots = np.array([x['source_xy_m'] for x in audit['sources']])
root_albers = np.column_stack(to_albers.transform(*(roots + origin).T))
boxes = []
for row in audit['sources']:
    lo, hi = np.asarray(row['original_bounds_m'])
    p = box(*(lo[:2] + origin), *(hi[:2] + origin))
    boxes.append(transform(to_albers.transform, p))
urban = unary_union([transform(from_wgs.transform, shape(feature['geometry']))
    for year in [2010, 2020]
    for feature in json.loads((ref / f'CENSUS_{year}_URBAN_AREAS.geojson').read_text())['features']])
cdp = transform(from_wgs.transform, shape(json.loads((r / 'evidence/whole-iv-coverage/isla_vista_cdp.geojson').read_text())['features'][0]['geometry']))
tile = transform(to_albers.transform, box(*(origin - 1300), *(origin + 1300)))
with rasterio.open(native_input) as ds:
    data = ds.read(1)
    tile_mask = geometry_mask([mapping(tile)], out_shape=data.shape, transform=ds.transform, invert=True)
    nominal_mask = geometry_mask([mapping(urban)], out_shape=data.shape, transform=ds.transform, invert=True)
    tree_boxes = rasterize([(mapping(x), 1) for x in boxes], out_shape=data.shape,
        transform=ds.transform, fill=0, dtype='uint8')
    classified = (data == 1) & tile_mask
    yy, xx = np.nonzero(classified)
    x = ds.transform.c + (xx + .5) * ds.transform.a
    y = ds.transform.f + (yy + .5) * ds.transform.e
    uv = np.column_stack(to_utm.transform(x, y)) - origin
    distances, nearest = cKDTree(roots).query(uv, workers=2)
    native_tree_distance, _ = cKDTree(np.column_stack([x, y])).query(root_albers, workers=2)
    pixel_area = abs(ds.transform.a * ds.transform.e)
    cap = np.maximum(4., np.minimum(14., np.array([q['retained_height_parameter_m'] for q in audit['sources']]) * .8))
    eligible = distances <= cap[nearest]
    assignment = np.bincount(nearest[eligible], minlength=len(roots))
    # Saved coordinates are exact classified-cell centres transformed to the
    # scene CRS. Nearest-root association is an authored spatial hypothesis.
    np.savez_compressed(out / 'source_support_assignments.npz',
        classified_local_xy_m=uv.astype('<f8'), native_row=yy.astype('<i4'), native_column=xx.astype('<i4'),
        nearest_source_index=nearest.astype('<i4'), nearest_distance_m=distances.astype('<f4'),
        eligible_radius_rule=eligible, source_ids=np.array([q['source_id'] for q in audit['sources']]))
    q = {'passed': True, 'source_canopy_year': 2022, 'mapped_tree_count': len(roots),
        'coordinate_operation': to_utm.description, 'coordinate_operation_advertised_accuracy_m': to_utm.accuracy,
        'positional_uncertainty': 'The selected NAD83-to-WGS84 operation advertises 4 m accuracy. This is separate from the 0.6 m native raster cell size; mapped-root correspondence is not sub-metre survey matching.',
        'classified_canopy_in_scene_tile_m2': int(classified.sum()) * pixel_area,
        'classified_canopy_within_current_tree_bbox_union_m2': int((classified & (tree_boxes > 0)).sum()) * pixel_area,
        'current_tree_bbox_union_m2': int(((tree_boxes > 0) & tile_mask).sum()) * pixel_area,
        'classified_canopy_outside_nominal_urban_union_m2': int((classified & ~nominal_mask).sum()) * pixel_area,
        'classified_area_within_nearest_root_distance_m2': {str(m): int((distances <= m).sum()) * pixel_area for m in [2, 4, 8, 12, 20]},
        'roots_with_classified_canopy_within_m': {str(m): int((native_tree_distance <= m).sum()) for m in [1, 3, 5, 10]},
        'authored_association': {'rule': 'Nearest retained mapped root, within clamp(0.8 * retained height, 4 m, 14 m). This is a correspondence hypothesis, not provider tree identity.',
            'associated_classified_area_m2': int(eligible.sum()) * pixel_area,
            'roots_with_any_associated_cells': int((assignment > 0).sum())},
        'tree_rows': [{'source_id': row['source_id'], 'source_xy_m': row['source_xy_m'],
            'nearest_classified_pixel_m': float(native_tree_distance[i]),
            'associated_cell_area_m2': int(assignment[i]) * pixel_area,
            'authored_maximum_association_radius_m': float(cap[i])} for i, row in enumerate(audit['sources'])],
        'limits': 'Bounding envelopes overestimate actual leaf coverage and may overlap other scene vegetation. The classification is dated, canopy-only and does not establish individual trunks, heights, species or leaf-area density. No source roots/heights or rendered geometry are changed by this audit.'}
(out / 'CANOPY_SUPPORT_AUDIT.json').write_text(json.dumps(q, indent=2) + '\n')
print(json.dumps({key: value for key, value in q.items() if key != 'tree_rows'}, indent=2), flush=True)
