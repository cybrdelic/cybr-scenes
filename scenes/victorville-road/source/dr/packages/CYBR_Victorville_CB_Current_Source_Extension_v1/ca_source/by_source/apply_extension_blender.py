"""Guarded material/daylight extension for a regenerated AV scene.
No scene load, save or render. Fresh combined replay remains UNVERIFIED.
Original AV mountain and all other geometry are retained.
"""
from pathlib import Path
import argparse
import array
import hashlib
import importlib.util
import json
import os
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from verify_extension import BASE_PIPELINE, digest, require, verify

EXPECTED_GRAPH = '680632118ab313783ef981d4e20299a987e5601d9d75c094925a3b19bfd497da'
EXPECTED_PROTECTED_GRAPH = '67436269d7b8d6a9d7f796927eaa189b84ada4cef6ed22ef26beb67c22ffe92b'
SNAPSHOT = ROOT / 'src'


def import_exact(name, path):
    """Reject a preloaded module from elsewhere instead of silently substituting."""
    if name in sys.modules:
        module = sys.modules[name]
        require(Path(module.__file__).resolve() == Path(path).resolve(), 'Conflicting imported module: ' + name)
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def geometry_stamp(scene):
    """Bounded per-mesh buffers; hashes actual coordinates/topology/corner normals.

    This adds a preservation check, not a substitute for inherited AV admission.
    It does not claim independent proof of every arbitrary custom attribute.
    """
    import bpy
    objects = [(o.name, o.type, o.data.name if o.data else None, list(map(list, o.matrix_world)), o.hide_render)
               for o in sorted(scene.objects, key=lambda o: o.name)]
    h = hashlib.sha256(json.dumps(objects, sort_keys=True).encode())
    for me in sorted(bpy.data.meshes, key=lambda m: m.name):
        h.update(me.name.encode())
        for coll, field, code, width in (
                (me.vertices, 'co', 'f', 3), (me.edges, 'vertices', 'i', 2),
                (me.loops, 'vertex_index', 'i', 1), (me.loops, 'edge_index', 'i', 1),
                (me.polygons, 'loop_start', 'i', 1), (me.polygons, 'loop_total', 'i', 1),
                (me.polygons, 'material_index', 'i', 1), (me.corner_normals, 'vector', 'f', 3)):
            require(len(coll) * width * array.array(code).itemsize <= 128 * 1024**2, 'Single geometry guard buffer exceeds 128 MiB')
            values = array.array(code, [0]) * (len(coll) * width)
            coll.foreach_get(field, values)
            h.update(str((field, len(coll), width)).encode())
            h.update(memoryview(values).cast('B'))
            del values
    return h.hexdigest()


