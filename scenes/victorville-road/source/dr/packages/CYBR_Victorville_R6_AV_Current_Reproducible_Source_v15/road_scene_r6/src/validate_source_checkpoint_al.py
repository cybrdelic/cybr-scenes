#!/usr/bin/env python3
"""Source-only AL layout checks. Never load Blender, solve terrain, or render."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import numpy as np
import render_checkpoint_ah as inherited
from render_checkpoint_al import selected_rows

ROOT=Path(__file__).resolve().parents[1]
FIELD='road_scene_r6/checkpoint_inputs_al/runoff_film_z_fields.npz'
FIELD_SHA='bdd8176d29209c21d97aab02c44743ab6b2ff2a9f4f25989513f1dd5636400d2'

def run():
    inherited.verify_lock()
    template=json.loads((ROOT/'receipts/integrated_render_templates_al.json').read_text())
    old=json.loads((ROOT/'receipts/integrated_render_templates_ak.json').read_text())
    require=inherited.require
    require(template['source_admission']==old['source_admission'],'Strict inherited Z admission changed')
    require(template['captures'][:len(old['captures'])]==old['captures'],'Inherited capture template changed')
    evidence=json.loads((ROOT.parent/'INTEGRATED_COMPONENT_EVIDENCE_AL_V12.json').read_text())
    packaged=evidence['packaged_public_evidence_sha256'];original=evidence['original_local_evidence_sha256']
    require(set(packaged)==set(original),'Original and normalized evidence coverage differs')
    checks=evidence['evidence_normalization_checks']
    require({r['path'] for r in checks}==set(packaged),'Missing path-normalization check')
    require(all(r['semantic_changes_only_paths'] is True for r in checks),'Unexpected evidence semantic change')
    for relative,expected in packaged.items():
        receipt_path=inherited.local_path(relative)
        require(inherited.digest(receipt_path)==expected,'Normalized evidence hash mismatch')
        text=receipt_path.read_text()
        for fragment in ('/'+'workspace/', '/'+'home/agent/', '/'+'root/'):
            require(fragment not in text,'Private machine path in normalized evidence')
    rows=selected_rows(template,'latest')
    require({r['role'] for r in rows}=={'al_detail','al_context'},'Latest must select both AL captures')
    path=inherited.local_path(FIELD)
    require(inherited.digest(path)==FIELD_SHA,'Exact AL source ledger differs')
    ownership_reports=[]
    for row in rows:
        require(row['settings']['road_film_ownership_al']=={'fields_path':FIELD},'Ownership input is not immutable and portable')
        require(any(r==dict(job_key_path=['road_film_ownership_al','fields_path'],package_path=FIELD,sha256=FIELD_SHA) for r in row['input_relocations']),'Missing exact field relocation')
        require('sample_final_surface_an.py' not in row['pipeline_files_sha256'],'Unfinished AN entered AL source')
        snapshot=ROOT/'checkpoint_pipeline_sources'/row['pipeline_sha256']
        spec=importlib.util.spec_from_file_location('ownership_under_test',snapshot/'road_film_ownership_al.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with np.load(path,allow_pickle=False) as source:fields=dict(source)
        before=fields['remaining_mobile_class_thickness_m'].copy()
        road,soil,split=module.split_inventory(fields)
        np.testing.assert_array_equal(road+soil,before)
        np.testing.assert_array_equal(fields['remaining_mobile_class_thickness_m'],before)
        receipt=json.loads((ROOT/'historical_captures_al'/row['name']/'ROAD_FILM_OWNERSHIP_AL.json').read_text())
        for key,value in split.items():require(value==receipt[key],'Captured split numerical result differs: '+key)
        require(hashlib.sha256(road[:,:,0].astype(np.float32).tobytes()).hexdigest()==receipt['output_matrix_sha256'],'Captured pavement matrix differs')
        require(receipt['source_field_sha256']==FIELD_SHA,'Captured ownership source differs')
        ownership_reports.append(dict(role=row['role'],actual_pinned_ledger_split_matches_capture=True))
    with tempfile.TemporaryDirectory(prefix='al_source_layout_') as tmp:
        t=Path(tmp)
        for row in rows:
            fixture=t/row['role']; fixture.mkdir()
            snapshot=fixture/'road_scene_r6/checkpoint_pipeline_sources'/row['pipeline_sha256']
            shutil.copytree(ROOT/'checkpoint_pipeline_sources'/row['pipeline_sha256'],snapshot)
            pipeline=inherited.stage_pipeline(row,fixture/'runtime',root=fixture/'road_scene_r6')
            for name in row['component_helper_names']:
                require(inherited.digest(pipeline.parent/'src'/name)==row['captured_pipeline_files_sha256'][name],'Sibling helper lookup differs')
            (snapshot/'render.py').write_text('raise RuntimeError("corrupted source fixture")\n')
            try:inherited.stage_pipeline(row,fixture/'rejected',root=fixture/'road_scene_r6')
            except ValueError:pass
            else:raise AssertionError('Corrupt snapshot was accepted')
            # Exercise real relocation logic using a tiny stand-in solely for the
            # absent generated native height. Production hash stays unchanged.
            testrow=copy.deepcopy(row)
            for item in testrow['input_relocations']:
                target=fixture/item['package_path'];target.parent.mkdir(parents=True,exist_ok=True)
                if item['package_path']==FIELD:shutil.copyfile(path,target)
                else:
                    target.write_bytes(b'synthetic native-height layout fixture')
                    item['sha256']=inherited.digest(target)
            original=inherited.local_path
            try:
                inherited.local_path=lambda relative: fixture/relative
                output=fixture/'capture'
                job=inherited.build_job(testrow,fixture/'unbuilt.blend','not-a-built-scene',output)
                require(job['road_film_ownership_al']['fields_path']==str(fixture/FIELD),'Pinned ledger relocation failed')
                require('runoff_support_fields' not in job['pavement_contact_ac'],'Historical generated AH cache injected')
                (fixture/FIELD).write_bytes(b'corrupt ledger fixture')
                try:inherited.build_job(testrow,fixture/'unbuilt.blend','not-a-built-scene',output)
                except ValueError:pass
                else:raise AssertionError('Corrupt numerical source was accepted')
            finally:inherited.local_path=original
    result=dict(passed=True,CPU_threads=1,exact_captured_source_and_sibling_helper_resolution=True,
        source_corruption_rejected=True,input_corruption_rejected=True,portable_job_relocations_passed=True,
        relocation_native_height_is_synthetic_fixture=True,pinned_Z_ledger_SHA256=FIELD_SHA,
        actual_pinned_ledger_split_checks=ownership_reports,inherited_templates_unchanged=True,
        strict_Z_admission_unchanged=True,blender_executed=False,rendered=False,
        full_saved_domain_solver_rerun=False,fresh_end_to_end_rebuild_verified=False,
        public_evidence_hashes_verified=len(packaged),new_evidence_private_machine_paths_absent=True,
        path_only_normalization_records_verified=True)
    print(json.dumps(result))
    return result

if __name__=='__main__':run()
