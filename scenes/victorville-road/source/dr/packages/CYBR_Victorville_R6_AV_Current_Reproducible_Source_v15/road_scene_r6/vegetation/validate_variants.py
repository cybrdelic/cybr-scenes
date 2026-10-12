"""Blender no-render validation. Run with blender -b --python this_file.py."""
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from desert_scrub import create_variants, variant_summary

started = time.monotonic()
collection = bpy.data.collections.new("Procedural scrub validation prototypes")
bpy.context.scene.collection.children.link(collection)
pre_images = set(bpy.data.images)
bank = create_variants(collection, seed=260910)
assert len(bank["shrubs"]) == 12
assert len(bank["grass"]) == 5
assert len(bank["all"]) == 17
assert set(bpy.data.images) == pre_images, "No image assets should be loaded"
summary = variant_summary(bank)
for obj, record in zip(bank["all"], summary):
    assert obj.type == "MESH"
    assert obj.hide_render and obj.hide_viewport
    assert len(obj.modifiers) == 0
    assert not obj.data.validate(verbose=True), f"Invalid geometry: {obj.name}"
    assert all(math.isfinite(c) for vertex in obj.data.vertices for c in vertex.co)
    assert record["bounds_min_m"][2] >= -1e-7
    assert abs(record["dimensions_m"][2]-obj["nominal_height_m"]) < 1e-5
    assert all(poly.area > 1e-14 for poly in obj.data.polygons), f"Degenerate faces: {obj.name}"
    assert all(poly.material_index < len(obj.data.materials) for poly in obj.data.polygons)
    assert record["triangles"] < 42000, f"Over-budget geometry: {obj.name}"
    instance = bpy.data.objects.new("Temporary linked-mesh instance", obj.data)
    collection.objects.link(instance)
    assert instance.data is obj.data
    assert not instance.hide_render and not instance.hide_viewport
    bpy.data.objects.remove(instance, do_unlink=True)
    digest = hashlib.sha256()
    for v in obj.data.vertices:
        digest.update(struct.pack("fff", *v.co))
    record["vertex_sha256"] = digest.hexdigest()
    record["geometry_valid"] = True

# New geometry with the same seed must be identical, without resetting global RNG.
from desert_scrub import _shrub, _ShrubSpec
spec = _ShrubSpec("Test", "olive_open_scrub", .47, .86, 10, .91)
a = _shrub(spec, 260910)
b = _shrub(spec, 260910)
assert a.vertices == b.vertices and a.faces == b.faces
assert bank["shrubs"][0]["leaf_count"] == a.leaf_count
report = {"blender_version": bpy.app.version_string, "seed": 260910,
          "validation": "Passed geometry, dimensions, linked-instance visibility, material indices, deterministic build and no image imports",
          "rendered": False,
          "build_and_validation_seconds": round(time.monotonic()-started, 3),
          "total_vertices": sum(x["vertices"] for x in summary),
          "total_triangles": sum(x["triangles"] for x in summary),
          "variants": summary}
(HERE/"validation_report.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
