#!/usr/bin/env python3
"""Make source-only AL v12 from exact AK v11; never build/render/upload.
Large JSON entries use standard lossless ZIP_LZMA to retain all old payloads.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from package_integrated_checkpoint_ah import (ROOT,SOURCE_SHA,MICROBED,MICROBED_SHA,
    HEIGHT,HEIGHT_SHA,require,digest,sha,read,public,encoded)
from package_integrated_checkpoint_ak import capture
from render_checkpoint_ah import stage_pipeline

BASE=ROOT/'deliverables/CYBR_Victorville_R6_AK_Portable_Road_Components_Source_v11.zip'
BASE_SHA='87da98b3e3c7a60dec52dad9da1de7b3f66763ec9e8173e9dc4182750b7fa224'
OUT=ROOT/'deliverables/CYBR_Victorville_R6_AL_Portable_Road_Components_Source_v12.zip'
PRESERVED={'README.txt':'README_AK_V11_CHECKPOINT.txt',
           'SOURCE_LOCK.json':'SOURCE_LOCK_AK_V11_CHECKPOINT.json',
           'regenerate.sh':'regenerate_ak_v11.sh'}
SELECTED=[('al_film_ownership_detail','al_detail','AL'),
          ('al_supported_ownership_context','al_context','AL')]
FIELD_LOCAL=ROOT/'receipts/runoff_film_z_fields.npz'
FIELD='road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz'
FIELD_SHA='bdd8176d29209c21d97aab02c44743ab6b2ff2a9f4f25989513f1dd5636400d2'
ENV=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')


def verify_base():
    require(BASE.stat().st_size==17085143 and sha(BASE)==BASE_SHA,'Immutable v11 ZIP differs')
    with zipfile.ZipFile(BASE) as z:
        require(z.testzip() is None,'v11 CRC failure')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==547 and len(set(z.namelist()))==547,'v11 entry count differs')
        require(set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'v11 closure mismatch')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'v11 lock mismatch: '+name)
        require(len(z.read(MICROBED))==3913561 and digest(z.read(MICROBED))==MICROBED_SHA,'Approved microbed changed')
    return lock


def readme():
    return '''VICTORVILLE R6: AL PORTABLE SOURCE CHECKPOINT v12

STATUS
Source-only extension of AK v11. Both successful AL executable snapshots remain exact; original JSON evidence
is retained as canonical, public-path copies with original local file hashes. This remains an unfinished scene checkpoint;
whole-scene visual acceptance and a fresh full build/render are UNVERIFIED.
This packaging pass performs CPU1 pure tests, exact small-ledger split checks,
archive CRC/hash checks, and extracted source/replay-layout checks only. It does
not load Blender, build a scene, rerun the full terrain model, render, or upload.

AL CHANGES AND LIMITS
The film correction separates historical Z pavement-owned stock from soil-owned
stock before image interpolation. Soil stock no longer falsely shades newly
exposed asphalt. Inventory remains conserved and unmodified; this is a numerical
ownership/representation fix, not a new transport solve or exact subcell model.
The historical ownership grid is 25 mm. Neither every grain's visible realization
nor calibrated film optics is proved.
The AL context additionally continues bank support from AH foundation/bed change
through Y=2..8.2 m. The existing Y<=2 m AC region and boundary-straddling triangles
are protected. No new sheet, remeshing, particles, random edge pattern, or mass
conservation claim is added. Context receipt: 9,040 changed vertices, movement
-18.199 to +16.239 mm; exact full-strength overlap audit: 1,094 polygons, zero
penetrations, minimum clearance approximately 0.800 mm. This historical mesh-pair
proof excludes onset/fade, particles, and shader normals. It does not establish
site realism, new physics, validated hydraulics, or whole-scene visual quality.
Inherited AH/AI/AJ/AK approximations and the shallow edge appearance remain.
Unfinished AN sources and results are not included or used.

PRESERVATION AND COMPRESSION
All 547 v11 payloads remain byte-identical after extraction. Only README.txt,
SOURCE_LOCK.json and regenerate.sh are replaced at their top-level names; exact
old bytes remain as README_AK_V11_CHECKPOINT.txt,
SOURCE_LOCK_AK_V11_CHECKPOINT.json and regenerate_ak_v11.sh. All earlier history
and exact approved microbed are retained. Microbed: 3,913,561 bytes; SHA256:
''' + MICROBED_SHA + '''
Large JSON entries use standard ZIP method 14 (ZIP_LZMA), losslessly recompressed
without changing their payload bytes. Some basic OS unzip utilities cannot read
method 14. Python 3 with its standard lzma module can extract this archive:
  python -m zipfile -e CYBR_Victorville_R6_AL_Portable_Road_Components_Source_v12.zip extracted_al
No dependency is silently dropped to meet the size budget.

EXACT PINNED NUMERICAL INPUT
AL requires receipts/runoff_film_z_fields.npz from its original successful runs.
Regeneration of byte-identical numerical fields across NumPy/Blender versions has
not been established, so the exact 2,093,642-byte ledger is bundled as an explicit
immutable source input at:
  road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz
SHA256:
''' + FIELD_SHA + '''
This sole new numerical-input exception contains all original arrays, unchanged.
It is separate from the inherited builder's output receipts/runoff_film_z_fields.npz,
so building Z cannot overwrite it. Replay checks its exact SHA and points AL at
this pinned copy. The captured adapter additionally checks its image stock and
ownership against the admitted scene. A mismatching rebuilt Z image fails closed;
do not substitute a new ledger or weaken admission to force a replay.
No .blend, native generated height map, AH_FIELDS cache, render image, or raw EXR
is bundled. Those outputs remain rebuild requirements. The original images and
native guides named by both clean receipts were verified before packaging;
those receipts are historical evidence, not bundled image data.

EXACT CAPTURES AND NORMALIZED RECEIPTS
  al_detail: al_film_ownership_detail, film ownership fix without far-bank change
  al_context: al_supported_ownership_context, film ownership plus AL bank support
Both are guided 1000 x 667, 24-sample Cycles captures with declared 4,480 MiB caps.
Their historical peak RSS was 3,079.324 MiB (detail) and 4,266.785 MiB (context).
Exact selected helpers are under checkpoint_pipeline_sources/<captured digest>.
Canonical public-path receipt copies are under road_scene_r6/historical_captures_al/.
JSON values differ from the originals only by path normalization; object keys and
formatting are canonically serialized. These JSON copies are not byte-identical
to the original local receipts. Additional public-path numerical-test evidence
is under historical_evidence_al/. Log normalization replaces the known project
path only. The evidence manifest records both original local SHA256 hashes and
packaged-copy hashes, plus path-only normalization checks. Captured executable
helpers and the exact pinned numerical source input remain byte-identical.

PORTABLE REPLAY
Use a fresh extraction. Requirements inherited from v11: Blender 4.3.2 with
Python/NumPy, Python 3 with NumPy/SciPy/Pillow, Linux bash and ps, official OIDN
2.5.1 executable in OIDN_BIN. No runtime or installer is bundled.
  bash test_source_al.sh
  bash regenerate.sh build-only
  bash regenerate.sh render-only
  bash regenerate.sh preview
  python road_scene_r6/src/render_checkpoint_al.py --role al_detail --tag al_detail_repeat
  python road_scene_r6/src/render_checkpoint_al.py --role al_context --tag al_context_repeat
  python road_scene_r6/src/render_checkpoint_al.py --role all --tag all_versions
Default latest selection renders both AL captures. Build-only uses unchanged
inherited wrappers through Z. Historical AK/AH entrypoints remain available.
Native GeometryHeight.npy must regenerate to its inherited exact SHA256:
''' + HEIGHT_SHA + '''
The unchanged inherited validation-only strict Z semantic guard remains required.
AL's source_admission contract equals AK/AH exactly; no schema, tolerance, guard,
or negative-control requirement is weakened. Each run records the actual rebuilt
scene hash and must reproduce its selected captured pipeline digest. Generated
AH_FIELDS.npz is recomputed per fresh run and is never pulled from old captures.
Seven inherited overwritten reports continue to use their immutable historical
copies for source-lock verification, exactly as in v11.

TEST SCOPE
The portable synthetic AL suite uses original ownership tests and original pure
bank fixtures plus dedicated exact-overlap/adapter regressions against selected
captured code. Original tests remain separately preserved without edits. The
actual historical AH/topology/cache test is not rerun or silently counted as
passed. Its historical receipt/log is retained. Exact pinned Z-ledger splitting
is checked separately against both captured ownership receipts and output-matrix
hashes; it is not a new terrain/runoff simulation.
Extracted source/layout checks stage exact helpers, reject corrupted snapshots
and numerical inputs, verify both latest selections and all prior templates, and
exercise portable input relocation with a tiny explicit stand-in solely for the
unbuilt native height map. This does not establish actual Blender compatibility,
fresh end-to-end regeneration, performance at native/4K scale, or scene quality.
'''


def normalize_json(raw):
    """Only path strings/keys may change semantically; serialization is canonical."""
    value=json.loads(raw);normalized=public(value);count=0
    def compare(before,after):
        nonlocal count
        if isinstance(before,dict):
            require(isinstance(after,dict) and len(before)==len(after),'JSON object shape changed')
            for key,item in before.items():
                target=public(key)
                if target!=key:count+=1
                require(target in after,'JSON key changed beyond public path')
                compare(item,after[target])
        elif isinstance(before,list):
            require(isinstance(after,list) and len(before)==len(after),'JSON array shape changed')
            for first,second in zip(before,after):compare(first,second)
        elif before!=after:
            require(isinstance(before,str) and before.startswith('/') and public(before)==after,'Non-path JSON value changed')
            count+=1
    compare(value,normalized)
    data=encoded(value)
    require(json.loads(data)==normalized,'Canonical evidence differs from path-only normalized values')
    return data,count


def prepare():
    lock=verify_base(); additions={}; proofs=[]; newrows=[]; testrows=[]; original_receipts={}; packaged_receipts={}; normalization=[]
    def add(name,data):
        if isinstance(data,str):data=data.encode()
        if name in additions:require(additions[name]==data,'Conflicting new entry: '+name)
        additions[name]=data
    with zipfile.ZipFile(BASE) as old:
        original=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ak.json'))
        ah=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ah.json'))
        require(original['source_admission']==ah['source_admission'],'Inherited strict contract changed')
        for source,target in PRESERVED.items():add(target,old.read(source))
        for key,h in original['source_admission']['files_sha256'].items():require(digest(old.read(key))==h,'Semantic source differs')
        for name in ('render_checkpoint_ah.py','render_checkpoint_ak.py','validate_checkpoint_source_ah.py',
                     'package_integrated_checkpoint_ah.py','package_integrated_checkpoint_ak.py'):
            require(old.read('road_scene_r6/src/'+name)==(ROOT/'src'/name).read_bytes(),'Inherited source changed: '+name)
    require(FIELD_LOCAL.stat().st_size==2093642 and sha(FIELD_LOCAL)==FIELD_SHA,'Exact captured film fields unavailable')
    add(FIELD,FIELD_LOCAL.read_bytes())
    for name,role,generation in SELECTED:
        row,files,reports,proof=capture(name,role,generation)
        folder=ROOT/'captures'/name
        require(read(folder/'job.json')==read(folder/'INTERNAL_PANEL.png.json')['job'],'AL job must not mutate')
        require('road_film_ownership_al.py' in files and 'sample_final_surface_an.py' not in files,'AL capture contaminated/incomplete')
        require(row['settings']['road_film_ownership_al']=={'fields_path':str(FIELD_LOCAL)},'Unexpected AL input')
        ownership=read(folder/'ROAD_FILM_OWNERSHIP_AL.json')
        require(ownership['source_field_sha256']==FIELD_SHA,'AL capture used a different field')
        row['settings']['road_film_ownership_al']['fields_path']=FIELD
        row['input_relocations'].append(dict(job_key_path=['road_film_ownership_al','fields_path'],package_path=FIELD,sha256=FIELD_SHA))
        if role=='al_context':
            require({'contact_bank_continuity_al.py','contact_triangle_clearance_al.py'}<=files.keys(),'Context bank/audit helper absent')
            bank=read(folder/'CONTACT_BANK_CONTINUITY_AL.json'); audit=bank['exact_triangle_clearance']
            require(bank['bounds_xy_m']==[-3.75,-3.04,2.,8.2] and bank['exact_zero_below_y_2'] is True and bank['triangle_boundary_leakage'] is False,'Historical AL bounds did not qualify')
            require(audit['penetrating_overlap_polygons']==0 and audit['overlap_polygons']==1094,'Historical exact overlap audit differs')
        proof.update(exact_Z_field_input_sha256=FIELD_SHA,unfinished_AN_excluded=True)
        newrows.append(row);proofs.append(proof)
        for filename,data in files.items():add('road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'+filename,data)
        for path in sorted(folder.rglob('*.json')):
            target='road_scene_r6/historical_captures_al/'+name+'/'+path.relative_to(folder).as_posix()
            raw=path.read_bytes();data,count=normalize_json(raw)
            add(target,data);original_receipts[target]=digest(raw);packaged_receipts[target]=digest(data)
            normalization.append(dict(path=target,format='JSON',path_values_or_keys_normalized=count,semantic_changes_only_paths=True,canonical_serialization=True))
    rows=original['captures']+newrows
    require(len({r['role'] for r in rows})==len(rows),'Replay roles duplicated')
    for name in ('render_checkpoint_al.py','validate_source_checkpoint_al.py','package_integrated_checkpoint_al.py','compare_al_ownership.py'):
        add('road_scene_r6/src/'+name,(ROOT/'src'/name).read_bytes())
    for path in sorted((ROOT/'checkpoint_tests_al').rglob('*.py')):add('road_scene_r6/'+path.relative_to(ROOT).as_posix(),path.read_bytes())
    for name in ('al_bank_continuity_tests.json','al_film_ownership_split.json','al_bank_continuity_tests.log','al_bank_with_exact_audit_tests.log'):
        raw=(ROOT/'receipts'/name).read_bytes();target='road_scene_r6/historical_evidence_al/'+name
        if name.endswith('.json'):data,count=normalize_json(raw)
        else:
            text=raw.decode();count=text.count(str(ROOT));data=text.replace(str(ROOT),'road_scene_r6').encode()
        add(target,data);original_receipts[target]=digest(raw);packaged_receipts[target]=digest(data)
        normalization.append(dict(path=target,format='JSON' if name.endswith('.json') else 'log',path_values_or_keys_normalized=count,semantic_changes_only_paths=True,canonical_serialization=name.endswith('.json')))
    add('road_scene_r6/receipts/integrated_render_templates_al.json',encoded(dict(schema_version=3,
        source_admission=original['source_admission'],captures=rows,default_selection='latest AL generation',
        immutable_numerical_inputs=[dict(package_path=FIELD,sha256=FIELD_SHA,bytes=2093642)])))
    with tempfile.TemporaryDirectory(prefix='checkpoint_al_pure_') as temp:
        t=Path(temp)
        for row in newrows:
            snapshot=t/'road_scene_r6/checkpoint_pipeline_sources'/row['pipeline_sha256'];snapshot.mkdir(parents=True)
            for name in row['pipeline_files_sha256']:
                (snapshot/name).write_bytes(additions['road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'+name])
            stage_pipeline(row,t/'layout'/row['role'],root=t/'road_scene_r6')
            receipt=t/(row['role']+'.json')
            result=subprocess.run([sys.executable,str(ROOT/'checkpoint_tests_al/run_snapshot_tests.py'),'--snapshot',str(snapshot),'--receipt',str(receipt)],env=ENV,capture_output=True,text=True,timeout=120)
            require(result.returncode==0,'AL pure tests failed:\n'+result.stdout+'\n'+result.stderr)
            report=read(receipt);require(report['passed'] and not report['skipped'],'Portable tests incomplete')
            add('road_scene_r6/receipts/portable_'+row['role']+'_tests_v12.json',encoded(report));testrows.append(report)
    add('test_source_al.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
bash test_source_ak.sh
python road_scene_r6/src/render_checkpoint_al.py --check-sources
python road_scene_r6/src/validate_source_checkpoint_al.py
python - <<'TESTS'
import json,subprocess,sys
from pathlib import Path
root=Path('road_scene_r6')
for row in json.loads((root/'receipts/integrated_render_templates_al.json').read_text())['captures']:
    if row.get('generation')=='AL':
        subprocess.run([sys.executable,str(root/'checkpoint_tests_al/run_snapshot_tests.py'),'--snapshot',str(root/'checkpoint_pipeline_sources'/row['pipeline_sha256'])],check=True)
TESTS
''')
    add('regenerate.sh','''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-preview}" in preview|build-only|render-only) ;; *) echo "Usage: bash regenerate.sh [preview|build-only|render-only]" >&2; exit 2 ;; esac
if [ -n "${MATERIAL_PATH_MAP_FILE:-}" ]; then echo "Unset MATERIAL_PATH_MAP_FILE." >&2; exit 2; fi
python road_scene_r6/src/render_checkpoint_al.py --check-sources
if [ "${1:-preview}" != build-only ]; then
  : "${OIDN_BIN:?Set OIDN_BIN to official OIDN 2.5.1 oidnDenoise}"
  test -f "$OIDN_BIN" && test -x "$OIDN_BIN"
fi
if [ "${1:-preview}" != render-only ]; then bash regenerate_ak_v11.sh build-only; fi
if [ "${1:-preview}" != build-only ]; then python road_scene_r6/src/render_checkpoint_al.py; fi
''')
    add('README.txt',readme())
    add('INTEGRATED_COMPONENT_EVIDENCE_AL_V12.json',encoded(dict(base_v11_archive_sha256=BASE_SHA,
        every_547_v11_entry_preserved=True,top_level_original_names_preserved_as=PRESERVED,
        selected_new_captures=proofs,original_local_evidence_sha256=original_receipts,
        packaged_public_evidence_sha256=packaged_receipts,evidence_normalization_checks=normalization,
        evidence_policy='Original local SHA retained; JSON semantic changes limited to public paths, formatting canonicalized; packaged evidence copies not byte-identical', 
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        pinned_numerical_source_input=dict(path=FIELD,bytes=2093642,sha256=FIELD_SHA,
            reason='Exact captured input retained; full numerical regeneration byte-identity unverified'),
        new_pure_test_counts=[r['tests_run'] for r in testrows],captured_source_bytes_changed=False,
        strict_Z_admission_unchanged=True,fresh_end_to_end_rebuild_verified=False,
        source_only_with_explicit_exact_numerical_input=True,new_render_performed_by_packager=False,
        whole_scene_user_approved=False,new_physics_or_site_realism_claim=False,
        compression='Lossless standard ZIP_LZMA for large JSON; Python zipfile extraction supported')))
    with zipfile.ZipFile(BASE) as old:
        for name,data in additions.items():
            if name in lock['files'] and name not in PRESERVED:require(old.read(name)==data,'Prior payload would change: '+name)
    for name,data in additions.items():
        if name==FIELD:continue
        require(Path(name).suffix in ('.py','.json','.txt','.sh','.log'),'Unexpected new binary payload')
        text=data.decode()
        for fragment in ('/'+'workspace/', '/'+'home/agent/', '/'+'root/'):
            require(fragment not in text,'Private machine path in new source/evidence: '+name)
        if name.endswith('.py'):ast.parse(text,filename=name)
        if name.endswith('.sh'):subprocess.run(['bash','-n'],input=text,text=True,check=True)
    files=dict(lock['files']);files.update({name:digest(data) for name,data in additions.items()})
    add('SOURCE_LOCK.json',encoded(dict(version='R6 portable AL source checkpoint v12',base_v11_archive_sha256=BASE_SHA,
        files=files,pinned_inputs_verified=lock['pinned_inputs_verified'],immutable_ground_verified=lock['immutable_ground_verified'],
        additional_pinned_numerical_input=dict(package_path=FIELD,sha256=FIELD_SHA,bytes=2093642),
        whole_scene_user_approved=False,fresh_end_to_end_rebuild_verified=False)))
    return additions,rows,testrows


def package(additions,rows,testrows):
    temp=OUT.with_suffix('.tmp.zip');require(not OUT.exists() and not temp.exists(),'Preserve existing package/staging archive')
    require(shutil.disk_usage(ROOT).free>200_000_000,'Insufficient bounded packaging space')
    lzma_entries=[]
    with zipfile.ZipFile(BASE) as old,zipfile.ZipFile(temp,'x') as new:
        entries=[(i.filename,old.read(i.filename),copy.copy(i)) for i in old.infolist() if i.filename not in additions]
        entries += [(name,data,None) for name,data in additions.items()]
        for name,data,info in entries:
            if info is None:
                info=zipfile.ZipInfo(name);info.create_system=3
                info.external_attr=(stat.S_IFREG|(0o755 if name.endswith('.sh') else 0o644))<<16
            method=zipfile.ZIP_LZMA if name.endswith('.json') and len(data)>100000 else zipfile.ZIP_DEFLATED
            if method==zipfile.ZIP_LZMA:lzma_entries.append(name)
            new.writestr(info,data,compress_type=method,compresslevel=8 if method==zipfile.ZIP_DEFLATED else None)
    require(temp.stat().st_size<=19_000_000,'Package exceeds 19 MB budget: '+str(temp.stat().st_size))
    with zipfile.ZipFile(temp) as z,zipfile.ZipFile(BASE) as old:
        require(z.testzip() is None,'AL archive CRC failed')
        lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'AL lock closure differs')
        for name,h in lock['files'].items():require(digest(z.read(name))==h,'AL source lock mismatch: '+name)
        for name in old.namelist():require(old.read(name)==z.read(PRESERVED.get(name,name)),'Old payload missing/changed: '+name)
        require(len(z.read(MICROBED))==3913561 and digest(z.read(MICROBED))==MICROBED_SHA,'Exact microbed changed')
        require(digest(z.read(FIELD))==FIELD_SHA and len(z.read(FIELD))==2093642,'Exact ledger changed')
        require(not any(n.lower().endswith(('.blend','.png','.exr','.pfm','.npy')) for n in z.namelist()),'Unintended generated output bundled')
        count=len(z.namelist())
        with tempfile.TemporaryDirectory(prefix='verify_al_v12_extracted_') as path:
            z.extractall(path)
            result=subprocess.run(['bash','test_source_al.sh'],cwd=path,env=ENV,capture_output=True,text=True,timeout=180)
            require(result.returncode==0,'Extracted source/tests failed:\n'+result.stdout+'\n'+result.stderr)
            test_output=result.stdout+'\n'+result.stderr
    require(sha(BASE)==BASE_SHA,'Base archive changed')
    temp.rename(OUT)
    result=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=sha(OUT),archive_entries=count,
        all_547_prior_payloads_preserved=True,original_top_entries_archived_as=PRESERVED,
        source_lock_and_crc_verified=True,extraction_source_check_and_pure_tests_passed=True,
        new_pure_test_counts=[r['tests_run'] for r in testrows],inherited_pure_suite_rerun=True,
        pinned_field_bytes=2093642,pinned_field_sha256=FIELD_SHA,
        approved_microbed_bytes=3913561,approved_microbed_sha256=MICROBED_SHA,
        lossless_lzma_json_entries=len(lzma_entries),selected_new_captures=[r[0] for r in SELECTED],
        strict_Z_admission_unchanged=True,fresh_end_to_end_rebuild_verified=False,
        rendered_by_packager=False,library_upload_performed=False,
        new_evidence_path_only_normalization_verified=True,new_evidence_private_machine_paths_absent=True)
    with (ROOT/'receipts/source_package_integrated_al_v12.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    with (ROOT/'receipts/source_package_integrated_al_v12_tests.log').open('x') as f:f.write(test_output)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check',action='store_true');m.add_argument('--package',action='store_true');a=p.parse_args()
    additions,rows,testrows=prepare()
    result=package(additions,rows,testrows) if a.package else dict(checked=True,new_entries=len(additions),new_test_counts=[r['tests_run'] for r in testrows])
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
