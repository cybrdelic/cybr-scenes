"""Retained source-backed GIS and elevation ingestion; no network side effects."""
from pathlib import Path
import json
import numpy as np
import rasterio
from scipy.ndimage import map_coordinates
from shapely import make_valid
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union

def polygons(geometry):
    if isinstance(geometry, Polygon):
        yield geometry
    elif hasattr(geometry, "geoms"):
        for child in geometry.geoms:
            yield from polygons(child)

def rings_geometry(rings):
    """ESRI rings may be either orientation; containment determines hole parity.

    Provider reprojection can reverse rings. Treating every ring as a solid
    building would fill actual courtyards, so this adapter is orientation-free.
    """
    valid = []
    for ring in rings:
        if len(ring) >= 4:
            valid.extend(polygons(make_valid(Polygon(np.asarray(ring)[:, :2]))))
    if not valid:
        return Polygon()
    valid.sort(key=lambda p: p.area, reverse=True)
    result = Polygon()
    for i, ring in enumerate(valid):
        depth = sum(p.contains(ring.representative_point()) for p in valid[:i])
        result = result.union(ring) if depth % 2 == 0 else result.difference(ring)
    return make_valid(result)

def arcgis_geometry(document):
    if "rings" in document:
        return rings_geometry(document["rings"])
    if "paths" in document:
        return unary_union([LineString(np.asarray(p)[:, :2]) for p in document["paths"] if len(p)>1])
    if "x" in document:
        return Point(document["x"], document["y"])
    raise ValueError("Unsupported GIS geometry")

class DEM:
    def __init__(self, path, frame):
        self.frame = frame
        with rasterio.open(path) as raster:
            if raster.count != 1 or raster.dtypes[0] not in ("float32", "float64"):
                raise ValueError("DEM must be a single floating-point elevation band, never RGB/hillshade")
            if raster.crs.to_epsg() != frame.epsg:
                raise ValueError("DEM horizontal CRS differs from the sector contract")
            self.values = raster.read(1, masked=True).astype(np.float64)
            if np.ma.getmaskarray(self.values).any() or not np.isfinite(self.values).all():
                raise ValueError("DEM has nodata; acquire a complete sector instead of filling invented heights")
            self.values = np.asarray(self.values)
            self.affine = raster.transform
            self.bounds = tuple(raster.bounds)
            self.resolution = tuple(raster.res)
            if not -100 <= self.values.min() <= self.values.max() <= 500:
                raise ValueError("Implausible coastal elevations; check units and raster function")

    def sample(self, x, y, outside="reject"):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        world_x, world_y = x+self.frame.origin[0], y+self.frame.origin[1]
        west, south, east, north = self.bounds
        if outside == "reject" and (np.any(world_x < west-1e-6) or np.any(world_x > east+1e-6)
                                     or np.any(world_y < south-1e-6) or np.any(world_y > north+1e-6)):
            raise ValueError("Geometry sample outside acquired DEM")
        col, row = ~self.affine * (world_x, world_y)
        # GeoTIFF affine refers to pixel edges; values refer to pixel centres.
        out = map_coordinates(self.values, [np.ravel(row-.5), np.ravel(col-.5)],
                              order=1, mode="nearest").reshape(x.shape)
        return float(out) if out.ndim == 0 else out

    def grid(self, n, extent):
        axis = np.linspace(-extent/2, extent/2, n)
        x, y = np.meshgrid(axis, axis)
        return self.sample(x, y)

def layer_rows(directory, name):
    rows = []
    for path in sorted(Path(directory).glob(f"{name}-[0-9][0-9][0-9].json")):
        d = json.loads(path.read_text())
        if d.get("spatialReference", {}).get("wkid",4326) != 4326:
            raise ValueError("GIS page must declare longitude/latitude input")
        rows.extend(d["features"])
    return rows
