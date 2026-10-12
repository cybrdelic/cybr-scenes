#!/usr/bin/env python3
"""Current AV static closure, strict admission and portable-layout checks only."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import numpy as np
import render_checkpoint_ah as inherited
import render_checkpoint_av as replay

ROOT=Path(__file__).resolve().parents[1]
FIELD='road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz'
FIELD_SHA='bdd8176d29209c21d97aab02c44743ab6b2ff2a9f4f25989513f1dd5636400d2'


def run():
    require=inherited.require;lock=inherited.verify_lock()
    template=json.loads((ROOT/'receipts/integrated_render_templates_av.json').read_text())
    evidence=json.loads((ROOT.parent/'CURRENT_COMPONENT_EVIDENCE_AV_V15.json').read_text())
    ah=json.loads((ROOT/'receipts/integrated_render_templates_ah.json').read_text())
    require(template['source_admission']==ah['source_admission']==evidence['exact_source_admission_contract'],'Strict inherited Z contract changed')
    closure=json.loads((ROOT/'receipts/current_dependency_closure_av.json').read_text())
    for name,sha in closure['retained_exact_required_files_sha256'].items():
        require(inherited.digest(inherited.local_path(name))==sha,'Exact required input/source changed: '+name)
    require(closure['missing_static_dependencies']==[],'Static closure incomplete')
    for edge in closure['local_import_edges']:
        require(inherited.local_path(edge['source']).is_file() and all(inherited.local_path(n).is_file() for n in edge['targets']),'Local import missing')
    for name in ('runoff_film_z.json','flow_shoulder_y.json'):
        require(not (ROOT/'receipts'/name).exists(),'Historical output would block fresh build')
    for key in ('whole_scene_user_approved','fresh_end_to_end_rebuild_verified','cache_is_required_input','cache_bytes_included'):
        require(evidence[key] is False,'Unproved status or cache dependency')
    require(not any(n.endswith('.blend') for n in lock['files']),'Serialized scene included as input')
    original=evidence['original_local_evidence_sha256'];public=evidence['packaged_public_evidence_sha256']
    require(set(original)==set(public),'Evidence coverage differs')
    require({r['path'] for r in evidence['evidence_normalization_checks']}==set(public),'Path-only proofs incomplete')
    require(all(r['semantic_changes_only_paths'] for r in evidence['evidence_normalization_checks']),'Non-path evidence mutation')
    for name,sha in public.items():
        path=inherited.local_path(name);require(inherited.digest(path)==sha,'Evidence hash changed')
        for fragment in ('/'+'workspace/', '/'+'home/agent/', '/'+'root/'):
            require(fragment not in path.read_text(),'Private path in normalized evidence')
    rows=replay.selected_rows(template,'latest')
    require(len(rows)==1 and rows[0]['role']=='av_outward' and evidence['latest_roles']==['av_outward'],'Current-only selection differs')
    require(inherited.digest(inherited.local_path(FIELD))==FIELD_SHA,'Pinned Z stock ledger changed')
    tree=ast.parse((ROOT/'src/render_checkpoint_av.py').read_text())
    imports=[n for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module=='render_checkpoint_ah']
    require(any('admit_scene' in {a.name for a in n.names} for n in imports),'Strict semantic admission bypassed')
    require('SOURCE_SHA' not in (ROOT/'src/render_checkpoint_av.py').read_text(),'Historical serialized byte gate returned')
    rejected=subprocess.run([sys.executable,str(ROOT/'src/render_checkpoint_av.py'),'--check-sources'],
        env=dict(os.environ,MATERIAL_PATH_MAP_FILE='explicit-forbidden-fixture'),capture_output=True,text=True)
    require(rejected.returncode!=0 and 'Unset MATERIAL_PATH_MAP_FILE' in rejected.stderr,'Unapproved path mapping accepted')
    row=rows[0];settings=row['settings']
    require(settings['graded_shoulder_ah']['foundation_revision']=='AT','AT not selected')
    require(settings['metric_fragments_as']['geometry_revision']=='fractured_candidate','Candidate morphology not selected')
    require(settings['pavement_contact_ac']['height_path']==settings['fractured_boundary_ar']['height_path'],'AR native height relocation missing')
    require(settings['road_film_ownership_al']['fields_path']==FIELD,'Pinned Z stock path differs')
    required_paths={('pavement_contact_ac','height_path'),('fractured_boundary_ar','height_path'),('road_film_ownership_al','fields_path')}
    require({tuple(r['job_key_path']) for r in row['input_relocations']}==required_paths,'Pinned input relocation set differs')
    require(not any(row['settings'].get(k) for k in ('sample_final_surface_an','refined_film_an')),'Unselected diagnostic enabled')
    # Exact small-ledger split checks use the captured source, not mutable public modules.
    snapshot=ROOT/'checkpoint_pipeline_sources'/row['pipeline_sha256']
    spec=importlib.util.spec_from_file_location('ownership_av_test',snapshot/'road_film_ownership_al.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with np.load(inherited.local_path(FIELD),allow_pickle=False) as data:fields=dict(data)
    before=fields['remaining_mobile_class_thickness_m'].copy();road,soil,split=module.split_inventory(fields)
    np.testing.assert_array_equal(road+soil,before);np.testing.assert_array_equal(fields['remaining_mobile_class_thickness_m'],before)
    report=json.loads((ROOT/'historical_captures_av'/row['name']/'ROAD_FILM_OWNERSHIP_AL.json').read_text())
    for key,value in split.items():require(value==report[key],'Actual ledger split differs: '+key)
    require(hashlib.sha256(road[:,:,0].astype(np.float32).tobytes()).hexdigest()==report['output_matrix_sha256'],'Captured stock image differs')
    with tempfile.TemporaryDirectory(prefix='av_source_layout_',dir=ROOT) as temp:
        fixture=Path(temp);root=fixture/'road_scene_r6';bank=root/'checkpoint_pipeline_sources'/row['pipeline_sha256']
        shutil.copytree(snapshot,bank);pipeline=replay.stage_pipeline(row,fixture/'runtime',root=root)
        for name in row['component_helper_names']:
            require(inherited.digest(pipeline.parent/'src'/name)==row['captured_pipeline_files_sha256'][name],'Sibling src lookup differs')
        for name in replay.VEGETATION_HELPERS:
            require(inherited.digest(pipeline.parent/'vegetation'/name)==row['captured_pipeline_files_sha256'][name],'Sibling vegetation lookup differs')
        (bank/'layered_scrub_ap.py').write_text('raise RuntimeError("corrupt fixture")\n')
        try:replay.stage_pipeline(row,fixture/'rejected',root=root)
        except ValueError:pass
        else:raise AssertionError('Corrupt shrub snapshot accepted')
        testrow=copy.deepcopy(row)
        for item in testrow['input_relocations']:
            target=fixture/item['package_path'];target.parent.mkdir(parents=True,exist_ok=True)
            if item['package_path']==FIELD:shutil.copyfile(inherited.local_path(FIELD),target)
            else:
                target.write_bytes(b'explicit synthetic absent native-height layout fixture')
                item['sha256']=inherited.digest(target)
        original_path=inherited.local_path
        try:
            inherited.local_path=lambda name:fixture/name
            capture=fixture/'capture';capture.mkdir()
            job=replay.build_job(testrow,fixture/'not_built.blend','fresh-actual-semantic-admitted-hash',capture)
            require(job['source_sha256']=='fresh-actual-semantic-admitted-hash','Historical scene hash gate returned')
            require(job['pavement_contact_ac']['height_path']==job['fractured_boundary_ar']['height_path']==str(fixture/settings['fractured_boundary_ar']['height_path']),'Native height consumers not relocated')
            require(job['road_film_ownership_al']['fields_path']==str(fixture/FIELD),'Pinned ledger not relocated')
            require(job['assembled_scene_cache_av']['path']==str(capture/'ASSEMBLED_SCENE_AV.blend'),'Cache output not portable')
            require(job['assembled_scene_cache_av']['allowed_directory']==str(capture),'Cache allowed directory not relocated')
            require('runoff_support_fields' not in job['pavement_contact_ac'],'Historical AH generated cache inserted')
            manifest,sha=replay.expected_manifest(row)
            require(sha==row['pipeline_sha256'],'Default exact manifest differs')
            nocache=replay.build_job(testrow,fixture/'not_built.blend','fresh-actual-semantic-admitted-hash',capture,cache_output=False)
            require('assembled_scene_cache_av' not in nocache,'Optional cache output is mandatory')
            no_manifest,no_sha=replay.expected_manifest(row,cache_output=False)
            require(set(manifest)-set(no_manifest)=={'assembled_scene_cache_av.py'} and no_sha!=sha,'No-cache manifest not explicitly audited')
            require(all(manifest[n]==no_manifest[n] for n in no_manifest),'No-cache source bytes changed')
            (fixture/FIELD).write_bytes(b'corrupt stock ledger')
            try:replay.build_job(testrow,fixture/'not_built.blend','fresh-actual-semantic-admitted-hash',capture)
            except ValueError:pass
            else:raise AssertionError('Corrupt stock ledger accepted')
        finally:inherited.local_path=original_path
    from check_av_numerical_evidence import run as numerical_check
    result=dict(passed=True,numerical_evidence=numerical_check(),CPU_threads=1,
        strict_Z_admission_unchanged=True,static_dependency_closure_checked=True,
        exact_captured_pipeline_src_vegetation_layout=True,source_corruption_rejected=True,input_corruption_rejected=True,
        both_native_height_consumers_relocated=True,cache_output_optional_and_portable=True,
        public_evidence_hashes_verified=len(public),native_height_layout_fixture_is_synthetic=True,
        blender_executed=False,rendered=False,fresh_end_to_end_rebuild_verified=False,whole_scene_user_approved=False)
    print(json.dumps(result));return result

if __name__=='__main__':run()
