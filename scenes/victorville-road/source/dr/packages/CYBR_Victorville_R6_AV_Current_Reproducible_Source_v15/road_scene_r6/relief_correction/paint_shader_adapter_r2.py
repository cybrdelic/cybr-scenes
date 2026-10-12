"""Copy the audited R6/R2 paint graph onto a caller-owned road material copy.

This module has no import-time Blender operations and never opens, saves, or
renders a scene.  The caller owns scene/object changes and must supply a LOCAL
COPY of the road material, not the shared original road/soil material.

``attach_shared_surface_paint(road_material, paint_material, stripe_bounds,
reference_position, broad_normal, *, label=None)`` adds one exact rectangular
stripe.  Call it again for another non-overlapping stripe; each call mixes over
the entire current road Surface BSDF, including its weathering/deposit graph.

``stripe_bounds`` is (xmin, xmax, ymin, ymax), in world metres, derived from the
source strip.  Both supplied sockets must be VECTOR outputs in the destination
material's node tree.  ``reference_position`` is the original paint sheet's
world position (including its resting Z), not the displaced surface position.
``broad_normal`` is the original broad world-space road normal; it must NOT be
the displaced tile's geometric normal or the full aggregate material normal.
The existing paint graph already adds its full aggregate normal to this broad
normal.  World ray-hit XY, independent of reference Z, bounds the stripe.

Geometry nodes upstream of the original crisp Alpha use ``reference_position``
for Position, preserving the original paint pattern's phase.  Other active
Geometry nodes, including the separate R2 shoulder-dust source, use the actual
shared-surface world Position, keeping their deposit field coupled to the road.
The classification follows graph ancestry, never source node names.  Every
source Geometry.Normal is replaced by ``broad_normal`` in either branch.

The returned dict exposes ``original_alpha``, ``stripe_mask``, ``mix_factor``,
``paint_bsdf``, ``surface_bsdf``, ``road_bsdf``, and source-to-copy provenance.
``paint_principled`` and its explicit Base Color/Roughness/Normal input hooks,
``road_bsdf_node``, and ``surface_composition_node``/``surface_output_input``
are retained, as are all original return hooks.  This adapter copies an existing
R2 dust film when present; it does not author or retune the deposition recipe.
Only the currently linked upstream graph is copied: the obsolete soft alpha
Map Range branch is deliberately neither visited nor copied, while active R2
Map Range, MixRGB, and CombineXYZ nodes are supported.  Source materials,
nodes, images, and image settings are never changed.  Unknown active node
types/settings fail rather than silently degrading the material.

The audited source's OBJECT/Strength=1 Normal Map is replaced with normalized
Color*2-1, with no channel flips.  The source object used identity orientation;
the result is already world-aligned.  Applying a sheared tile's object normal
transform here would add the broad slope twice.  Other spaces/strengths fail.
"""
from __future__ import annotations

import math

__all__ = ["PaintAdapterError", "attach_shared_surface_paint"]


class PaintAdapterError(ValueError):
    """The supplied graph is outside the audited R6 paint contract."""


_SUPPORTED = frozenset({
    "ShaderNodeBsdfPrincipled", "ShaderNodeNewGeometry", "ShaderNodeTexNoise",
    "ShaderNodeTexImage", "ShaderNodeNormalMap", "ShaderNodeMath",
    "ShaderNodeVectorMath", "ShaderNodeSeparateXYZ", "ShaderNodeMixRGB",
    "ShaderNodeMapRange", "ShaderNodeCombineXYZ",
})
_STRUCTURAL = frozenset({
    "rna_type", "id_data", "name", "parent", "inputs", "outputs",
    "internal_links", "dimensions", "type",
})
_NESTED = frozenset({"texture_mapping", "color_mapping", "image_user", "color_ramp"})
_SHARED_IDS = frozenset({"image", "object"})


def _value(value):
    """Detach scalar/enum/array values without copying referenced datablocks."""
    if isinstance(value, (str, bool, int, float, type(None))):
        return value
    if isinstance(value, set):
        return set(value)
    return tuple(value)


