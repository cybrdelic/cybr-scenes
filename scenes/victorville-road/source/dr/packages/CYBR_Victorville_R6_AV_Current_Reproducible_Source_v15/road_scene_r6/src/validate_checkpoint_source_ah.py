#!/usr/bin/env python3
"""Strict validation-only admission of Z for portable component replay."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT.parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if a.receipt.exists():
        raise FileExistsError('Preserve existing admission receipt')
    lock = json.loads((PACKAGE / 'SOURCE_LOCK.json').read_text())
    template = ROOT / 'receipts/integrated_render_templates_ah.json'
    if digest(template) != lock['files'][str(template.relative_to(PACKAGE))]:
        raise ValueError('Replay template source lock mismatch')
    contract = json.loads(template.read_text())['source_admission']
    for relative, expected in contract['files_sha256'].items():
        path = (PACKAGE / relative).resolve()
        if not path.is_relative_to(PACKAGE.resolve()) or digest(path) != expected:
            raise ValueError('Pinned semantic source admission dependency differs: ' + relative)
    guard_path = PACKAGE / contract['manifest_path']
    guard = json.loads(guard_path.read_text())
    helper = PACKAGE / contract['helper_path']
    sys.path.insert(0, str(ROOT / 'src'))
    spec = importlib.util.spec_from_file_location('checkpoint_semantic_guard_ah', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.digest_record(guard['snapshot']) != guard['semantic_sha256']:
        raise ValueError('Guard semantic digest differs')
    if guard['source_sha256'] != contract['historical_source_sha256']:
        raise ValueError('Guard belongs to a different original source')
    before = digest(a.source)
    import bpy
    bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()))
    bpy.context.view_layer.update()
    semantic = module.verify_scene(bpy, guard)
    if digest(a.source) != before:
        raise ValueError('Source changed during admission')
    result = dict(semantic_match=True, semantic_sha256=semantic,
                  actual_source_sha256=before, historical_source_sha256=guard['source_sha256'],
                  source_serialization_matches_original=before == guard['source_sha256'],
                  serialized_byte_equality_required=False, guard_file_sha256=digest(guard_path),
                  validation_only=True, model_executed=False, scene_written=False)
    with a.receipt.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print('COMPONENT_Z_ADMISSION', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
