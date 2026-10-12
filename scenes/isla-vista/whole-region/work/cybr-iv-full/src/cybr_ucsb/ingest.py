"""Normalize real GIS/OSM geometry without substituting a procedural campus."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from scipy.ndimage import map_coordinates
from shapely import make_valid
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, mapping, shape
from shapely.ops import polygonize, unary_union
from .coordinates import Sector
from .sources import Archive, write_json


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


def metres(value):
    if value is None:
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(m|metres|meters|ft|feet|'|\")?\s*", str(value))
    if not match:
        return None
    number = float(match[1])
    unit = match[2] or "m"
    return number * (.3048 if unit in ("ft", "feet", "'") else .0254 if unit == '"' else 1)


@dataclass
class Feature:
    id: str
    category: str
    geometry: object
    properties: dict
    source: str
    uncertainty: dict = field(default_factory=dict)

    def json(self):
        return {"type":"Feature", "id":self.id, "geometry":mapping(self.geometry),
                "properties":{"category":self.category, "source":self.source,
                              "source_properties":self.properties, "uncertainty":self.uncertainty}}


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


@dataclass
class Dataset:
    sector: Sector
    dem: DEM
    features: list[Feature]
    report: dict

    def selected(self, category):
        return [f for f in self.features if f.category == category]

    def save(self, path):
        write_json(path, {"type":"FeatureCollection", "name":self.sector.name,
                         "coordinate_contract":self.sector.metadata(),
                         "features":[f.json() for f in self.features]})


def layer_rows(directory, name):
    rows = []
    for path in sorted(Path(directory).glob(f"{name}-[0-9][0-9][0-9].json")):
        d = json.loads(path.read_text())
        if d.get("spatialReference", {}).get("wkid",4326) != 4326:
            raise ValueError("GIS page must declare longitude/latitude input")
        rows.extend(d["features"])
    return rows


def load_osm(directory):
    elements, conflicts = {}, []
    for path in sorted(Path(directory).glob("osm-*.osm")):
        root = ET.parse(path).getroot()
        if root.tag != "osm":
            raise ValueError("Not an OSM API snapshot: " + str(path))
        for element in root:
            if element.tag not in ("node", "way", "relation"):
                continue
            key = element.tag, element.attrib["id"]
            previous = elements.get(key)
            if previous is not None:
                v, old = int(element.get("version",0)), int(previous.get("version",0))
                if v != old:
                    conflicts.append({"type":key[0],"id":key[1],"versions":[old,v]})
                if v < old:
                    continue
            elements[key] = element
    nodes = {key[1]:(float(e.attrib["lon"]),float(e.attrib["lat"]))
             for key,e in elements.items() if key[0] == "node"}
    return elements, nodes, conflicts


def osm_category(tags):
    if tags.get("building") not in (None, "no"):
        return "building"
    if tags.get("natural") == "tree":
        return "tree"
    if tags.get("natural") == "water" or "water" in tags:
        return "water"
    if tags.get("natural") == "coastline":
        return "coastline"
    if tags.get("amenity") == "parking":
        return "parking"
    if tags.get("highway"):
        return "path" if tags["highway"] in ("footway","path","cycleway","pedestrian","steps") else "road"
    if tags.get("barrier") == "hedge":
        return "hedge"
    if tags.get("leisure") in ("pitch","playground","sports_centre"):
        return "recreation"
    if tags.get("landuse") in ("grass","meadow","forest") or tags.get("natural") in (
        "grassland","scrub","wood","sand","beach") or tags.get("leisure") in ("park","garden"):
        return "landcover"
    return None


def ingest(directory, sector=Sector()):
    archive = Archive(directory)
    source_count = archive.verify()
    stored = archive.manifest.get("sector",{})
    for key in ("longitude","latitude","extent","epsg"):
        if key in stored and stored[key] != getattr(sector,key):
            raise ValueError("Source snapshot belongs to a different sector: " + key)
    frame, clip = sector.frame, sector.clip
    dem = DEM(Path(directory)/"dem.tif", frame)
    features, rejected, overrides = [], [], []
    categories = {"buildings":"building", "lawns":"landcover", "trees":"vegetation", "hedges":"hedge",
                  "roads":"road", "driving-surfaces":"pavement", "parking":"parking",
                  "bike-paths":"path", "footpaths":"path", "water":"water", "recreation":"recreation", "roofs":"roof"}
    campus_buildings = []
    for name, category in categories.items():
        for row in layer_rows(directory, name):
            props = row["attributes"]
            object_id = next((props[k] for k in ("OBJECTID","OBJECTID_1","objectid","FID") if props.get(k) is not None), None)
            if object_id is None:
                raise ValueError("GIS feature has no stable object ID: " + name)
            identifier = f"ucsb:{name}:{object_id}"
            try:
                geometry = frame.project_geometry(arcgis_geometry(row["geometry"])).intersection(clip)
                if geometry.is_empty:
                    continue
                geometry = make_valid(geometry)
                uncertainty = {"source_epoch":"2026 DFSS" if name=="buildings" else "legacy campus GIS; temporal mismatch retained"}
                if category == "building":
                    title = str(props.get("LONGNAME") or props.get("BUILDINGID") or identifier).strip()
                    props = dict(props, name=title)
                    if title == "Storke Tower":
                        height, method = 175*.3048, "UCSB published 175 ft AGL"
                        overrides.append({"id":identifier,"field":"BLDGHEIGHT","raw":props.get("BLDGHEIGHT"),
                                          "used_m":height,"reason":"UCSB published reference conflicts with raw GIS height",
                                          "url":"https://www.campuscalendar.ucsb.edu/storke_tower"})
                    else:
                        # BLDGHEIGHT has no declared unit/datum and contains known
                        # duplicate tower values. Keep it; do not assert it as AGL.
                        levels = props.get("FLOORCOUNT")
                        height = max(3.5, min(45, float(levels or 2)*3.6))
                        method = "FLOORCOUNT × estimated 3.6 m" if levels else "missing height: estimated 7.2 m massing"
                    props.update(height_m=height, height_method=method)
                    uncertainty.update(height_estimated=title!="Storke Tower", facade="not reconstructed",
                                       roof="flat massing; source roof/aspect records retained for later reconstruction")
                    campus_buildings.append(geometry)
                features.append(Feature(identifier, category, geometry, props, "UCSB "+name, uncertainty))
            except (ValueError, KeyError) as e:
                rejected.append({"id":identifier,"reason":str(e)})
    campus_union = unary_union(campus_buildings)
    elements, nodes, conflicts = load_osm(directory)
    relation_members = set()
    for (kind, identifier), element in sorted(elements.items()):
        tags = {t.get("k"):t.get("v") for t in element.findall("tag")}
        category = osm_category(tags)
        if not category:
            continue
        source_id = f"osm:{kind}:{identifier}"
        candidate_members = []
        try:
            if kind == "node":
                geometry = Point(nodes[identifier])
            elif kind == "way":
                refs = [n.get("ref") for n in element.findall("nd")]
                if any(ref not in nodes for ref in refs):
                    raise ValueError("Missing OSM member nodes; no interpolated substitute")
                points = [nodes[ref] for ref in refs]
                closed = len(refs)>=4 and refs[0]==refs[-1]
                area = closed and (category in ("building","water","landcover","parking","recreation") or tags.get("area")=="yes")
                geometry = make_valid(Polygon(points)) if area else LineString(points)
            else:
                if tags.get("type") != "multipolygon":
                    continue
                outer, inner = [], []
                for member in element.findall("member"):
                    if member.get("type") != "way":
                        continue
                    way = elements.get(("way",member.get("ref")))
                    if way is None:
                        raise ValueError("Incomplete multipolygon member")
                    refs = [n.get("ref") for n in way.findall("nd")]
                    if any(ref not in nodes for ref in refs):
                        raise ValueError("Incomplete multipolygon node")
                    (inner if member.get("role")=="inner" else outer).append(LineString([nodes[r] for r in refs]))
                    member_tags = {t.get("k"):t.get("v") for t in way.findall("tag")}
                    # A coastline can also be a beach/park relation boundary.
                    # Suppress only members of the same semantic layer, and
                    # only after the entire relation has been reconstructed.
                    if osm_category(member_tags)==category:
                        candidate_members.append(f"osm:way:{member.get('ref')}")
                shells = unary_union(list(polygonize(unary_union(outer))))
                holes = unary_union(list(polygonize(unary_union(inner))))
                geometry = shells.difference(holes)
            geometry = make_valid(frame.project_geometry(geometry)).intersection(clip)
            if geometry.is_empty:
                continue
            if category=="building":
                if geometry.area <= 1 or not isinstance(geometry,(Polygon,MultiPolygon)):
                    continue
                overlap = geometry.intersection(campus_union).area/geometry.area
                if overlap > .45:
                    # Join height tags to the authoritative campus footprint.
                    candidates = [f for f in features if f.category=="building" and
                                  f.geometry.intersection(geometry).area/max(geometry.area,1)>.45]
                    if candidates:
                        target = max(candidates,key=lambda f:(
                            f.properties.get("name","").strip().lower()==tags.get("name","").strip().lower(),
                            f.geometry.intersection(geometry).area/max(f.geometry.union(geometry).area,1)))
                        target.properties["osm_match"] = {"id":source_id, "tags":tags}
                        h = metres(tags.get("height"))
                        if h and target.properties.get("name")!="Storke Tower":
                            target.properties.update(height_m=h,height_method="explicit OSM height tag, metres")
                            target.uncertainty["height_estimated"] = False
                    continue
                height = metres(tags.get("height"))
                levels = metres(tags.get("building:levels"))
                height_estimated = height is None
                height = height or ((levels or 2)*3.3)
                tags.update(height_m=max(2,min(80,height)),
                            height_method="explicit OSM height tag" if not height_estimated else
                            "building:levels × estimated 3.3 m" if levels else "missing height: estimated 6.6 m massing")
                uncertainty = {"height_estimated":height_estimated,"facade":"not reconstructed",
                               "roof":"flat massing; any source roof tags retained but not yet reconstructed"}
            elif category in ("road","path","hedge"):
                width = metres(tags.get("width"))
                uncertainty = {"width_estimated":width is None, "width_m":width}
            else:
                uncertainty = {}
            tags["osm_version"] = int(element.get("version",0))
            tags["osm_timestamp"] = element.get("timestamp")
            features.append(Feature(source_id,category,geometry,tags,"OpenStreetMap",uncertainty))
            relation_members.update(candidate_members)
        except (ValueError,KeyError) as e:
            rejected.append({"id":source_id,"reason":str(e)})
    # Geometry from a multipolygon relation owns its member outlines. Retain
    # the relation itself so inner rings do not become standalone solid areas.
    features = [f for f in features if f.id not in relation_members]
    counts = {category:sum(f.category==category for f in features) for category in sorted({f.category for f in features})}
    report = {"schema":"cybr-geospatial-ingestion/1", "sector":sector.metadata(), "source_files_verified":source_count,
              "counts":counts,"height_overrides":overrides,"rejected":rejected,"osm_version_conflicts":conflicts,
              "dem":{"range_m":[float(dem.values.min()),float(dem.values.max())],
                     "export_pixel_spacing_m":list(dem.resolution), "native_resolution":"see raw dem-catalog.json",
                     "vertical_datum":"see raw catalogue; no vertical datum transformation applied"},
              "image_generation_used":False, "missing_source_policy":"record/reject; never synthesize geographic layouts"}
    return Dataset(sector,dem,features,report)
