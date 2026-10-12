#!/usr/bin/env python3
"""Optional, scene-only ORIGINAL ASPHALT INTERIOR SPECIMEN. Never renders.

Run with Blender 4.3.2, --background --threads 2 --python-exit-code 1.
Only the road object's mesh/material slot references change. The source scene,
source maps, shared soil material, physical road perimeter, paint, cracks,
shoulder contact, cameras and lighting are untouched. A footprint intersecting
an overlay is rejected: this is deliberately NOT a painted-road correction.
"""
from __future__ import annotations
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '2'
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from relief_math import (TILE_M, HEIGHT_SCALE_M, HEIGHT_SHA256, grid_shape,
                         patch_indices, build_patch, interpolate, sample_height,
                         smoothstep, footprint_weight)

ROAD = 'Crowned asphalt crust / longitudinal rise'
BASE_NORMAL = 'relief_original_broad_normal'
VERSION = 'Original dense asphalt interior relief specimen v1'


def sha256(path):
    result = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def coordinates(mesh):
    co = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    mesh.vertices.foreach_get('co', co.ravel())
    return co


def attributes(mesh):
    """Preserve every supported user point attribute; reject lossy schemas."""
    schema = {'FLOAT': ('value', 1, np.float32, False),
              'FLOAT_VECTOR': ('vector', 3, np.float32, False),
              'FLOAT_COLOR': ('color', 4, np.float32, False),
              'BYTE_COLOR': ('color', 4, np.float32, False),
              'INT': ('value', 1, np.int32, True),
              'BOOLEAN': ('value', 1, bool, True)}
    result = {}
    for a in mesh.attributes:
        if a.name == 'position' or a.name.startswith('.'):
            continue
        if a.domain != 'POINT' or a.data_type not in schema:
            raise ValueError(f'Unsupported attribute {a.name}: {a.domain}/{a.data_type}; refusing loss')
        prop, size, dtype, discrete = schema[a.data_type]
        array = np.empty((len(a.data), size), dtype=dtype)
        a.data.foreach_get(prop, array.ravel())
        result[a.name] = (a.data_type, prop, discrete, array if size > 1 else array[:, 0])
    if BASE_NORMAL in result:
        raise ValueError('This scene already contains the relief specimen; no stacking')
    return result


def verify_source_grid(mesh, co):
    ny, nx = grid_shape(co)
    if len(mesh.polygons) != (ny-1)*(nx-1):
        raise ValueError('Unexpected road face count; script requires the original R6 road grid')
    counts = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get('loop_total', counts)
    if not np.all(counts == 4):
        raise ValueError('Road is not the original all-quad grid')
    loops = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', loops)
    faces = loops.reshape(-1, 4)
    q = (np.arange(ny-1)[:, None]*nx + np.arange(nx-1)[None]).ravel()
    expected = np.column_stack((q, q+1, q+nx+1, q+nx))
    if not np.array_equal(faces, expected):
        raise ValueError('Road connectivity/order changed; refusing guessed remeshing')
    mesh.calc_loop_triangles()
    diagonal = np.empty(len(faces), dtype=bool)
    seen = np.zeros(len(faces), dtype=np.int32)
    for tri in mesh.loop_triangles:
        face_id = tri.polygon_index
        ids = set(tri.vertices)
        diagonal[face_id] = faces[face_id, 0] in ids and faces[face_id, 2] in ids
        seen[face_id] += 1
    if not np.all(seen == 2):
        raise ValueError('Unexpected source tessellation')
    return faces, diagonal.reshape(ny-1, nx-1)


