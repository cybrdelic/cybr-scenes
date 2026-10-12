"""Airy, wholly procedural Mojave-inspired scrub for Blender 4.3+.

This is representative scene dressing, not a botanical/site reconstruction.
No images, scans, alpha cards, spheres, subdivision, or external dependencies.
Geometry is in metres, rooted at local z=0, and is deterministic for a seed.

    from desert_scrub import create_variants
    bank = create_variants(prototype_collection, seed=260910)
    proto = bank["shrubs"][0]
    instance = bpy.data.objects.new("Roadside scrub", proto.data)
    scene_collection.objects.link(instance)
    instance.location = (x, y, terrain_z)

The returned prototype objects are individually hidden in the viewport/render;
new objects sharing their mesh are visible normally. Do not copy their hide flags.
Do not hide a collection that also contains the visible instances. Recommended:
random z-rotation, 0.8–1.2 XY scale and 0.85–1.15 Z scale. Mix the three shrub
families unevenly, leave bare interspaces, and cluster grasses locally. The
module never changes lights, camera, render settings, existing meshes/materials,
or collection visibility, and uses no bpy.ops/context-dependent operations.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import bpy
from mathutils import Vector

__all__ = ["create_variants", "variant_summary"]
_UP = Vector((0.0, 0.0, 1.0))
_TAU = 2.0 * math.pi


@dataclass(frozen=True)
class _ShrubSpec:
    name: str
    family: str
    height: float
    spread: float
    basal_stems: int
    living_fraction: float
    leaf_scale: float = 1.0


class _Mesh:
    def __init__(self) -> None:
        self.vertices: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.material_indices: list[int] = []
        self.smooth: list[bool] = []
        self.leaf_count = 0
        self.branch_count = 0
        self.blade_count = 0

    def face(self, indices: tuple[int, ...], material: int, smooth=False) -> None:
        self.faces.append(indices)
        self.material_indices.append(material)
        self.smooth.append(smooth)

    def tube(self, points: list[Vector], radii: list[float], material: int,
             sides: int = 5, phase: float = 0.0) -> None:
        """Connected tapering rings, with tiny closed ends, not separate cones."""
        if len(points) < 2:
            return
        start = len(self.vertices)
        reference = Vector((0.317, 0.719, 0.618))
        for j, (point, radius) in enumerate(zip(points, radii)):
            tangent = points[min(j + 1, len(points)-1)] - points[max(j - 1, 0)]
            tangent.normalize()
            side = tangent.cross(reference)
            if side.length_squared < 1e-9:
                side = tangent.cross(_UP)
            side.normalize()
            other = tangent.cross(side).normalized()
            for k in range(sides):
                angle = _TAU * k / sides + phase
                p = point + radius * (math.cos(angle)*side + math.sin(angle)*other)
                self.vertices.append(tuple(p))
        self.face(tuple(start + k for k in reversed(range(sides))), material)
        for j in range(len(points)-1):
            a, b = start+j*sides, start+(j+1)*sides
            for k in range(sides):
                self.face((a+k, a+(k+1)%sides, b+(k+1)%sides, b+k), material, True)
        self.face(tuple(start+(len(points)-1)*sides+k for k in range(sides)), material)
        self.branch_count += 1

    def leaf(self, base: Vector, direction: Vector, normal: Vector,
             length: float, width: float, curl: float, material: int) -> None:
        """Eight small folded triangles form one irregular almond-shaped leaf.

        The central fold, cupped margins and mildly bent tip catch light without
        thick polyhedral leaf volumes. Two-sided shading is provided by Blender.
        """
        axis = direction.normalized()
        side = normal.cross(axis)
        if side.length_squared < 1e-9:
            side = _UP.cross(axis)
        if side.length_squared < 1e-9:
            side = Vector((1.0, 0.0, 0.0))
        side.normalize()
        up = axis.cross(side).normalized()
        off = len(self.vertices)
        # Outline: narrow petiole, asymmetric shoulder, pointed tip, other side.
        outline = [(0.0, 0.0, 0.0), (.26, -.40, -.055),
                   (.67, -.48, -.035), (1.0, .025, curl),
                   (.68, .46, -.020), (.29, .43, -.050)]
        for u, v, z in outline:
            p = base+axis*(length*u)+side*(width*v)+up*(width*z)
            self.vertices.append(tuple(p))
        self.vertices.append(tuple(base + axis*(length*.39)+up*(width*.13)))
        self.vertices.append(tuple(base + axis*(length*.72)+up*(width*.075)))
        for face in ((0, 1, 6), (1, 2, 6), (2, 7, 6), (2, 3, 7),
                     (3, 4, 7), (4, 5, 7), (5, 6, 7), (5, 0, 6)):
            self.face(tuple(off+i for i in face), material, False)
        self.leaf_count += 1

    def blade(self, points: list[Vector], width: float, material: int,
              orientation: float) -> None:
        """Thin, folded, tapered strip, curved and twisted along its length."""
        off = len(self.vertices)
        for j, point in enumerate(points):
            t = j/(len(points)-1)
            side = Vector((math.cos(orientation+t*.7), math.sin(orientation+t*.7), .12*t))
            local_width = width*((1-t)**.65) if j < len(points)-1 else width*.025
            for k in (-1, 0, 1):
                p = point + side*(local_width*.5*k)
                if k == 0:
                    p.z += local_width*.22
                self.vertices.append(tuple(p))
        for j in range(len(points)-1):
            a, b = off+j*3, off+(j+1)*3
            self.face((a, a+1, b+1, b), material)
            self.face((a+1, a+2, b+2, b+1), material)
        self.blade_count += 1

    def fit_height(self, height: float) -> None:
        minz = min(p[2] for p in self.vertices)
        maxz = max(p[2] for p in self.vertices)
        factor = height/(maxz-minz)
        # Leaves retain plausible aspect ratios; fitted sizes include their tips.
        self.vertices = [(x*factor, y*factor, (z-minz)*factor)
                         for x, y, z in self.vertices]

    def object(self, name: str, collection: Any, materials: list[Any],
               attributes: dict[str, Any]) -> Any:
        data = bpy.data.meshes.new(name + " / shared geometry")
        data.from_pydata(self.vertices, [], self.faces)
        for material in materials:
            data.materials.append(material)
        data.polygons.foreach_set("material_index", self.material_indices)
        data.polygons.foreach_set("use_smooth", self.smooth)
        data.update()
        obj = bpy.data.objects.new(name, data)
        collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_viewport = True
        obj["prototype_only"] = True
        obj["units"] = "metres"
        obj["source"] = "Procedural branching, individual leaves and blades; no image sources"
        for key, value in attributes.items():
            obj[key] = value
        obj["leaf_count"] = self.leaf_count
        obj["branch_count"] = self.branch_count
        obj["blade_count"] = self.blade_count
        obj["vertex_count"] = len(self.vertices)
        obj["polygon_count"] = len(self.faces)
        data["prototype_family"] = attributes["family"]
        data["nominal_height_m"] = attributes["nominal_height_m"]
        return obj


def _material(name: str, color: tuple[float, float, float], leaf=False,
              bark=False) -> Any:
    """Create only this module's own materials. Never mutate an existing material."""
    mat = bpy.data.materials.new("Mojave scrub / " + name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = .88 if leaf else .95
    bsdf.inputs["IOR"].default_value = 1.38
    bsdf.inputs["Specular IOR Level"].default_value = .18 if leaf else .14
    info = nodes.new("ShaderNodeObjectInfo")
    variation = nodes.new("ShaderNodeMapRange")
    variation.inputs["From Min"].default_value = 0
    variation.inputs["From Max"].default_value = 1
    variation.inputs["To Min"].default_value = .83
    variation.inputs["To Max"].default_value = 1.13
    links.new(info.outputs["Random"], variation.inputs["Value"])
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1
    tint.inputs[1].default_value = (*color, 1)
    links.new(variation.outputs["Result"], tint.inputs[2])
    links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
    if bark:
        coordinates = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 155
        noise.inputs["Detail"].default_value = 2
        noise.inputs["Roughness"].default_value = .72
        links.new(coordinates.outputs["Object"], noise.inputs["Vector"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = .20
        bump.inputs["Distance"].default_value = .00045
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if leaf:
        trans = nodes.new("ShaderNodeBsdfTranslucent")
        links.new(tint.outputs["Color"], trans.inputs["Color"])
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = .075
        links.new(bsdf.outputs["BSDF"], mix.inputs[1])
        links.new(trans.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], out.inputs["Surface"])
    else:
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _palette() -> list[Any]:
    # RGB tuples are linear scene color, deliberately dull, dry and low-chroma.
    specs = [
        ("weathered stem", (.115, .086, .058), False, True),
        ("fine grey twig", (.168, .150, .122), False, True),
        ("sun-bleached dead wood", (.238, .212, .170), False, True),
        ("olive leaf shadow", (.070, .084, .039), True, False),
        ("olive leaf dusty", (.112, .130, .063), True, False),
        ("olive leaf warm", (.147, .149, .078), True, False),
        ("sage leaf shadow", (.140, .153, .110), True, False),
        ("sage leaf silver", (.210, .222, .164), True, False),
        ("sage leaf warm", (.235, .232, .166), True, False),
        ("senescent leaf", (.222, .177, .092), True, False),
        ("dry grass dark", (.162, .127, .064), False, False),
        ("dry grass straw", (.297, .238, .132), False, False),
        ("dry grass bleached", (.394, .330, .211), False, False),
        ("grass basal muted", (.127, .140, .075), False, False),
    ]
    return [_material(name, color, leaf, bark) for name, color, leaf, bark in specs]


def _curve(a: Vector, b: Vector, c: Vector, count: int) -> list[Vector]:
    return [a*(1-t)**2+b*(2*t*(1-t))+c*t*t
            for t in (j/(count-1) for j in range(count))]


def _sample(points: list[Vector], t: float) -> tuple[Vector, Vector]:
    t = max(0.0, min(.999999, t))*(len(points)-1)
    j = int(t)
    return points[j].lerp(points[j+1], t-j), (points[j+1]-points[j]).normalized()


def _polar(angle: float, length: float, z: float = 0.0) -> Vector:
    return Vector((math.cos(angle)*length, math.sin(angle)*length, z))


def _leaf_spray(mesh: _Mesh, path: list[Vector], spec: _ShrubSpec,
                rng: random.Random, vigor: float) -> None:
    silver = spec.family == "silver_low_scrub"
    count = rng.randint(5, 8) if silver else rng.randint(6, 9)
    base_length = (.027 if silver else .016)*spec.leaf_scale
    phase = rng.uniform(0, _TAU)
    for j in range(count):
        t = .14+.80*(j+.2*rng.random())/count
        # A few missing nodes, especially on drought-thinned outer twigs.
        if rng.random() > vigor:
            continue
        origin, tangent = _sample(path, t)
        axial = _polar(phase+j*2.399, 1.0, rng.uniform(-.1, .3))
        side = tangent.cross(axial).normalized()
        if side.length_squared < 1e-9:
            side = tangent.cross(_UP).normalized()
        # Paired small olive leaflets; alternating broader silver leaves.
        signs = (1.0,) if silver else (-1.0, 1.0)
        for sign in signs:
            direction = (side*sign + tangent*rng.uniform(.12, .50) +
                         _UP*rng.uniform(-.04, .38)).normalized()
            length = base_length*rng.uniform(.68, 1.20)*(1-.25*t)
            width = length*(rng.uniform(.50, .78) if silver else rng.uniform(.30, .48))
            # Pitch varies, retaining face-on flecks and narrow edge-on leaves.
            normal = (_UP*rng.uniform(.18, 1.0) + tangent*rng.uniform(-.4, .5) +
                      side*rng.uniform(-.4, .4)).normalized()
            mat = rng.choice((6, 6, 7, 7, 8)) if silver else rng.choice((3, 4, 4, 4, 5))
            if rng.random() < .095:
                mat = 9
            mesh.leaf(origin, direction, normal, length, width,
                      rng.uniform(-.17, .20), mat)


def _shrub(spec: _ShrubSpec, seed: int) -> _Mesh:
    rng = random.Random(seed)
    mesh = _Mesh()
    h = spec.height
    radius = spec.spread*.5
    silver = spec.family == "silver_low_scrub"
    dry = spec.family == "dry_open_scrub"
    wind_angle = rng.uniform(0, _TAU)
    wind = _polar(wind_angle, h*rng.uniform(.045, .14))
    # The crown has distinct strong and weak sectors, not a radial sphere.
    strong_angle = rng.uniform(0, _TAU)
    missing_sector = strong_angle+rng.uniform(1.2, 2.6)
    n = spec.basal_stems
    for stem in range(n):
        angle = _TAU*(stem+rng.uniform(-.29, .29))/n + strong_angle
        vigor = .78 + .19*math.cos(angle-strong_angle)+rng.uniform(-.07, .07)
        # A wide sector remains conspicuously open even in healthy variants.
        sector_distance = abs(math.atan2(math.sin(angle-missing_sector),
                                        math.cos(angle-missing_sector)))
        sector_thinned = sector_distance < .47
        live = (rng.random() < spec.living_fraction and not
                (sector_thinned and rng.random() < .78))
        tipz = h*rng.uniform(.50, .86)*(1.0 if live else rng.uniform(.76, 1.16))
        radial = radius*rng.uniform(.52, .90)*(.80+vigor*.20)
        root = _polar(angle+rng.uniform(-.4, .4), h*rng.uniform(.006, .055), 0)
        end = _polar(angle+rng.uniform(-.20, .20), radial, tipz)+wind
        # Several independent arching basal stems: no exposed lollipop trunk.
        elbow = root + _polar(angle-.18, radial*.28, tipz*rng.uniform(.38, .60))
        main = _curve(root, elbow, end, 6)
        base_radius = h*rng.uniform(.0080, .0135)
        radii = [base_radius*(1-.89*j/(len(main)-1)) for j in range(len(main))]
        mesh.tube(main, radii, 0 if live else 2, 6, rng.uniform(0, 2))
        secondary_count = rng.randint(4, 6)
        for branch in range(secondary_count):
            t = .22+.67*(branch+rng.uniform(.08, .70))/secondary_count
            start, tangent = _sample(main, t)
            sign = 1 if branch%2 else -1
            branch_angle = angle+sign*rng.uniform(.42, 1.16)
            reach = radius*rng.uniform(.20, .44)*(1-.37*t)
            rise = h*rng.uniform(.08, .25)*(1-.16*t)
            target = start+_polar(branch_angle, reach, rise)+wind*.12
            control = start + tangent*(reach*.40) + Vector((0, 0, rise*.17))
            branch_path = _curve(start, control, target, 4)
            r = base_radius*rng.uniform(.30, .46)*(1-.52*t)
            branch_live = live and rng.random() < (.84 if not silver else .91)
            mat = 1 if branch_live else rng.choice((1, 2, 2))
            mesh.tube(branch_path, [r, r*.71, r*.39, r*.14], mat, 5)
            twig_count = rng.randint(2, 4)
            for twig in range(twig_count):
                u = .29+.65*(twig+rng.uniform(.2, .8))/twig_count
                twig_start, twig_direction = _sample(branch_path, u)
                twig_angle = branch_angle + (-1 if twig%2 else 1)*rng.uniform(.42, 1.15)
                twig_reach = h*rng.uniform(.065, .15)
                twig_rise = h*rng.uniform(.035, .14)
                twig_end = twig_start+_polar(twig_angle, twig_reach, twig_rise)
                twig_mid = twig_start+twig_direction*(twig_reach*.36)+Vector((0, 0, twig_rise*.18))
                twig_path = _curve(twig_start, twig_mid, twig_end, 4)
                tr = max(.00055, r*rng.uniform(.27, .43))
                mesh.tube(twig_path, [tr, tr*.77, tr*.45, tr*.095], mat, 4)
                if branch_live and rng.random() < (.84 if silver else .88):
                    _leaf_spray(mesh, twig_path, spec, rng, min(.97, vigor))
                elif rng.random() < .28:
                    # Retained dry leaves, isolated rather than a dead solid crown.
                    p, direction = _sample(twig_path, rng.uniform(.48, .85))
                    mesh.leaf(p, direction+_polar(twig_angle+.8, .7, .2), _UP,
                              .018*spec.leaf_scale, .007, -.23, 9)
            if branch_live and rng.random() < .66:
                _leaf_spray(mesh, branch_path, spec, rng, min(.78, vigor))
            if (not branch_live) or rng.random() < .25:
                # Fine, forked dead terminal extension breaks the crown contour.
                p, direction = _sample(branch_path, .75)
                length = h*rng.uniform(.07, .16)
                tip = p+direction*length+_polar(branch_angle-.7, length*.45, -.015)
                mesh.tube([p, p.lerp(tip, .55)+_UP*length*.12, tip],
                          [max(.00065, r*.23), .00048, .00010], 2, 4)
        # Occasional low, weathered side branch near the ground.
        if rng.random() < (.36 if dry else .19):
            start = main[1]
            tip = _polar(angle+.45, radius*rng.uniform(.55, .90), h*rng.uniform(.09, .20))
            mesh.tube([start, start.lerp(tip, .50)+_UP*h*.07, tip],
                      [base_radius*.33, base_radius*.14, .0003], 2, 5)
    mesh.fit_height(spec.height)
    return mesh


def _grass(height: float, seed: int, kind: str) -> _Mesh:
    rng = random.Random(seed)
    mesh = _Mesh()
    spread = height*(.54 if kind == "upright_bunchgrass" else .90)
    wind_angle = rng.uniform(0, _TAU)
    # Off-centre sub-tufts preserve gaps and clumping inside each bunch.
    centres = [_polar(rng.uniform(0, _TAU), spread*rng.uniform(.02, .17), 0)
               for _ in range(rng.randint(3, 5))]
    blade_count = rng.randint(39, 61) if kind != "sparse_stubble" else rng.randint(24, 37)
    for blade in range(blade_count):
        angle = rng.uniform(0, _TAU)
        centre = rng.choice(centres)
        origin = centre+_polar(angle, spread*rng.uniform(0, .06))
        blade_h = height*rng.uniform(.30, .93)
        lean = spread*rng.uniform(.20, .68)
        if kind == "upright_bunchgrass":
            lean *= .65
        bend = _polar(angle, lean)+_polar(wind_angle, height*.10)
        points = []
        for j in range(6):
            t = j/5
            p = origin+bend*t*t
            p.z = blade_h*(t-.26*t**3)
            points.append(p)
        mat = rng.choices((10, 11, 12, 13), (.20, .44, .30, .06))[0]
        mesh.blade(points, rng.uniform(.0012, .0033), mat, angle+math.pi*.5)
    stalk_count = rng.randint(8, 15) if kind != "sparse_stubble" else rng.randint(4, 7)
    for stalk in range(stalk_count):
        angle = rng.uniform(0, _TAU)
        origin = rng.choice(centres)+_polar(angle, spread*.025)
        h = height*rng.uniform(.66, 1.0)
        bend = _polar(angle, spread*rng.uniform(.12, .45))+_polar(wind_angle, height*.11)
        target = origin+bend+_UP*h
        path = _curve(origin, origin+bend*.13+_UP*h*.61, target, 5)
        r = rng.uniform(.00052, .00083)
        mesh.tube(path, [r, r*.86, r*.66, r*.42, r*.18], 11, 4)
        # Sparse open seed panicles: straw wire and tiny folded husks, no balls.
        for j in range(rng.randint(3, 6)):
            t = rng.uniform(.75, .97)
            p, tangent = _sample(path, t)
            heading = angle+j*2.399
            extent = height*rng.uniform(.025, .077)
            tip = p+_polar(heading, extent, extent*rng.uniform(.28, .60))
            mesh.tube([p, tip], [r*.34, r*.075], 12, 3)
            mesh.leaf(tip, tangent+_polar(heading, .38), _UP,
                      rng.uniform(.006, .012), rng.uniform(.0012, .0020), .05, 12)
    mesh.fit_height(height)
    return mesh


def create_variants(collection: Any, seed: int = 260910) -> dict[str, list[Any]]:
    """Build 12 shrub and five dry-grass shared-mesh prototypes.

    Args:
        collection: An existing bpy.types.Collection receiving hidden prototypes.
        seed: Any integer; does not change global Python/NumPy random state.

    Returns:
        Dictionary: shrubs, grass, olive_open_scrub, silver_low_scrub,
        dry_open_scrub, and all. Each list contains Blender mesh objects; mesh
        data can be linked by ordinary bpy.data.objects.new(name, proto.data).
        Shrub root-to-top height: 0.22–1.08 m. Grass: 0.14–0.47 m.
    """
    if not isinstance(collection, bpy.types.Collection):
        raise TypeError("collection must be a bpy.types.Collection")
    specs = [
        _ShrubSpec("Olive spreading A", "olive_open_scrub", .47, .86, 10, .91),
        _ShrubSpec("Olive spreading B", "olive_open_scrub", .64, 1.02, 11, .88),
        _ShrubSpec("Olive upright A", "olive_open_scrub", .84, 1.04, 12, .89),
        _ShrubSpec("Olive upright B", "olive_open_scrub", 1.08, 1.18, 13, .84, 1.05),
        _ShrubSpec("Olive young open", "olive_open_scrub", .31, .48, 7, .84, .85),
        _ShrubSpec("Silver low A", "silver_low_scrub", .33, .60, 9, .93, .91),
        _ShrubSpec("Silver low B", "silver_low_scrub", .44, .86, 11, .94),
        _ShrubSpec("Silver low asymmetric", "silver_low_scrub", .58, 1.04, 12, .89, 1.02),
        _ShrubSpec("Silver young low", "silver_low_scrub", .22, .39, 7, .89, .76),
        _ShrubSpec("Drought thinned spreading", "dry_open_scrub", .42, .76, 9, .43),
        _ShrubSpec("Drought thinned upright", "dry_open_scrub", .72, .90, 11, .36),
        _ShrubSpec("Low weathered skeleton", "dry_open_scrub", .29, .65, 8, .21, .83),
    ]
    materials = _palette()
    result: dict[str, list[Any]] = {"shrubs": [], "grass": [], "all": [],
                                   "olive_open_scrub": [], "silver_low_scrub": [],
                                   "dry_open_scrub": []}
    for j, spec in enumerate(specs):
        local_seed = int(seed)+j*104729
        mesh = _shrub(spec, local_seed)
        obj = mesh.object("Mojave prototype / "+spec.name, collection, materials,
                          {"family": spec.family, "nominal_height_m": spec.height,
                           "nominal_spread_m": spec.spread, "generation_seed": local_seed,
                           "description": "Airy basal branches, folded individual leaves, bare twigs"})
        result["shrubs"].append(obj)
        result[spec.family].append(obj)
        result["all"].append(obj)
    grass_specs = [("Fine upright straw", .39, "upright_bunchgrass"),
                   ("Dry arching bunch", .28, "arching_bunchgrass"),
                   ("Tall open seed grass", .47, "upright_bunchgrass"),
                   ("Low dry stubble", .14, "sparse_stubble"),
                   ("Wind-bent bunch", .23, "arching_bunchgrass")]
    for j, (name, height, family) in enumerate(grass_specs):
        local_seed = int(seed)+1500007+j*104729
        mesh = _grass(height, local_seed, family)
        obj = mesh.object("Mojave prototype / "+name, collection, materials,
                          {"family": family, "nominal_height_m": height,
                           "generation_seed": local_seed,
                           "description": "Folded curved grass blades and open seed panicles"})
        result["grass"].append(obj)
        result["all"].append(obj)
    return result


def variant_summary(variants: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Machine-readable counts/bounds; useful for scene receipts and budgets."""
    result = []
    for obj in variants["all"]:
        xyz = [v.co for v in obj.data.vertices]
        lower = [min(v[i] for v in xyz) for i in range(3)]
        upper = [max(v[i] for v in xyz) for i in range(3)]
        result.append({"name": obj.name, "family": obj["family"],
                       "vertices": len(obj.data.vertices),
                       "polygons": len(obj.data.polygons),
                       "triangles": sum(len(p.vertices)-2 for p in obj.data.polygons),
                       "leaves": obj["leaf_count"], "branches": obj["branch_count"],
                       "blades": obj["blade_count"],
                       "bounds_min_m": lower, "bounds_max_m": upper,
                       "dimensions_m": [upper[i]-lower[i] for i in range(3)]})
    return result
