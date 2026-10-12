"""Small, layered roadside scrub: dead skirts, low live lobes, sparse shoots.

Wholly procedural geometry in metres. No alpha cards, image textures, scans,
spheres, modifiers, operators, scattering, or scene-setting changes. This is a
representative Mojave-inspired silhouette, not a botanical reconstruction.

``create_variants(collection, seed)`` returns ``shrubs`` and ``all`` banks of six
individually hidden prototypes. Create visible instances with
``bpy.data.objects.new(name, prototype.data)`` and link those to a scene collection.
Do not copy the prototype visibility flags. Optional ``materials`` is the
14-material desert_scrub palette in its existing order; supplied/existing
materials are reused without modification. Exact-name existing palette reuse is
automatic; otherwise desert_scrub creates a fresh palette through its own API.

Nominal heights are 0.14–0.56 m; maximum horizontal spans are 0.30–0.60 m.
Tall variants keep most geometry low and reserve height for a few wiry shoots.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import bpy
from mathutils import Vector

try:
    from . import desert_scrub as _base
except ImportError:
    import desert_scrub as _base

__all__ = ["create_variants", "variant_summary"]
_UP = Vector((0.0, 0.0, 1.0))
_TAU = math.tau


@dataclass(frozen=True)
class _Spec:
    name: str
    height: float
    spread: float
    lobes: int
    silver: bool
    crown_fraction: float
    shoots: int
    dry_fraction: float = .12


SPECS = (
    _Spec("Low olive cushion", .14, .30, 4, False, .67, 0),
    _Spec("Split silver cushion", .21, .42, 5, True, .65, 1),
    _Spec("Wind-laid olive tangle", .29, .55, 5, False, .55, 2),
    _Spec("Broken silver skirt", .35, .60, 6, True, .49, 3, .24),
    _Spec("Dry-root live islands", .44, .59, 5, False, .43, 3, .33),
    _Spec("Low silver with old shoots", .56, .60, 6, True, .37, 4, .21),
)


def _point(rng: random.Random, radius: float, z: float = 0.0) -> Vector:
    return _base._polar(rng.uniform(0, _TAU), radius*math.sqrt(rng.random()), z)


def _twig(mesh: Any, points: list[Vector], radius: float, mat: int,
          sides: int = 4) -> None:
    mesh.tube(points, [radius*(1-.94*j/(len(points)-1))
                      for j in range(len(points))], mat, sides)


def _leaves(mesh: Any, path: list[Vector], rng: random.Random,
            spec: _Spec, count: int, dead: bool = False) -> None:
    """Individual folded leaves, clustered along offset lateral shoots."""
    phase = rng.uniform(0, _TAU)
    size = min(.023, max(.012, spec.spread*.039))
    for i in range(count):
        t = .09+.89*(i+rng.uniform(.05, .80))/count
        origin, tangent = _base._sample(path, t)
        direction = _base._polar(phase+i*2.399, 1, rng.uniform(-.35, .55))
        direction = (direction+tangent*.33).normalized()
        normal = (_UP+_base._polar(phase+i*1.8, rng.uniform(.25, 1.3))).normalized()
        length = size*rng.uniform(.63, 1.18)
        width = length*rng.uniform(.48, .72) if spec.silver else length*rng.uniform(.31, .49)
        material = (rng.choice((6, 6, 7, 7, 8)) if spec.silver
                    else rng.choice((3, 3, 4, 4, 5)))
        if dead or rng.random() < .10:
            material = 9
        mesh.leaf(origin, direction, normal, length, width,
                  rng.uniform(-.24, .18), material)


def _geometry(spec: _Spec, seed: int) -> Any:
    rng = random.Random(seed)
    mesh = _base._Mesh()
    r, h = spec.spread*.5, spec.height
    crown = h*spec.crown_fraction
    wind = _base._polar(rng.uniform(0, _TAU), r*.13)
    rootlets = [_point(rng, r*.17, .002) for _ in range(7)]

    # Tangled low skirt: offset anchors, crooked branches which sweep across
    # sectors, and downward terminal hooks. Deliberately no evenly spaced rays.
    skirt_paths = []
    for i in range(48):
        root = rng.choice(rootlets)
        angle = rng.uniform(0, _TAU)
        endpoint = _base._polar(angle, r*rng.uniform(.52, 1),
                               crown*rng.uniform(.03, .24))+wind
        crossing = root+_base._polar(angle+rng.uniform(-1.35, 1.35),
                                     r*rng.uniform(.23, .59), crown*rng.uniform(.14, .38))
        path = _base._curve(root, crossing, endpoint, 5)
        # Uneven kink prevents a nest of identical parabola arcs.
        path[2] += _base._polar(angle+.9, r*rng.uniform(-.07, .07), crown*.025)
        _twig(mesh, path, rng.uniform(.0010, .0026), rng.choice((0, 1, 2, 2)), 4)
        skirt_paths.append(path)
        for j in range(rng.randint(2, 4)):
            start, tangent = _base._sample(path, rng.uniform(.28, .93))
            reach = r*rng.uniform(.12, .35)
            end = start+_base._polar(angle+rng.uniform(-1.6, 1.6), reach,
                                     crown*rng.uniform(-.09, .10))
            end.z = max(.003, end.z)
            middle = start+tangent*reach*.33+_UP*crown*.025
            _twig(mesh, [start, middle, end], rng.uniform(.0004, .0010),
                  rng.choice((1, 2, 2)), 3)
            if rng.random() < .14:
                _leaves(mesh, [start, middle, end], rng, spec, 2, True)

    # Several *offset* live islands. Each has a crooked supporting scaffold,
    # secondary cross-branches, and many short laterals carrying geometric
    # leaves. Crowns overlap locally rather than making a single radial fan.
    hubs = []
    phase = rng.uniform(0, _TAU)
    for island in range(spec.lobes):
        angle = phase+island*2.399+rng.uniform(-.42, .42)
        hub = _base._polar(angle, r*rng.uniform(.17, .59),
                          crown*rng.uniform(.56, .95))+wind
        hubs.append(hub)
        lobe_r = r*rng.uniform(.26, .42)
        root = rng.choice(rootlets)
        shoulder = root.lerp(hub, .43)+_base._polar(angle+.8, lobe_r*.32, -.012)
        scaffold = _base._curve(root, shoulder, hub, 5)
        _twig(mesh, scaffold, rng.uniform(.0018, .0032), 0, 5)
        dry_island = rng.random() < spec.dry_fraction
        for branch in range(10):
            start, tangent = _base._sample(scaffold, rng.uniform(.40, .94))
            heading = rng.uniform(0, _TAU)
            target = hub+_base._polar(heading, lobe_r*rng.uniform(.33, 1.0),
                                     crown*rng.uniform(-.28, .12))
            path = _base._curve(start, start.lerp(target, .50)+_UP*crown*.10, target, 4)
            _twig(mesh, path, rng.uniform(.00065, .00125), 1 if not dry_island else 2)
            _leaves(mesh, path, rng, spec, 7 if dry_island else 12, dry_island)
            # Side shoot is attached, branching sideways and slightly down.
            fork, tangent = _base._sample(path, rng.uniform(.44, .73))
            tip = fork+_base._polar(heading+rng.choice((-1, 1))*rng.uniform(.6, 1.7),
                                    lobe_r*rng.uniform(.45, .80),
                                    crown*rng.uniform(-.16, .16))
            fork_path = _base._curve(fork, fork.lerp(tip, .50)+_UP*crown*.035, tip, 3)
            _twig(mesh, fork_path, rng.uniform(.00035, .00065), 1, 3)
            _leaves(mesh, fork_path, rng, spec, 4 if dry_island else 7, dry_island)

    # Short tangled basal leaf-bearing twigs close holes below the live islands.
    # They are rooted to the skirt, not floating foliage clumps or filled blobs.
    for i in range(24):
        start, tangent = _base._sample(rng.choice(skirt_paths), rng.uniform(.12, .58))
        end = start+_point(rng, r*.24, crown*rng.uniform(.12, .27))
        path = _base._curve(start, start.lerp(end, .55)+_UP*crown*.06, end, 3)
        _twig(mesh, path, .00065, 1, 3)
        _leaves(mesh, path, rng, spec, 6, i%5 == 0)

    # Sparse tall wiry shoots emerge from the low core; foliage stays mostly low.
    for i in range(spec.shoots):
        root = rng.choice(rootlets)
        heading = rng.uniform(0, _TAU)
        tip = _base._polar(heading, r*rng.uniform(.21, .66), h*rng.uniform(.84, 1.0))
        path = _base._curve(root, root+_base._polar(heading-.45, r*.11, h*.66), tip, 6)
        _twig(mesh, path, rng.uniform(.0012, .0018), 2, 4)
        for j in range(3):
            start, tangent = _base._sample(path, .39+j*.18)
            end = start+_base._polar(heading+(-1 if j%2 else 1)*.85,
                                    r*rng.uniform(.12, .28), h*rng.uniform(.025, .09))
            fork = [start, start.lerp(end, .45)+_UP*h*.025, end]
            _twig(mesh, fork, .00056, 2, 3)
            if i == 0 and j == 0:
                _leaves(mesh, fork, rng, spec, 4)

    # Fit exact physical bounds, retaining asymmetric offsets about the root.
    lo = [min(v[axis] for v in mesh.vertices) for axis in range(3)]
    hi = [max(v[axis] for v in mesh.vertices) for axis in range(3)]
    xy = spec.spread/max(hi[0]-lo[0], hi[1]-lo[1])
    z = spec.height/(hi[2]-lo[2])
    mesh.vertices = [(x*xy, y*xy, (height-lo[2])*z) for x, y, height in mesh.vertices]
    return mesh


def _palette() -> list[Any]:
    names = ("weathered stem", "fine grey twig", "sun-bleached dead wood",
             "olive leaf shadow", "olive leaf dusty", "olive leaf warm",
             "sage leaf shadow", "sage leaf silver", "sage leaf warm",
             "senescent leaf", "dry grass dark", "dry grass straw",
             "dry grass bleached", "grass basal muted")
    found = [bpy.data.materials.get("Mojave scrub / "+name) for name in names]
    return found if all(mat is not None for mat in found) else _base._palette()


def create_variants(collection: Any, seed: int = 261010,
                    materials: list[Any] | None = None) -> dict[str, list[Any]]:
    """Create six hidden shared-mesh prototypes, without placing instances.

    Returns lists keyed by ``all``, ``shrubs``, ``layered_low_scrub``,
    ``layered_olive_scrub``, and ``layered_silver_scrub``. All prototypes are
    rooted at z=0. No global random state or existing material is modified.
    """
    if not isinstance(collection, bpy.types.Collection):
        raise TypeError("collection must be a bpy.types.Collection")
    palette = list(materials) if materials is not None else _palette()
    if len(palette) < 14:
        raise ValueError("materials must contain the 14 desert_scrub palette slots")
    result = {key: [] for key in ("all", "shrubs", "layered_low_scrub",
                                  "layered_olive_scrub", "layered_silver_scrub")}
    for i, spec in enumerate(SPECS):
        local_seed = int(seed)+104729*i
        mesh = _geometry(spec, local_seed)
        family = "layered_silver_scrub" if spec.silver else "layered_olive_scrub"
        obj = mesh.object("Layered Mojave prototype / "+spec.name, collection, palette,
                          {"family": family, "nominal_height_m": spec.height,
                           "nominal_spread_m": spec.spread,
                           "generation_seed": local_seed, "layered_lobe_count": spec.lobes,
                           "tall_shoot_count": spec.shoots,
                           "description": "Low intertwined dead skirt, offset live lobes, sparse tall shoots"})
        for key in ("all", "shrubs", "layered_low_scrub", family):
            result[key].append(obj)
    return result


def variant_summary(variants: dict[str, list[Any]]) -> list[dict[str, Any]]:
    return _base.variant_summary(variants)
