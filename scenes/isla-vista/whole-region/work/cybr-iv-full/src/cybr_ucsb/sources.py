"""Cache exact public source responses, paginate GIS queries, hash every input."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
import urllib.parse
import requests
from .coordinates import Sector

BUILDINGS = "https://services1.arcgis.com/4TXrdeWh0RyCqPgB/ArcGIS/rest/services/Buildings2026/FeatureServer/0"
CAMPUS = "https://services1.arcgis.com/4TXrdeWh0RyCqPgB/ArcGIS/rest/services/ucsb_icm.gdb/FeatureServer"
ELEVATION = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
OSM = "https://www.openstreetmap.org/api/0.6/map"
STORKE = "https://www.campuscalendar.ucsb.edu/storke_tower"
LAYERS = {"parking": 2, "bike-paths": 5, "roofs": 8, "trees": 14,
          "footpaths": 18, "roads": 20, "driving-surfaces": 21,
          "lawns": 22, "hedges": 23, "recreation": 24, "water": 30}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n")
    temporary.replace(path)


class Archive:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.directory / "manifest.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {
            "schema": "cybr-geospatial-sources/1", "image_generation_used": False, "files": {}}
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "CYBR-UCSB/0.1 reproducible geospatial research"

    def fetch(self, name, url, parameters=None, attribution="", license="unspecified", note=""):
        full = requests.Request("GET", url, params=parameters).prepare().url
        path = self.directory / name
        row = self.manifest["files"].get(name)
        if path.exists() and row and row["url"] == full and sha256(path) == row["sha256"]:
            return path
        for attempt in range(3):
            try:
                r = self.session.get(full, timeout=90)
                r.raise_for_status()
                body = r.content
                if r.headers.get("Content-Type", "").startswith("application/json"):
                    document = r.json()
                    if isinstance(document, dict) and "error" in document:
                        raise RuntimeError(f"Source API rejected {name}: {document['error']}")
                break
            except (requests.RequestException, RuntimeError):
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(body)
        temporary.replace(path)
        self.manifest["files"][name] = {
            "url": full, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256(path), "bytes": len(body), "attribution": attribution,
            "license": license, "note": note,
            "http_date": r.headers.get("Date"), "etag": r.headers.get("ETag")}
        write_json(self.manifest_path, self.manifest)
        print(f"acquired {name}: {len(body):,} bytes", flush=True)
        return path

    def verify(self):
        for name, row in self.manifest["files"].items():
            path = self.directory / name
            from public_inputs import validate
            if not path.is_file():
                raise ValueError("Missing source input: " + name)
            validate(path.read_bytes(), {**row, "path": str(path)})
        return len(self.manifest["files"])

    def layer(self, name, endpoint, bounds=None):
        metadata = self.fetch(name+"-metadata.json", endpoint, {"f": "pjson"}, "UC Santa Barbara")
        description = json.loads(metadata.read_text())
        oid = description.get("objectIdField", description.get("objectIdFieldName", "OBJECTID"))
        query = {"where": "1=1", "outFields": "*", "outSR": 4326,
                 "f": "json", "returnGeometry": "true", "orderByFields": oid}
        if bounds:
            query.update(geometry=",".join(map(str, bounds)), geometryType="esriGeometryEnvelope",
                         inSR=4326, spatialRel="esriSpatialRelIntersects")
        features = []
        page = 0
        while True:
            p = dict(query, resultOffset=page*1000, resultRecordCount=1000)
            path = self.fetch(f"{name}-{page:03}.json", endpoint+"/query", p, "UC Santa Barbara",
                              note="Raw GIS page; projected by provider to longitude/latitude")
            d = json.loads(path.read_text())
            if "features" not in d:
                raise ValueError("Missing GIS features: " + name)
            features.extend(d["features"])
            if not d.get("exceededTransferLimit", False):
                break
            if not d["features"] or page > 100:
                raise ValueError("GIS pagination did not make progress")
            page += 1
        return features


def acquire(directory, sector=Sector()):
    a = Archive(directory)
    bounds = sector.wgs84_bounds
    a.layer("buildings", BUILDINGS, bounds)
    for name, index in LAYERS.items():
        a.layer(name, f"{CAMPUS}/{index}", bounds)
    a.fetch("elevation-metadata.json", ELEVATION, {"f": "pjson"}, "USGS 3DEP", "US public domain")
    a.fetch("dem.tif", ELEVATION+"/exportImage", {
        "f": "image", "bbox": ",".join(map(str, sector.utm_bounds)), "bboxSR": sector.epsg,
        "imageSR": sector.epsg, "size": "513,513", "format": "tiff", "pixelType": "F32",
        "renderingRule": json.dumps({"rasterFunction": "None"}),
        "interpolation": "RSP_BilinearInterpolation"}, "USGS 3DEP", "US public domain",
        "Float32 elevation, not hillshade; requested pixel spacing is not native survey resolution")
    a.fetch("dem-catalog.json", ELEVATION+"/query", {
        "f": "json", "where": "1=1", "geometry": f"{sector.longitude},{sector.latitude}",
        "geometryType": "esriGeometryPoint", "inSR": 4326, "outFields": "*", "returnGeometry": "false",
        "spatialRel": "esriSpatialRelIntersects"},
        "USGS 3DEP", "US public domain", "Source DEM catalogue at sector centre, including vertical datum")
    west, south, east, north = bounds
    # Small map requests stay below the OSM 50,000-node limit. Shared ways and
    # nodes are merged by type/id/version during normalization.
    for ix in range(3):
        for iy in range(3):
            box = [west+(east-west)*ix/3, south+(north-south)*iy/3,
                   west+(east-west)*(ix+1)/3, south+(north-south)*(iy+1)/3]
            a.fetch(f"osm-{ix}-{iy}.osm", OSM, {"bbox": ",".join(map(str, box))},
                    "© OpenStreetMap contributors", "ODbL 1.0",
                    "Live API map snapshot; per-element source IDs, timestamps and versions retained")
    a.fetch("storke-reference.html", STORKE, attribution="UC Santa Barbara",
            note="Published 175-foot tower height; disagreement with GIS BLDGHEIGHT is retained")
    a.manifest["sector"] = sector.metadata()
    write_json(a.manifest_path, a.manifest)
    a.verify()
    return a
