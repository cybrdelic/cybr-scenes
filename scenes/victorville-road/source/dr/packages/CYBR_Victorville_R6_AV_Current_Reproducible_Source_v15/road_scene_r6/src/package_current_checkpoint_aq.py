#!/usr/bin/env python3
"""Current-only AQ v14 source/evidence packaging. No builds, solves or renders."""
import ast
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
from package_current_checkpoint_ap import ROOT,ENV,digest,file_sha,require,enc
from package_integrated_checkpoint_ak import capture
from package_integrated_checkpoint_al import normalize_json,FIELD,FIELD_SHA

BASE=ROOT/'deliverables/CYBR_Victorville_R6_AP_Current_Reproducible_Source_v13.zip'
BASE_SHA='d99ab7fbc3e88c6c585f009995d291c5bc8838f2bb8c078b1dc25b85d3b0d13c'
OUT=ROOT/'deliverables/CYBR_Victorville_R6_AQ_Current_Reproducible_Source_v14.zip'
CAPTURE='aq_continuous_contact_context'
NEW_SOURCES={'continuous_contact_aq.py','assemble_road_margin_aq.py','current_contact_film_aq.py','refined_film_event_an.py','flow_sediment_model_ao.py'}

def prepare():
    require(file_sha(BASE)==BASE_SHA,'Preserve current AP v13 archive')
    row,files,reports,proof=capture(CAPTURE,'aq_context','AQ')
    require(NEW_SOURCES<=files.keys(),'Exact AQ source dependency missing')
    folder=ROOT/'captures'/CAPTURE
    require(json.loads((folder/'job.json').read_text())==json.loads((folder/'INTERNAL_PANEL.png.json').read_text())['job'],'AQ captured job mutated')
    for key in ('continuous_contact_aq','road_margin_aq','current_contact_film_aq'):
        require(row['settings'][key]=={'enabled':True},'AQ recipe activation differs')
    require(not row['settings'].get('road_margin_ap'),'AP adapter unexpectedly selected')
    row['settings']['road_film_ownership_al']['fields_path']=FIELD
    row['input_relocations'].append(dict(job_key_path=['road_film_ownership_al','fields_path'],package_path=FIELD,sha256=FIELD_SHA))
    row.update(default_latest=True,status='Useful contact progress candidate; unfinished and not accepted',vegetation_helper_names=['layered_scrub_ap.py','desert_scrub.py'])
    contact=json.loads((folder/'CONTINUOUS_CONTACT_AQ.json').read_text());audit=contact['exact_triangle_clearance']
    require(contact['visible_y_m']==[0.,15.] and audit['overlap_polygons']==18482 and audit['penetrating_overlap_polygons']==0,'AQ actual contact proof differs')
    require(audit['minimum_linear_mesh_clearance_m']>=.0008,'AQ actual rounded clearance differs')
    film=json.loads((folder/'AQ_CURRENT_FILM.json').read_text())
    require(film['coverage']['missing_xy_count']==0 and film['class_ledger']['passed'] is True,'AQ current surface/film proof failed')
    kept={};omitted={};original_hashes={};public_hashes={};normalization=[]
    with zipfile.ZipFile(BASE) as old:
        require(old.testzip() is None,'AP base CRC failed')
        oldlock=json.loads(old.read('SOURCE_LOCK.json'))
        oldtemplate=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_ap.json'))
        priorclosure=json.loads(old.read('road_scene_r6/receipts/current_dependency_closure_ap.json'))
        contract=oldtemplate['source_admission']
        for n in old.namelist():
            reason=None
            if n.startswith(('road_scene_r6/checkpoint_pipeline_sources/','road_scene_r6/historical_captures_ap/','road_scene_r6/historical_evidence_ap/')):
                reason='Previous AP capture snapshot/evidence; retained in AP v13'
            elif n in {'SOURCE_LOCK.json','README.txt','CURRENT_COMPONENT_EVIDENCE_AP_V13.json','test_source_current_ap.sh',
                       'road_scene_r6/receipts/integrated_render_templates_ap.json','road_scene_r6/receipts/current_dependency_closure_ap.json',
                       'road_scene_r6/receipts/ap_diagnostic_close_finding.json'}:
                reason='Previous current-version metadata or replay selection replaced explicitly'
            if reason:omitted[n]=dict(sha256=digest(old.read(n)),reason=reason)
            else:kept[n]=old.read(n)
        for n,h in oldlock['files'].items():
            if n in kept:require(digest(kept[n])==h,'AP dependency source differs')
        snapshot='road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'
        for n,data in files.items():kept[snapshot+n]=data
        # These new public source copies come only from the captured snapshot,
        # never from mutable live scene modules while another version is edited.
        for n in NEW_SOURCES:kept['road_scene_r6/src/'+n]=files[n]
        for path in sorted(folder.rglob('*.json')):
            target='road_scene_r6/historical_captures_aq/'+CAPTURE+'/'+path.relative_to(folder).as_posix()
            raw=path.read_bytes();data,count=normalize_json(raw);kept[target]=data
            original_hashes[target]=digest(raw);public_hashes[target]=digest(data)
            normalization.append(dict(path=target,semantic_changes_only_paths=True,canonical_serialization=True,path_values_or_keys_normalized=count))
        numeric=[]
        for name,key in (('AQ_FINAL_SURFACE.npz','source_sha256'),('AQ_CURRENT_FILM.npz','fields_sha256')):
            path=folder/name;h=file_sha(path);require(h==film[key],'Actual AQ numerical evidence differs')
            target='road_scene_r6/historical_numerical_aq/'+name;kept[target]=path.read_bytes()
            numeric.append(dict(package_path=target,bytes=len(kept[target]),sha256=h,role='Exact generated historical numerical evidence; never a replay cache/input'))
        source_test=ROOT/'receipts/continuous_contact_aq_source_tests.json';raw=source_test.read_bytes();data,count=normalize_json(raw)
        target='road_scene_r6/historical_evidence_aq/'+source_test.name;kept[target]=data
        original_hashes[target]=digest(raw);public_hashes[target]=digest(data)
        normalization.append(dict(path=target,semantic_changes_only_paths=True,canonical_serialization=True,path_values_or_keys_normalized=count))
        kept['road_scene_r6/receipts/integrated_render_templates_aq.json']=enc(dict(schema_version=5,source_admission=contract,
            captures=[row],default_selection='Current AQ context only',immutable_numerical_inputs=oldtemplate['immutable_numerical_inputs']))
        # Keep the exact minimal AH strict-admission contract and validators.
        require(json.loads(kept['road_scene_r6/receipts/integrated_render_templates_ah.json'])['source_admission']==contract,'Inherited guard contract changed')
        kept['regenerate.sh']=kept['regenerate.sh'].replace(b'render_checkpoint_ap.py',b'render_checkpoint_aq.py')
        for n in ('render_checkpoint_aq.py','validate_source_current_aq.py','check_aq_numerical_evidence.py','package_current_checkpoint_aq.py'):
            kept['road_scene_r6/src/'+n]=(ROOT/'src'/n).read_bytes()
        for path in sorted((ROOT/'checkpoint_tests_aq').rglob('*.py')):
            kept['road_scene_r6/'+path.relative_to(ROOT).as_posix()]=path.read_bytes()
        # Keep all prior exact builder/input closure, replacing only the inactive
        # snapshot and replay-root source with the exact AQ versions.
        required={n:h for n,h in priorclosure['retained_exact_required_files_sha256'].items() if n in kept}
        for n,data in files.items():required[snapshot+n]=digest(data)
        for n in NEW_SOURCES:required['road_scene_r6/src/'+n]=digest(files[n])
        for n in ('regenerate_y.sh','regenerate_z_v9.sh'):required[n]=digest(kept[n])
        require(all(digest(kept[n])==h for n,h in required.items()),'Required builder/input bytes changed')
        # Explicit import closure inside the captured helper bank, separate from
        # conservatively retained inherited builder sources.
        local_names={Path(n).stem:n for n in files if n.endswith('.py')};edges=[]
        for n,data in files.items():
            # Captured render.py retains disabled historical job branches.
            # Its active helpers are the exact selected manifest; checking all
            # optional branch imports would falsely require inactive AF/AB jobs.
            if not n.endswith('.py') or n=='render.py':continue
            for node in ast.walk(ast.parse(data,filename=n)):
                imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
                for module in imports:
                    key=module.split('.')[0]
                    if key in local_names:edges.append(dict(source=snapshot+n,module=module,targets=[snapshot+local_names[key]]))
                    elif 'road_scene_r6/src/'+key+'.py' in kept:
                        raise ValueError('Captured AQ helper omitted local import dependency: '+key)
        closure=dict(priorclosure)
        closure.update(current_AP_v13_sha256=BASE_SHA,retained_exact_required_files_sha256=required,
            local_import_edges=priorclosure['local_import_edges']+edges,missing_static_dependencies=[],
            current_capture_dependency_edges=edges,current_replay_entrypoint='road_scene_r6/src/render_checkpoint_aq.py',
            exact_generated_numerical_evidence=numeric,generated_numeric_evidence_used_as_replay_inputs=False,
            omitted_entries=omitted)
        kept['road_scene_r6/receipts/current_dependency_closure_aq.json']=enc(closure)
        proof.update(elapsed_seconds=json.loads((folder/'resource_receipt.json').read_text())['elapsed_seconds'],exact_Z_field_input_sha256=FIELD_SHA)
        kept['CURRENT_COMPONENT_EVIDENCE_AQ_V14.json']=enc(dict(base_AP_v13_sha256=BASE_SHA,
            exact_source_admission_contract=contract,latest_roles=['aq_context'],selected_current_capture=proof,
            original_local_evidence_sha256=original_hashes,packaged_public_evidence_sha256=public_hashes,
            evidence_normalization_checks=normalization,exact_generated_numerical_evidence=numeric,
            generated_evidence_used_as_replay_inputs=False,fresh_end_to_end_rebuild_verified=False,
            whole_scene_user_approved=False,material_quality_accepted=False,
            visual_finding='Useful continuous contact improvement; inherited scalloped boundary and smooth inner soil remain unfinished'))
        kept['test_source_current_aq.sh']=b'''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python verify_pinned_inputs.py
python road_scene_r6/src/render_checkpoint_aq.py --check-sources
python road_scene_r6/src/validate_source_current_aq.py
python - <<'TESTS'
import json,subprocess,sys
from pathlib import Path
root=Path('road_scene_r6');row=json.loads((root/'receipts/integrated_render_templates_aq.json').read_text())['captures'][0]
snapshot=str(root/'checkpoint_pipeline_sources'/row['pipeline_sha256'])
for generation in ('ak','al','ap','aq'):
    command=[sys.executable,str(root/('checkpoint_tests_'+generation)/'run_snapshot_tests.py'),'--snapshot',snapshot]
    if generation=='ak':command+=['--generation','AK']
    subprocess.run(command,check=True)
TESTS
'''
        kept['README.txt']=('''VICTORVILLE AQ: CURRENT REPRODUCIBLE SOURCE DELIVERY v14

STATUS AND SCOPE
Current-only AQ context source checkpoint, preserving the exact approved inputs,
inherited builders, strict Y/Z semantic guards and captured AQ helper bank.
The AP v13 archive remains unchanged and available with earlier source history.
Useful contact improvement has been observed. Inherited scalloped boundary and
smooth inner soil remain unfinished; no whole-scene/material acceptance exists.
Fresh end-to-end regeneration remains UNVERIFIED. No Blender, build, render,
full transport solve or upload was performed by this packaging pass.

ACTUAL AQ EVIDENCE
Historical guided Cycles context: 1000 x 667, 24 samples, 359.748 seconds,
4,358.523 MiB peak against a 4,480 MiB cap; resource guard passed.
AQ moved 168,832 existing soil vertices over the complete visible y=0..15 m.
Topology, world XY and original asphalt were retained. The post-float32 mesh-pair
audit covered 18,482 overlap polygons, found zero penetrations and minimum
clearance 0.80000094 mm. That audit excludes particles, section sidewalls and
shader normals. It does not prove particle-footprint collision safety.
The new film uses the final actual AQ surface on a 1281 x 89, 12.5 mm grid with
zero uncovered centres, and its captured per-class balance passed 1e-12 m3.
AO restricts deposition to downhill wet contact; erosion retains its earlier
symmetric wet footprint. Open boundaries, sampling/subcell ownership, opacity,
virtual-height and pavement-only realization limitations remain explicit.
AQ removes AP's extra fine-color/normal flattening and added fine-grain burial,
and limits larger K bodies near inspection. This is still an authored historical
scene and illustrative post-storm candidate, not validated site reconstruction,
hydrology, transport, optics, botanical identity or an accepted final material.

EXACT SOURCE AND NUMERICAL RECORDS
The approved 3,913,561-byte microbed and original pinned 2,093,642-byte Z ledger
remain exact. The Z ledger is still used by the inherited AL stage and is not
overwritten. The exact captured AQ helper bank is authoritative; AN-named
surface/film utilities and the AO model are genuine dependencies, not promotion
of their earlier diagnostic scenes. All older uncertain small source remains.
The two AQ NPZ files under historical_numerical_aq/ are exact historical outputs
for auditing. They are NOT replay inputs or cached substitutes: each AQ replay
resamples the final admitted scene and executes its own new event, writing fresh
outputs in the new capture directory. Per-version byte identity of newly solved
fields across Blender/NumPy installations has not been established.
Canonical public-path JSON evidence retains original-local and packaged hashes.
Every non-path value is preserved. No old AH cache, native maps, .blend, image or
raw guide is bundled. Images/native guides named by the AQ receipt were checked
before packaging; those outputs are historical proof, not included binaries.

STRICT REPLAY AND BUILD
No source validator, guard, schema or tolerance is weakened. The unchanged AH
validator reads its exact minimal admission contract. The newly admitted Z
scene's actual serialized hash is used; no historical .blend-byte gate returns.
Each fresh runtime stages exact pipeline/src/vegetation siblings and must record
the exact AQ captured pipeline digest. Only aq_context is a replay selection.
The inherited Z-v9/Y build chain and all required static inputs stay pinned.
The closure manifest records exact-file hashes, import edges, generated inputs
and external dependencies. This is static closure, not a completed dynamic build.

EXTRACT AND RUN
Python 3 with its standard lzma module supports the ZIP_LZMA JSON entries:
  python -m zipfile -e CYBR_Victorville_R6_AQ_Current_Reproducible_Source_v14.zip current_aq
Requirements: Blender 4.3.2 with Python/NumPy; Python 3 with NumPy/SciPy/Pillow;
Linux bash/ps; official OIDN 2.5.1 executable in OIDN_BIN. Use a fresh extraction.
  bash test_source_current_aq.sh
  bash regenerate.sh build-only
  bash regenerate.sh render-only
  bash regenerate.sh preview
  python road_scene_r6/src/render_checkpoint_aq.py --check-sources
  python road_scene_r6/src/render_checkpoint_aq.py --role aq_context --tag aq_context_repeat

TEST LIMITS
Small inherited AK/AL/AP suites run against the AQ snapshot, plus six original
AQ contact fixtures and seven unchanged AO receiver-gate fixtures. The latter
do not count old AO actual-domain, integration or serialization runs as fresh.
All six original offline shrub variants are checked. The archived AQ NPZ grids,
source equality, stock split and class balance are audited without solving.
Exact Z split, source/ledger corruption rejection and portable layout checks
remain. Only layout testing substitutes a tiny explicit native-height fixture;
production native-height SHA and semantic admission remain unchanged.
Native/4K performance, fresh full rebuild, and final appearance remain unverified.
''').encode()
        lock=dict(oldlock,version='AQ current-only reproducible source delivery v14',base_AP_v13_sha256=BASE_SHA,
            files={n:digest(d) for n,d in kept.items()},whole_scene_user_approved=False,fresh_end_to_end_rebuild_verified=False)
        kept['SOURCE_LOCK.json']=enc(lock)
    return kept,row,numeric

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});kept,row,numeric=prepare()
    temp=OUT.with_suffix('.tmp.zip');require(not OUT.exists() and not temp.exists(),'Preserve prior output/staging')
    require(shutil.disk_usage(ROOT).free>180*1024**2,'Need packaging space and 120 MiB reserve')
    for n,d in kept.items():
        if n.endswith('.py'):ast.parse(d,filename=n)
        if n.endswith('.sh'):subprocess.run(['bash','-n'],input=d,check=True)
    with zipfile.ZipFile(temp,'x') as z:
        for n,d in kept.items():
            info=zipfile.ZipInfo(n);info.create_system=3;info.external_attr=(stat.S_IFREG|(0o755 if n.endswith('.sh') else 0o644))<<16
            method=zipfile.ZIP_LZMA if n.endswith('.json') and len(d)>100000 else zipfile.ZIP_DEFLATED
            z.writestr(info,d,compress_type=method,compresslevel=8 if method==zipfile.ZIP_DEFLATED else None)
    require(temp.stat().st_size<19_000_000,'Unexpected AQ package growth');kept.clear();gc.collect()
    with zipfile.ZipFile(temp) as z:
        require(z.testzip() is None,'AQ CRC failed');lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'AQ lock closure differs')
        for n,h in lock['files'].items():require(digest(z.read(n))==h,'AQ source lock differs: '+n)
        with tempfile.TemporaryDirectory(prefix='verify_aq_current_') as path:
            z.extractall(path)
            result=subprocess.run(['bash','test_source_current_aq.sh'],cwd=path,env=ENV,capture_output=True,text=True,timeout=220)
            require(result.returncode==0,'AQ extracted checks failed:\n'+result.stdout+'\n'+result.stderr)
            output=result.stdout+'\n'+result.stderr
        entries=len(z.namelist())
    require(file_sha(BASE)==BASE_SHA,'AP v13 changed');temp.rename(OUT)
    result=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=file_sha(OUT),archive_entries=entries,
        AP_v13_preserved_sha256=BASE_SHA,source_lock_and_crc_verified=True,
        exact_AQ_snapshot_sha256=row['pipeline_sha256'],current_replay_roles=['aq_context'],
        static_source_closure_and_extracted_tests_passed=True,exact_historical_AQ_arrays=numeric,
        historical_AQ_arrays_used_as_replay_inputs=False,strict_Y_Z_admission_unchanged=True,
        fresh_end_to_end_regeneration_verified=False,whole_scene_user_approved=False,
        blender_launched=False,rendered=False,uploaded=False)
    (ROOT/'receipts/source_package_current_aq_v14.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'receipts/source_package_current_aq_v14_tests.log').write_text(output)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
