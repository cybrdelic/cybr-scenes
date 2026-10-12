#!/usr/bin/env python3
"""Build a current-only AP delivery from immutable full v13, source checks only."""
import ast
import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'deliverables/CYBR_Victorville_R6_AP_Portable_Road_Components_Source_v13.zip'
BASE_SHA='8b813beb845bd7544575a4cdb1c5edff4573e90fedfe871f72ee346728f4ddde'
OUT=ROOT/'deliverables/CYBR_Victorville_R6_AP_Current_Reproducible_Source_v13.zip'
ENV=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
CONTEXT='road_scene_r6/historical_captures_ap/ap_correlated_margin_context/'
DETAIL='road_scene_r6/historical_captures_ap/ap_correlated_margin_detail/'
FIELD='road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz'
MICROBED='discrete_grains_r5/prototypes/microbed.npz'
GUARDS={'road_scene_r6/receipts/y_semantic_source_guard_v3.json','road_scene_r6/receipts/z_semantic_source_guard_ah.json'}
BUILD_ROOTS=['discrete_grains_r5/src/build_diagnostic.py','discrete_grains_r5/asphalt/source/generate_native4096.py',
    'far_road_r5d/bake/bake_r5d.py','road_scene_r6/src/build_scene.py','road_scene_r6/src/prepare_weather_layer.py',
    'road_scene_r6/src/prepare_sediment_patches.py','road_scene_r6/src/prepare_erosion_network.py',
    'road_scene_r6/src/prepare_eroded_ridges.py','road_scene_r6/src/prepare_shoulder_dust.py',
    'road_scene_r6/relief_correction/prepare_tiled_relief_r2.py','road_scene_r6/src/prepare_runoff_shoulder_y.py',
    'road_scene_r6/src/prepare_runoff_film_z_portable.py']

def digest(data):return hashlib.sha256(data).hexdigest()
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def require(test,msg):
    if not test:raise ValueError(msg)
