#!/usr/bin/env python3
"""Source-only AV v15 packaging. Never builds, renders, creates cache or uploads.

--terminal-approved is an explicit operator gate, not a substitute for checked
actual capture evidence. Invoke only after the parent approves the terminal run.
"""
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
import tempfile
import zipfile
from package_current_checkpoint_ap import ROOT, ENV, digest, file_sha, require, enc, MICROBED
from package_integrated_checkpoint_ah import HEIGHT, HEIGHT_SHA, PIPELINE_CORE
from package_integrated_checkpoint_al import normalize_json, FIELD, FIELD_SHA

BASE = ROOT/'deliverables/CYBR_Victorville_R6_AQ_Current_Reproducible_Source_v14.zip'
BASE_SHA = '7fbecac18a65f1911b6ce3372f441e2bbfecd9940cbea099abcf2bcf81e9f027'
OUT = ROOT/'deliverables/CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15.zip'
CAPTURE = 'av_integrated_road_outer_view'
REQUIRED = {'fractured_boundary_ar.py','soil_rim_bridge_ar.py','integrate_fracture_ar.py',
    'graded_shoulder_foundation_at.py','metric_margin_fragments_as.py',
    'metric_margin_fragments_as_fractured_candidate.py','assemble_metric_fragments_as.py',
    'refresh_view_grains_au.py','assembled_scene_cache_av.py','layered_scrub_ap.py','desert_scrub.py'}
LOCAL_FILES = ('render_checkpoint_av.py','validate_source_current_av.py','package_current_checkpoint_av.py',
               'prepare_cached_view_av.py','check_av_numerical_evidence.py')
TEST_FILES = ('test_fractured_boundary_ar.py','test_soil_rim_bridge_ar.py','test_metric_edge_strip_aa.py',
              'test_metric_margin_fragments_as.py','test_metric_margin_fragments_as_fractured_candidate.py',
              'test_refresh_view_grains_au.py')


