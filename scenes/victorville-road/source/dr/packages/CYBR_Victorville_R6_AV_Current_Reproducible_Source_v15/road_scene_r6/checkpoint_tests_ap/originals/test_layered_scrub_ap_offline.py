"""Pure structural geometry checks; no Blender subprocess or scene changes.

Writes layered_scrub_ap_offline_receipt.json beside this file. These checks do
not claim Blender API validation or visual approval; those belong to integration.
"""
import importlib.util
import json
import math
from pathlib import Path
import sys
import types

import numpy as np


class Vector(np.ndarray):
    def __new__(cls, value):
        return np.asarray(value, dtype=float).view(cls)

    @property
    def length_squared(self):
        return float(np.dot(self, self))

    @property
    def length(self):
        return math.sqrt(self.length_squared)

    def normalized(self):
        return Vector(self/(self.length or 1))

    def normalize(self):
        self[:] = self.normalized()

    def cross(self, other):
        return Vector(np.cross(self, other))

    def lerp(self, other, amount):
        return Vector(self*(1-amount)+other*amount)

    @property
    def z(self):
        return self[2]

    @z.setter
    def z(self, value):
        self[2] = value


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    here = Path(__file__).resolve().parent
    sys.modules["mathutils"] = types.SimpleNamespace(Vector=Vector)
    sys.modules["bpy"] = types.SimpleNamespace()
    load("desert_scrub", here/"desert_scrub.py")
    module = load("layered_scrub_ap", here/"layered_scrub_ap.py")
    records = []
    for i, spec in enumerate(module.SPECS):
        seed = 261010+i*104729
        a = module._geometry(spec, seed)
        b = module._geometry(spec, seed)
        assert a.vertices == b.vertices, "Geometry must be deterministic"
        assert a.faces == b.faces
        assert a.material_indices == b.material_indices
        xyz = np.array(a.vertices)
        assert np.isfinite(xyz).all()
        assert abs(xyz[:, 2].min()) < 1e-9
        assert abs(xyz[:, 2].max()-spec.height) < 1e-9
        dimensions = np.ptp(xyz, axis=0)
        assert abs(max(dimensions[:2])-spec.spread) < 1e-9
        assert len(a.faces) == len(a.material_indices) == len(a.smooth)
        assert min(min(f) for f in a.faces) >= 0
        assert max(max(f) for f in a.faces) < len(a.vertices)
        assert set(a.material_indices).issubset(set(range(14)))
        assert a.leaf_count > 500
        assert a.branch_count > 250
        low_fraction = float(np.mean(xyz[:, 2] < spec.height*.50))
        if spec.height >= .35:
            assert low_fraction > .70, "Tall variants must retain dense low crowns"
        # Check triangle areas, including triangulated quads and capped tubes.
        min_area = math.inf
        for face in a.faces:
            p = xyz[face[0]]
            for j in range(1, len(face)-1):
                area = np.linalg.norm(np.cross(xyz[face[j]]-p, xyz[face[j+1]]-p))*.5
                min_area = min(min_area, float(area))
        assert min_area > 1e-16, "Degenerate geometry detected"
        records.append({"name": spec.name, "seed": seed,
                        "vertices": len(a.vertices), "polygons": len(a.faces),
                        "triangles": sum(len(f)-2 for f in a.faces),
                        "leaves": a.leaf_count, "branches": a.branch_count,
                        "dimensions_m": dimensions.tolist(),
                        "vertices_below_half_height_fraction": low_fraction,
                        "minimum_triangle_area_m2": min_area})
    total = sum(row["vertices"] for row in records)
    assert total < 120000
    assert len(records) == 6
    receipt = {"status": "passed", "test": "Offline geometry only; no Blender launched",
               "checks": ["determinism", "finite vertices", "valid face/material indices",
                          "positive triangle area", "exact heights and maximum horizontal spans",
                          "dense low crown fraction", "six-prototype vertex budget"],
               "blender_integration": "not run", "visual_validation": "not run",
               "total_vertices": total, "variants": records}
    target = here/"layered_scrub_ap_offline_receipt.json"
    target.write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
