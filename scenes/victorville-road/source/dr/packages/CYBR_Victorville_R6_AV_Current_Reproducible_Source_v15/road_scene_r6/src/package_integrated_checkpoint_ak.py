#!/usr/bin/env python3
"""Build the source-only AK v11 checkpoint from immutable AH v10.
Never launches Blender, builds scenes, renders, uploads, or rewrites old entries.
Only CPU1 small pure tests and source/layout/hash checks are performed here.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from package_integrated_checkpoint_ah import (ROOT, SOURCE_SHA, MICROBED, MICROBED_SHA,
    HEIGHT, HEIGHT_SHA, PIPELINE_CORE, require, digest, sha, read, public, encoded)
from render_checkpoint_ah import REGENERATED_REPORTS, stage_pipeline

BASE=ROOT/'deliverables/CYBR_Victorville_R6_AH_Portable_Road_Components_Source_v2.zip'
BASE_SHA='8c2a6d3f52e21f96f44ea3bfca0fbc2dff384dad7849339f6bac4c595860fe57'
OUT=ROOT/'deliverables/CYBR_Victorville_R6_AK_Portable_Road_Components_Source_v11.zip'
PRESERVED={'README.txt':'README_AH_V10_CHECKPOINT.txt',
           'SOURCE_LOCK.json':'SOURCE_LOCK_AH_V10_CHECKPOINT.json',
           'regenerate.sh':'regenerate_ah_v10.sh'}
SELECTED=[('ai_sorted_support_context_preview','ai_context','AI'),
          ('ai_sorted_shoulder_detail','ai_detail','AI'),
          ('aj_retained_stock_context_preview','aj_context','AJ'),
          ('ak_substrate_units_context_preview','ak_context','AK'),
          ('ak_substrate_units_detail','ak_detail','AK')]
REQUIRED_NEW={'sediment_surface_ai.py','assemble_sediment_surface_ai.py',
    'transported_grain_exposure.py','flow_transport_ae.py','assemble_graded_shoulder_ah.py',
    'runoff_edge_support_ai.py','pavement_contact_ac.py','assemble_pavement_contact_ac.py'}


def verify_base():
    require(BASE.stat().st_size==11831302 and sha(BASE)==BASE_SHA,'Immutable v10 ZIP differs')
    with zipfile.ZipFile(BASE) as z:
        require(z.testzip() is None,'v10 CRC failure')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'v10 closure mismatch')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'v10 source lock mismatch: '+name)
        data=z.read(MICROBED)
        require(len(data)==3913561 and digest(data)==MICROBED_SHA,'Approved microbed changed')
        require(not any(n.lower().endswith('.blend') for n in z.namelist()),'Unexpected scene in v10')
    return lock


def normalized_report_job(job, folder):
    """Remove only the exact output-derived AI/AJ field; reject unsafe values."""
    result=copy.deepcopy(job);contact=result.get('pavement_contact_ac',{})
    if 'runoff_support_fields' in contact:
        require(contact.get('runoff_support') is True,'Derived support field without enabled runoff support')
        require(contact['runoff_support_fields']==str(folder/'AH_FIELDS.npz'),
                'Unexpected derived runoff support path')
        del contact['runoff_support_fields']
    return result


def capture(name,role,generation):
    require(Path(name).name==name,'Capture name must be flat')
    folder=ROOT/'captures'/name
    job=read(folder/'job.json');raw=read(folder/'INTERNAL_PANEL.png.json')
    clean=read(folder/'CLEAN_OIDN_PANEL.png.json');memory=read(folder/'PRE_RENDER_MEMORY_ADAPTATIONS.json')
    resource=read(folder/'resource_receipt.json')
    require('runoff_support_fields' not in job.get('pavement_contact_ac',{}),'Job may not inject a historical generated cache')
    require(raw['job']==clean['job'],'Raw/clean job mismatch')
    normalized=normalized_report_job(raw['job'],folder)
    require(job==normalized,'Capture differs beyond single derived field: '+name)
    if generation=='AK':require(job==raw['job'],'AK must retain fixed unmutated job receipt')
    require(job['source_sha256']==raw['source_sha256']==clean['source_sha256']==SOURCE_SHA,'Z source mismatch')
    require(raw['pipeline']==clean['pipeline']==memory['pipeline'],'Pipeline receipt mismatch')
    require(resource.get('exit_code')==resource.get('actual_process_exit_code')==0 and
            resource.get('resource_contract_passed') is True and not resource.get('resource_contract_violations'),
            'Capture resource contract failed: '+name)
    cap=job['rss_cap_mib']
    require(type(cap) is int and 0<cap<=4480 and resource['RSS_cap_MiB']==cap and
            max(resource['peak_process_tree_RSS_MiB'],resource['kernel_max_child_RSS_MiB'])<=cap,
            'Declared/actual capture cap differs')
    require(job['engine']=='CYCLES' and job['capture_mode']=='guided' and job['save_guides'] is True,'Guided Cycles required')
    require(job['width']<=1200 and job['height']<=900 and raw['resolution']==clean['resolution']==[job['width'],job['height']],'Bounded preview only')
    require(clean.get('raw_guides_retained') is True and clean['oidn_guide_contract']['valid'] is True,'Guide contract failed')
    checked={}
    for filename,h in clean['files_sha256'].items():
        require(sha(filename)==h,'Capture image/native guide hash mismatch: '+filename)
        checked[public(filename)]=h
    image=folder/'CLEAN_OIDN_PANEL.png'
    require(clean['files_sha256'][str(image)]==sha(image),'Final image mismatch')
    pipeline=raw['pipeline'];manifest=pipeline['files']
    require(digest(json.dumps(manifest,sort_keys=True).encode())==pipeline['sha256'],'Snapshot manifest digest mismatch')
    snapshot=Path(pipeline['snapshot'])
    require(snapshot.resolve()==(ROOT/'pipeline/pipeline_snapshots'/pipeline['sha256']).resolve(),'Unexpected snapshot path')
    files={}
    for filename,h in manifest.items():
        require(Path(filename).name==filename,'Snapshot filename must be flat')
        data=(snapshot/filename).read_bytes();require(digest(data)==h,'Snapshot differs: '+filename)
        files[filename]=data
    require(PIPELINE_CORE|REQUIRED_NEW<=set(files),'Component snapshot incomplete')
    if generation=='AK':require('substrate_history_ak.py' in files,'AK history source absent')
    # The watchdog is separate from the captured manifest. Reuse byte-identical
    # v10 support sources, never silently upgrade them from a mutable live file.
    with zipfile.ZipFile(BASE) as old:
        old_template=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ah.json'))
        row=old_template['captures'][0]
        for filename in ('bounded_clean_run.py','resource_contract.py'):
            data=old.read('road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'+filename)
            require(digest(data)==row['pipeline_files_sha256'][filename],'Inherited watchdog differs')
            files[filename]=data
    for filename,data in files.items():
        if not filename.endswith('.py') or filename=='render.py':continue
        for node in ast.walk(ast.parse(data,filename=filename)):
            mods=([a.name for a in node.names] if isinstance(node,ast.Import) else
                  [node.module] if isinstance(node,ast.ImportFrom) and node.module else [])
            for mod in mods:
                candidate=mod.split('.')[0]+'.py'
                if (ROOT/'src'/candidate).exists():require(candidate in files,'Uncaptured local helper dependency: '+candidate)
    settings={k:v for k,v in copy.deepcopy(job).items() if k not in ('source','source_sha256','output')}
    relocations=[]
    for key in ('pavement_contact_ac','edge_ravel_aa'):
        if key in settings:
            require(sha(settings[key]['height_path'])==HEIGHT_SHA,'Required generated native height differs')
            settings[key]['height_path']=HEIGHT
            relocations.append(dict(job_key_path=[key,'height_path'],package_path=HEIGHT,sha256=HEIGHT_SHA))
    for key in ('graded_shoulder_ah','visible_shoulder_ad','graded_shoulder_af'):
        require(not settings.get(key,{}).get('cache_path'),'Unpackaged numerical cache dependency')
    template=dict(name=name,role=role,generation=generation,settings=settings,
        pipeline_sha256=pipeline['sha256'],captured_pipeline_files_sha256=manifest,
        pipeline_files_sha256={k:digest(v) for k,v in files.items()},
        component_helper_names=sorted(set(manifest)-PIPELINE_CORE),input_relocations=relocations,
        derived_job_field_normalization=('pavement_contact_ac.runoff_support_fields generated from current output directory'
            if raw['job']!=job else None))
    reports={p.stem.lower():read(p) for p in folder.glob('*.json')}
    proof=dict(name=name,role=role,generation=generation,source_sha256=SOURCE_SHA,
        clean_image_sha256=sha(image),pipeline_sha256=pipeline['sha256'],
        original_job_sha256=sha(folder/'job.json'),original_raw_receipt_sha256=sha(folder/'INTERNAL_PANEL.png.json'),
        original_clean_receipt_sha256=sha(folder/'CLEAN_OIDN_PANEL.png.json'),
        historical_images_and_native_guides_verified=checked,raw_guides_retained=True,
        resource_contract_passed=True,declared_cap_MiB=cap,
        peak_MiB=max(resource['peak_process_tree_RSS_MiB'],resource['kernel_max_child_RSS_MiB']),
        normalization_limited_to_exact_derived_field=True,generated_AH_fields_included=False)
    return template,files,reports,proof


def readme(rows):
    selected='\n'.join('- '+r['role']+': '+r['name']+'; '+str(r['settings']['width'])+' x '+str(r['settings']['height'])+
                      ', '+str(r['settings']['samples'])+' samples, declared cap '+str(r['settings']['rss_cap_mib'])+' MiB.' for r in rows)
    return '''VICTORVILLE R6: AK COMPLETE PORTABLE SOURCE CHECKPOINT v11

STATUS
Complete source-only extension of AH v10, including every inherited source,
approved input and historical record through Z/AC/AH. AI, AJ and AK snapshots
are added byte-for-byte from actual successful bounded captures. This is an
unfinished progress checkpoint, not user acceptance of the whole road scene.
A fresh clean-directory full end-to-end regeneration remains UNVERIFIED.
The packager performed only small pure CPU tests and archive/layout/hash checks.
It did not load/build scenes, run a full terrain solve, render or upload.

WHAT CHANGED
AI connects the first two metres of the broken pavement edge to the actual
sampled bank support and maps conservative transport fields to surface exposure.
A shallow continuous lip remains; inherited AC wording about disconnected sectors
is a legacy assumption and does not prove AI properties. The farther scalloped
edge and uniform pale soil remain limitations. AJ fixes the availability gate:
surviving deposited stock may exist where net bed height is negative. Its 1.8 mm
weighted top-layer proxy is limited by per-class retained stock, but it is not
resolved vertical stratigraphy. The matched visual effect was small; AJ is a
correctness checkpoint, not a major visual leap.
AK adds authored approximate historical substrate units: armor/grit, compacted
fines and thin receiving sand. Their current-foundation gradients and connected
unequal reaches suggest a pre-existing history independent of recent storms.
The prior skin is already inside existing ground. It adds no height layer and
reallocates the same 18 mm initial active inventory among classes. Surface
representation changes use existing approved grain prototypes at retained metric
scale. Full packing/contact and calibrated geomorphic history are not proved.
Historical strata, runoff and sediment transport are illustrative approximations,
not measured Victorville conditions or validated physics/hydraulics. Repeated
storm transport, preview LOD and MFD directional/resolution limitations remain.

FILES AND PRESERVATION
Every v10 archive entry remains byte-identical. Only the top-level README,
SOURCE_LOCK and regenerate wrapper are superseded at their original names;
their exact old bytes remain as README_AH_V10_CHECKPOINT.txt,
SOURCE_LOCK_AH_V10_CHECKPOINT.json and regenerate_ah_v10.sh. Earlier archive
history remains intact. No old production helper is replaced by a newer version.
Exact version-specific helpers live under:
  road_scene_r6/checkpoint_pipeline_sources/<captured SHA256>/
The approved microbed remains exactly 3,913,561 bytes, SHA256:
''' + MICROBED_SHA + '''
No .blend, native generated map, numerical field cache, raw EXR or rendered image
is bundled. Those outputs must be rebuilt; retained receipts are historical
evidence, not present binary outputs. The capture's native raw EXR guides and raw
and final PNGs were checked before packaging. Earlier redundant PFM conversion
cleanup does not remove any files named by these selected clean-receipt hashes.

PORTABLE REGENERATION
Use a fresh extraction. Requirements: Blender 4.3.2 with Python/NumPy; Python 3
with NumPy, SciPy, Pillow; Linux bash and ps; official OIDN 2.5.1. Set OIDN_BIN to
its existing executable. No installer, binary runtime or native scene is bundled.

1. Verify sources only, without Blender or generated maps:
   python road_scene_r6/src/render_checkpoint_ak.py --check-sources
2. Build the complete inherited source chain through Z:
   bash regenerate.sh build-only
3. Render only the latest AK context/detail progress pair after build:
   bash regenerate.sh render-only
4. Build plus latest pair:
   bash regenerate.sh preview
5. Select any single version/camera, using a fresh run tag:
   python road_scene_r6/src/render_checkpoint_ak.py --role ai_context --tag ai_repeat
   python road_scene_r6/src/render_checkpoint_ak.py --role aj_context --tag aj_repeat
   python road_scene_r6/src/render_checkpoint_ak.py --role ak_detail --tag ak_detail_repeat
   python road_scene_r6/src/render_checkpoint_ak.py --role all --tag all_versions
Inherited AH entrypoint and regenerate_ah_v10.sh remain available. Historical
comparison helpers expect their original capture directory names; select/read
fresh captures explicitly rather than treating historical images as bundled.

REPLAY AND STRICT ADMISSION
The new wrapper imports the unchanged v10 source-lock validator, exact-snapshot
stager, input relocation and strict scene-admission functions. The AK admission
contract must equal the inherited AH contract exactly. It calls the SAME pinned
validation-only Z semantic guard at receipts/z_semantic_source_guard_ah.json.
The rebuilt Z scene must match its complete recorded semantic schema; its actual
serialized source SHA is recorded and used. No arbitrary scene is accepted by
hash alone. No guard or tolerance was weakened. Original geometry/material
negative-control evidence is preserved, not claimed to have been rerun here.
Strict validation may reject different renderer-version output; never bypass it.

Every replay stages a fresh runtime/pipeline and sibling runtime/src containing
identical capture-selected source bytes. Captured render.py remains unpatched.
Each new clean receipt must reproduce that selected captured pipeline digest.
AI/AJ old raw/clean jobs contain exactly one derived field injected at runtime:
pavement_contact_ac.runoff_support_fields = <capture>/AH_FIELDS.npz. Only that
field is normalized after verifying its exact output-directory path and enabled
runoff_support. Any other job difference fails. Latest AK copied its contact
config and already matches job.json without normalization. Templates never use
historical AH_FIELDS.npz. The selected pipeline regenerates it in the new run.
GeometryHeight.npy must regenerate to the inherited pinned native SHA256:
''' + HEIGHT_SHA + '''
Seven inherited overwritten output reports still use their exact immutable
historical_receipts_ah copies for source-lock checking; all production source,
inputs, templates and semantic contracts remain checked at runtime paths.

RESOURCES
Declared per-capture caps are preserved, never inferred downward from measured
peaks. AI detail declares 4480 MiB despite its approximately 3085 MiB peak.
AI/AJ/AK context and detail remain bounded at 4480 MiB or lower. Original AH/AC
caps remain unchanged. Strict scene admission retains its separate 4096 MiB,
two-thread and ten-minute bounds. Existing stopped AH trials remain failures.
The default latest pair is two separate runs; no native/4K render is added.

SELECTED CAPTURES
''' + selected + '''

TESTS AND CAVEATS
Run the portable pure regression suite against each pinned snapshot with:
  bash test_source_ak.sh
Fresh tests run CPU1 without Blender: AI/AJ optical/stock allocation and edge
support/contact regressions, plus synthetic-foundation AK history invariants and
a small spatial-inventory conservation solve. Exact original test sources and
historical actual-field receipts remain included separately. Actual AH/topology
fixtures are not bundled, and these actual-field tests were not rerun as part of
packaging. This distinction is recorded explicitly in each test receipt.
Source-only layout tests check exact helper resolution, job normalization,
source-corruption rejection, immutable source guard and inherited closure.
The extracted archive passes source checking, but a complete fresh build/render
was not performed. Successful historical previews and pure tests do not establish
fresh end-to-end portability or whole-scene quality acceptance.
'''


def prepare(include_detail=True):
    lock=verify_base();additions={};newrows=[];proofs=[];snapshots={}
    def add(name,data):
        if isinstance(data,str):data=data.encode()
        if name in additions:require(additions[name]==data,'Conflicting new entry: '+name)
        additions[name]=data
    with zipfile.ZipFile(BASE) as old:
        original=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ah.json'))
        for source,target in PRESERVED.items():add(target,old.read(source))
        for key,h in original['source_admission']['files_sha256'].items():
            require(digest(old.read(key))==h,'Original semantic contract differs')
        guard=json.loads(old.read(original['source_admission']['manifest_path']))
        require(guard['source_sha256']==SOURCE_SHA,'Original Z source guard differs')
        require(digest(json.dumps(guard['snapshot'],sort_keys=True,separators=(',',':')).encode())==guard['semantic_sha256'],'Semantic snapshot digest differs')
        require(old.read('road_scene_r6/src/render_checkpoint_ah.py')==(ROOT/'src/render_checkpoint_ah.py').read_bytes(),'Local inherited wrapper changed')
        require(old.read('road_scene_r6/src/package_integrated_checkpoint_ah.py')==(ROOT/'src/package_integrated_checkpoint_ah.py').read_bytes(),'Local inherited packager changed')
    selection=SELECTED if include_detail else SELECTED[:-1]
    for name,role,generation in selection:
        row,files,reports,proof=capture(name,role,generation)
        newrows.append(row);proofs.append(proof);snapshots[row['pipeline_sha256']]=(generation,files)
        for filename,data in files.items():add('road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'+filename,data)
        for suffix,value in reports.items():add('road_scene_r6/receipts/'+name+'_'+suffix+'.json',encoded(value))
    rows=original['captures']+newrows
    require(len({r['role'] for r in rows})==len(rows),'Replay roles must be unique')
    for name in ('render_checkpoint_ak.py','package_integrated_checkpoint_ak.py','compare_ai_progress.py','compare_ak_progress.py'):
        add('road_scene_r6/src/'+name,(ROOT/'src'/name).read_bytes())
    for path in sorted((ROOT/'checkpoint_tests_ak').rglob('*.py')):
        add('road_scene_r6/'+str(path.relative_to(ROOT)),path.read_bytes())
    for name in ('ai_edge_support_tests.json','ai_visual_review.json','aj_inventory_correction.json',
                 'aj_projected_coverage.json','ak_initial_inventory_test.json','ak_substrate_history/AK_SUBSTRATE_HISTORY.json'):
        add('road_scene_r6/receipts/'+name,encoded(read(ROOT/'receipts'/name)))
    for path in sorted((ROOT/'receipts').glob('ak*visual*review*.json')):
        add('road_scene_r6/receipts/'+path.name,encoded(read(path)))
    add('road_scene_r6/receipts/integrated_render_templates_ak.json',encoded(dict(schema_version=2,
        source_admission=original['source_admission'],captures=rows,default_selection='latest AK generation')))
    testrows=[]
    with tempfile.TemporaryDirectory(prefix='checkpoint_ak_tests_') as temp:
        t=Path(temp)
        for h,(generation,files) in snapshots.items():
            snapshot=t/'road_scene_r6/checkpoint_pipeline_sources'/h;snapshot.mkdir(parents=True)
            for name,data in files.items():(snapshot/name).write_bytes(data)
            row=next(r for r in newrows if r['pipeline_sha256']==h)
            staged=stage_pipeline(row,t/'layout'/h,root=t/'road_scene_r6')
            for name in row['component_helper_names']:require(sha(staged.parent/'src'/name)==row['captured_pipeline_files_sha256'][name],'Exact helper lookup failed')
            receipt=t/(generation+'_tests.json')
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run([sys.executable,str(ROOT/'checkpoint_tests_ak/run_snapshot_tests.py'),
                '--snapshot',str(snapshot),'--generation',generation,'--receipt',str(receipt)],
                env=env,capture_output=True,text=True,timeout=120)
            require(result.returncode==0,'Pure '+generation+' tests failed:\n'+result.stdout+'\n'+result.stderr)
            report=read(receipt);require(report['passed'] is True,'Pure tests not passed')
            add('road_scene_r6/receipts/portable_'+generation.lower()+'_tests_v11.json',encoded(report));testrows.append(report)
            (snapshot/'render.py').write_text('raise RuntimeError("corrupted fixture")\n')
            try:stage_pipeline(row,t/'corrupt'/h,root=t/'road_scene_r6')
            except ValueError:pass
            else:raise AssertionError('Corrupt captured source admitted')
    folder=ROOT/'captures'/selection[0][0];job=read(folder/'job.json')
    mutated=copy.deepcopy(job);mutated['pavement_contact_ac']['runoff_support_fields']=str(folder/'AH_FIELDS.npz')
    require(normalized_report_job(mutated,folder)==job,'Exact derived path failed normalization')
    for field,value in (('runoff_support_fields',str(folder/'UNEXPECTED.npz')),('runoff_support',False)):
        bad=copy.deepcopy(mutated);bad['pavement_contact_ac'][field]=value
        try:normalized_report_job(bad,folder)
        except ValueError:pass
        else:raise AssertionError('Unsafe derived-field normalization admitted')
    bad=copy.deepcopy(mutated);bad['samples']+=1
    require(normalized_report_job(bad,folder)!=job,'Unrelated job mutation normalized away')
    layout=dict(passed=True,exact_captured_source_bytes=True,sibling_src_resolution=True,
        corrupt_snapshot_rejected=True,exact_only_derived_field_normalization=True,
        wrong_derived_path_rejected=True,disabled_support_with_derived_field_rejected=True,
        unrelated_job_mutation_rejected=True,strict_Z_contract_equal_to_v10=True,
        source_guard_and_admission_code_unchanged=True,blender_executed=False,rendered=False,
        new_snapshot_generations=[r['generation'] for r in testrows],pure_tests=[r['tests_run'] for r in testrows])
    add('road_scene_r6/receipts/portable_layout_ak_test_v11.json',encoded(layout))
    add('test_source_ak.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python road_scene_r6/src/render_checkpoint_ak.py --check-sources
python - <<'TESTS'
import json,subprocess,sys
from pathlib import Path
root=Path('road_scene_r6');rows=json.loads((root/'receipts/integrated_render_templates_ak.json').read_text())['captures'];seen=set()
for row in rows:
    if row.get('generation') not in ('AI','AJ','AK') or row['pipeline_sha256'] in seen:continue
    seen.add(row['pipeline_sha256'])
    subprocess.run([sys.executable,str(root/'checkpoint_tests_ak/run_snapshot_tests.py'),'--snapshot',str(root/'checkpoint_pipeline_sources'/row['pipeline_sha256']),'--generation',row['generation']],check=True)
TESTS
''')
    add('regenerate.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-preview}" in preview|build-only|render-only) ;; *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;; esac
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then echo "Unset MATERIAL_PATH_MAP_FILE." >&2; exit 2; fi
python road_scene_r6/src/render_checkpoint_ak.py --check-sources
if [ "${1:-preview}" != build-only ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to official OIDN 2.5.1 oidnDenoise}"
  test -f "$OIDN_BIN" && test -x "$OIDN_BIN"
fi
if [ "${1:-preview}" != render-only ]; then bash regenerate_ah_v10.sh build-only; fi
if [ "${1:-preview}" != build-only ]; then python road_scene_r6/src/render_checkpoint_ak.py; fi
''')
    add('README.txt',readme(rows))
    add('INTEGRATED_COMPONENT_EVIDENCE_AK_V11.json',encoded(dict(base_v10_archive_sha256=BASE_SHA,
        every_v10_entry_preserved=True,top_level_original_names_preserved_as=PRESERVED,
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        selected_new_captures=proofs,new_pure_test_counts={r['generation']:r['tests_run'] for r in testrows},
        captured_source_bytes_changed=False,new_render_performed_by_packager=False,
        strict_Z_admission_unchanged=True,fresh_end_to_end_rebuild_verified=False,
        whole_scene_user_approved=False,AJ_visual_effect='Small correctness change',
        AK_history='Authored approximate prior substrate units, not surveyed strata or validated physics',
        source_only_no_generated_fields_or_scenes=True)))
    with zipfile.ZipFile(BASE) as old:
        for name,data in additions.items():
            if name in lock['files'] and name not in PRESERVED:
                require(old.read(name)==data,'Prior production/history entry would change: '+name)
    for name,data in additions.items():
        require(Path(name).suffix in ('.py','.json','.txt','.sh'),'New binary payload is forbidden')
        text=data.decode()
        for fragment in ('/'+'workspace/', '/'+'home/agent/', '/'+'root/'):
            require(fragment not in text,'Private path in added source/evidence: '+name)
        if name.endswith('.py'):ast.parse(text,filename=name)
        if name.endswith('.sh'):subprocess.run(['bash','-n'],input=text,text=True,check=True)
    files=dict(lock['files']);files.update({name:digest(data) for name,data in additions.items()})
    add('SOURCE_LOCK.json',encoded(dict(version='R6 complete portable AK source checkpoint v11',
        base_v10_archive_sha256=BASE_SHA,files=files,pinned_inputs_verified=lock['pinned_inputs_verified'],
        immutable_ground_verified=lock['immutable_ground_verified'],whole_scene_user_approved=False,
        fresh_end_to_end_rebuild_verified=False)))
    return additions,rows,layout


def package(additions,rows,layout):
    temp=OUT.with_suffix('.tmp.zip')
    require(not OUT.exists() and not temp.exists(),'Preserve existing package or staging archive')
    require(shutil.disk_usage(ROOT).free>100_000_000,'Insufficient bounded packaging space')
    with zipfile.ZipFile(BASE) as old,zipfile.ZipFile(temp,'x',zipfile.ZIP_DEFLATED,compresslevel=8) as new:
        for info in old.infolist():
            if info.filename not in additions:new.writestr(info,old.read(info.filename))
        for name,data in additions.items():
            info=zipfile.ZipInfo(name);info.create_system=3
            info.external_attr=(stat.S_IFREG|(0o755 if name.endswith('.sh') else 0o644))<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            new.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=8)
    require(temp.stat().st_size<=19_000_000,'Package exceeds 19 MB budget')
    with zipfile.ZipFile(temp) as z,zipfile.ZipFile(BASE) as old:
        require(z.testzip() is None,'New CRC check failed')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'New source closure differs')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'New locked entry differs: '+name)
        for name in old.namelist():require(old.read(name)==z.read(PRESERVED.get(name,name)),'Prior source/history entry changed or missing: '+name)
        require(len(z.read(MICROBED))==3913561 and digest(z.read(MICROBED))==MICROBED_SHA,'Microbed not exact')
        require(not any(n.lower().endswith('.blend') for n in z.namelist()),'Scene accidentally included')
        count=len(z.namelist())
        with tempfile.TemporaryDirectory(prefix='verify_ak_v11_extracted_') as path:
            z.extractall(path)
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run(['bash','test_source_ak.sh'],cwd=path,env=env,capture_output=True,text=True,timeout=120)
            require(result.returncode==0,'Extracted source/tests failed:\n'+result.stdout+'\n'+result.stderr)
    require(sha(BASE)==BASE_SHA,'Base archive changed during packaging')
    temp.rename(OUT)
    result=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=sha(OUT),archive_entries=count,
        all_367_prior_entries_preserved=True,source_lock_and_crc_verified=True,
        extraction_source_check_and_pure_tests_passed=True,pure_test_counts=layout['pure_tests'],
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        selected_captures=[r['name'] for r in rows],strict_Z_admission_unchanged=True,
        fresh_end_to_end_rebuild_verified=False,rendered_by_packager=False,library_upload_performed=False)
    with (ROOT/'receipts/source_package_integrated_ak_v11.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--without-detail',action='store_true')
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--check',action='store_true');mode.add_argument('--package',action='store_true')
    args=p.parse_args();require(not(args.package and args.without_detail),'Final package requires AK detail')
    additions,rows,layout=prepare(not args.without_detail)
    result=package(additions,rows,layout) if args.package else dict(checked=True,entries_to_add=len(additions),captures=[r['name'] for r in rows],layout=layout,package_written=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
