"""Pure geometry smoke test using a tiny Vector stand-in; does not launch Blender.

This checks the builder's math. It does not validate Blender APIs or materials;
validate_variants.py is the actual Blender no-render integration test.
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

HERE = Path(__file__).resolve().parent
sys.modules['mathutils'] = types.SimpleNamespace(Vector=Vector)
sys.modules['bpy'] = types.SimpleNamespace()
spec = importlib.util.spec_from_file_location('desert_scrub_test', HERE/'desert_scrub.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
records = []
for i, (family, height, width, n, live, size) in enumerate([
    ('olive_open_scrub', .47, .86, 10, .91, 1),
    ('olive_open_scrub', 1.08, 1.18, 13, .84, 1.05),
    ('silver_low_scrub', .22, .39, 7, .89, .76),
    ('silver_low_scrub', .58, 1.04, 12, .89, 1.02),
    ('dry_open_scrub', .72, .90, 11, .36, 1),
    ('dry_open_scrub', .29, .65, 8, .21, .83),
]):
    item = module._ShrubSpec('test', family, height, width, n, live, size)
    a = module._shrub(item, 260910+i*104729)
    b = module._shrub(item, 260910+i*104729)
    assert a.vertices == b.vertices
    xyz = np.array(a.vertices)
    assert np.all(np.isfinite(xyz))
    assert abs(xyz[:, 2].min()) < 1e-9
    assert abs(xyz[:, 2].max()-height) < 1e-9
    assert len(a.faces) == len(a.material_indices) == len(a.smooth)
    assert max(max(face) for face in a.faces) < len(a.vertices)
    tri = sum(len(face)-2 for face in a.faces)
    assert tri < 42000
    records.append(dict(family=family, height=height, vertices=len(a.vertices),
                        faces=len(a.faces), triangles=tri, leaves=a.leaf_count,
                        branches=a.branch_count, dimensions=np.ptp(xyz, axis=0).tolist()))
for i, (family, height) in enumerate([('upright_bunchgrass', .47),
                                    ('arching_bunchgrass', .28),
                                    ('sparse_stubble', .14)]):
    a = module._grass(height, 260910+i*104729, family)
    xyz = np.array(a.vertices)
    assert np.all(np.isfinite(xyz))
    assert abs(xyz[:, 2].max()-height) < 1e-9
    assert a.blade_count > 20
    records.append(dict(family=family, height=height, vertices=len(a.vertices),
                        faces=len(a.faces), blades=a.blade_count,
                        dimensions=np.ptp(xyz, axis=0).tolist()))
print(json.dumps(dict(test='Pure geometry smoke test only; no Blender launched',
                      status='passed', variants=records), indent=2))
