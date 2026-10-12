#!/usr/bin/env python3
"""Append portable road-component sources to immutable Z v9 without extraction.
No Blender, numerical model, scene writes, renders or uploads. Final context
selection must identify a successful capture explicitly reviewed by the parent.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile
from render_checkpoint_ah import REGENERATED_REPORTS

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'deliverables/CYBR_Victorville_R6_Z_Portable_Procedural_Road_Source.zip'
BASE_SHA = '4ed9c2e524cd44f5e847e2ac08c4a70d6171ff2cde05c3edb75c7678e91437dc'
OUT = ROOT / 'deliverables/CYBR_Victorville_R6_AH_Portable_Road_Components_Source_v2.zip'
SOURCE_SHA = '29a2e1ca28867182554594981482e704ccbc97d9fb2806b48bc0c06f8375231a'
MICROBED = 'discrete_grains_r5/prototypes/microbed.npz'
MICROBED_SHA = '7a09007d50e444c28231fd30cddda185d2f01146f3b1a47b014ebd25c0b415c4'
HEIGHT = 'discrete_grains_r5/asphalt/native4096/GeometryHeight.npy'
HEIGHT_SHA = '9c6ebba3a109088842a73434cea02069aa3a5a98e1b871a3f7b7b5e246de0c83'
PIPELINE_CORE = {'preview_mesh_cull.py','render.py','oidn_image_bridge.py','clean_receipt.py',
    'clean_render.sh','render.sh','png_precision_check.py','oidn_contract.py',
    'verify_pipeline_snapshot.py','capture_modes.py','raw_receipt.py','transport_components.py',
    'component_image_bridge.py','component_receipt.py'}
NEW_SOURCES = ('pavement_contact_ac.py','metric_edge_strip_aa.py','edge_ravel_field_aa.py',
    'assemble_raveled_edge_aa.py','assemble_pavement_contact_ac.py','flow_transport_ae.py',
    'context_mesh_refine_ab.py','visible_shoulder_flow_ad.py','assemble_visible_shoulder_ad.py',
    'context_field_cache_ad.py','shoulder_context_flow_ab.py','assemble_shoulder_context_ab.py',
    'context_field_cache_ab.py','graded_shoulder_foundation_af.py','assemble_graded_shoulder_af.py',
    'graded_shoulder_foundation_ah.py','assemble_graded_shoulder_ah.py','terrain_normal_transfer_ah.py',
    'render_checkpoint_ah.py','validate_checkpoint_source_ah.py','package_integrated_checkpoint_ah.py',
    'capture_z_semantic_checkpoint_ah.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def public(value):
    if isinstance(value, str):
        if value.startswith('/') and '\n' not in value:
            path = Path(value).resolve()
            generated = ROOT.parents[1] / 'materials-cloud-20261009/work/normal_fix/native4096'
            if path.is_relative_to(generated):
                return 'discrete_grains_r5/asphalt/native4096/' + str(path.relative_to(generated))
            if path.is_relative_to(ROOT.parent):
                return str(path.relative_to(ROOT.parent))
            # A historical executable path is metadata, never a replay input.
            raise ValueError('Unmapped private path in new provenance: ' + value)
        return value
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, dict):
        return {public(k): public(v) for k,v in value.items()}
    return value


def encoded(value):
    return (json.dumps(public(value), indent=2, sort_keys=True) + '\n').encode()


def verify_base():
    require(BASE.stat().st_size == 8377260 and sha(BASE) == BASE_SHA, 'Preserve immutable v9 ZIP')
    with zipfile.ZipFile(BASE) as z:
        require(z.testzip() is None, 'v9 ZIP corruption')
        lock = json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist()) == len(set(z.namelist())) and set(z.namelist()) == set(lock['files']) | {'SOURCE_LOCK.json'}, 'v9 dependency closure differs')
        for name, expected in lock['files'].items():
            require(digest(z.read(name)) == expected, 'v9 source lock differs: ' + name)
        approved = z.read(MICROBED)
        require(len(approved) == 3913561 and digest(approved) == MICROBED_SHA, 'Approved microbed differs')
    return lock


def closure():
    todo = list(NEW_SOURCES)
    result = {}
    while todo:
        name = todo.pop()
        if name in result:
            continue
        path = ROOT / 'src' / name
        require(path.is_file() and not path.is_symlink(), 'Missing component source: ' + name)
        data = path.read_bytes()
        tree = ast.parse(data, filename=name)
        result[name] = data
        for node in ast.walk(tree):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            for module in mods:
                candidate = module.split('.')[0] + '.py'
                if (ROOT / 'src' / candidate).is_file() and candidate not in result:
                    todo.append(candidate)
    return result


def capture(name, role):
    require(Path(name).name == name, 'Capture tag must be a simple name')
    folder = ROOT / 'captures' / name
    job = read(folder / 'job.json')
    raw = read(folder / 'INTERNAL_PANEL.png.json')
    clean = read(folder / 'CLEAN_OIDN_PANEL.png.json')
    memory = read(folder / 'PRE_RENDER_MEMORY_ADAPTATIONS.json')
    resources = read(folder / 'resource_receipt.json')
    require(job == raw['job'] == clean['job'], 'Capture job mismatch: ' + name)
    require(job['source_sha256'] == raw['source_sha256'] == clean['source_sha256'] == SOURCE_SHA,
            'Captured Z source mismatch: ' + name)
    require(raw['pipeline'] == clean['pipeline'] == memory['pipeline'], 'Captured snapshot mismatch: ' + name)
    require(resources.get('resource_contract_passed') is True and resources.get('exit_code') == 0,
            'Capture resource contract failed: ' + name)
    cap = 4480 if role == 'context' else 4096
    require(resources['RSS_cap_MiB'] == job['rss_cap_mib'] == cap and
            max(resources['peak_process_tree_RSS_MiB'], resources['kernel_max_child_RSS_MiB']) <= cap,
            'Capture resource bounds changed: ' + name)
    require(job['engine'] == 'CYCLES' and job['capture_mode'] == 'guided' and job['save_guides'] is True,
            'Guided Cycles capture required')
    require(job['width'] <= 1200 and job['height'] <= 900 and raw['resolution'] == clean['resolution'] == [job['width'],job['height']], 'Only bounded previews supported')
    require(clean.get('raw_guides_retained') is True and clean['oidn_guide_contract']['valid'] is True,
            'Missing OIDN guide contract')
    checked_files = {}
    for path, expected in clean['files_sha256'].items():
        require(sha(path) == expected, 'Capture pixels/guides differ: ' + Path(path).name)
        checked_files[public(path)] = expected
    image = folder / 'CLEAN_OIDN_PANEL.png'
    image_sha = sha(image)
    require(clean['files_sha256'][str(image)] == image_sha, 'Clean image does not match receipt')
    pipeline = raw['pipeline']
    require(digest(json.dumps(pipeline['files'],sort_keys=True).encode()) == pipeline['sha256'], 'Snapshot manifest digest differs')
    snapshot = Path(pipeline['snapshot'])
    require(snapshot.resolve().is_relative_to((ROOT / 'pipeline/pipeline_snapshots').resolve()), 'Snapshot outside source folder')
    files = {}
    for filename, expected in pipeline['files'].items():
        data = (snapshot / filename).read_bytes()
        require(digest(data) == expected, 'Snapshot source differs: ' + filename)
        files[filename] = data
    require(PIPELINE_CORE <= set(files), 'Captured pipeline core incomplete')
    for filename in ('bounded_clean_run.py','resource_contract.py'):
        files[filename] = (ROOT / 'pipeline' / filename).read_bytes()
    settings = {k:v for k,v in job.items() if k not in ('source','source_sha256','output')}
    relocations = []
    for key in ('pavement_contact_ac','edge_ravel_aa'):
        if key in settings:
            original = settings[key]['height_path']
            require(sha(original) == HEIGHT_SHA, 'Captured native height differs')
            settings[key] = dict(settings[key],height_path=HEIGHT)
            relocations.append(dict(job_key_path=[key,'height_path'],package_path=HEIGHT,sha256=HEIGHT_SHA))
    for component in ('graded_shoulder_ah','visible_shoulder_ad','graded_shoulder_af'):
        require(not settings.get(component,{}).get('cache_path'), 'Do not silently omit required numerical cache')
    template = dict(name=name,role=role,settings=settings,pipeline_sha256=pipeline['sha256'],
        captured_pipeline_files_sha256=pipeline['files'],
        pipeline_files_sha256={k:digest(v) for k,v in files.items()},
        component_helper_names=sorted(set(pipeline['files'])-PIPELINE_CORE),input_relocations=relocations)
    reports = dict(job=job,raw_report=raw,clean_report=clean,memory_adaptations=memory,resources=resources)
    for path in folder.glob('*.json'):
        if path.name not in {'job.json','INTERNAL_PANEL.png.json','CLEAN_OIDN_PANEL.png.json','PRE_RENDER_MEMORY_ADAPTATIONS.json','resource_receipt.json'}:
            reports[path.stem.lower()] = read(path)
    evidence = dict(name=name,role=role,clean_image_sha256=image_sha,source_sha256=SOURCE_SHA,
        original_raw_receipt_sha256=sha(folder/'INTERNAL_PANEL.png.json'),
        original_clean_receipt_sha256=sha(folder/'CLEAN_OIDN_PANEL.png.json'),
        original_job_sha256=sha(folder/'job.json'),historical_files_verified=checked_files,
        pipeline_sha256=pipeline['sha256'],resource_contract_passed=True)
    return template,files,reports,evidence


def admission():
    manifest = ROOT / 'receipts/z_semantic_source_guard_ah.json'
    proof_path = ROOT / 'receipts/z_semantic_admission_proof_ah.json'
    guard,proof = read(manifest),read(proof_path)
    require(guard['source_sha256'] == proof['source_sha256'] == SOURCE_SHA, 'Z semantic guard source differs')
    require(digest(json.dumps(guard['snapshot'],sort_keys=True,separators=(',',':')).encode()) == guard['semantic_sha256'] == proof['semantic_sha256'], 'Z semantic snapshot digest differs')
    require(proof['manifest_sha256'] == sha(manifest) and proof['passed'] is True and
            proof['unchanged_source_admitted'] is True and proof['geometry_mutation_rejected'] is True and
            proof['material_mutation_rejected'] is True and proof['scene_saved'] is False and proof['rendered'] is False,
            'Required positive/negative Z admission controls incomplete')
    files = {'road_scene_r6/receipts/z_semantic_source_guard_ah.json':manifest.read_bytes()}
    for filename,key in (('semantic_scene_guard_z.py','helper_sha256'),('prepare_physical_lenses.py','base_helper_sha256')):
        data = (ROOT / 'src' / filename).read_bytes()
        require(digest(data) == guard[key] == proof[key], 'Z semantic admission helper differs')
        files['road_scene_r6/src/' + filename] = data
    contract = dict(manifest_path='road_scene_r6/receipts/z_semantic_source_guard_ah.json',
        helper_path='road_scene_r6/src/semantic_scene_guard_z.py',historical_source_sha256=SOURCE_SHA,
        files_sha256={k:digest(v) for k,v in files.items()})
    return contract,files,proof


def readme(templates):
    captures = '\n'.join('- '+r['role']+': '+r['name']+', '+str(r['settings']['width'])+' x '+str(r['settings']['height'])+', '+str(r['settings']['samples'])+' samples.' for r in templates)
    return '''VICTORVILLE R6: PORTABLE ROAD COMPONENT SOURCE CHECKPOINT

STATUS AND SCOPE
This complete source-only extension retains the entire Z portable v9 archive,
including all earlier Y/Z sources, material producers, exact approved inputs,
and historical evidence. It adds the useful AC_D supported broken-pavement edge,
its same-camera Z baseline, and any explicitly selected AH wider-bank preview.
This is progress work, not an accepted finished whole scene. AF is retained as
historical experimental code only and is not promoted as a successful design.
A complete fresh clean-directory end-to-end rebuild remains UNVERIFIED.
No new render, Blender build or numerical solve was performed for packaging.

WHAT THE COMPONENTS DO
AC reconstructs a locally supported pavement section, raveled metric crown,
intermittent exposed course and anchored subsurface aggregate against real ground
triangles. It retains the original surface recipe and metric grading; local soil
geometry and existing particle/root placements change. Course thickness and
weathering sectors are authored interpretations, not surveyed Victorville data.
AH authors a coherent wider graded bank and shallow connected wash, then applies
restrained finite-stock AE transport to its actual triangle surface. Authored
construction volume is accounted separately from conservative sediment mass.
AE fixes downhill donor/scour limiting; residual grid bias and resolution effects
remain. These components are visual models, not validated hydraulics. Existing
particles are repositioned; deposited-class population reallocation is incomplete.
Read the actual component reports and inherited material/LOD limits.

PORTABLE REGENERATION
Use a fresh extraction. Requirements: Blender 4.3.2 with its Python/NumPy, Python 3
with NumPy, SciPy and Pillow, and official OIDN 2.5.1. Set OIDN_BIN to its
existing executable before any preview. Linux bash and ps are used by the bounded
capture scripts. There are no bundled .blend files, generated native maps, raw
render caches or historical pixels. The source chain produces the required maps.

1. Verify every packaged source/input without building:
   python road_scene_r6/src/render_checkpoint_ah.py --check-sources
2. Rebuild the complete inherited chain through Z:
   bash regenerate.sh build-only
3. Run the selected bounded component previews:
   bash regenerate.sh render-only
   Or select only the matched detail pair, using distinct fresh run names:
   python road_scene_r6/src/render_checkpoint_ah.py --role baseline --tag baseline_repeat
   python road_scene_r6/src/render_checkpoint_ah.py --role edge --tag edge_repeat
4. Run build plus previews in one invocation:
   bash regenerate.sh preview

The top-level wrapper delegates the inherited build to regenerate_z_v9.sh and
then uses the new component replay. It never overwrites an existing render run.
A new successful render needs separate pixel review. No native/4K render is added.
Full rebuild portability is not established by these command recipes.

EXACT SOURCE RESOLUTION
Each receipt-selected captured snapshot stays byte-for-byte unchanged in
road_scene_r6/checkpoint_pipeline_sources/<digest>. Its manifest is recomputed
from real hashes. At replay time, render_checkpoint_ah.py verifies SOURCE_LOCK,
copies that snapshot into a fresh run/runtime/pipeline directory and copies the
same captured component helpers to its sibling run/runtime/src. This satisfies
the captured render.py parent.parent/src lookup without patching that source,
altering its claimed hash, or falling back to changing live helper versions.
The captured pipeline digest must match the digest of the newly rendered receipt.
A separate manifest lists the supporting bounded watchdog sources too.

Seven inherited builders reuse historical output-report filenames. Those original
reports are additionally preserved under historical_receipts_ah at their exact
archive hashes. Source verification checks these immutable copies for those seven
explicitly enumerated outputs, allowing a build to write fresh reports in place.
Every production source, approved input, semantic guard and replay template is
still checked at its actual runtime path. No generated report is accepted as a
substitute source-admission contract. The original seven entries also remain in
the ZIP, so no prior archive dependency has been moved or removed.

GENERATED INPUT AND SOURCE ADMISSION
The required native GeometryHeight.npy is generated by the inherited material
producer and must match SHA256 ''' + HEIGHT_SHA + '''.
The exact approved microbed is 3,913,561 bytes, SHA256:
''' + MICROBED_SHA + '''
Every archive retains those approved bytes. Never regenerate a substitute cache.

A rebuilt Z is admitted only after strict equality with the pinned semantic Z
snapshot. The new validation-only wrapper loads the real scene, verifies the
manifest and helper hashes, then checks the complete recorded semantic schema.
It records the actual source-file SHA256 and never substitutes the historical
serialized hash. Replayed jobs use that actual admitted hash. An arbitrary scene
cannot be accepted just by computing its hash. Unsupported or changed state fails
closed. Geometry/material negative controls were tested on original Z. Alternate
serialized-byte admission and full fresh regeneration remain independently
UNVERIFIED. Renderer/version differences may legitimately fail the strict guard;
do not edit the guard or bypass an actual mismatch.

SELECTED HISTORICAL CAPTURES
''' + captures + '''

The baseline and AC_D edge use the same camera, source and preview settings except
for the explicit pavement_contact_ac assembly. Selected provenance retains the
original raw/clean receipt SHA256 values while removing machine-specific paths
from readable receipt copies. Packaged receipt-copy hashes are in SOURCE_LOCK;
those are distinct from the original receipt hashes. Historical pixel and guide
hashes are evidence only; the binary images are not bundled in this source ZIP.
Preview adaptations include asphalt-only 1024 maps, stride-2 native grid LOD,
compact BVH and conservative off-screen culling. They are not native-detail or
indirect-lighting-equivalence proof. Material sources remain unchanged.

AH RESOURCE HISTORY
The first AH attempt failed corner-normal validation before rendering. AH_B and
AH_C were correctly stopped by the original 4096 MiB owned-process RSS guard
before first sample. AH_C's allocator-page release did not free pages or solve
that resource limit. The selected AH_D uses the explicitly approved 4480 MiB
cap, and passed at a 4245.18 MiB sampled peak in 140.86 seconds. Its allocator
trim also reported no pages released. Geometry, images, shaders and sample
settings were not changed by that allocator call. The source-only provenance
retains these stopped attempts as diagnostic records; they are not render passes.
AC_D and its baseline retain their 4096 MiB caps. Strict source admission has a
separate 4096 MiB / two-thread cap. Replay does not silently raise any limit.

ARCHIVE PRESERVATION
README_Z_V9_CHECKPOINT.txt, SOURCE_LOCK_Z_V9_CHECKPOINT.json and
regenerate_z_v9.sh preserve the v9 top-level files. Every other v9 entry remains
byte-identical under its original name. SOURCE_LOCK.json binds the new archive.
The original external v9 ZIP remains untouched. Earlier READMEs and replay scripts
are historical and retain their prior caveats; the new replay is the supported
component entrypoint. All prior production-source dependencies remain included.
'''


def prepare(context_capture=None,review_path=None):
    lock = verify_base()
    templates=[]; additions={}; evidence=[]
    def add(name,data):
        if isinstance(data,str):data=data.encode()
        if name in additions:require(additions[name]==data,'Conflicting new entry: '+name)
        additions[name]=data
    for name,data in closure().items():
        add('road_scene_r6/src/'+name,data)
    selected=[('ac_z_matched_baseline_preview','baseline'),('ac_d_supported_edge_preview','edge')]
    if context_capture:
        require(review_path is not None,'Context selection requires a visual review receipt')
        review=read(review_path)
        require(review.get('inspected') is True and review.get('whole_scene_user_approved') is False,
                'Visual review status must explicitly be inspected progress')
        require(review.get('passed_cap_MiB') == 4480, 'Reviewed context cap differs')
        selected.append((context_capture,'context'))
        add('road_scene_r6/receipts/integrated_visual_review_ah.json',encoded(review))
    for name,role in selected:
        template,files,reports,proof=capture(name,role)
        if role=='context':
            require(review['capture_name']==name and review['image_sha256']==proof['clean_image_sha256'],
                    'Reviewed context pixels differ')
        templates.append(template);evidence.append(proof)
        for filename,data in files.items():
            add('road_scene_r6/checkpoint_pipeline_sources/'+template['pipeline_sha256']+'/'+filename,data)
        for suffix,value in reports.items():
            add('road_scene_r6/receipts/'+name+'_'+suffix+'.json',encoded(value))
    if context_capture:
        diagnostics=[]
        for name in ('ah_integrated_bank_context_preview','ah_b_integrated_bank_context_preview',
                     'ah_c_integrated_bank_context_preview'):
            folder=ROOT/'captures'/name
            resources=read(folder/'resource_receipt.json')
            require(resources.get('resource_contract_passed') is False,
                    'Historical failed attempt unexpectedly passed')
            diagnostics.append(dict(name=name,diagnostic_only=True,selected_for_replay=False,
                resources=resources,job=read(folder/'job.json'),
                original_resource_receipt_sha256=sha(folder/'resource_receipt.json')))
        add('road_scene_r6/receipts/integrated_failed_attempts_ah.json',encoded(diagnostics))
    a,b=templates[:2]
    require({k:v for k,v in b['settings'].items() if k!='pavement_contact_ac'}==a['settings'],
            'Selected edge and baseline are not matched')
    contract,guard_files,proof=admission()
    for name,data in guard_files.items():add(name,data)
    add('road_scene_r6/receipts/z_semantic_admission_proof_ah.json',encoded(proof))
    for name in ('ac_contact_tests.json','ae_transport_api.json','ae_transport_tests.json'):
        add('road_scene_r6/receipts/'+name,encoded(read(ROOT/'receipts'/name)))
    resources=read(ROOT/'receipts/z_semantic_capture_ah_resource.json')
    require(resources.get('resource_contract_passed') is True and resources.get('exit_code')==0
            and resources['RSS_cap_MiB']==4096 and resources['CPU_threads']==2,
            'Z semantic capture resource controls failed')
    add('road_scene_r6/receipts/z_semantic_capture_ah_resource.json',encoded(resources))
    # Parent may produce a separately bounded semantic control receipt.
    for path in sorted((ROOT/'receipts').glob('z_semantic*ah*resources*.json')):
        r=read(path);require(r.get('resource_contract_passed') is True,'Semantic resource validation failed')
        add('road_scene_r6/receipts/'+path.name,encoded(r))
    add('road_scene_r6/receipts/integrated_render_templates_ah.json',encoded(dict(schema_version=1,
        source_admission=contract,captures=templates)))
    with zipfile.ZipFile(BASE) as base:
        add('README_Z_V9_CHECKPOINT.txt',base.read('README.txt'))
        add('SOURCE_LOCK_Z_V9_CHECKPOINT.json',base.read('SOURCE_LOCK.json'))
        add('regenerate_z_v9.sh',base.read('regenerate.sh'))
        for relative in sorted(REGENERATED_REPORTS):
            require(relative in lock['files'], 'Unknown regenerated-report overlap')
            add('historical_receipts_ah/'+relative,base.read(relative))
        for name,data in list(additions.items()):
            if name in lock['files']:
                require(base.read(name)==data,'Do not overwrite prior source dependency: '+name)
    add('README.txt',readme(templates))
    add('regenerate.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-preview}" in preview|build-only|render-only) ;; *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;; esac
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then echo "Unset MATERIAL_PATH_MAP_FILE." >&2; exit 2; fi
python road_scene_r6/src/render_checkpoint_ah.py --check-sources
if [ "${1:-preview}" != build-only ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to official OIDN 2.5.1 oidnDenoise}"
  test -f "$OIDN_BIN" && test -x "$OIDN_BIN"
fi
if [ "${1:-preview}" != render-only ]; then bash regenerate_z_v9.sh build-only; fi
if [ "${1:-preview}" != build-only ]; then python road_scene_r6/src/render_checkpoint_ah.py; fi
''')
    add('INTEGRATED_COMPONENT_EVIDENCE_AH.json',encoded(dict(base_v9_archive_sha256=BASE_SHA,
        all_prior_source_dependencies_retained=True,approved_microbed_bytes=3913561,
        approved_microbed_sha256=MICROBED_SHA,selected_captures=evidence,
        current_source_sha256={k:digest(v) for k,v in additions.items() if k.startswith('road_scene_r6/src/')},
        fresh_end_to_end_rebuild_verified=False,new_render_performed_by_packager=False,
        captured_render_source_bytes_changed=False,arbitrary_serialized_scene_admitted=False,
        regenerated_output_reports_with_immutable_historical_copies=sorted(REGENERATED_REPORTS),
        whole_scene_user_approved=False,historical_AF_promoted=False)))
    for name,data in additions.items():
        require(Path(name).suffix in ('.py','.json','.txt','.sh'), 'Unexpected new binary payload')
        text=data.decode()
        for fragment in ('/'+ 'workspace/', '/'+ 'home/agent/', '/'+ 'root/'):
            require(fragment not in text,'Private path in new deliverable: '+name)
        if name.endswith('.py'):ast.parse(text,filename=name)
        if name.endswith('.sh'):subprocess.run(['bash','-n'],input=text,text=True,check=True)
    files=dict(lock['files']);files.update({name:digest(data) for name,data in additions.items()})
    add('SOURCE_LOCK.json',encoded(dict(version='R6 portable supported pavement and integrated bank sources',
        base_v9_archive_sha256=BASE_SHA,files=files,pinned_inputs_verified=lock['pinned_inputs_verified'],
        immutable_ground_verified=lock['immutable_ground_verified'],whole_scene_user_approved=False,
        fresh_end_to_end_rebuild_verified=False)))
    return additions,templates


def test_layout(templates):
    spec=importlib.util.spec_from_file_location('portable_replay_ah',ROOT/'src/render_checkpoint_ah.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    results=[]
    with tempfile.TemporaryDirectory(prefix='checkpoint_layout_ah_') as temp:
        testroot=Path(temp)/'road_scene_r6'
        for row in templates:
            target=testroot/'checkpoint_pipeline_sources'/row['pipeline_sha256']
            target.mkdir(parents=True,exist_ok=True)
            source=ROOT/'pipeline/pipeline_snapshots'/row['pipeline_sha256']
            for name,h in row['pipeline_files_sha256'].items():
                origin=(source if name in row['captured_pipeline_files_sha256'] else ROOT/'pipeline')/name
                data=origin.read_bytes();require(digest(data)==h,'Source changed before resolver test')
                (target/name).write_bytes(data)
            stage=module.stage_pipeline(row,testroot/'runs'/row['role'],root=testroot)
            # Parse, do not execute, the captured render source; its relative
            # resolution is the exact filesystem structure checked by the wrapper.
            ast.parse((stage/'render.py').read_text())
            for helper in row['component_helper_names']:
                require(sha(stage.parent/'src'/helper)==row['captured_pipeline_files_sha256'][helper],
                        'Relative helper lookup failed')
            results.append(dict(role=row['role'],helpers=len(row['component_helper_names']),
                                exact_source_bytes=True,sibling_src_resolution=True))
            # Deliberate corruption must be rejected before a new staging run.
            (target/'render.py').write_text('raise RuntimeError("deliberately corrupted fixture")\n')
            try:module.stage_pipeline(row,testroot/'corrupted'/row['role'],root=testroot)
            except ValueError:pass
            else:raise AssertionError('Corrupt captured source admitted')
        package=Path(temp)/'source_lock_fixture';package.mkdir()
        report=sorted(REGENERATED_REPORTS)[0]
        original=b'{"historical": true}\n';current=b'{"fresh_output": true}\n'
        production='road_scene_r6/src/production_fixture.py'
        locked={report:digest(original),'historical_receipts_ah/'+report:digest(original),
                production:digest(b'PASS = True\n')}
        for relative,data in ((report,current),('historical_receipts_ah/'+report,original),
                              (production,b'PASS = True\n')):
            path=package/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        (package/'SOURCE_LOCK.json').write_text(json.dumps(dict(files=locked)))
        old_package=module.PACKAGE;module.PACKAGE=package
        try:
            module.verify_lock()
            (package/production).write_bytes(b'PASS = False\n')
            try:module.verify_lock()
            except ValueError:pass
            else:raise AssertionError('Changed production input admitted')
            (package/production).write_bytes(b'PASS = True\n')
            (package/'historical_receipts_ah'/report).write_bytes(current)
            try:module.verify_lock()
            except ValueError:pass
            else:raise AssertionError('Changed historical evidence admitted')
        finally:module.PACKAGE=old_package
    return dict(passed=True,checks=results,corrupt_snapshot_rejected=True,blender_executed=False,
                scene_written=False,rendered=False,source_only_layout_test=True,
                regenerated_report_output_allowed=True,changed_production_source_rejected=True,
                changed_historical_evidence_rejected=True)


def package(additions,templates):
    require(not OUT.exists() and not OUT.with_suffix('.tmp.zip').exists(),'Preserve previous AH package')
    require(shutil.disk_usage(ROOT).free>25_000_000,'Insufficient free disk for bounded package')
    temp=OUT.with_suffix('.tmp.zip')
    with zipfile.ZipFile(BASE) as base,zipfile.ZipFile(temp,'x',zipfile.ZIP_DEFLATED,compresslevel=8) as dest:
        for info in base.infolist():
            if info.filename not in additions:dest.writestr(info,base.read(info.filename))
        for name,data in additions.items():
            info=zipfile.ZipInfo(name);info.create_system=3
            info.external_attr=(stat.S_IFREG|(0o755 if name.endswith('.sh') else 0o644))<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            dest.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=8)
    with zipfile.ZipFile(temp) as z,zipfile.ZipFile(BASE) as old:
        require(z.testzip() is None,'New ZIP corruption')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'New source closure mismatch')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'New lock mismatch: '+name)
        for name in old.namelist():
            target={'README.txt':'README_Z_V9_CHECKPOINT.txt','SOURCE_LOCK.json':'SOURCE_LOCK_Z_V9_CHECKPOINT.json','regenerate.sh':'regenerate_z_v9.sh'}.get(name,name)
            require(old.read(name)==z.read(target),'Prior dependency changed or dropped: '+name)
        approved=z.read(MICROBED)
        require(len(approved)==3913561 and digest(approved)==MICROBED_SHA,'Approved cache changed')
        count=len(z.namelist())
    require(temp.stat().st_size<=19_000_000,'Source checkpoint exceeds 19 MB limit')
    require(sha(BASE)==BASE_SHA,'Frozen v9 ZIP changed')
    temp.rename(OUT)
    result=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=sha(OUT),archive_entries=count,
        all_prior_entries_preserved=True,source_lock_and_crc_verified=True,
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        selected_captures=[r['name'] for r in templates],fresh_end_to_end_rebuild_verified=False,
        rendered_by_packager=False,library_upload_performed=False)
    receipt=ROOT/'receipts/source_package_integrated_ah_v2.json'
    with receipt.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--context-capture')
    p.add_argument('--visual-review',type=Path)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--package',action='store_true')
    args=p.parse_args()
    additions,templates=prepare(args.context_capture,args.visual_review)
    test=test_layout(templates)
    additions['road_scene_r6/receipts/portable_layout_ah_test.json']=encoded(test)
    lock=json.loads(additions['SOURCE_LOCK.json'])
    lock['files']['road_scene_r6/receipts/portable_layout_ah_test.json']=digest(additions['road_scene_r6/receipts/portable_layout_ah_test.json'])
    additions['SOURCE_LOCK.json']=encoded(lock)
    if args.package:result=package(additions,templates)
    else:result=dict(checked=True,files_to_add=len(additions),selected_captures=[r['name'] for r in templates],source_layout_test=test,package_written=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