def _copy_settings(source, target, *, structural=False):
    """Copy every writable RNA value and the known embedded texture settings.

    Readonly scalar values are Blender-derived metadata.  Readonly embedded
    structs still contain writable shader settings and must be copied too.
    Image/Object pointers are shared by identity; their datablocks are readonly
    to this adapter.  Unknown pointer/collection settings are unsupported.
    """
    embedded = []
    for prop in source.bl_rna.properties:
        key = prop.identifier
        if key == "rna_type" or key == "id_data" or key.startswith("bl_"):
            continue
        if structural and key in _STRUCTURAL:
            continue
        value = getattr(source, key)
        if prop.type == "POINTER":
            if key in _NESTED:
                if value is not None:
                    embedded.append((value, getattr(target, key)))
            elif key in _SHARED_IDS and not prop.is_readonly:
                setattr(target, key, value)
                if getattr(target, key) != value:
                    raise PaintAdapterError(f"Datablock identity changed: {key}")
            else:
                raise PaintAdapterError(f"Unsupported RNA pointer: {source.bl_rna.identifier}.{key}")
        elif prop.type == "COLLECTION":
            if key != "elements" or source.bl_rna.identifier != "ColorRamp":
                raise PaintAdapterError(f"Unsupported RNA collection: {source.bl_rna.identifier}.{key}")
            elements = target.elements
            # Color ramps require at least two elements.  Preserve duplicates,
            # alpha values, interpolation mode, and endpoint positions.
            while len(elements) > 2:
                elements.remove(elements[-1])
            # Hold references: changing a position can reorder the collection.
            endpoints = (elements[0], elements[1])
            for index, old in enumerate(value):
                new = endpoints[index] if index < 2 else elements.new(old.position)
                new.position = old.position
                new.color = tuple(old.color)
        elif not prop.is_readonly:
            if prop.type not in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
                raise PaintAdapterError(f"Unsupported RNA setting: {source.bl_rna.identifier}.{key}")
            setattr(target, key, _value(value))
    # Assign Image before its ImageUser and all controlling enums before their
    # embedded settings; source RNA declaration order need not guarantee this.
    for old, new in embedded:
        _copy_settings(old, new)


def _copy_socket_defaults(source, target):
    # Indices, not names, disambiguate repeated Math/Vector Math socket names.
    for collection_name in ("inputs", "outputs"):
        old = getattr(source, collection_name)
        new = getattr(target, collection_name)
        if len(old) != len(new):
            raise PaintAdapterError(f"Socket layout changed for {source.name}")
        for a, b in zip(old, new):
            if a.identifier != b.identifier or a.type != b.type:
                raise PaintAdapterError(f"Socket schema changed: {source.name}/{a.identifier}")
            if hasattr(a, "default_value"):
                b.default_value = _value(a.default_value)


def _material_tree(material, role):
    if material is None or not material.use_nodes or material.node_tree is None:
        raise PaintAdapterError(f"{role} must have an existing shader node tree")
    return material.node_tree


def _surface(tree, role):
    outputs = [node for node in tree.nodes
               if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output]
    if len(outputs) != 1:
        raise PaintAdapterError(f"{role} needs one unambiguous active Material Output")
    output = outputs[0]
    surface = output.inputs["Surface"]
    if len(surface.links) != 1:
        raise PaintAdapterError(f"{role} Surface must have exactly one linked BSDF")
    return output, surface.links[0].from_socket


def _index(sockets, socket):
    for index, candidate in enumerate(sockets):
        if candidate == socket:
            return index
    raise PaintAdapterError("A source link refers to a missing socket")


def _vector_output(socket, tree, role):
    if (socket is None or not getattr(socket, "is_output", False)
            or socket.type != "VECTOR" or socket.node.id_data != tree):
        raise PaintAdapterError(f"{role} must be a VECTOR output in the road material node tree")


def _active_graph(root):
    """Return dependency-ordered active nodes and input links, without writes."""
    nodes, links, visiting, done = [], [], set(), set()

    def visit(node):
        name = node.name
        if name in done:
            return
        if name in visiting:
            raise PaintAdapterError("Paint shader contains a cycle")
        if node.bl_idname not in _SUPPORTED:
            raise PaintAdapterError(f"Unsupported active paint node: {name} ({node.bl_idname})")
        if node.mute:
            raise PaintAdapterError(f"Muted active paint node requires unsupported bypass handling: {name}")
        visiting.add(name)
        for socket in node.inputs:
            if len(socket.links) > 1:
                raise PaintAdapterError(f"Multiple links on paint input: {name}/{socket.name}")
            for link in socket.links:
                if not getattr(link, "is_valid", True) or getattr(link, "is_muted", False):
                    raise PaintAdapterError(f"Invalid/muted active paint link: {name}/{socket.name}")
                visit(link.from_node)
                links.append(link)
        visiting.remove(name)
        done.add(name)
        nodes.append(node)

    visit(root)
    return nodes, links