def enc(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()

def prepare():
    require(file_sha(BASE)==BASE_SHA,'Full v13 changed')
    with zipfile.ZipFile(BASE) as old:
        require(old.testzip() is None,'Full v13 CRC failed')
        full_lock=json.loads(old.read('SOURCE_LOCK.json'))
        full_template=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ap.json'))
        row=next(r for r in full_template['captures'] if r['role']=='ap_context')
        snapshot='road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'
        contract=full_template['source_admission'];kept={};omitted={}
        for info in old.infolist():
            n=info.filename;reason=None
            if '/' not in n and n not in {'PINNED_INPUTS.json','verify_pinned_inputs.py','regenerate_y.sh','regenerate_z_v9.sh'}:
                reason='Superseded top-level history/entrypoint; full v13 retains it'
            elif n.startswith('road_scene_r6/checkpoint_pipeline_sources/') and not n.startswith(snapshot):
                reason='Not referenced by the sole current AP replay; historical snapshot'
            elif n.startswith('road_scene_r6/historical_captures_al/'):
                reason='Historical AL capture evidence, not a source/build input'
            elif n.startswith(DETAIL) and Path(n).name not in {'ROAD_MARGIN_AP.json','resource_receipt.json'}:
                reason='Unpromoted diagnostic close capture evidence, not a build input'
            elif n.startswith('road_scene_r6/receipts/'):
                if 'render_templates' in Path(n).name:
                    reason='Historical render-job selections replaced by the current-only contract/template'
                elif info.file_size>100000 and n not in GUARDS:
                    reason='Historical render/raw/clean/memory receipt, not a builder or admission input'
            if reason:
                omitted[n]={'sha256':digest(old.read(n)),'reason':reason}
            else:kept[n]=old.read(n)
        # No source code is pruned on uncertain dynamic dependency grounds.
        for n in old.namelist():
            if n.endswith('.py') and not n.startswith('road_scene_r6/checkpoint_pipeline_sources/'):
                require(n in kept,'Unexpected non-snapshot source removal: '+n)
        kept['road_scene_r6/receipts/integrated_render_templates_ap.json']=enc(dict(schema_version=4,
            source_admission=contract,captures=[row],default_selection='Current AP context only',
            immutable_numerical_inputs=full_template['immutable_numerical_inputs']))
        # The exact unchanged strict validator reads this contract at its old path.
        # Only unused capture rows are removed; every admission field stays exact.
        kept['road_scene_r6/receipts/integrated_render_templates_ah.json']=enc(dict(schema_version=1,
            source_admission=contract,captures=[],scope='Strict inherited admission contract only; current replay uses AP template'))
        regenerate=old.read('regenerate.sh').decode().replace('bash regenerate_al_v12.sh build-only','bash regenerate_z_v9.sh build-only')
        kept['regenerate.sh']=regenerate.encode()
        source_evidence=json.loads(old.read('INTEGRATED_COMPONENT_EVIDENCE_AP_V13.json'))
        selected_evidence={n:h for n,h in source_evidence['packaged_public_evidence_sha256'].items() if n in kept}
        current_proof=next(r for r in source_evidence['selected_new_captures'] if r['role']=='ap_context')
        detail_proof=next(r for r in source_evidence['selected_new_captures'] if r['role']=='ap_detail')
        kept['road_scene_r6/receipts/ap_diagnostic_close_finding.json']=enc(dict(
            capture='ap_correlated_margin_detail',promoted=False,material_quality_accepted=False,
            finding='The matched close exposed excessive fine-surface smoothing from extra burial/normal attenuation and visibly faceted or repeated legacy K clast bodies.',
            current_selection='AP context only; previous AK/native-S close identities were not superseded',
            full_archive_detail_proof=detail_proof,context_useful_gain='Layered scrub and coherent gravel margin at scene scale',
            whole_scene_accepted=False,fresh_end_to_end_regeneration_verified=False))
        kept['CURRENT_COMPONENT_EVIDENCE_AP_V13.json']=enc(dict(
            full_v13_archive_sha256=BASE_SHA,exact_source_admission_contract=contract,
            latest_roles=['ap_context'],diagnostic_close_promoted=False,selected_current_capture=current_proof,
            original_local_evidence_sha256={n:source_evidence['original_local_evidence_sha256'][n] for n in selected_evidence},
            packaged_public_evidence_sha256=selected_evidence,
            evidence_normalization_checks=[r for r in source_evidence['evidence_normalization_checks'] if r['path'] in selected_evidence],
            historical_storage='Prior Library source versions and separately retained full v13 archive; no Library link is invented',
            fresh_end_to_end_rebuild_verified=False,whole_scene_user_approved=False,AP_material_quality_accepted=False))
        # Keep every non-snapshot Python source and all small static data. Audit
        # local imports plus explicit runtime path inputs rather than pretending
        # a static checker executed Blender or resolved arbitrary Python code.
        original_sources={n for n in old.namelist() if n.endswith('.py') and '/checkpoint_pipeline_sources/' not in n}
        names={}
        for n in original_sources:names.setdefault(Path(n).stem,[]).append(n)
        edges=[];missing=[]
        roots=BUILD_ROOTS+['road_scene_r6/src/render_checkpoint_ap.py','road_scene_r6/src/render_checkpoint_ah.py','road_scene_r6/src/validate_checkpoint_source_ah.py']
        todo=list(roots);visited=set()
        while todo:
            n=todo.pop()
            if n in visited:continue
            visited.add(n)
            if n not in kept:missing.append(n);continue
            for node in ast.walk(ast.parse(kept[n],filename=n)):
                imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
                for module in imports:
                    top=module.split('.')[0]
                    if top not in names:continue
                    same=str(Path(n).parent/(top+'.py'))
                    targets=[same] if same in names[top] else sorted(names[top])
                    edges.append(dict(source=n,module=module,targets=targets));todo.extend(targets)
        explicit={'PINNED_INPUTS.json','verify_pinned_inputs.py',MICROBED,FIELD,
            'discrete_grains_r5/prototypes/fracture_solids.json','discrete_grains_r5/asphalt/material.json',
            'road_scene_r6/receipts/flow_source_fingerprint.json',*GUARDS,
            'road_scene_r6/src/roadside_clasts.py','road_scene_r6/relief_correction/prepare_tiled_relief.py',
            'road_scene_r6/relief_correction/paint_shader_adapter_r2.py','road_scene_r6/relief_correction/affine_tile_adapter.py'}
        # These directories cover dynamic vegetation imports, recipe helpers,
        # all frozen relief adapters, the exact captured runtime and test files.
        groups=('discrete_grains_r5/','far_road_r5d/','road_scene_r6/vegetation/','road_scene_r6/relief_correction/',snapshot,'historical_receipts_ah/')
        required=set(visited)|explicit|{n for n in kept if n.startswith(groups)}
        for n in required:
            if n not in kept:missing.append(n)
        require(not missing,'Required source/input closure failed: '+repr(missing))
        exact={n:digest(kept[n]) for n in sorted(required)}
        for n,h in exact.items():require(digest(old.read(n))==h,'Required original bytes changed: '+n)
        for n,h in contract['files_sha256'].items():require(digest(kept[n])==h,'Strict source admission bytes changed')
        closure=dict(full_v13_sha256=BASE_SHA,build_entrypoints=BUILD_ROOTS,
            build_shell_chain=['regenerate.sh build-only','regenerate_z_v9.sh build-only','regenerate_y.sh build-only'],
            local_import_edges=edges,active_static_source_files=sorted(visited),missing_static_dependencies=missing,
            retained_exact_required_files_sha256=exact,all_non_snapshot_python_sources_retained=True,
            generated_dependencies=['Native asphalt 4096 maps and GeometryHeight.npy','R5D bake maps','S/Y/Z scene outputs','Per-run AH_FIELDS.npz'],
            external_runtime_dependencies=['Blender 4.3.2 with Python/NumPy','Python 3 with NumPy/SciPy/Pillow','Linux bash and ps','Official OIDN 2.5.1'],
            limitations='Static import/path and exact-byte closure only. Arbitrary Python runtime paths and a complete fresh build remain unverified.',
            omitted_entries=omitted)
        kept['road_scene_r6/receipts/current_dependency_closure_ap.json']=enc(closure)
        kept['road_scene_r6/src/validate_source_current_ap.py']=(ROOT/'src/validate_source_current_ap.py').read_bytes()
        kept['road_scene_r6/src/package_current_checkpoint_ap.py']=Path(__file__).read_bytes()
        kept['test_source_current_ap.sh']=b'''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python verify_pinned_inputs.py
python road_scene_r6/src/render_checkpoint_ap.py --check-sources
python road_scene_r6/src/validate_source_current_ap.py
python - <<'TESTS'
import json,subprocess,sys
from pathlib import Path
root=Path('road_scene_r6');row=json.loads((root/'receipts/integrated_render_templates_ap.json').read_text())['captures'][0]
snapshot=str(root/'checkpoint_pipeline_sources'/row['pipeline_sha256'])
for generation in ('ak','al','ap'):
    command=[sys.executable,str(root/('checkpoint_tests_'+generation)/'run_snapshot_tests.py'),'--snapshot',snapshot]
    if generation=='ak':command+=['--generation','AK']
    subprocess.run(command,check=True)
TESTS
'''
        kept['README.txt']=('''VICTORVILLE AP: CURRENT REPRODUCIBLE SOURCE DELIVERY v13

PURPOSE AND STATUS
This package contains the current AP context recipe, exact required source and
inputs, strict admission manifests, current evidence, and portable entrypoints.
It avoids accumulating unrelated historical capture receipts/snapshots/jobs.
The full history remains in previous Library source versions and the separately
retained full v13 ZIP, SHA256:
'''+BASE_SHA+'''
This archive does not replace or delete that full checkpoint.

AP context shows useful scene-scale scrub/gravel improvement, but whole-scene
and AP material-quality acceptance have not been given. The matched close is
diagnostic, NOT promoted: fine surfaces are oversmoothed by burial/normal
attenuation and repeated legacy K clasts can look faceted. Previous AK/native-S
close identities are not superseded. The diagnostic finding, resource receipt
and exact provenance are retained without another runnable capture selection.

WHAT IS EXACT
The approved 3,913,561-byte microbed and exact 2,093,642-byte Z ledger are intact.
All required builders and transitive static inputs retain their full-v13 hashes.
The AP captured snapshot, including its sampler and vegetation helpers, is exact.
All non-snapshot Python source is conservatively retained; unused historical
tools may reference history stored only in full v13. Use the entrypoints below.
The dependency manifest lists retained exact inputs, static local-import edges,
generated prerequisites, and every omitted entry with its hash and reason.

STRICT ADMISSION
The same Y semantic guard, Z semantic guard, source validators, schemas and
tolerances remain unchanged. The AH template path retains the exact admission
contract with no historical capture jobs. Its SHA is bound by the new source
lock. Replay records the newly admitted scene hash and never requires matching
the old serialized .blend bytes. No guard or negative-control requirement is
weakened. Old small admission/negative-control proof receipts remain historical
evidence; Blender checks were not rerun during this packaging pass.

CURRENT ENTRYPOINTS
Extract using Python 3 with standard lzma support (ZIP_LZMA method 14 is used):
  python -m zipfile -e CYBR_Victorville_R6_AP_Current_Reproducible_Source_v13.zip current_ap
Use a fresh extraction. Requirements: Blender 4.3.2 with Python/NumPy; Python 3
with NumPy/SciPy/Pillow; Linux bash/ps; official OIDN 2.5.1 in OIDN_BIN.
  bash test_source_current_ap.sh
  bash regenerate.sh build-only
  bash regenerate.sh render-only
  bash regenerate.sh preview
  python road_scene_r6/src/render_checkpoint_ap.py --check-sources
  python road_scene_r6/src/render_checkpoint_ap.py --role ap_context --tag ap_context_repeat
There is exactly ONE replay selection: current AP context. Build-only dispatches
directly to the unchanged Z-v9/Y build chain, bypassing historical render checks.
No previous capture cache is injected. The native maps, scenes and AH fields
must be rebuilt. The inherited exact native-height SHA and Z-ledger checks apply.

CURRENT TEST SCOPE AND LIMITS
Current dependency/source-lock and extracted replay-layout checks plus the
original AK/AL/AP pure suites run against the current exact AP snapshot.
The historical AI/AJ/AK/AL snapshot-specific repeated suites are not silently
counted as rerun: those snapshots are intentionally absent. Current suites
still test their inherited mechanisms without altering tests or assertions.
The AP suite also reproduces all six original offline shrub-geometry variants.
Corrupt source/ledger rejection and exact current ledger splitting are checked.
The absent native height map uses an explicitly tiny synthetic layout fixture
only in layout testing, never in actual production admission.

Fresh end-to-end regeneration is UNVERIFIED. No Blender, terrain solve, scene
build, render or upload occurred during packaging. AP remains an authored
historical composition, not validated transport, optics, botanical identity,
site reconstruction or collision dynamics. No photo pixels are scene inputs.
AP leaves road/terrain geometry unchanged, uses actual legacy K clasts at their
metric size, and retains R5D prototype shapes/materials/scale while lowering
existing scene grain origins by at most 0.62748 mm. A broad smooth inner strip,
scalloped contact, mainly-left shrubs, simpler far hills/opposite shoulder and
inherited approximation limits remain.
''').encode()
        lock=dict(version='AP current-only reproducible source delivery v13',full_v13_archive_sha256=BASE_SHA,
            files={n:digest(d) for n,d in kept.items()},pinned_inputs_verified=full_lock['pinned_inputs_verified'],
            immutable_ground_verified=full_lock['immutable_ground_verified'],additional_pinned_numerical_input=full_lock['additional_pinned_numerical_input'],
            whole_scene_user_approved=False,fresh_end_to_end_rebuild_verified=False)
        kept['SOURCE_LOCK.json']=enc(lock)
    return kept,omitted,row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    kept,omitted,row=prepare();temp=OUT.with_suffix('.tmp.zip')
    require(not OUT.exists() and not temp.exists(),'Preserve prior output/staging')
    require(shutil.disk_usage(ROOT).free>200*1024**2,'Insufficient space plus reserve')
    for n,d in kept.items():
        if n.endswith('.py'):ast.parse(d,filename=n)
        if n.endswith('.sh'):subprocess.run(['bash','-n'],input=d,check=True)
    with zipfile.ZipFile(temp,'x') as z:
        for n,d in kept.items():
            info=zipfile.ZipInfo(n);info.create_system=3;info.external_attr=(stat.S_IFREG|(0o755 if n.endswith('.sh') else 0o644))<<16
            method=zipfile.ZIP_LZMA if n.endswith('.json') and len(d)>100000 else zipfile.ZIP_DEFLATED
            z.writestr(info,d,compress_type=method,compresslevel=8 if method==zipfile.ZIP_DEFLATED else None)
    require(temp.stat().st_size<19_000_000,'Current-only archive unexpectedly too large')
    kept.clear();gc.collect()
    with zipfile.ZipFile(temp) as z:
        require(z.testzip() is None,'Current archive CRC failed')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'Current lock closure failed')
        for n,h in lock['files'].items():require(digest(z.read(n))==h,'Current lock hash failed: '+n)
        with tempfile.TemporaryDirectory(prefix='verify_ap_current_') as path:
            z.extractall(path)
            result=subprocess.run(['bash','test_source_current_ap.sh'],cwd=path,env=ENV,capture_output=True,text=True,timeout=180)
            require(result.returncode==0,'Current extracted checks failed:\n'+result.stdout+'\n'+result.stderr)
            output=result.stdout+'\n'+result.stderr
        entries=len(z.namelist())
    require(file_sha(BASE)==BASE_SHA,'Full v13 changed')
    temp.rename(OUT)
    result=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=file_sha(OUT),archive_entries=entries,
        full_v13_preserved_sha256=BASE_SHA,omitted_historical_entries=len(omitted),source_lock_and_crc_verified=True,
        current_static_dependency_closure_checked=True,extracted_check_sources_and_pure_tests_passed=True,
        current_replay_roles=['ap_context'],strict_Y_and_Z_admission_unchanged=True,
        current_AP_exact_snapshot_sha256=row['pipeline_sha256'],fresh_end_to_end_regeneration_verified=False,
        diagnostic_close_promoted=False,whole_scene_user_approved=False,blender_launched=False,rendered=False,uploaded=False)
    (ROOT/'receipts/source_package_current_ap_v13.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'receipts/source_package_current_ap_v13_tests.log').write_text(output)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
