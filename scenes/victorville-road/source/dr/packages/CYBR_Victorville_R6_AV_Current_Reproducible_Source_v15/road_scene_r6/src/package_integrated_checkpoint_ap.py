#!/usr/bin/env python3
"""Extend exact AL v12 with successful AP sources, receipts and portable replay.
No Blender, terrain solve, rendering, upload or remote write. CPU1 checks only.
"""
from __future__ import annotations
import argparse
import ast
import copy
import gc
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from package_integrated_checkpoint_ah import ROOT, MICROBED, MICROBED_SHA, HEIGHT_SHA, require, digest, sha, read, encoded
from package_integrated_checkpoint_ak import capture
from package_integrated_checkpoint_al import FIELD, FIELD_SHA, normalize_json
from render_checkpoint_ap import stage_pipeline

BASE=ROOT/'deliverables/CYBR_Victorville_R6_AL_Portable_Road_Components_Source_v12.zip'
BASE_SHA='ef496c4bd39a4051044b72a9aaa023bc59dbb497595e8de908d951f9f1978a3d'
OUT=ROOT/'deliverables/CYBR_Victorville_R6_AP_Portable_Road_Components_Source_v13.zip'
PRESERVED={'README.txt':'README_AL_V12_CHECKPOINT.txt','SOURCE_LOCK.json':'SOURCE_LOCK_AL_V12_CHECKPOINT.json','regenerate.sh':'regenerate_al_v12.sh'}
SELECTED=[('ap_correlated_margin_context','ap_context','AP'),('ap_correlated_margin_detail','ap_detail','AP')]
ENV=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
NEW_HELPERS={'assemble_road_margin_ap.py','road_margin_composition_ap.py','sample_final_surface_an.py','layered_scrub_ap.py','desert_scrub.py'}

def verify_base():
    require(BASE.stat().st_size==18990072 and sha(BASE)==BASE_SHA,'Immutable v12 differs')
    with zipfile.ZipFile(BASE) as z:
        require(z.testzip() is None,'v12 CRC failure')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==673 and len(set(z.namelist()))==673,'v12 entry count differs')
        require(set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'v12 lock closure differs')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'v12 hash differs: '+name)
        require(digest(z.read(MICROBED))==MICROBED_SHA and len(z.read(MICROBED))==3913561,'Approved microbed differs')
        require(digest(z.read(FIELD))==FIELD_SHA and len(z.read(FIELD))==2093642,'Exact Z ledger differs')
    return lock