def verify_no_overlays(scene, co, indices):
    """Conservative overlap check. Paint draping is intentionally unsupported."""
    ny, nx = grid_shape(co)
    j0, j1, i0, i1 = indices
    patch = co.reshape(ny, nx, 3)[j0:j1+1, i0:i1+1]
    lo, hi = patch[:, :, :2].min(axis=(0, 1)), patch[:, :, :2].max(axis=(0, 1))
    checked = []
    prefixes = ('Worn marking following road profile',
                'Sparse narrow transverse pavement fissure',
                'Wind and grading dust deposit')
    for obj in scene.objects:
        if obj.type != 'MESH' or not obj.name.startswith(prefixes):
            continue
        points = coordinates(obj.data).astype(np.float64)
        matrix = np.asarray(obj.matrix_world)
        points = points @ matrix[:3, :3].T + matrix[:3, 3]
        other_lo, other_hi = points[:, :2].min(axis=0), points[:, :2].max(axis=0)
        if np.all(other_hi >= lo) and np.all(other_lo <= hi):
            raise ValueError(f'Footprint overlaps {obj.name!r}. Choose an unpainted interior footprint; do not hide or delete the overlay.')
        checked.append(obj.name)
    return lo, hi, checked


def verify_packed_shader(material):
    """Verify actual packed bitmap identity and world-XY phase in the loaded scene."""
    expected = {
        'BaseColor.png': ('34b00d3b699e64aad064c95aac78c9bdbddd18384175e6549bd182c2275314af', 'sRGB'),
        'Roughness.png': ('c97210fce888fe17d062c0e58f3691b10f28b93b41c7738413b14970d55cc90e', 'Non-Color'),
        'Normal_Object_RGB16.png': ('98eddd45b4a84a3a5c4873ad22f25dddd5caeac628e910aa412f9f4e292cb3dc', 'Non-Color'),
    }
    if not material or not material.use_nodes:
        raise ValueError('Original material node tree missing')
    verified = {}
    for filename, (digest, color_space) in expected.items():
        node = material.node_tree.nodes.get('Approved original asphalt / '+filename)
        if not node or node.bl_idname != 'ShaderNodeTexImage' or not node.image:
            raise ValueError('Missing exact original image node: '+filename)
        if (node.extension != 'REPEAT' or node.interpolation != 'Linear'
                or node.projection != 'FLAT' or node.image.colorspace_settings.name != color_space):
            raise ValueError('Original image sampling contract changed: '+filename)
        if not node.image.packed_file or hashlib.sha256(node.image.packed_file.data).hexdigest() != digest:
            raise ValueError('Packed original bitmap identity mismatch: '+filename)
        link = node.inputs['Vector'].links
        if len(link) != 1:
            raise ValueError('Image must have its original world-position input')
        scale = link[0].from_node
        if (scale.bl_idname != 'ShaderNodeVectorMath' or scale.operation != 'SCALE'
                or scale.inputs['Scale'].is_linked or abs(scale.inputs['Scale'].default_value-4) > 1e-9):
            raise ValueError('Original 0.25 m repeat changed')
        coordinate = scale.inputs[0].links
        if (len(coordinate) != 1 or coordinate[0].from_node.bl_idname != 'ShaderNodeNewGeometry'
                or coordinate[0].from_socket.name != 'Position'):
            raise ValueError('Original material is not sampled directly in world XY')
        verified[filename] = digest
    return verified


def patch_material(material):
    """Clone only the road's material and use pre-displacement broad normals.

    The shader's full object normal already carries ALL original relief slope.
    Full-normal + broad-original-normal is correct. Full-normal + displaced
    Geometry.Normal would count the geometry slope twice. No residual texture
    is fabricated. The original shared road/soil material is never edited.
    """
    if not material or not material.use_nodes:
        raise ValueError('Road material must have its original node tree')
    copy = material.copy()
    copy.name = material.name + ' / interior relief normal adapter'
    nodes, links = copy.node_tree.nodes, copy.node_tree.links
    attr = nodes.new('ShaderNodeAttribute')
    attr.name = 'Original broad normal; full asphalt slope already present'
    attr.attribute_name = BASE_NORMAL
    replaced = 0
    for node in list(nodes):
        if node.bl_idname != 'ShaderNodeNewGeometry':
            continue
        for link in list(node.outputs['Normal'].links):
            links.new(attr.outputs['Vector'], link.to_socket)
            replaced += 1
    if not replaced:
        raise ValueError('Expected broad Geometry.Normal links were absent; refusing unknown normal contract')
    copy['relief_normal_contract'] = 'Full original object normal plus captured original broad surface normal, once'
    return copy, replaced