def captured(old):
    folder=ROOT/'captures'/CAPTURE
    read=lambda name:json.loads((folder/name).read_text())
    job=read('job.json');raw=read('INTERNAL_PANEL.png.json');clean=read('CLEAN_OIDN_PANEL.png.json')
    resources=read('resource_receipt.json');memory=read('PRE_RENDER_MEMORY_ADAPTATIONS.json')
    require(job==raw['job']==clean['job'],'Exact active captured job changed')
    require(job['source_sha256']==raw['source_sha256']==clean['source_sha256'],'Actual source evidence differs')
    require(file_sha(job['source'])==job['source_sha256'],'Actual historical Z source changed')
    require(raw['pipeline']==clean['pipeline']==memory['pipeline'],'Actual pipeline evidence differs')
    require(resources.get('exit_code')==resources.get('actual_process_exit_code')==0 and
            resources.get('resource_contract_passed') is True and not resources.get('resource_contract_violations'),
            'Actual AV resource contract did not pass')
    cap=job['rss_cap_mib']
    require(type(cap) is int and 0<cap<=4480 and cap==resources['RSS_cap_MiB'] and
            max(resources['peak_process_tree_RSS_MiB'],resources['kernel_max_child_RSS_MiB'])<=cap,
            'Actual AV resource peak exceeds declared cap')
    require(job['engine']=='CYCLES' and job['capture_mode']=='guided' and job['save_guides'] is True,'Guided Cycles required')
    require(raw['resolution']==clean['resolution']==[job['width'],job['height']]==[1000,667],'Bounded qualified view changed')
    require(clean.get('raw_guides_retained') is True and clean['oidn_guide_contract']['valid'] is True,'Guides failed')
    checked={}
    for name,h in clean['files_sha256'].items():
        require(file_sha(name)==h,'Actual image or native guide hash changed: '+name)
        checked[Path(name).name]=h
    pipeline=raw['pipeline'];manifest=pipeline['files']
    require(digest(json.dumps(manifest,sort_keys=True).encode())==pipeline['sha256'],'Actual manifest digest changed')
    snapshot=Path(pipeline['snapshot'])
    require(snapshot.resolve()==(ROOT/'pipeline/pipeline_snapshots'/pipeline['sha256']).resolve(),'Unexpected capture snapshot')
    files={}
    for name,h in manifest.items():
        require(Path(name).name==name,'Manifest paths must be flat')
        files[name]=(snapshot/name).read_bytes()
        require(digest(files[name])==h,'Exact captured helper changed: '+name)
    require(PIPELINE_CORE|REQUIRED<=files.keys(),'Captured AV source dependency missing')
    baseline=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_aq.json'))['captures'][0]
    for name in ('bounded_clean_run.py','resource_contract.py'):
        data=old.read('road_scene_r6/checkpoint_pipeline_sources/'+baseline['pipeline_sha256']+'/'+name)
        active=(ROOT/'pipeline'/name).read_bytes()
        if name=='bounded_clean_run.py':
            expected='7d5421644f0188178ee29f4a732b4d5a608564de82b29cc47516b27794a486fe'
            suffix=b"\n# Propagate the guarded child/contract result to callers as well as the receipt.\nraise SystemExit(int(r['exit_code']))\n"
            require(active==data+suffix and digest(active)==expected,'Unexpected AV watchdog edit')
        else:
            require(active==data,'Resource contract changed')
        files[name]=active
    settings={k:copy.deepcopy(v) for k,v in job.items() if k not in ('source','source_sha256','output')}
    relocations=[]
    for key in ('pavement_contact_ac','fractured_boundary_ar'):
        require(file_sha(settings[key]['height_path'])==HEIGHT_SHA,'Native-height input differs')
        settings[key]['height_path']=HEIGHT
        relocations.append(dict(job_key_path=[key,'height_path'],package_path=HEIGHT,sha256=HEIGHT_SHA))
    require(file_sha(settings['road_film_ownership_al']['fields_path'])==FIELD_SHA,'Pinned Z stock ledger differs')
    settings['road_film_ownership_al']['fields_path']=FIELD
    relocations.append(dict(job_key_path=['road_film_ownership_al','fields_path'],package_path=FIELD,sha256=FIELD_SHA))
    contact=read('CONTINUOUS_CONTACT_AQ.json')['exact_triangle_clearance']
    require(contact['penetrating_overlap_polygons']==0 and contact['minimum_linear_mesh_clearance_m']>=.0008,
            'Actual final road/soil contact proof failed')
    ar=read('FRACTURED_BOUNDARY_AR.json')
    require(ar['scene_assigned'] is True and ar['original_source_materials_and_world_phase_unchanged'] is True,
            'Actual fractured topology/source-phase proof failed')
    au=read('VIEW_GRAIN_REFRESH_AU.json')
    require(au['prototype_geometry_and_materials_unchanged'] is True and au['original_origins_unchanged'] is True and
            au['protected_before_sha256']==au['protected_after_sha256'] and au['instance_scale']==[1,1,1] and
            au['new_supplement_objects']==0 and au['immutable_source_file_written'] is False and
            au['view_count']==2 and au['after_count']<=au['maximum_instances']<=294363,
            'Actual bounded source-scale grain allocation proof failed')
    cache_path=Path(job['assembled_scene_cache_av']['path'])
    cache_meta=json.loads(cache_path.with_suffix('.blend.json').read_text())
    require(cache_meta['pipeline']==pipeline and cache_meta['assembly_job']==job,'Cache provenance differs from actual assembly')
    require(cache_meta.get('saved_before_preview_reductions') is True and cache_meta.get('immutable_source_verified') is True,'Cache pre-LOD/source proof absent')
    require(cache_path.stat().st_size==cache_meta['bytes'] and file_sha(cache_path)==cache_meta['sha256'],'Actual cache bytes changed')
    settings['assembled_scene_cache_av']['path']='OUTPUT_CAPTURE/ASSEMBLED_SCENE_AV.blend'
    settings['assembled_scene_cache_av']['allowed_directory']='OUTPUT_CAPTURE'
    row=dict(name=CAPTURE,role='av_outward',generation='AV',settings=settings,
        pipeline_sha256=pipeline['sha256'],captured_pipeline_files_sha256=manifest,
        pipeline_files_sha256={n:digest(d) for n,d in files.items()},
        component_helper_names=sorted(set(manifest)-PIPELINE_CORE),vegetation_helper_names=['layered_scrub_ap.py','desert_scrub.py'],
        support_source_provenance={n:dict(sha256=digest(files[n]),included_in_render_manifest=False,
            role='Exact bounded launch support; AV watchdog propagates recorded resource failure as process exit')
            for n in ('bounded_clean_run.py','resource_contract.py')},input_relocations=relocations,default_latest=True,status='Combined progress candidate; no whole-scene acceptance',
        optional_output_relocations=[['assembled_scene_cache_av','path'],['assembled_scene_cache_av','allowed_directory']])
    proof=dict(name=CAPTURE,role='av_outward',source_sha256=job['source_sha256'],pipeline_sha256=pipeline['sha256'],
        original_job_sha256=file_sha(folder/'job.json'),clean_image_sha256=file_sha(folder/'CLEAN_OIDN_PANEL.png'),
        historical_images_and_guides_verified=checked,resource_contract_passed=True,declared_cap_MiB=cap,
        peak_MiB=max(resources['peak_process_tree_RSS_MiB'],resources['kernel_max_child_RSS_MiB']),
        elapsed_seconds=resources['elapsed_seconds'],cache_sha256=cache_meta['sha256'],cache_bytes=cache_meta['bytes'],
        cache_bytes_required_for_regeneration=False,cache_created_by_packager=False)
    return row,files,proof,cache_path.with_suffix('.blend.json')