def run(base_archive, z_admission, output_dir, variant='candidate', with_aw=False, scene_receipt=None):
    """Apply to bpy.context.scene. Keeps result in the caller-owned session only."""
    import bpy
    require(variant in ('baseline', 'candidate'), 'Use baseline or candidate')
    require(with_aw is False, 'BY retains the original AV landforms; AW is not part of this extension')
    require(not os.environ.get('MATERIAL_PATH_MAP_FILE'), 'Unset MATERIAL_PATH_MAP_FILE')
    require(tuple(bpy.app.version[:2]) == (4, 3), 'Captured material graph requires Blender 4.3.x; original was 4.3.2')
    proof = verify(base_archive)
    scene_path = Path(bpy.data.filepath).resolve()
    require(bpy.data.filepath and scene_path.is_file(), 'Open the regenerated AV assembled scene first')
    require(not bpy.data.is_dirty, 'Reopen the fresh, unedited AV assembled scene before applying')
    receipt_path = Path(scene_receipt).resolve() if scene_receipt else scene_path.with_suffix('.blend.json')
    meta = json.loads(receipt_path.read_text())
    require(digest(scene_path) == meta['sha256'] and scene_path.stat().st_size == meta['bytes'], 'Loaded AV scene bytes mismatch')
    require(meta.get('saved_before_preview_reductions') is True and meta.get('immutable_source_verified') is True,
            'Require AV default pre-preview assembled output and its original receipt')
    require(meta['pipeline']['sha256'] == BASE_PIPELINE, 'Wrong AV assembly source pipeline')
    import zipfile
    with zipfile.ZipFile(base_archive) as z:
        template = json.loads(z.read('road_scene_r6/receipts/integrated_render_templates_av.json'))
    row = next(r for r in template['captures'] if r.get('generation') == 'AV' and r.get('default_latest'))
    require(meta['pipeline']['files'] == row['captured_pipeline_files_sha256'], 'AV source closure differs')
    require(meta['assembly_job']['refresh_view_grains_au'] == row['settings']['refresh_view_grains_au'],
            'Original finite grain allocation differs; refuse automatic densification')
    admission_path = Path(z_admission).resolve()
    admission = json.loads(admission_path.read_text())
    resources = json.loads(admission_path.with_name('source_admission_resources.json').read_text())
    require(admission.get('semantic_match') is True and admission.get('scene_written') is False,
            'Retained strict Z semantic admission did not pass')
    require(admission['actual_source_sha256'] == meta['source_sha256'], 'Z admission does not belong to this AV build')
    require(resources.get('resource_contract_passed') is True and resources.get('exit_code') == 0,
            'Strict Z admission resource contract failed')
    require(not bpy.context.scene.get('az_extension_wrapper_applied'), 'Extension already applied in this session')
    # Exact sibling bank; AW dependencies are imported only when explicitly selected.
    if str(SNAPSHOT) not in sys.path:
        sys.path.insert(0, str(SNAPSHOT))
    for file in SNAPSHOT.glob('*.py'):
        if file.stem in sys.modules:
            module_path = getattr(sys.modules[file.stem], '__file__', None)
            require(module_path and Path(module_path).resolve() == file.resolve(), 'Conflicting snapshot module: ' + file.stem)
    az = import_exact('fine_coating_az', SNAPSHOT / 'fine_coating_az.py')
    scene = bpy.context.scene
    ground = scene.objects.get(az.GROUND)
    require(ground and ground.type == 'MESH' and ground.data.materials, 'Regenerated AV shoulder missing')
    az.hooks(ground.data.materials[0])  # preserve all original semantic endpoint hooks
    require(az.graph_stamp(ground.data.materials[0]) == EXPECTED_GRAPH, 'Original AV material graph differs; do not bypass')
    out = Path(output_dir).resolve()
    require(not out.exists(), 'Fresh output directory required')
    out.mkdir(parents=True, exist_ok=False)
    aw_report = None
    if with_aw:
        aw = import_exact('apply_legacy_profile_aw', SNAPSHOT / 'apply_legacy_profile_aw.py')
        fields = ROOT / 'inputs/AH_FIELDS.npz'
        aw_report = aw.apply(scene, {'fields_path': str(fields), 'fields_sha256':
            'cb13eb9f9422741f113d244f249e6b70cece71596934df63643a59412483dac3'}, out)
        require(az.graph_stamp(ground.data.materials[0]) == EXPECTED_GRAPH, 'AW unexpectedly changed material graph')
    before = geometry_stamp(scene)
    az_report = None
    if variant in ('baseline', 'candidate'):
        az_report = az.apply(scene, {'helper_path': str(SNAPSHOT / 'fine_response.py'),
            'microbed_path': str(ROOT / 'inputs/microbed.npz'),
            'builder_path': str(ROOT / 'inputs/build_diagnostic.py')}, out)
        require(az_report['preserved_non_hook_graph_sha256'] == EXPECTED_PROTECTED_GRAPH,
                'Non-hook original graph differs; do not accept this result')
    bw = import_exact('historical_fine_area_bw', SNAPSHOT / 'historical_fine_area_bw.py')
    bw_report = bw.apply(scene, {'revision': 1}, out)
    import_exact('road_wear_field_by', SNAPSHOT / 'road_wear_field_by.py')
    wear_report = None
    if variant == 'candidate':
        wear = import_exact('road_surface_wear_by', SNAPSHOT / 'road_surface_wear_by.py')
        wear_report = wear.apply(scene, {'revision': 1}, out)
    daylight = import_exact('align_context_daylight_bt', SNAPSHOT / 'align_context_daylight_bt.py')
    # Daylight only changes the sky direction, not light energy/exposure.
    daylight_report = daylight.apply(scene, {'mode': 'align_sky_to_existing_sun'}, out)
    require(geometry_stamp(scene) == before, 'Material-only extension changed mesh geometry or object transforms')
    require(digest(scene_path) == meta['sha256'], 'Input scene file changed')
    scene['az_extension_wrapper_applied'] = True
    report = dict(**proof, input_scene_sha256=meta['sha256'],
        av_scene_receipt_sha256=digest(receipt_path), z_admission_sha256=digest(admission_path),
        variant=variant, AW_explicitly_applied=with_aw, AZ_applied=True, BW_applied=True, BY_applied=variant == 'candidate', original_AV_mountains_retained=True,
        AZ_geometry_preservation_sha256=before, original_material_graph_sha256=EXPECTED_GRAPH,
        scene_saved=False, rendered=False, preview_LOD_applied=False, grain_allocation_modified=False,
        scope='In-memory current material/daylight extension. Original AV geometry, including mountains, retained. Source scene file untouched.',
        limitations=['Fresh clean-directory AV regeneration and combined extension replay remain unverified.',
                    'Historical crop pipeline includes preview reductions absent from this apply-only operation.',
                    'This is not automatic full-scene semantic admission or a native/8K density proof.'])
    with (out / 'EXTENSION_APPLICATION.json').open('x') as stream:
        json.dump(report, stream, indent=2)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-archive', required=True)
    p.add_argument('--z-admission', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--scene-receipt')
    p.add_argument('--variant', choices=['baseline', 'candidate'], default='candidate')
    p.add_argument('--with-aw', action='store_true')
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    print(json.dumps(run(**vars(args)), indent=2))