def _validate_paint(tree, root_socket):
    if getattr(tree, "animation_data", None) is not None:
        raise PaintAdapterError("Animated/driven paint graphs are outside the static source contract")
    root = root_socket.node
    if root.bl_idname != "ShaderNodeBsdfPrincipled" or root_socket.type != "SHADER":
        raise PaintAdapterError("Source paint Surface must be a directly linked Principled BSDF")
    alpha = root.inputs["Alpha"]
    if len(alpha.links) != 1:
        raise PaintAdapterError("Source paint must retain its linked crisp Alpha signal")
    original_alpha = alpha.links[0].from_socket
    if (original_alpha.node.bl_idname != "ShaderNodeMath"
            or original_alpha.node.operation != "GREATER_THAN"):
        raise PaintAdapterError("Expected the current GREATER_THAN crisp paint alpha, not a soft/unknown mask")
    nodes, links = _active_graph(root)
    normals = [node for node in nodes if node.bl_idname == "ShaderNodeNormalMap"]
    if len(normals) != 1:
        raise PaintAdapterError("Expected exactly one active original full aggregate Normal Map")
    normal = normals[0]
    strength = normal.inputs["Strength"]
    if normal.space != "OBJECT" or strength.is_linked or strength.default_value != 1.0:
        raise PaintAdapterError("Only source OBJECT Normal Map with constant Strength=1 is supported")
    if not normal.inputs["Color"].is_linked:
        raise PaintAdapterError("Original aggregate Normal Map Color must remain linked")
    broad_links = 0
    for link in links:
        if link.from_node.bl_idname == "ShaderNodeNewGeometry":
            if link.from_socket.name not in {"Position", "Normal"}:
                raise PaintAdapterError(f"Unsupported active Geometry output: {link.from_socket.name}")
            broad_links += link.from_socket.name == "Normal"
    if not broad_links:
        raise PaintAdapterError("Original broad Geometry.Normal term is absent")
    for node in nodes:
        if node.bl_idname in {"ShaderNodeTexNoise", "ShaderNodeTexImage"}:
            if not node.inputs["Vector"].is_linked:
                raise PaintAdapterError(f"Implicit texture coordinates are unsupported: {node.name}")
        if node.bl_idname == "ShaderNodeTexImage" and node.image is None:
            raise PaintAdapterError(f"Active source image is missing: {node.name}")
    return root, original_alpha, nodes, links


