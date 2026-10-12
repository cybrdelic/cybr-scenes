"""AZ: isolated in-memory fine-coat endpoint replacement, never a scene build.

Only two AI color endpoints and its one normal endpoint change on a staged copy
of the current left-shoulder material. Finite masks, roughness, geometry, burial,
original materials and prototypes are untouched. No renderer or scene load.
"""
from pathlib import Path
import gc
import hashlib
import importlib.util
import json
import time
import numpy as np

GROUND = 'Graded shoulder and alluvial plain -1'
MEAN = (.29535648, .24439612, .17515583, 1.)
HELPER_SHA = '163927b3f5edcd556e03c59f3170bd791d8c9bc930f85d0638bb499fbbeef202'
SIDE_M = .18
MAX_HELPER_WORKING_BYTES = 196 * 1024 ** 2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_helper(path):
    import sys
    path = Path(path)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == HELPER_SHA, 'Audited AZ helper hash changed')
    name = 'az_verified_fine_response'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source_arrays(config):
    """Bounded native arrays plus exact area-weighted global slope moments.

    Does not instantiate the large all-channel moment pyramid. The audit's mip
    proof is separate. Only native slope images are needed by this adapter.
    """
    root = Path(__file__).resolve().parents[1]
    sibling = Path(__file__).with_name('fine_response.py')
    default_helper = sibling if sibling.is_file() else root / 'audits/fines_response_az/fine_response.py'
    helper_path = Path(config.get('helper_path', default_helper))
    helper = load_helper(helper_path)
    microbed = Path(config.get('microbed_path', root.parent / 'discrete_grains_r5/prototypes/microbed.npz'))
    builder = Path(config.get('builder_path', root.parent / 'discrete_grains_r5/src/build_diagnostic.py'))
    response = helper.load_response(microbed, builder)
    h = response.height_m.astype('f8')
    sy, sx = np.gradient(h, SIDE_M / 1100, SIDE_M / 1100, edge_order=2)
    sums = np.zeros(6, dtype='f8')
    wx = np.ones(1101); wx[[0, -1]] = .5
    # Row blocks avoid full covariance/second-moment temporary arrays.
    for start in range(0, 1101, 32):
        stop = min(start + 32, 1101)
        wy = np.ones(stop - start)
        if start == 0: wy[0] = .5
        if stop == 1101: wy[-1] = .5
        w = wy[:, None] * wx[None, :]
        x, y = sx[start:stop], sy[start:stop]
        sums += [w.sum(), (w * x).sum(), (w * y).sum(), (w * x * x).sum(), (w * x * y).sum(), (w * y * y).sum()]
    mean = sums[1:3] / sums[0]
    second = sums[3:6] / sums[0]
    variance = second[[0, 2]] - mean * mean
    color = response.color_linear.copy()
    slopes = np.empty(color.shape, dtype='f4')
    slopes[..., 0], slopes[..., 1], slopes[..., 2] = sx, sy, 0.
    # Conservative maximum simultaneously live NumPy payload, including source
    # helper generation intermediates; guard native shape and never allocate mips.
    estimated_live_array_upper_bound = 190 * 1024 ** 2
    require(estimated_live_array_upper_bound <= MAX_HELPER_WORKING_BYTES, 'AZ helper working-array contract exceeded')
    report = dict(helper_sha256=HELPER_SHA, microbed_sha256=response.sha256,
                  builder_sha256=response.builder_sha256, native_shape=[1101, 1101], side_m=SIDE_M,
                  source_variant=response.variant, height_range_m=[float(h.min()), float(h.max())],
                  metric_slope_mean_xy=mean.tolist(), metric_slope_second_xx_xy_yy=second.tolist(),
                  rms_total_slope=float(np.sqrt(second[0] + second[2])),
                  root_footprint_slope_variance_trace=float(variance.sum()),
                  source_principled_roughness=.84, roughness_modified=False,
                  shader_noise_bump_variance_included=False,
                  excluded_bump=dict(noise_scale_per_m=9200, detail=2, noise_roughness=.7,
                                     bump_distance_m=.000015, bump_strength=.6),
                  mip_policy='Native texture filtering only; source moments recorded, not converted ad hoc to GGX roughness. Separate audit proves first/second-moment conservation.',
                  estimated_live_numpy_array_upper_bound_bytes=estimated_live_array_upper_bound,
                  memory_estimate_is_not_measured_RSS=True)
    del h, sx, sy, response, x, y, w
    gc.collect()
    return color, slopes, report


