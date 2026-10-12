"""Explicit longitude/latitude, projected metres, GEO mm and glTF axes.

Horizontal WGS84 input is projected to UTM zone 11N; the renderer uses a
small local origin so native float32 meshlets do not lose centimetres.
DEM elevations retain their source vertical datum. No geoid conversion is
silently applied, and absolute elevation is never confused with AGL height.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import numpy as np
from pyproj import Transformer, Proj
from shapely.geometry import box
from shapely.ops import transform


@dataclass(frozen=True)
class Sector:
    name: str = "all-isla-vista-and-coastal-context"
    longitude: float = -119.855
    latitude: float = 34.4135
    extent: float = 2048.0
    epsg: int = 32611

    def __post_init__(self):
        if not (-120 < self.longitude < -119 and 34 < self.latitude < 35):
            raise ValueError("This first sector is constrained to the UCSB region")
        if not 64 <= self.extent <= 8192 or not np.isfinite(self.extent):
            raise ValueError("Sector extent must be 64–8192 metres")
        if self.epsg != 32611:
            raise ValueError("The UCSB coordinate contract uses EPSG:32611")

    @property
    def frame(self):
        return Frame(self.longitude, self.latitude, self.epsg)

    @property
    def clip(self):
        h = self.extent / 2
        return box(-h, -h, h, h)

    @property
    def utm_bounds(self):
        x, y = self.frame.origin
        h = self.extent / 2
        return x-h, y-h, x+h, y+h

    @property
    def wgs84_bounds(self):
        # Transform every corner; UTM grid north is not true north.
        inverse = self.frame.inverse
        w, s, e, n = self.utm_bounds
        xx, yy = inverse.transform([w, e, e, w], [s, s, n, n])
        return min(xx), min(yy), max(xx), max(yy)

    def metadata(self):
        d = asdict(self)
        d.update(self.frame.metadata())
        d["utm_bounds"] = list(self.utm_bounds)
        d["wgs84_bounds"] = list(self.wgs84_bounds)
        return d


class Frame:
    def __init__(self, longitude, latitude, epsg=32611):
        self.longitude, self.latitude, self.epsg = longitude, latitude, epsg
        self.forward = Transformer.from_crs(4326, epsg, always_xy=True)
        self.inverse = Transformer.from_crs(epsg, 4326, always_xy=True)
        self.origin = np.array(self.forward.transform(longitude, latitude))

    def local(self, longitude, latitude):
        x, y = self.forward.transform(longitude, latitude)
        return np.asarray(x)-self.origin[0], np.asarray(y)-self.origin[1]

    def geographic(self, east, north):
        return self.inverse.transform(np.asarray(east)+self.origin[0],
                                      np.asarray(north)+self.origin[1])

    def project_geometry(self, geometry, source_epsg=4326):
        transformer = Transformer.from_crs(source_epsg, self.epsg, always_xy=True)
        def project(x, y, z=None):
            xx, yy = transformer.transform(x, y)
            xx, yy = np.asarray(xx)-self.origin[0], np.asarray(yy)-self.origin[1]
            return (xx, yy) if z is None else (xx, yy, z)
        return transform(project, geometry)

    def metadata(self):
        return {
            "horizontal_crs": f"EPSG:{self.epsg}",
            "input_axis_order": "longitude, latitude (always_xy=True)",
            "local_origin_utm_m": self.origin.tolist(),
            "local_axes": "east, grid-north, up; metres",
            "geo_axes": "east, grid-north, up; millimetres",
            "gltf_axes": "east, up, minus-grid-north; metres",
            "grid_convergence_degrees": Proj(self.epsg).get_factors(
                self.longitude, self.latitude).meridian_convergence,
            "vertical_policy": "Retain DEM datum; building heights are AGL offsets",
        }


def local_to_geo(vertices):
    a = np.asarray(vertices, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != 3 or not np.isfinite(a).all():
        raise ValueError("Expected finite Nx3 local coordinates")
    return a * 1000


def geo_to_gltf(vertices):
    a = np.asarray(vertices, dtype=np.float64) * .001
    return a[:, [0, 2, 1]] * [1, 1, -1]