def readme():
    return '''VICTORVILLE R6: AP PORTABLE SOURCE CHECKPOINT v13

STATUS
This source-only extension preserves every AL v12 payload and adds the exact
successful AP context and diagnostic detail helper snapshots. It remains an unfinished road
scene candidate. Context visual review found a clear scene-scale improvement;
whole-scene USER ACCEPTANCE and AP material-quality acceptance have not been given. Fresh clean-directory full
end-to-end regeneration remains UNVERIFIED. Packaging ran only CPU1 small pure
tests, ledger split checks, archive hashes/CRC and extracted replay-layout checks.
It did not launch Blender, solve the terrain, build a scene, render or upload.

WHAT AP CHANGES AND WHAT IT DOES NOT PROVE
One authored metric historical distribution coordinates fine/gravel exposure,
legacy K clast placement and layered scrub on sampled current terrain triangles.
The 64-body clast bank uses actual legacy K geometry at unchanged metric size
(approximately 6.7--31.2 mm measured horizontal bounding diagonal). New clasts
are partially embedded; individual contact/collision dynamics are not solved.
The context records 5,507 new clasts and 210 shared-mesh plant instances.
Approved R5D prototype geometry, materials and scale remain untouched. Existing
fine-grain scene origins are lowered by up to 0.62748 mm. The terrain and road
geometry are unchanged by AP. Ground shading uses a scene material copy with
bounded authored mixtures; this does not validate optics, storm mass transport,
sediment dynamics, botanical identity, measured site conditions or Victorville
reconstruction. No reference-photo pixels become scene data.
Known limits: a broad smooth fine strip, scalloped pavement contact, somewhat
even clasts within patches, shrubs mainly on the left, and simpler far hills
and opposite shoulder. The matched AP close exposed excessive fine-surface
smoothing from extra burial/normal attenuation and visibly faceted/repeated
legacy K coarse bodies. That close is DIAGNOSTIC ONLY and has not been promoted.
Existing AK/native-S close identities/history remain retained and unchanged.
Historical AL/AH/AI/AK approximations remain.
The exact sample_final_surface_an.py file is required by AP's triangle sampler.
Its AN diagnostic/film job settings are disabled; AN/AO diagnostic scenes and
results are not included as current scene evidence.

PRESERVATION AND EXACT INPUTS
All 673 v12 payloads remain byte-identical after extraction. The three replaced
top-level names are retained exactly as README_AL_V12_CHECKPOINT.txt,
SOURCE_LOCK_AL_V12_CHECKPOINT.json and regenerate_al_v12.sh. Earlier histories
remain unchanged. Approved microbed: 3,913,561 bytes; SHA256:
''' + MICROBED_SHA + '''
The exact existing 2,093,642-byte Z numerical ledger remains pinned at
road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz; SHA256:
''' + FIELD_SHA + '''
It is separate from inherited builders' output receipts. Do not replace this
input or weaken semantic admission when a fresh build fails. The adapter also
checks admitted scene image stock and ownership. Numerical regeneration across
renderer/NumPy versions has not been established as byte-identical.
No .blend, rendered PNG/EXR, native GeometryHeight.npy, or generated AH_FIELDS
cache is bundled. Those are regeneration requirements. Named historical images
and raw native guides were verified during packaging but are not bundled.

LOSSLESS ZIP_LZMA
Large JSON entries use standard ZIP method 14, losslessly compressed. Some OS
unzip tools lack support. Python 3 with the standard lzma module can extract:
  python -m zipfile -e CYBR_Victorville_R6_AP_Portable_Road_Components_Source_v13.zip extracted_ap
No inherited payload is silently dropped to reduce archive size.

EXACT CAPTURES AND PUBLIC EVIDENCE
ap_context: ap_correlated_margin_context, guided 1000 x 667, 24 Cycles samples,
201.103 s, 4,334.855 MiB historical peak, declared 4,480 MiB cap, guard passed.
ap_detail (diagnostic only, excluded from latest): ap_correlated_margin_detail,
guided 1000 x 667, 32 Cycles samples,
231.659 s, 3,075.684 MiB historical peak, declared 4,480 MiB cap, guard passed.
Both share the exact captured pipeline under checkpoint_pipeline_sources/.
Historical canonical JSON copies are under historical_captures_ap/ and
historical_evidence_ap/. Only paths change semantically; canonical JSON formatting
also differs. The evidence manifest records original-local and packaged hashes
plus path-only normalization proofs. Historical preflight remains explicitly
pre-render evidence, not current completion status. Comparison scripts require
separately rebuilt original-named image files; they are not replay prerequisites.

PORTABLE REPLAY
Use a fresh extraction. Requirements inherited from v12: Blender 4.3.2 with its
Python/NumPy; Python 3 with NumPy/SciPy/Pillow; Linux bash and ps; official OIDN
2.5.1 executable in OIDN_BIN. No runtime or installer is bundled.
  bash test_source_ap.sh
  bash regenerate.sh build-only
  bash regenerate.sh render-only
  bash regenerate.sh preview
  python road_scene_r6/src/render_checkpoint_ap.py --role ap_context --tag ap_context_repeat
  python road_scene_r6/src/render_checkpoint_ap.py --role ap_detail --tag ap_detail_repeat
  python road_scene_r6/src/render_checkpoint_ap.py --role all --tag all_versions
Default latest selection renders AP context only. AP detail requires explicit
--role ap_detail (or --role all, which includes all diagnostic/historical roles).
Build-only chains through the
unchanged historical source/build wrappers to Z. All older replay entrypoints
and templates remain available. Native GeometryHeight.npy must reproduce SHA256:
''' + HEIGHT_SHA + '''
Replay uses the unchanged strict validation-only Z semantic admission function,
schema, tolerances and negative-control contract. It records the newly admitted
scene's actual serialized SHA; it does not require an old .blend byte hash.
Captured render.py and helpers stay byte-identical. AP staging adds an exact
sibling vegetation directory beside pipeline and src to satisfy captured lookup.
Each clean replay receipt must reproduce the selected captured pipeline digest.
AH_FIELDS.npz is freshly generated, never injected from historical captures.

TEST SCOPE
The tiny AP suite checks 7 authored-field fixtures and 7 exact-triangle-sampler
fixtures, then reruns the original offline shrub test on all 6 variants, 78,296
vertices, reproducing its complete historical receipt. Blender is stubbed only
in that offline geometry fixture. These are not rendered visual validation or
API integration tests. The inherited pure suites are separately rerun.
Extracted tests verify source-lock closure, all prior templates, exact pinned
Z split against both AP captured ownership receipts, pipeline/src/vegetation
lookup, and rejection of corrupt shrub sources and corrupt pinned ledger inputs.
Only the absent generated height map is replaced by an explicitly synthetic tiny
layout fixture; the production SHA and strict source admission stay unchanged.
No full-domain solver, historical actual AH topology/cache test, native/4K
performance test, end-to-end rebuild or user visual approval is claimed.
'''

