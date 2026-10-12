#!/usr/bin/env python3
"""Current AQ dependency and portable layout checks; no scene execution."""
import ast
import copy
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
import render_checkpoint_aq as replay

ROOT=Path(__file__).resolve().parents[1]
FIELD='road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz'
FIELD_SHA='bdd8176d29209c21d97aab02c44743ab6b2ff2a9f4f25989513f1dd5636400d2'

def run():
    require=inherited.require
    lock=inherited.verify_lock()
    template=json.loads((ROOT/'receipts/integrated_render_templates_aq.json').read_text())
    evidence=json.loads((ROOT.parent/'CURRENT_COMPONENT_EVIDENCE_AQ_V14.json').read_text())
    ah=json.loads((ROOT/'receipts/integrated_render_templates_ah.json').read_text())
    require(template['source_admission']==ah['source_admission']==evidence['exact_source_admission_contract'],'Strict inherited Z contract changed')
    closure=json.loads((ROOT/'receipts/current_dependency_closure_aq.json').read_text())
    for name,sha in closure['retained_exact_required_files_sha256'].items():
        require(inherited.digest(inherited.local_path(name))==sha,'Required exact input/source differs: '+name)
    require(closure['missing_static_dependencies']==[],'Static dependency closure incomplete')
    for item in closure['local_import_edges']:
        require(all(inherited.local_path(name).is_file() for name in item['targets']),'Local import dependency missing')
    require(not (ROOT/'receipts/runoff_film_z.json').exists(),'Historical Z output would block fresh build')
    require(not (ROOT/'receipts/flow_shoulder_y.json').exists(),'Historical Y output would block fresh build')
    original=evidence['original_local_evidence_sha256'];packaged=evidence['packaged_public_evidence_sha256']
    require(set(original)==set(packaged),'Evidence coverage differs')
    normalization=evidence['evidence_normalization_checks']
    require({r['path'] for r in normalization}==set(packaged),'Path-only evidence proofs incomplete')
    require(all(r['semantic_changes_only_paths'] for r in normalization),'Evidence changed beyond paths')
    for name,sha in packaged.items():
        path=inherited.local_path(name)
        require(inherited.digest(path)==sha,'Evidence hash changed')
        for fragment in ('/'+'workspace/', '/'+'home/agent/', '/'+'root/'):
            require(fragment not in path.read_text(),'Private path in normalized evidence')
    latest=replay.selected_rows(template,'latest')
    require({r['role'] for r in latest}==set(evidence['latest_roles'])=={'aq_context'},'Latest must exclude the diagnostic close')
    rows=[r for r in template['captures'] if r.get('generation')=='AQ']
    require({r['role'] for r in rows}=={'aq_context'},'Only current context is a replay selection')
    require(inherited.digest(inherited.local_path(FIELD))==FIELD_SHA,'Exact pinned Z ledger changed')
    replay_tree=ast.parse((ROOT/'src/render_checkpoint_aq.py').read_text())
    imports=[n for n in ast.walk(replay_tree) if isinstance(n,ast.ImportFrom) and n.module=='render_checkpoint_ah']
    require(any('admit_scene' in {a.name for a in n.names} for n in imports),'Replay must reuse strict semantic admission')
    require('SOURCE_SHA' not in (ROOT/'src/render_checkpoint_aq.py').read_text(),'Historical blend-byte guard regression')
    rejected=subprocess.run([sys.executable,str(ROOT/'src/render_checkpoint_aq.py'),'--check-sources'],
        env=dict(os.environ,MATERIAL_PATH_MAP_FILE='explicit-forbidden-fixture'),capture_output=True,text=True)
    require(rejected.returncode!=0 and 'Unset MATERIAL_PATH_MAP_FILE' in rejected.stderr,'Unapproved path mapping accepted')
    field_splits=[]
    for row in rows:
        require(row['settings']['road_margin_aq']=={'enabled':True},'AQ not enabled exactly')
        require(not any(row['settings'].get(k) for k in ('sample_final_surface_an','refined_film_an')),'AN diagnostic enabled')
        require('apply_refined_film_an.py' not in row['pipeline_files_sha256'],'AN film diagnostic source entered AP')
        require(row['settings']['road_film_ownership_al']=={'fields_path':FIELD},'Field input is not portable/pinned')
        require(any(r==dict(job_key_path=['road_film_ownership_al','fields_path'],package_path=FIELD,sha256=FIELD_SHA) for r in row['input_relocations']),'Exact ledger relocation missing')
        snapshot=ROOT/'checkpoint_pipeline_sources'/row['pipeline_sha256']
        spec=importlib.util.spec_from_file_location('ownership_ap_test',snapshot/'road_film_ownership_al.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with np.load(inherited.local_path(FIELD),allow_pickle=False) as source:fields=dict(source)
        before=fields['remaining_mobile_class_thickness_m'].copy()
        road,soil,split=module.split_inventory(fields)
        np.testing.assert_array_equal(road+soil,before)
        np.testing.assert_array_equal(fields['remaining_mobile_class_thickness_m'],before)
        receipt=json.loads((ROOT/'historical_captures_aq'/row['name']/'ROAD_FILM_OWNERSHIP_AL.json').read_text())
        for key,value in split.items():require(value==receipt[key],'Exact captured split differs: '+key)
        import hashlib
        require(hashlib.sha256(road[:,:,0].astype(np.float32).tobytes()).hexdigest()==receipt['output_matrix_sha256'],'Captured image stock matrix differs')
        field_splits.append(row['role'])
    with tempfile.TemporaryDirectory(prefix='ap_source_layout_') as temp:
        temp=Path(temp)
        for row in rows:
            fixture=temp/row['role'];fixture.mkdir()
            root=fixture/'road_scene_r6';snapshot=root/'checkpoint_pipeline_sources'/row['pipeline_sha256']
            shutil.copytree(ROOT/'checkpoint_pipeline_sources'/row['pipeline_sha256'],snapshot)
            pipeline=replay.stage_pipeline(row,fixture/'runtime',root=root)
            for name in row['component_helper_names']:
                require(inherited.digest(pipeline.parent/'src'/name)==row['captured_pipeline_files_sha256'][name],'Sibling src lookup differs')
            for name in replay.VEGETATION_HELPERS:
                require(inherited.digest(pipeline.parent/'vegetation'/name)==row['captured_pipeline_files_sha256'][name],'Sibling vegetation lookup differs')
            target=snapshot/'layered_scrub_ap.py';target.write_text('raise RuntimeError("corrupt fixture")\n')
            try:replay.stage_pipeline(row,fixture/'rejected',root=root)
            except ValueError:pass
            else:raise AssertionError('Corrupted shrub snapshot accepted')
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
                job=inherited.build_job(testrow,fixture/'not_built.blend','actual-rebuilt-hash-placeholder',fixture/'capture')
                require(job['source_sha256']=='actual-rebuilt-hash-placeholder','Replay pinned a historical serialized scene hash')
                require(job['road_film_ownership_al']['fields_path']==str(fixture/FIELD),'Pinned ledger not relocated')
                require('runoff_support_fields' not in job['pavement_contact_ac'],'Old generated AH cache inserted')
                (fixture/FIELD).write_bytes(b'corrupt source ledger')
                try:inherited.build_job(testrow,fixture/'not_built.blend','actual-rebuilt-hash-placeholder',fixture/'capture')
                except ValueError:pass
                else:raise AssertionError('Corrupt ledger admitted')
            finally:inherited.local_path=original_path
    from check_aq_numerical_evidence import run as check_numerical_evidence
    numerical=check_numerical_evidence()
    result=dict(numerical_evidence=numerical,passed=True,CPU_threads=1,strict_Z_admission_unchanged=True,
        current_static_dependency_closure_checked=True,current_replay_context_only=True,
        exact_captured_pipeline_src_vegetation_layout=True,source_corruption_rejected=True,
        input_corruption_rejected=True,actual_pinned_ledger_split_roles=field_splits,
        public_evidence_hashes_verified=len(packaged),historical_blend_byte_guard_regression=False,
        native_height_layout_fixture_is_synthetic=True,blender_executed=False,rendered=False,
        fresh_end_to_end_rebuild_verified=False,whole_scene_user_approved=False)
    print(json.dumps(result))
    return result

if __name__=='__main__':run()