def mirrored_coordinates(xy, side_m=SIDE_M, size=1101):
    """Pure fixture oracle: centered finite patch with derivative-correct mirror."""
    q = (np.asarray(xy, dtype='f8') + side_m / 2) / side_m
    cell = np.floor(q)
    parity = cell - 2 * np.floor(cell / 2)
    sign = 1 - 2 * parity
    fraction = q - cell
    mirrored = fraction * sign + parity
    uv = (mirrored * (size - 1) + .5) / size
    return uv, sign


def _socket_value(socket):
    if not hasattr(socket, 'default_value'): return None
    value = socket.default_value
    if isinstance(value, (str, int, float, bool)): return value
    try: return list(value)
    except TypeError: return str(value)


def graph_stamp(material, include_nodes=None, omit_links_to=()):
    tree = material.node_tree
    selected = set(include_nodes) if include_nodes is not None else {n.name for n in tree.nodes}
    nodes = []
    for n in tree.nodes:
        if n.name not in selected: continue
        props = {key: getattr(n, key) for key in ('operation', 'blend_type', 'use_clamp', 'clamp_result', 'interpolation', 'extension') if hasattr(n, key)}
        nodes.append(dict(name=n.name, type=n.bl_idname, label=n.label, mute=n.mute, properties=props,
                          inputs=[(s.identifier, _socket_value(s)) for s in n.inputs],
                          image=n.image.name if hasattr(n, 'image') and n.image else None,
                          attribute=getattr(n, 'attribute_name', None)))
    links = sorted((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
                   for l in tree.links if l.from_node.name in selected and l.to_node.name in selected
                   and (l.to_node.name, l.to_socket.identifier) not in omit_links_to)
    return hashlib.sha256(json.dumps(dict(nodes=sorted(nodes, key=lambda a: a['name']), links=links), sort_keys=True).encode()).hexdigest()


def _from(socket):
    return socket.links[0].from_socket if len(socket.links) == 1 else None


def _constant(socket, value):
    return not socket.is_linked and hasattr(socket, 'default_value') and abs(float(socket.default_value) - value) < 1e-6


def _attribute(socket, name):
    source = _from(socket)
    return source is not None and source.node.bl_idname == 'ShaderNodeAttribute' and source.node.attribute_name == name and source.name == 'Fac'


def _scaled_attribute(socket, name, amount):
    source = _from(socket)
    return (source is not None and source.node.bl_idname == 'ShaderNodeMath' and source.node.operation == 'MULTIPLY'
            and _attribute(source.node.inputs[0], name) and _constant(source.node.inputs[1], amount))


def _ai_attenuation(socket):
    source = _from(socket)
    if source is None or source.node.bl_idname != 'ShaderNodeMath' or source.node.operation != 'MAXIMUM': return False
    n = source.node
    if not _scaled_attribute(n.inputs[0], 'ai_fine_coat', .68): return False
    sub = _from(n.inputs[1])
    if sub is None or sub.node.bl_idname != 'ShaderNodeMath' or sub.node.operation != 'MULTIPLY' or not _constant(sub.node.inputs[1], .25): return False
    pair = _from(sub.node.inputs[0])
    return (pair is not None and pair.node.bl_idname == 'ShaderNodeMath' and pair.node.operation == 'MULTIPLY'
            and _attribute(pair.node.inputs[0], 'ak_historical_matrix') and _attribute(pair.node.inputs[1], 'ak_historical_compaction'))


def _reaches(start_node, target_socket):
    seen = set(); todo = [start_node]
    while todo:
        node = todo.pop()
        if node.name in seen: continue
        seen.add(node.name)
        for output in node.outputs:
            for link in output.links:
                if link.to_socket == target_socket: return True
                todo.append(link.to_node)
    return False


def hooks(material):
    require(material.use_nodes and material.node_tree is not None, 'AZ requires a node material')
    nodes = material.node_tree.nodes
    require(not any(n.name.startswith('AZ /') for n in nodes), 'AZ already applied')
    bs = nodes.get('Linked dry dielectric'); geo = nodes.get('World surface geometry')
    require(bs is not None and geo is not None and geo.bl_idname == 'ShaderNodeNewGeometry', 'Expected original ground surface nodes missing')
    colors = []
    for n in nodes:
        if n.bl_idname != 'ShaderNodeMixRGB' or n.blend_type != 'MIX' or n.inputs[2].is_linked: continue
        if np.allclose(tuple(n.inputs[2].default_value), MEAN, rtol=0, atol=1e-6): colors.append(n)
    require(len(colors) == 2, 'Expected exactly two AI fixed-mean fine color endpoints')
    roles = []
    for n in colors:
        role = next((name for name, amount in [('ak_historical_matrix', .40), ('ai_fine_coat', .85)] if _scaled_attribute(n.inputs[0], name, amount)), None)
        require(role is not None and n.inputs[1].is_linked and _reaches(n, bs.inputs['Base Color']), 'Fine color hook is not on expected finite AI mask/output path')
        roles.append(role)
    require(set(roles) == {'ak_historical_matrix', 'ai_fine_coat'}, 'AI color mask roles differ')
    normals = []
    for n in nodes:
        if n.bl_idname != 'ShaderNodeMixRGB' or n.blend_type != 'MIX': continue
        target = _from(n.inputs[2])
        if target == geo.outputs['Normal'] and _ai_attenuation(n.inputs[0]): normals.append(n)
    require(len(normals) == 1 and normals[0].inputs[1].is_linked and _reaches(normals[0], bs.inputs['Normal']), 'Expected exactly one AI broad-normal fine endpoint')
    return colors, normals[0], geo, bs


def _build_nodes(material, color_image, slope_image, geo):
    n, links = material.node_tree.nodes, material.node_tree.links
    def node(kind, label):
        q = n.new(kind); q.name = 'AZ / ' + label; q.label = q.name; return q
    def put(q, key, value):
        links.new(value, q.inputs[key]) if hasattr(value, 'node') else setattr(q.inputs[key], 'default_value', value)
    def math(op, a, b=0.):
        q = node('ShaderNodeMath', op); q.operation = op; put(q, 0, a); put(q, 1, b); return q.outputs[0]
    separate = node('ShaderNodeSeparateXYZ', 'world metric position'); links.new(geo.outputs['Position'], separate.inputs[0])
    uv, signs = [], []
    for axis in ('X', 'Y'):
        q = math('DIVIDE', math('ADD', separate.outputs[axis], .09), .18)
        cell = math('FLOOR', q)
        parity = math('SUBTRACT', cell, math('MULTIPLY', 2., math('FLOOR', math('MULTIPLY', cell, .5))))
        sign = math('SUBTRACT', 1., math('MULTIPLY', 2., parity))
        fraction = math('SUBTRACT', q, cell)
        mirrored = math('ADD', math('MULTIPLY', fraction, sign), parity)
        uv.append(math('DIVIDE', math('ADD', math('MULTIPLY', mirrored, 1100.), .5), 1101.)); signs.append(sign)
    coords = node('ShaderNodeCombineXYZ', 'matched mirrored texel centers'); links.new(uv[0], coords.inputs['X']); links.new(uv[1], coords.inputs['Y'])
    textures = []
    for label, image in [('linear fine color', color_image), ('metric fine XY slopes', slope_image)]:
        q = node('ShaderNodeTexImage', label); q.image = image; q.extension = 'EXTEND'; q.interpolation = 'Linear'; links.new(coords.outputs[0], q.inputs['Vector']); textures.append(q)
    s = node('ShaderNodeSeparateXYZ', 'decoded metric slopes'); links.new(textures[1].outputs['Color'], s.inputs[0])
    fine = node('ShaderNodeCombineXYZ', 'signed fine-only normal slope')
    links.new(math('MULTIPLY', math('MULTIPLY', s.outputs['X'], signs[0]), -1.), fine.inputs['X'])
    links.new(math('MULTIPLY', math('MULTIPLY', s.outputs['Y'], signs[1]), -1.), fine.inputs['Y'])
    broad = node('ShaderNodeSeparateXYZ', 'current broad normal'); links.new(geo.outputs['Normal'], broad.inputs[0])
    denom = math('MAXIMUM', broad.outputs['Z'], .04)
    slope = node('ShaderNodeVectorMath', 'current broad normal slope once'); slope.operation = 'SCALE'; links.new(geo.outputs['Normal'], slope.inputs[0]); links.new(math('DIVIDE', 1., denom), slope.inputs['Scale'])
    combined = node('ShaderNodeVectorMath', 'broad plus fine only'); combined.operation = 'ADD'; links.new(slope.outputs[0], combined.inputs[0]); links.new(fine.outputs[0], combined.inputs[1])
    normal = node('ShaderNodeVectorMath', 'fine-coat endpoint normal'); normal.operation = 'NORMALIZE'; links.new(combined.outputs[0], normal.inputs[0])
    return textures[0].outputs['Color'], normal.outputs[0]


def apply(scene, config, out):
    import bpy
    start = time.monotonic(); out = Path(out)
    require(out.is_dir(), 'Existing output directory required')
    receipt_path = out / 'FINE_COATING_AZ.json'
    require(not receipt_path.exists(), 'Refusing to overwrite AZ receipt')
    ground = scene.objects.get(GROUND)
    require(ground is not None and ground.type == 'MESH' and len(ground.data.materials) >= 1, 'Expected current left shoulder missing')
    require(ground.data.users == 1, 'Shared ground mesh would expand material-slot scope')
    old = ground.data.materials[0]
    require(old is not None and not old.get('az_fine_endpoint'), 'AZ material already applied or missing')
    source_hooks = hooks(old)
    original_stamp = graph_stamp(old)
    color, slopes, data_report = source_arrays(config)
    staged = None; images = []; committed = False
    try:
        staged = old.copy(); staged.name = 'AZ original fine-only coating / copied current ground'
        color_hooks, normal_hook, geo, bs = hooks(staged)
        require(graph_stamp(staged) == original_stamp, 'Material copy differs before endpoint edit')
        names = {n.name for n in staged.node_tree.nodes}
        allowed = {(n.name, n.inputs[2].identifier) for n in color_hooks + [normal_hook]}
        protected_stamp = graph_stamp(staged, names, allowed)
        rough_link = _from(bs.inputs['Roughness'])
        require(rough_link is not None, 'Current finite roughness link missing')
        rough_ref = (rough_link.node.name, rough_link.identifier)
        rgba = np.empty((1101, 1101, 4), dtype='f4'); rgba[..., 3] = 1.
        for label, payload in [('linear color', color), ('metric XY slope', slopes)]:
            image = bpy.data.images.new('AZ / original R5D fines ' + label, width=1101, height=1101, alpha=True, float_buffer=True)
            images.append(image); image.colorspace_settings.name = 'Non-Color'
            rgba[..., :3] = payload; image.pixels.foreach_set(rgba.ravel()); image.update()
        del rgba, color, slopes
        gc.collect()
        fine_color, fine_normal = _build_nodes(staged, images[0], images[1], geo)
        for n in color_hooks: staged.node_tree.links.new(fine_color, n.inputs[2])
        staged.node_tree.links.new(fine_normal, normal_hook.inputs[2])
        require(graph_stamp(staged, names, allowed) == protected_stamp, 'Existing masks, values, or non-hook links changed')
        rough = _from(bs.inputs['Roughness'])
        require((rough.node.name, rough.identifier) == rough_ref, 'Existing roughness path changed')
        require(graph_stamp(old) == original_stamp, 'Protected original material changed')
        staged['az_fine_endpoint'] = True
        ground.data.materials[0] = staged; committed = True
        report = dict(source_material=old.name, scene_material=staged.name, original_material_sha256=original_stamp,
                      original_material_unchanged=graph_stamp(old) == original_stamp,
                      replaced_color_hooks=[n.name for n in color_hooks], replaced_normal_hook=normal_hook.name,
                      preserved_non_hook_graph_sha256=protected_stamp, source=data_report,
                      mapping='Mirrored finite 0.18 m XY patches centered at world origin; inclusive1101 node texel centres; mirror derivatives sign-correct in both axes',
                      generated_images=[dict(name=i.name, shape=list(i.size), float_buffer=i.is_float, colorspace=i.colorspace_settings.name) for i in images],
                      roughness_masks_burial_geometry_prototypes_unchanged=True,
                      normals='Source fine-only metric slope plus current World surface geometry normal slope once. Original composite grit normal is not part of the new endpoint.',
                      temporary_numpy_arrays_released=True, scene_saved=False, rendered=False,
                      limitations=['Mirroring has continuous values but possible derivative cusps/reflected pattern at finite patch joins.',
                                   'Source shader procedural bump variance excluded; native finite-difference source slopes are not exact Blender source interpolated normals.',
                                   'Texture filtering may discard unresolved variance. Moments are recorded, not applied through an invented GGX roughness conversion.',
                                   'Intrinsic recipes preserved; visual improvement and exact optical equivalence unverified.'],
                      elapsed_seconds=time.monotonic() - start)
        with receipt_path.open('x') as stream: json.dump(report, stream, indent=2)
        return report
    except BaseException:
        if committed: ground.data.materials[0] = old
        if staged is not None: bpy.data.materials.remove(staged)
        for image in images:
            if image.users == 0: bpy.data.images.remove(image)
        raise
    finally:
        gc.collect()