def prepare():
    lock=verify_base();additions={};proofs=[];newrows=[];tests=[];original_hashes={};public_hashes={};checks=[]
    def add(name,data):
        if isinstance(data,str):data=data.encode()
        require(name not in additions or additions[name]==data,'Conflicting new payload: '+name)
        additions[name]=data
    def evidence(path,target):
        raw=path.read_bytes();data,count=normalize_json(raw)
        add(target,data);original_hashes[target]=digest(raw);public_hashes[target]=digest(data)
        checks.append(dict(path=target,format='JSON',path_values_or_keys_normalized=count,semantic_changes_only_paths=True,canonical_serialization=True))
    with zipfile.ZipFile(BASE) as old:
        original=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_al.json'))
        ah=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ah.json'))
        require(original['source_admission']==ah['source_admission'],'Inherited strict Z contract differs')
        for source,target in PRESERVED.items():add(target,old.read(source))
        for key,h in original['source_admission']['files_sha256'].items():require(digest(old.read(key))==h,'Semantic source changed')
        for name in ('render_checkpoint_ah.py','render_checkpoint_al.py','validate_checkpoint_source_ah.py'):
            require(old.read('road_scene_r6/src/'+name)==(ROOT/'src'/name).read_bytes(),'Inherited live source changed: '+name)
    for name,role,generation in SELECTED:
        row,files,reports,proof=capture(name,role,generation);folder=ROOT/'captures'/name
        require(read(folder/'job.json')==read(folder/'INTERNAL_PANEL.png.json')['job'],'AP job mutated')
        require(NEW_HELPERS<=files.keys(),'AP captured helpers incomplete')
        require('apply_refined_film_an.py' not in files,'AN film diagnostic contaminates AP')
        require(row['settings']['road_margin_ap']=={'enabled':True},'AP settings changed')
        require(not any(row['settings'].get(k) for k in ('sample_final_surface_an','refined_film_an')),'AN diagnostic enabled')
        margin=read(folder/'ROAD_MARGIN_AP.json')
        require(all(margin[k] is False for k in ('terrain_geometry_changed','road_geometry_changed','approved_R5D_prototype_materials_scale_changed')),'AP invariant receipt differs')
        require(max(r['max_burial_m'] for r in margin['existing_fine_grain_burial'].values())<=.0006275,'Unexpected R5D origin burial')
        require(read(folder/'ROAD_FILM_OWNERSHIP_AL.json')['source_field_sha256']==FIELD_SHA,'AP used another Z ledger')
        row['settings']['road_film_ownership_al']['fields_path']=FIELD
        row['input_relocations'].append(dict(job_key_path=['road_film_ownership_al','fields_path'],package_path=FIELD,sha256=FIELD_SHA))
        row['vegetation_helper_names']=['layered_scrub_ap.py','desert_scrub.py']
        row['default_latest']=role=='ap_context'
        row['status']='scene-scale progress candidate, not accepted' if role=='ap_context' else 'diagnostic close, not promoted'
        proof.update(exact_Z_field_input_sha256=FIELD_SHA,AN_diagnostic_enabled=False,AP_sampler_reuses_exact_AN_named_helper=True,
            elapsed_seconds=read(folder/'resource_receipt.json')['elapsed_seconds'])
        newrows.append(row);proofs.append(proof)
        for filename,data in files.items():add('road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'+filename,data)
        for path in sorted(folder.rglob('*.json')):
            evidence(path,'road_scene_r6/historical_captures_ap/'+name+'/'+path.relative_to(folder).as_posix())
    rows=original['captures']+newrows
    require(len({r['role'] for r in rows})==len(rows),'Duplicate replay role')
    for name in ('render_checkpoint_ap.py','validate_source_checkpoint_ap.py','package_integrated_checkpoint_ap.py','compare_ap_margin.py'):
        add('road_scene_r6/src/'+name,(ROOT/'src'/name).read_bytes())
    # Exact captured bytes are authoritative for these new standalone source copies.
    for name in sorted(NEW_HELPERS):
        target='vegetation/' if name in ('layered_scrub_ap.py','desert_scrub.py') else 'src/'
        add('road_scene_r6/'+target+name,additions['road_scene_r6/checkpoint_pipeline_sources/'+newrows[0]['pipeline_sha256']+'/'+name])
    for path in sorted((ROOT/'checkpoint_tests_ap').rglob('*')):
        if path.is_file() and path.suffix in ('.py','.json'):add('road_scene_r6/'+path.relative_to(ROOT).as_posix(),path.read_bytes())
    for path in (ROOT/'receipts/ap_source_preflight.json',ROOT/'receipts/ap_visual_comparison.json',ROOT/'vegetation/layered_scrub_ap_offline_receipt.json'):
        evidence(path,'road_scene_r6/historical_evidence_ap/'+path.name)
    add('road_scene_r6/receipts/integrated_render_templates_ap.json',encoded(dict(schema_version=4,
        source_admission=original['source_admission'],captures=rows,default_selection='AP context only; detail diagnostic excluded',
        immutable_numerical_inputs=original['immutable_numerical_inputs'])))
    with tempfile.TemporaryDirectory(prefix='checkpoint_ap_pure_') as temp:
        root=Path(temp);seen=set()
        for row in newrows:
            if row['pipeline_sha256'] in seen:continue
            seen.add(row['pipeline_sha256'])
            snapshot=root/'road_scene_r6/checkpoint_pipeline_sources'/row['pipeline_sha256'];snapshot.mkdir(parents=True)
            for name in row['pipeline_files_sha256']:
                (snapshot/name).write_bytes(additions['road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'+name])
            stage_pipeline(row,root/'layout'/row['role'],root=root/'road_scene_r6')
            receipt=root/(row['role']+'.json')
            result=subprocess.run([sys.executable,str(ROOT/'checkpoint_tests_ap/run_snapshot_tests.py'),'--snapshot',str(snapshot),'--receipt',str(receipt)],env=ENV,capture_output=True,text=True,timeout=120)
            require(result.returncode==0,'AP pure checks failed:\n'+result.stdout+'\n'+result.stderr)
            report=read(receipt);require(report['passed'] and report['skipped']==0,'AP pure checks incomplete')
            tests.append(report);add('road_scene_r6/receipts/portable_ap_tests_v13.json',encoded(report))
    add('test_source_ap.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
bash test_source_al.sh
python road_scene_r6/src/render_checkpoint_ap.py --check-sources
python road_scene_r6/src/validate_source_checkpoint_ap.py
python - <<'TESTS'
import json,subprocess,sys
from pathlib import Path
root=Path('road_scene_r6');seen=set()
for row in json.loads((root/'receipts/integrated_render_templates_ap.json').read_text())['captures']:
    if row.get('generation')=='AP' and row['pipeline_sha256'] not in seen:
        seen.add(row['pipeline_sha256'])
        subprocess.run([sys.executable,str(root/'checkpoint_tests_ap/run_snapshot_tests.py'),'--snapshot',str(root/'checkpoint_pipeline_sources'/row['pipeline_sha256'])],check=True)
TESTS
''')
    add('regenerate.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-preview}" in preview|build-only|render-only) ;; *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;; esac
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then echo "Unset MATERIAL_PATH_MAP_FILE." >&2; exit 2; fi
python road_scene_r6/src/render_checkpoint_ap.py --check-sources
if [ "${1:-preview}" != build-only ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to official OIDN 2.5.1 oidnDenoise}"
  test -f "$OIDN_BIN" && test -x "$OIDN_BIN"
fi
if [ "${1:-preview}" != render-only ]; then bash regenerate_al_v12.sh build-only; fi
if [ "${1:-preview}" != build-only ]; then python road_scene_r6/src/render_checkpoint_ap.py; fi
''')
    add('README.txt',readme())
    add('INTEGRATED_COMPONENT_EVIDENCE_AP_V13.json',encoded(dict(base_v12_archive_sha256=BASE_SHA,
        every_673_v12_entry_preserved=True,top_level_original_names_preserved_as=PRESERVED,
        selected_new_captures=proofs,latest_roles=['ap_context'],diagnostic_roles=['ap_detail'],
        original_local_evidence_sha256=original_hashes,packaged_public_evidence_sha256=public_hashes,
        evidence_normalization_checks=checks,evidence_policy='Original hashes retained; canonical JSON changes only public paths semantically',
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        pinned_Z_ledger=dict(package_path=FIELD,bytes=2093642,sha256=FIELD_SHA),
        new_pure_test_counts=[r['tests_run'] for r in tests],scrub_variants_tested=6,
        captured_source_bytes_changed=False,strict_Z_admission_unchanged=True,
        inherited_Z_scene_byte_hash_used_as_admission=False,fresh_end_to_end_rebuild_verified=False,
        new_render_performed_by_packager=False,whole_scene_user_approved=False,AP_material_quality_accepted=False,
        new_physics_or_site_realism_claim=False,compression='Standard lossless ZIP_LZMA for large JSON')))
    with zipfile.ZipFile(BASE) as old:
        for name,data in additions.items():
            if name in lock['files'] and name not in PRESERVED:require(old.read(name)==data,'Prior payload would change: '+name)
    for name,data in additions.items():
        require(Path(name).suffix in ('.py','.json','.txt','.sh','.log'),'Unexpected new binary')
        text=data.decode()
        for fragment in ('/'+'workspace/', '/'+'home/agent/', '/'+'root/'):require(fragment not in text,'Private path in new payload: '+name)
        if name.endswith('.py'):ast.parse(text,filename=name)
        if name.endswith('.sh'):subprocess.run(['bash','-n'],input=text,text=True,check=True)
    files=dict(lock['files']);files.update({name:digest(data) for name,data in additions.items()})
    add('SOURCE_LOCK.json',encoded(dict(version='R6 portable AP source checkpoint v13',base_v12_archive_sha256=BASE_SHA,
        files=files,pinned_inputs_verified=lock['pinned_inputs_verified'],immutable_ground_verified=lock['immutable_ground_verified'],
        additional_pinned_numerical_input=lock['additional_pinned_numerical_input'],
        whole_scene_user_approved=False,fresh_end_to_end_rebuild_verified=False)))
    return additions,rows,tests