def write_mesh(old, co, attrs, broad_normals, patch, displaced):
    old_faces, _ = verify_source_grid(old, co)
    kept_faces = old_faces[~patch['remove_faces']]
    triangles = patch['triangles']
    allco = np.concatenate((co, displaced)).astype(np.float32)
    # Drop superseded interior vertices, retain every externally used vertex.
    used = np.unique(np.concatenate((kept_faces.ravel(), triangles.ravel())))
    remap = np.full(len(allco), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    qfaces, tfaces = remap[kept_faces], remap[triangles]
    flat = np.concatenate((qfaces.ravel(), tfaces.ravel())).astype(np.int32)
    sizes = np.r_[np.full(len(qfaces), 4, dtype=np.int32), np.full(len(tfaces), 3, dtype=np.int32)]
    starts = np.r_[0, np.cumsum(sizes[:-1])].astype(np.int32)
    new = bpy.data.meshes.new(old.name + ' / bounded original relief')
    new.vertices.add(len(used))
    new.vertices.foreach_set('co', allco[used].ravel())
    new.loops.add(len(flat))
    new.loops.foreach_set('vertex_index', flat)
    new.polygons.add(len(sizes))
    new.polygons.foreach_set('loop_start', starts)
    new.polygons.foreach_set('loop_total', sizes)
    old_smooth = np.empty(len(old.polygons), dtype=bool)
    old.polygons.foreach_get('use_smooth', old_smooth)
    if not np.all(old_smooth):
        raise ValueError('Expected a smoothly shaded original road')
    new.polygons.foreach_set('use_smooth', np.ones(len(sizes), dtype=bool))
    material_ids = np.empty(len(old.polygons), dtype=np.int32)
    old.polygons.foreach_get('material_index', material_ids)
    if not np.all(material_ids == material_ids[0]):
        raise ValueError('Road has multiple face materials; refusing ambiguous patch ownership')
    new.polygons.foreach_set('material_index', np.full(len(sizes), material_ids[0], dtype=np.int32))
    for name, (dtype, prop, discrete, values) in attrs.items():
        v = interpolate(values, patch['ids'], patch['weights'], discrete)
        output = np.concatenate((values, v))[used]
        attr = new.attributes.new(name, dtype, 'POINT')
        attr.data.foreach_set(prop, output.ravel())
    normal = interpolate(broad_normals, patch['ids'], patch['weights'])
    normal = np.concatenate((broad_normals, normal))[used].astype(np.float32)
    attr = new.attributes.new(BASE_NORMAL, 'FLOAT_VECTOR', 'POINT')
    attr.data.foreach_set('vector', normal.ravel())
    new.update()
    if new.validate(verbose=True):
        raise ValueError('Blender repaired the replacement mesh; candidate rejected')
    outer = patch['outer_vertex_ids']
    written = coordinates(new)
    if not np.array_equal(written[remap[outer]], co[outer]):
        raise ValueError('The original patch seam moved')
    # The entire actual road perimeter, including Z, must match bit-for-bit.
    ny, nx = grid_shape(co)
    perimeter = np.unique(np.r_[np.arange(nx), np.arange((ny-1)*nx, ny*nx),
                               np.arange(0, ny*nx, nx), np.arange(nx-1, ny*nx, nx)])
    if not np.array_equal(written[remap[perimeter]], co[perimeter]):
        raise ValueError('Physical road boundary moved')
    if not np.allclose(displaced[patch['inner_vertex_ids']-len(co)],
                       patch['base'][patch['inner_vertex_ids']-len(co)], rtol=0, atol=0):
        raise ValueError('Fine-grid boundary must have exactly zero displacement')
    return new, dict(old_vertices=len(co), new_vertices=len(used),
                     new_dense_vertices=len(displaced), preserved_faces=len(kept_faces),
                     replaced_quads=int(patch['remove_faces'].sum()),
                     new_triangles=len(triangles), preserved_boundary_vertices=len(perimeter),
                     preserved_patch_seam_vertices=len(outer))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--height', type=Path, required=True)
    parser.add_argument('--bounds', type=float, nargs=4, default=(-2.78, -2.28, -0.35, 0.45),
                        metavar=('XMIN', 'XMAX', 'YMIN', 'YMAX'))
    parser.add_argument('--spacing-mm', type=float, default=1000*TILE_M/512)
    parser.add_argument('--max-new-vertices', type=int, default=2000000)
    parser.add_argument('--border-fade-mm', type=float, default=30)
    parser.add_argument('--reference-width', type=int, default=2048)
    parser.add_argument('--footprint-fade-pixels', type=float, nargs=2, default=(0.3, 0.9))
    parser.add_argument('--inspect-only', action='store_true', help='Validate/count and write a JSON plan; no mesh creation/save')
    args = parser.parse_args(argv)
    source, output, height_path = args.source.resolve(), args.output.resolve(), args.height.resolve()
    if source == output or output.exists():
        raise ValueError('Output must be new and distinct from the immutable source')
    if source.suffix != '.blend' or output.suffix != '.blend':
        raise ValueError('Source and output must be .blend files')
    if not source.is_file() or not height_path.is_file():
        raise ValueError('Source scene and original height file must exist')
    if not (0.1 <= args.spacing_mm <= 1000*TILE_M/512 + 1e-9):
        raise ValueError('Spacing must be 0.1–0.48828125 mm; coarser aliasing is not an allowed shortcut')
    if not (1 <= args.max_new_vertices <= 2000000):
        raise ValueError('This bounded specimen caps new vertices at 2,000,000')
    if not (5 <= args.border_fade_mm <= 100 and 128 <= args.reference_width <= 8192):
        raise ValueError('Invalid fade or reference width')
    if not (0 <= args.footprint_fade_pixels[0] < args.footprint_fade_pixels[1]):
        raise ValueError('Invalid projected-footprint thresholds')
    if sha256(height_path) != HEIGHT_SHA256:
        raise ValueError('Height bytes are not the pinned original dense asphalt GeometryHeight.npy')
    input_sha = sha256(source)
    height = np.load(height_path, allow_pickle=False)
    if height.shape != (513, 513):
        raise ValueError('Expected original 513×513 geometry field')
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    if not scene.camera:
        raise ValueError('Source scene needs its existing camera for footprint LOD')
    obj = scene.objects.get(ROAD)
    if not obj or obj.type != 'MESH' or obj.modifiers or obj.data.shape_keys:
        raise ValueError('Expected an unmodified original road mesh')
    if not np.allclose(np.asarray(obj.matrix_world), np.eye(4), rtol=0, atol=1e-9):
        raise ValueError('Road must retain identity world transform for original XY material phase')
    old = obj.data
    co = coordinates(old)
    faces, diagonal = verify_source_grid(old, co)
    attrs = attributes(old)
    if len(old.materials) != 1:
        raise ValueError('Expected one shared source road/soil material')
    packed_hashes = verify_packed_shader(old.materials[0])
    required = {'asphalt_share', 'macro_tint', 'road_edge_inset_m', 'road_deposit_depth_m'}
    if not required.issubset(attrs):
        raise ValueError('Use fixed-contact I or a later scene; missing same-surface deposit attributes')
    indices = patch_indices(co, args.bounds)
    lo, hi, overlays = verify_no_overlays(scene, co, indices)
    patch = build_patch(co, indices, args.spacing_mm/1000, args.max_new_vertices, diagonal)
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    width = args.reference_width
    aspect = (scene.render.resolution_y*scene.render.pixel_aspect_y
              / (scene.render.resolution_x*scene.render.pixel_aspect_x))
    ref_height = int(round(width*aspect))
    camera = scene.camera
    projection = camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),
                                           x=width, y=ref_height,
                                           scale_x=scene.render.pixel_aspect_x,
                                           scale_y=scene.render.pixel_aspect_y)
    vp = np.asarray(projection @ camera.matrix_world.inverted(), dtype=np.float64)
    extent = float(np.ptp(height)) * HEIGHT_SCALE_M
    weights, pixels = footprint_weight(patch['base'], vp, width, ref_height, extent,
                                       args.footprint_fade_pixels)
    weights *= smoothstep(0, args.border_fade_mm/1000, patch['edge_distance'])
    relief = sample_height(height, patch['base'][:, :2]) * weights
    if np.max(weights) <= 0.01:
        raise ValueError('Original relief is subpixel at this camera/width; do not create a pointless dense patch')
    report = dict(version=VERSION, status='INSPECT_ONLY' if args.inspect_only else 'UNRENDERED_SPECIMEN',
                  source_scene=str(source), source_scene_sha256=input_sha,
                  source_height=str(height_path), source_height_sha256=HEIGHT_SHA256,
                  verified_packed_shader_hashes=packed_hashes,
                  source_height_range_m=[float((height.min()-.5)*HEIGHT_SCALE_M), float((height.max()-.5)*HEIGHT_SCALE_M)],
                  requested_bounds_xy=args.bounds, resolved_bounds_xy=[float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1])],
                  source_grid_indices=list(indices), dense_grid_shape=list(patch['fine_shape']),
                  new_dense_vertices=len(patch['base']), tile_m=TILE_M,
                  height_scale_m=HEIGHT_SCALE_M, geometry_spacing_mm=args.spacing_mm,
                  height_phase='g[::-1]; fract(world XY / 0.25) * 512; no half-texel translation',
                  attribute_names=list(attrs), overlay_objects_checked=len(overlays),
                  reference_resolution=[width, ref_height], camera=camera.name,
                  footprint_peak_to_valley_pixels=[float(pixels.min()), float(pixels.max())],
                  displacement_weight_range=[float(weights.min()), float(weights.max())],
                  displacement_delta_m=[float(relief.min()), float(relief.max())],
                  shared_ground_material_edited=False, approved_assets_edited=False,
                  paint_modified=False, road_boundary_modified=False, render_run=False, threads=2,
                  limits=['Unpainted interior specimen only; not a full road correction',
                          'Camera-specific footprint fade; re-evaluate for other views',
                          'Requires actual visual/contact and resource validation before promotion'])
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output.with_suffix('.plan.json' if args.inspect_only else '.receipt.json')
    if receipt_path.exists():
        raise ValueError('Receipt path already exists; use a fresh output name')
    if args.inspect_only:
        receipt_path.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
        return
    broad = np.empty((len(co), 3), dtype=np.float32)
    old.vertices.foreach_get('normal', broad.ravel())
    displaced = patch['base'].copy()
    displaced[:, 2] += relief
    replacement, counts = write_mesh(old, co, attrs, broad, patch, displaced)
    copies = [patch_material(material) for material in old.materials]
    for material, _ in copies:
        replacement.materials.append(material)
    obj.data = replacement
    obj['relief_specimen'] = VERSION
    obj['relief_source_height_sha256'] = HEIGHT_SHA256
    scene['optional_asphalt_relief'] = VERSION + '; not visually validated'
    # Set no render flag/output/camera/light/material parameters beyond the
    # local normal adapter. The only persistent output is a new candidate file.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)
    if sha256(source) != input_sha or sha256(height_path) != HEIGHT_SHA256:
        raise ValueError('Immutable inputs changed unexpectedly')
    report.update(counts)
    report.update(output_scene=str(output), output_scene_sha256=sha256(output),
                  normal_links_replaced=sum(n for _, n in copies),
                  normal_contract='Original full material normal + captured original broad normal; no displaced Geometry.Normal term')
    receipt_path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
