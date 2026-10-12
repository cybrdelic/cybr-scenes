"""Retain an unresampled native 2022 canopy-classification window for IV."""
from pathlib import Path
import hashlib
import json
import math
import sys

r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(r / 'geo-deps'))
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import Window, from_bounds
from shapely.geometry import shape, mapping, box
from shapely.ops import transform as shapely_transform
from pyproj import Transformer

d = r / 'data/urban-canopy-2022'
ref = r / 'references/urban-canopy-2022'
archive = d / 'CALFIRE_UrbanCanopy_SantaBarbaraCounty.zip'
member = 'CALFIRE_UrbanCanopy_SantaBarbaraCounty/Canopy_2022_0.TIF'
origin = np.array([237001.80699345336, 3811663.448398269])
bounds_utm = [*(origin - 1300), *(origin + 1300)]
footprint_utm = box(*bounds_utm)
target = d / 'iv_canopy_2022_native_060m.tif'
with rasterio.Env(GDAL_CACHEMAX=32 * 1024 * 1024):
    with rasterio.open('/vsizip/' + str(archive) + '/' + member) as ds:
        bounds = transform_bounds('EPSG:32611', ds.crs, *bounds_utm, densify_pts=21)
        fractional = from_bounds(*bounds, ds.transform)
        x0, y0 = math.floor(fractional.col_off), math.floor(fractional.row_off)
        x1, y1 = math.ceil(fractional.col_off + fractional.width), math.ceil(fractional.row_off + fractional.height)
        window = Window(x0, y0, x1 - x0, y1 - y0)
        assert window.width * window.height < 25_000_000
        data = ds.read(1, window=window)
        profile = ds.profile.copy()
        profile.update(width=data.shape[1], height=data.shape[0], transform=ds.window_transform(window),
                       compress='deflate', tiled=True, blockxsize=256, blockysize=256)
        with rasterio.open(target, 'w', **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(source_year='2022', source_provider='CAL FIRE / USFS / NOAA / EarthDefine',
                source_member=member, subset_operation='Native aligned window only; no reprojection or resampling',
                classification='1 = classified canopy; 255 = original NoData/background, not a valid zero-height measurement')
        footprint = transform_geom('EPSG:32611', ds.crs, mapping(footprint_utm))
        tile_mask = geometry_mask([footprint], out_shape=data.shape, transform=profile['transform'], invert=True)
        cdp_json = json.loads((r / 'evidence/whole-iv-coverage/isla_vista_cdp.geojson').read_text())
        if cdp_json['type'] == 'FeatureCollection':
            cdp_geometry = cdp_json['features'][0]['geometry']
        elif cdp_json['type'] == 'Feature':
            cdp_geometry = cdp_json['geometry']
        else:
            cdp_geometry = cdp_json
        cdp = transform_geom('EPSG:4326', ds.crs, cdp_geometry)
        cdp_mask = geometry_mask([cdp], out_shape=data.shape, transform=profile['transform'], invert=True)
        pixel_area = abs(profile['transform'].a * profile['transform'].e)
        assert set(np.unique(data)).issubset({1, 255})
    with rasterio.open(target) as check:
        assert np.array_equal(check.read(1), data)
        assert check.transform == profile['transform'] and check.crs.to_epsg() == 3310

q = {'passed': True, 'source_archive_sha256': json.loads((ref / 'COUNTY_ARCHIVE_RECEIPT.json').read_text())['sha256'],
    'source_archive_member': member, 'native_crs': 'EPSG:3310', 'native_pixel_size_m': .6,
    'native_pixel_values_retained': True, 'resampling': False,
    'window': [x0, y0, x1 - x0, y1 - y0], 'shape': list(data.shape),
    'subset_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'subset_bytes': target.stat().st_size,
    'values': {str(int(v)): int((data == v).sum()) for v in np.unique(data)},
    'classified_canopy_in_scene_tile_m2': float(np.count_nonzero((data == 1) & tile_mask) * pixel_area),
    'classified_canopy_in_iv_cdp_m2': float(np.count_nonzero((data == 1) & cdp_mask) * pixel_area),
    'cdp_rasterized_area_m2': float(cdp_mask.sum() * pixel_area),
    'classification_year': 2022, 'metadata_release': 'May 2025',
    'scope': 'Dated two-dimensional classification, not individual trees, tree heights, species, exact crowns, photographic texture or a replacement scan mesh.',
    'background_limit': 'The native raster contains 1 and NoData 255. Background alone does not distinguish non-canopy from an unassessed location. Source metadata limits mapping to the combined 2010/2020 Census urban areas; an urban-area coverage check remains separate.',
    'accuracy_limit': 'Provider describes accuracy assessment and manual review but the supplied metadata does not report a numerical local classification accuracy.'}
(ref / 'IV_NATIVE_SUBSET_RECEIPT.json').write_text(json.dumps(q, indent=2) + '\n')
print(json.dumps(q, indent=2), flush=True)