def package(additions,rows,tests):
    temp=OUT.with_suffix('.tmp.zip');require(not OUT.exists() and not temp.exists(),'Preserve existing archive/staging')
    require(shutil.disk_usage(ROOT).free>250_000_000,'Need space for archive/extraction and 120 MiB reserve')
    lzma_entries=[]
    with zipfile.ZipFile(BASE) as old,zipfile.ZipFile(temp,'x') as new:
        def write(name,data,info=None):
            if info is None:
                info=zipfile.ZipInfo(name);info.create_system=3
                info.external_attr=(stat.S_IFREG|(0o755 if name.endswith('.sh') else 0o644))<<16
            method=zipfile.ZIP_LZMA if name.endswith('.json') and len(data)>100000 else zipfile.ZIP_DEFLATED
            if method==zipfile.ZIP_LZMA:lzma_entries.append(name)
            new.writestr(info,data,compress_type=method,compresslevel=8 if method==zipfile.ZIP_DEFLATED else None)
        # Stream previous entries one at a time rather than holding the whole ZIP.
        for info in old.infolist():
            if info.filename not in additions:write(info.filename,old.read(info.filename),copy.copy(info))
        for name,data in additions.items():write(name,data)
    require(temp.stat().st_size<25_000_000,'Unexpected source archive growth')
    additions.clear();gc.collect()
    with zipfile.ZipFile(temp) as z,zipfile.ZipFile(BASE) as old:
        require(z.testzip() is None,'v13 CRC failed')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'v13 lock closure differs')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'v13 hash differs: '+name)
        for name in old.namelist():require(old.read(name)==z.read(PRESERVED.get(name,name)),'Prior payload changed: '+name)
        require(digest(z.read(MICROBED))==MICROBED_SHA and len(z.read(MICROBED))==3913561,'Microbed differs')
        require(digest(z.read(FIELD))==FIELD_SHA and len(z.read(FIELD))==2093642,'Z ledger differs')
        require(not any(n.lower().endswith(('.blend','.png','.exr','.pfm','.npy')) for n in z.namelist()),'Generated output bundled')
        count=len(z.namelist());extracted_bytes=sum(i.file_size for i in z.infolist())
        require(shutil.disk_usage(ROOT).free>extracted_bytes+120*1024**2+8*1024**2,'Extraction would violate disk reserve')
        with tempfile.TemporaryDirectory(prefix='verify_ap_v13_extracted_') as path:
            z.extractall(path)
            result=subprocess.run(['bash','test_source_ap.sh'],cwd=path,env=ENV,capture_output=True,text=True,timeout=240)
            require(result.returncode==0,'Extracted source/test check failed:\n'+result.stdout+'\n'+result.stderr)
            test_output=result.stdout+'\n'+result.stderr
    require(sha(BASE)==BASE_SHA,'Base archive changed')
    temp.rename(OUT)
    result=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=sha(OUT),archive_entries=count,
        all_673_prior_payloads_preserved=True,original_top_entries_archived_as=PRESERVED,
        source_lock_and_crc_verified=True,extracted_source_layout_and_pure_tests_passed=True,
        new_pure_test_counts=[r['tests_run'] for r in tests],scrub_variants_checked=6,
        inherited_pure_suites_rerun=True,pinned_field_bytes=2093642,pinned_field_sha256=FIELD_SHA,
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        lossless_lzma_json_entries=len(lzma_entries),selected_new_captures=[r[0] for r in SELECTED],
        latest_roles=['ap_context'],diagnostic_roles=['ap_detail'],AP_material_quality_accepted=False,
        strict_Z_admission_unchanged=True,fresh_end_to_end_rebuild_verified=False,
        rendered_by_packager=False,library_upload_performed=False,new_evidence_path_only_normalization_verified=True,
        new_evidence_private_machine_paths_absent=True,whole_scene_user_approved=False)
    with (ROOT/'receipts/source_package_integrated_ap_v13.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    with (ROOT/'receipts/source_package_integrated_ap_v13_tests.log').open('x') as f:f.write(test_output)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check',action='store_true');m.add_argument('--package',action='store_true');args=p.parse_args()
    if hasattr(os,'sched_getaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    additions,rows,tests=prepare()
    result=package(additions,rows,tests) if args.package else dict(checked=True,new_entries=len(additions),new_pure_test_counts=[r['tests_run'] for r in tests])
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
