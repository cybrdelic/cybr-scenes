"""Read-only, fail-closed validation for reusing a completed clean capture."""
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from capture_modes import capture_mode,final_image,is_workbench_raw,component_filter_policy
from transport_components import LIGHT_PASSES

PIPELINE_FILES = frozenset({
    'render.py', 'render.sh', 'clean_render.sh', 'oidn_image_bridge.py',
    'clean_receipt.py', 'png_precision_check.py', 'oidn_contract.py',
    'verify_pipeline_snapshot.py', 'capture_modes.py', 'raw_receipt.py',
    'transport_components.py','component_image_bridge.py','component_receipt.py',
})


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_cache(job, receipt_path, pipeline_root):
    """Return {valid: bool, reasons: list[str]}; never write files or render.

    Both the recorded immutable snapshot and the current capture implementation
    must match. Packed image bytes are covered by the verified scene hash;
    external image files are checked individually. All retained outputs matter,
    including raw guides and the linear denoised EXR, not just the display PNG.
    """
    reasons = []

    def require(condition, reason):
        if not condition:
            reasons.append(reason)

    try:
        root = Path(pipeline_root).resolve()
        receipt = json.loads(Path(receipt_path).read_text())
        require(receipt['job'] == job, 'Job differs from cached capture')
        source_hash = hash_file(job['source'])
        require(source_hash == receipt['source_sha256'], 'Source scene changed')
        if job.get('source_sha256'):
            require(source_hash == job['source_sha256'], 'Expected source SHA mismatch')

        pipeline = receipt['pipeline']
        files = pipeline['files']
        require(PIPELINE_FILES <= set(files) <= PIPELINE_FILES | {'path_config.py'},
                'Pipeline stage manifest is incomplete or unsupported')
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        require(digest == pipeline['sha256'], 'Pipeline manifest digest mismatch')
        snapshot = root / 'pipeline_snapshots' / digest
        require(Path(pipeline['snapshot']).resolve() == snapshot, 'Snapshot path does not match digest')
        for name, expected_hash in files.items():
            if Path(name).name != name:
                reasons.append('Pipeline stage is not a basename')
                continue
            require(hash_file(snapshot / name) == expected_hash, 'Modified pipeline snapshot: ' + name)
            current = (root.parent / 'material-production' / 'materials' / name
                       if name == 'path_config.py' else root / name)
            require(hash_file(current) == expected_hash, 'Current pipeline changed: ' + name)

        relocation = receipt.get('relocation')
        configured_map = os.environ.get('MATERIAL_PATH_MAP_FILE')
        require(bool(configured_map) == bool(relocation), 'Path-map configuration context changed')
        if relocation:
            require('path_config.py' in files, 'Relocation helper missing from snapshot')
            require(relocation['helper_sha256'] == files.get('path_config.py'),
                    'Relocation helper digest mismatch')
            if configured_map:
                require(Path(configured_map).resolve() == Path(relocation['config_path']),
                        'Path-map configuration location changed')
            require(hash_file(relocation['config_path']) == relocation['config_sha256'],
                    'Path-map configuration content changed')
        else:
            require('path_config.py' not in files, 'Unrecorded relocation stage')

        # A packed image's displayed path may be absent or point to an unrelated
        # external file. Its actual bytes are already inside the hashed scene.
        checked = {}
        for dependency in receipt['image_dependencies']:
            if dependency['packed']:
                continue
            path = dependency['path']
            if path not in checked:
                checked[path] = hash_file(path)
            require(checked[path] == dependency['sha256'], 'External image changed: ' + path)

        raw = Path(job['output'])
        mode=capture_mode(job);workbench=is_workbench_raw(job);clean=final_image(job)
        require(receipt.get('capture_mode','guided')==mode,'Processing mode differs')
        guide_dir = raw.parent / (raw.stem + '_guides')
        require(Path(receipt['raw_path']) == raw, 'Raw output path mismatch')
        require(Path(receipt[{'guided':'clean_path','unfiltered':'unfiltered_path','component-recombined':'component_path'}[mode]]) == clean, 'Clean output path mismatch' if mode=='guided' else 'Unfiltered output path mismatch')
        guides = receipt['guide_paths']
        require((not guides) if workbench else (len(guides)==3 and len(set(guides))==3), 'Required raw-guide set differs')
        hashes = receipt['files_sha256']
        required = [raw, clean, *map(Path, guides)]
        if mode=='guided':required.append(guide_dir/'denoised_linear.exr')
        elif mode=='component-recombined':
            component_dir=guide_dir/'components';policy=component_filter_policy(job);both=policy=='filter_both'
            require(receipt.get('component_filter_policy','retain_transmission')==policy,'Component filter policy differs')
            transports=receipt['transport_paths'];require(set(transports)==set(LIGHT_PASSES),'Physical transport pass set differs')
            required.extend(map(Path,transports.values()))
            required.extend(component_dir/n for n in ['linear_component_accounting.npz','denoised_remainder_linear.exr','component_recombined_linear.exr','export_receipt.json','component_receipt.json','identity_raw_passthrough.png','REVIEW_retained_signal.png','REVIEW_raw_remainder.png','REVIEW_filtered_remainder.png'])
            if both:required.extend(component_dir/n for n in ['denoised_transmission_linear.exr','REVIEW_filtered_transmission.png'])
        elif workbench:required.append(raw.with_suffix('.png.native.json'))
        else:required.extend([guide_dir/'raw_passthrough.png',guide_dir/'png_roundtrip_check.json',guide_dir/'guide_contract.json',guide_dir/'guide_stats.json'])
        for path in required:
            require(str(path) in hashes, 'Required output hash missing: ' + str(path))
        for path, expected_hash in hashes.items():
            require(hash_file(path) == expected_hash, 'Capture output changed: ' + path)
        require(receipt['raw_guides_retained'] is (not workbench), 'Raw guide-retention claim differs')
        if mode=='guided':
            contract=receipt['oidn_guide_contract']
            require(contract['valid'] is True and not contract['violations'],'Invalid OIDN guide contract')
        elif mode=='component-recombined':
            component=receipt['component_filter'];require(receipt['engine']=='CYCLES' and receipt['oidn_executed'] is True,'Invalid component engine/filter claim')
            require(component['identity_exact_float32'] is True,'Component identity reconstruction failed')
            require(component['feature_contract']['valid'] is True and not component['feature_contract']['violations'],'Invalid remainder guide contract')
            require(component.get('component_filter_policy','retain_transmission')==policy,'Component export/filter policy differs')
            require(component['transmission_emission_untouched'] is (not both) and component['delta64_untouched'] is True and component['clipping'] is False,'Protected component changed')
            if both:
                tc=component['transmission_feature_contract']
                require(tc['valid'] is True and not tc['violations'],'Invalid transmission guide contract')
                require(component.get('both_components_filtered') is True and component.get('signed_transmission_terms_untouched') is True and component['signed_transmission_accounting']['signed_terms_untouched'] is True,'Signed transmission protection/filter scope differs')
            require(receipt['noise_acceptance'] is False and receipt['quality_acceptance'] is False,'Component processing cannot automatically accept visual quality')
            reference=job.get('component_reference_beauty')
            if reference:require(hash_file(reference['path'])==reference['sha256'] and component['independent_comparison']['equal_float32'] is True,'Independent component reference changed or differs')
        else:
            require(receipt['postprocess']=='none' and receipt['oidn_executed'] is False,'Unfiltered capture executed filtering')
            require(receipt['noise_acceptance'] is False,'Raw capture cannot automatically accept noise')
            require(receipt['raw_hdr_retained'] is (not workbench),'Raw HDR retention claim differs')
            require(receipt['physical_lighting_evaluated'] is (not workbench),'Geometry-study lighting claim differs')
        precision=receipt['native_png_validation'] if workbench else receipt['color_bridge_native_precision']
        require(precision['opaque'] is True,'Nonopaque native PNG')
        if not workbench:require(precision['max_error_native']<=1,'Invalid native PNG precision check')
        require(precision['bit_depth']==int(job.get('color_depth',16)),'Native PNG bit depth differs from requested capture')
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append('Incomplete or unreadable cache: ' + str(error))
    return {'valid': not reasons, 'reasons': reasons}