def attach_shared_surface_paint(road_material, paint_material, stripe_bounds,
                                reference_position, broad_normal, *, label=None):
    """Append one source-faithful, opaque paint mix to a road-local material.

    Bounds have sharp inclusive edges; no feather, width expansion, or mask
    redesign is introduced.  Alpha is consumed once as the shader mix factor.
    A failed call removes its added nodes and restores the original road link.
    Repeated calls are supported, but the caller must validate non-overlapping
    bounds and must not reuse a rectangle accidentally.

    ``copied_nodes`` maps source names to destination nodes; Geometry and Normal
    Map substitutions instead appear in ``geometry_replacements`` and
    ``normal_replacements``.  ``created_nodes`` includes every added node.
    ``coordinate_provenance`` records the graph-based Position source per
    Geometry node.  ``alpha_geometry_nodes`` identifies the original paint
    branch; ``shared_surface_position`` exposes the actual hit-position socket.
    """
    road_tree = _material_tree(road_material, "Road destination")
    paint_tree = _material_tree(paint_material, "Source paint")
    if road_material == paint_material or road_tree == paint_tree:
        raise PaintAdapterError("Destination must be separate from the original paint material")
    if getattr(road_material, "library", None) is not None:
        raise PaintAdapterError("Destination must be an editable local road material copy")
    _vector_output(reference_position, road_tree, "Reference paint position")
    _vector_output(broad_normal, road_tree, "Original broad normal")
    try:
        bounds = tuple(float(value) for value in stripe_bounds)
    except (TypeError, ValueError) as exc:
        raise PaintAdapterError("Bounds must be (xmin, xmax, ymin, ymax)") from exc
    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise PaintAdapterError("Bounds must contain four finite world-metre values")
    xmin, xmax, ymin, ymax = bounds
    if xmin >= xmax or ymin >= ymax:
        raise PaintAdapterError("Stripe bounds must have positive X and Y extent")
    road_output, road_bsdf = _surface(road_tree, "Road destination")
    paint_output, source_bsdf = _surface(paint_tree, "Source paint")
    if any(paint_output.inputs[name].is_linked for name in ("Volume", "Displacement")):
        raise PaintAdapterError("Paint has an unsupported Volume or Displacement branch")
    root, source_alpha, source_nodes, source_links = _validate_paint(paint_tree, source_bsdf)
    # R2 adds its own Geometry source without changing the original crisp
    # Alpha graph.  Trace that graph rather than relying on Blender's mutable
    # node names or creation order.  The node-level classification intentionally
    # also preserves every original paint Position link from a shared source.
    alpha_nodes, _ = _active_graph(source_alpha.node)
    alpha_geometry_names = frozenset(
        node.name for node in alpha_nodes
        if node.bl_idname == "ShaderNodeNewGeometry"
    )
    label = label or f"Shared-surface paint / {paint_material.name}"
    created, copied, geometry, normal_replacements, outputs, inputs = [], {}, {}, {}, {}, {}
    coordinate_provenance = {}
    links = road_tree.links

    def new(node_type, suffix):
        node = road_tree.nodes.new(node_type)
        created.append(node)
        node.name = f"{label} / {suffix}"
        node.label = suffix
        return node

    def connect(value, socket):
        if hasattr(value, "node"):
            links.new(value, socket)
        else:
            socket.default_value = value

    def math_node(operation, a, b, suffix):
        node = new("ShaderNodeMath", suffix)
        node.operation = operation
        node.use_clamp = False
        connect(a, node.inputs[0])
        connect(b, node.inputs[1])
        return node.outputs[0]

    try:
        # This single actual-hit source drives dust AND stripe bounds.  Its
        # Normal is deliberately unused: all source normals use broad_normal.
        hit = new("ShaderNodeNewGeometry", "Actual shared-surface world XY")
        for source in source_nodes:
            if source.bl_idname == "ShaderNodeNewGeometry":
                is_original_paint = source.name in alpha_geometry_names
                position = reference_position if is_original_paint else hit.outputs["Position"]
                geometry[source.name] = {"Position": position, "Normal": broad_normal}
                coordinate_provenance[source.name] = {
                    "position_source": (
                        "reference_position" if is_original_paint
                        else "shared_surface_geometry_position"
                    ),
                    "normal_source": "broad_normal",
                    "upstream_of_original_alpha": is_original_paint,
                }
                for index, socket in enumerate(source.outputs):
                    if socket.name in geometry[source.name]:
                        outputs[(source.name, index)] = geometry[source.name][socket.name]
                continue
            if source.bl_idname == "ShaderNodeNormalMap":
                scale = new("ShaderNodeVectorMath", source.name + " / raw RGB times two")
                scale.operation = "SCALE"
                scale.inputs["Scale"].default_value = 2.0
                sub = new("ShaderNodeVectorMath", source.name + " / signed world normal")
                sub.operation = "SUBTRACT"
                sub.inputs[1].default_value = (1.0, 1.0, 1.0)
                links.new(scale.outputs["Vector"], sub.inputs[0])
                norm = new("ShaderNodeVectorMath", source.name + " / normalize without object transform")
                norm.operation = "NORMALIZE"
                links.new(sub.outputs["Vector"], norm.inputs[0])
                inputs[(source.name, _index(source.inputs, source.inputs["Color"]))] = scale.inputs[0]
                outputs[(source.name, _index(source.outputs, source.outputs["Normal"]))] = norm.outputs["Vector"]
                normal_replacements[source.name] = (scale, sub, norm)
                continue
            target = new(source.bl_idname, source.name)
            _copy_settings(source, target, structural=True)
            _copy_socket_defaults(source, target)
            copied[source.name] = target
            for index, socket in enumerate(target.inputs):
                inputs[(source.name, index)] = socket
            for index, socket in enumerate(target.outputs):
                outputs[(source.name, index)] = socket

        for link in source_links:
            # Copy the alpha upstream branch, but do not connect it to opacity.
            if link.to_node == root and link.to_socket == root.inputs["Alpha"]:
                continue
            src_key = (link.from_node.name, _index(link.from_node.outputs, link.from_socket))
            dst_key = (link.to_node.name, _index(link.to_node.inputs, link.to_socket))
            if src_key not in outputs or dst_key not in inputs:
                raise PaintAdapterError("An active source link has no supported replacement")
            links.new(outputs[src_key], inputs[dst_key])

        paint = copied[root.name]
        paint.inputs["Alpha"].default_value = 1.0
        alpha = outputs[(source_alpha.node.name, _index(source_alpha.node.outputs, source_alpha))]
        opaque_bsdf = outputs[(root.name, _index(root.outputs, source_bsdf))]

        split = new("ShaderNodeSeparateXYZ", "Exact original stripe bounds")
        links.new(hit.outputs["Position"], split.inputs[0])
        # Inclusive boundary tests: 1 - (x < xmin), 1 - (x > xmax).
        # This also avoids any edge widening from a COMPARE epsilon.
        left = math_node("SUBTRACT", 1.0, math_node("LESS_THAN", split.outputs["X"], xmin, "X below stripe"), "X at or above minimum")
        right = math_node("SUBTRACT", 1.0, math_node("GREATER_THAN", split.outputs["X"], xmax, "X above stripe"), "X at or below maximum")
        low = math_node("SUBTRACT", 1.0, math_node("LESS_THAN", split.outputs["Y"], ymin, "Y below stripe"), "Y at or above minimum")
        high = math_node("SUBTRACT", 1.0, math_node("GREATER_THAN", split.outputs["Y"], ymax, "Y above stripe"), "Y at or below maximum")
        xmask = math_node("MULTIPLY", left, right, "Exact stripe X mask")
        ymask = math_node("MULTIPLY", low, high, "Exact stripe Y mask")
        mask = math_node("MULTIPLY", xmask, ymask, "Exact original stripe rectangle")
        factor = math_node("MULTIPLY", mask, alpha, "Original crisp alpha times stripe mask")
        mix = new("ShaderNodeMixShader", "Complete road or opaque original paint")
        links.new(factor, mix.inputs[0])
        links.new(road_bsdf, mix.inputs[1])
        links.new(opaque_bsdf, mix.inputs[2])
        if paint.inputs["Alpha"].is_linked or paint.inputs["Alpha"].default_value != 1.0:
            raise PaintAdapterError("Copied paint is not opaque")
        # Commit last.  No original road input other than Surface is touched.
        links.new(mix.outputs[0], road_output.inputs["Surface"])
    except Exception:
        for node in reversed(created):
            road_tree.nodes.remove(node)
        surface = road_output.inputs["Surface"]
        if not surface.is_linked:
            links.new(road_bsdf, surface)
        raise

    return {
        "original_alpha": alpha,
        "stripe_mask": mask,
        "mix_factor": factor,
        "paint_bsdf": opaque_bsdf,
        "paint_principled": paint,
        "paint_base_color_input": paint.inputs["Base Color"],
        "paint_roughness_input": paint.inputs["Roughness"],
        "paint_normal_input": paint.inputs["Normal"],
        "surface_bsdf": mix.outputs[0],
        "surface_composition_node": mix,
        "surface_output_input": road_output.inputs["Surface"],
        "road_bsdf": road_bsdf,
        "road_bsdf_node": road_bsdf.node,
        "copied_nodes": copied,
        "geometry_replacements": geometry,
        "coordinate_provenance": coordinate_provenance,
        "alpha_geometry_nodes": tuple(
            node.name for node in alpha_nodes
            if node.bl_idname == "ShaderNodeNewGeometry"
        ),
        "shared_surface_position": hit.outputs["Position"],
        "normal_replacements": normal_replacements,
        "created_nodes": tuple(created),
        "source_material": paint_material.name,
        "source_active_nodes": tuple(node.name for node in source_nodes),
        "stripe_bounds": bounds,
        "normal_contract": "Normalized raw RGB*2-1 in source world orientation + original broad slope once",
    }