def prepare():
    require(file_sha(BASE)==BASE_SHA,'AQ v14 baseline changed')
    folder=ROOT/'captures'/CAPTURE
    with zipfile.ZipFile(BASE) as old:
        require(old.testzip() is None,'AQ baseline CRC failed')
        oldlock=json.loads(old.read('SOURCE_LOCK.json'))
        row,files,proof,cache_receipt=captured(old)
        prior=json.loads(old.read('road_scene_r6/receipts/current_dependency_closure_aq.json'))
        oldtemplate=json.loads(old.read('road_scene_r6/receipts/integrated_render_templates_aq.json'))
        contract=oldtemplate['source_admission'];kept={};omitted={}
        for name in old.namelist():
            reason=None
            if name.startswith(('road_scene_r6/checkpoint_pipeline_sources/','road_scene_r6/historical_captures_aq/',
                                'road_scene_r6/historical_evidence_aq/','road_scene_r6/historical_numerical_aq/')):
                reason='Replaced previous capture snapshot/evidence; exact history remains in AQ v14'
            elif name in {'SOURCE_LOCK.json','README.txt','CURRENT_COMPONENT_EVIDENCE_AQ_V14.json','test_source_current_aq.sh',
                'road_scene_r6/receipts/integrated_render_templates_aq.json','road_scene_r6/receipts/current_dependency_closure_aq.json'}:
                reason='Replaced current-version entrypoint or metadata'
            if reason:omitted[name]=dict(sha256=digest(old.read(name)),reason=reason)
            else:kept[name]=old.read(name)
        for n,h in oldlock['files'].items():
            if n in kept:require(digest(kept[n])==h,'Inherited input changed: '+n)
        snapshot='road_scene_r6/checkpoint_pipeline_sources/'+row['pipeline_sha256']+'/'
        for n,data in files.items():kept[snapshot+n]=data
        # Exact captured helpers belong in their snapshot. Keep inherited builder
        # modules unchanged; only genuinely new modules get public source copies.
        for n,data in files.items():
            if n.endswith('.py') and n not in PIPELINE_CORE and 'road_scene_r6/src/'+n not in kept:
                kept['road_scene_r6/src/'+n]=data
        original={};public={};normalization=[]
        def evidence(path,target):
            raw=path.read_bytes();data,count=normalize_json(raw);kept[target]=data
            original[target]=digest(raw);public[target]=digest(data)
            normalization.append(dict(path=target,semantic_changes_only_paths=True,canonical_serialization=True,path_values_or_keys_normalized=count))
        for path in sorted(folder.rglob('*.json')):
            evidence(path,'road_scene_r6/historical_captures_av/'+CAPTURE+'/'+path.relative_to(folder).as_posix())
        evidence(cache_receipt,'road_scene_r6/historical_captures_av/'+CAPTURE+'/ASSEMBLED_SCENE_AV.blend.json')
        film=json.loads((folder/'AQ_CURRENT_FILM.json').read_text());numeric=[]
        require(film['coverage']['missing_xy_count']==0 and film['class_ledger']['passed'] is True,'Actual current film proof failed')
        for name,key in (('AQ_FINAL_SURFACE.npz','source_sha256'),('AQ_CURRENT_FILM.npz','fields_sha256')):
            path=folder/name;h=file_sha(path);require(h==film[key],'AV numerical evidence changed')
            target='road_scene_r6/historical_numerical_av/'+name;kept[target]=path.read_bytes()
            numeric.append(dict(package_path=target,bytes=len(kept[target]),sha256=h,role='Exact actual AV generated evidence; never a replay input'))
        for name in ('at_foundation_numerical.json','au_view_grains_source_check.json','au_view_grains_blender_fixture.json',
                     'au_view_grains_blender_resources_b.json','cache_av_fixture_resources.json','av_source_preflight_tests.json','av_inherited_source_preflight_tests.json'):
            evidence(ROOT/'receipts'/name,'road_scene_r6/historical_evidence_av/'+name)
        kept['road_scene_r6/receipts/integrated_render_templates_av.json']=enc(dict(schema_version=6,source_admission=contract,
            captures=[row],default_selection='Current AV outward assembly replay only',immutable_numerical_inputs=oldtemplate['immutable_numerical_inputs'],
            cache_is_required_input=False,cache_output_is_optional=True))
        require(json.loads(kept['road_scene_r6/receipts/integrated_render_templates_ah.json'])['source_admission']==contract,'Strict Z contract changed')
        kept['regenerate.sh']=kept['regenerate.sh'].replace(b'render_checkpoint_aq.py',b'render_checkpoint_av.py')
        for n in LOCAL_FILES:kept['road_scene_r6/src/'+n]=(ROOT/'src'/n).read_bytes()
        for n in TEST_FILES:kept['road_scene_r6/checkpoint_tests_av/originals/'+n]=(ROOT/'src'/n).read_bytes()
        for path in sorted((ROOT/'checkpoint_tests_av').glob('*.py')):
            kept['road_scene_r6/checkpoint_tests_av/'+path.name]=path.read_bytes()
        # Retained production builders/static inputs remain byte-identical.
        required={n:h for n,h in prior['retained_exact_required_files_sha256'].items() if n in kept}
        for n,data in files.items():required[snapshot+n]=digest(data)
        for n in LOCAL_FILES:required['road_scene_r6/src/'+n]=digest(kept['road_scene_r6/src/'+n])
        require(all(digest(kept[n])==h for n,h in required.items()),'Inherited exact dependencies changed')
        names={Path(n).stem:n for n in files if n.endswith('.py')};edges=[]
        for name,data in files.items():
            if not name.endswith('.py') or name=='render.py':continue
            for node in ast.walk(ast.parse(data,filename=name)):
                imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
                for module in imports:
                    key=module.split('.')[0]
                    if key in names:edges.append(dict(source=snapshot+name,module=module,targets=[snapshot+names[key]]))
                    elif 'road_scene_r6/src/'+key+'.py' in kept:
                        raise ValueError('Captured AV helper omitted local dependency: '+key)
        retained_edges=[e for e in prior['local_import_edges'] if e['source'] in kept and all(n in kept for n in e['targets'])]
        closure=dict(prior)
        closure.update(current_AQ_v14_sha256=BASE_SHA,retained_exact_required_files_sha256=required,
            local_import_edges=retained_edges+edges,current_capture_dependency_edges=edges,missing_static_dependencies=[],
            current_replay_entrypoint='road_scene_r6/src/render_checkpoint_av.py',exact_generated_numerical_evidence=numeric,
            generated_numeric_evidence_used_as_replay_inputs=False,omitted_entries=omitted,
            additional_generated_dependency=HEIGHT,additional_height_consumer='fractured_boundary_ar.height_path',
            optional_cache_output='Fresh capture/ASSEMBLED_SCENE_AV.blend; never an input prerequisite')
        kept['road_scene_r6/receipts/current_dependency_closure_av.json']=enc(closure)
        kept['CURRENT_COMPONENT_EVIDENCE_AV_V15.json']=enc(dict(base_AQ_v14_sha256=BASE_SHA,
            exact_source_admission_contract=contract,latest_roles=['av_outward'],selected_current_capture=proof,
            original_local_evidence_sha256=original,packaged_public_evidence_sha256=public,evidence_normalization_checks=normalization,
            exact_generated_numerical_evidence=numeric,generated_evidence_used_as_replay_inputs=False,
            fresh_end_to_end_rebuild_verified=False,whole_scene_user_approved=False,material_quality_accepted=False,
            snapshot_is_authoritative=True,old_source_copies_retained_for_inherited_build_chain=True,
            cache_is_required_input=False,cache_bytes_included=False))
        kept['test_source_current_av.sh']=(ROOT/'src/test_source_current_av.sh').read_bytes()
        kept['README.txt']=(ROOT/'src/README_CURRENT_AV.txt').read_bytes()
        require(len(kept[MICROBED])==3913561 and digest(kept[MICROBED])==oldlock['files'][MICROBED],'Pinned microbed differs')
        require(len(kept[FIELD])==2093642 and digest(kept[FIELD])==FIELD_SHA,'Pinned Z stock ledger differs')
        require(not any(n.endswith(('.blend','.png','.exr','.pfm','.npy')) for n in kept),'Unexpected large generated/image payload')
        lock=dict(oldlock,version='AV current-only reproducible source delivery v15',base_AQ_v14_sha256=BASE_SHA,
            files={n:digest(d) for n,d in kept.items()},whole_scene_user_approved=False,fresh_end_to_end_rebuild_verified=False)
        kept['SOURCE_LOCK.json']=enc(lock)
    return kept,row,numeric


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--terminal-approved',action='store_true');args=p.parse_args()
    require(args.terminal_approved,'Wait for parent terminal approval before packaging actual evidence')
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    require(not OUT.exists() and not OUT.with_suffix('.tmp.zip').exists(),'Preserve earlier archive/staging')
    require(shutil.disk_usage(ROOT).free>180*1024**2,'Need packaging space plus reserve')
    kept,row,numeric=prepare();temp=OUT.with_suffix('.tmp.zip')
    for n,d in kept.items():
        if n.endswith('.py'):ast.parse(d,filename=n)
        if n.endswith('.sh'):subprocess.run(['bash','-n'],input=d,check=True)
    with zipfile.ZipFile(temp,'x') as z:
        for n,d in kept.items():
            info=zipfile.ZipInfo(n);info.create_system=3;info.external_attr=(stat.S_IFREG|(0o755 if n.endswith('.sh') else 0o644))<<16
            method=zipfile.ZIP_LZMA if n.endswith('.json') and len(d)>100000 else zipfile.ZIP_DEFLATED
            z.writestr(info,d,compress_type=method,compresslevel=6 if method==zipfile.ZIP_DEFLATED else None)
    require(temp.stat().st_size<19_000_000,'AV source archive exceeds 19 MB budget');kept.clear();gc.collect()
    with zipfile.ZipFile(temp) as z:
        require(z.testzip() is None,'AV CRC failure');lock=json.loads(z.read('SOURCE_LOCK.json'))
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(lock['files'])|{'SOURCE_LOCK.json'},'AV lock coverage differs')
        for n,h in lock['files'].items():require(digest(z.read(n))==h,'AV locked file differs: '+n)
        with tempfile.TemporaryDirectory(prefix='verify_av_current_',dir=ROOT/'deliverables') as path:
            z.extractall(path)
            result=subprocess.run(['bash','test_source_current_av.sh'],cwd=path,env=ENV,capture_output=True,text=True,timeout=240)
            output=result.stdout+'\n'+result.stderr
            require(result.returncode==0,'Extracted AV source tests failed:\n'+output)
        entries=len(z.namelist())
    require(file_sha(BASE)==BASE_SHA,'AQ baseline changed during packaging');temp.rename(OUT)
    report=dict(path=str(OUT),bytes=OUT.stat().st_size,sha256=file_sha(OUT),archive_entries=entries,
        AQ_v14_preserved_sha256=BASE_SHA,source_lock_and_crc_verified=True,exact_AV_snapshot_sha256=row['pipeline_sha256'],
        current_replay_roles=['av_outward'],static_closure_and_extracted_tests_passed=True,exact_historical_AV_arrays=numeric,
        cache_is_required_input=False,cache_created_by_packager=False,strict_Y_Z_admission_unchanged=True,
        fresh_end_to_end_regeneration_verified=False,whole_scene_user_approved=False,blender_launched=False,rendered=False,uploaded=False)
    (ROOT/'receipts/source_package_current_av_v15.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'receipts/source_package_current_av_v15_tests.log').write_text(output)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
