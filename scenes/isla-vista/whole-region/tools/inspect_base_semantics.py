#!/usr/bin/env python3
"""Strict decoded GLB/NPZ comparison, with separate container diagnostics.

No numeric tolerance is an acceptance criterion. Rounded float hashes are only
for investigating failures. Unknown extensions, sparse accessors, nonembedded
resources and matrix accessors fail closed. This checker covers this exporter's
GLB 2.0 subset, not arbitrary glTF.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def array_record(array):
    array = np.asarray(array)
    assert not array.dtype.hasobject, "Object arrays are not permitted"
    array = np.ascontiguousarray(array.astype(array.dtype.newbyteorder('<'), copy=False))
    result = {"dtype": array.dtype.str, "shape": list(array.shape), "sha256": digest(array.tobytes())}
    if array.dtype.kind in "fiu":
        assert np.isfinite(array).all(), "Non-finite array"
        result.update(min=float(array.min()) if array.size else None,
                      max=float(array.max()) if array.size else None)
    return result


def inspect_glb(path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', raw)
    assert (magic, version, length) == (b'glTF', 2, len(raw))
    chunks = []; offset = 12
    while offset < length:
        size, kind = struct.unpack_from('<II', raw, offset)
        offset += 8
        assert offset + size <= length
        chunks.append((kind, raw[offset:offset + size])); offset += size
    assert [c[0] for c in chunks] == [0x4e4f534a, 0x004e4942]
    doc = json.loads(chunks[0][1]); binary = chunks[1][1]
    assert not doc.get('extensionsUsed') and not doc.get('extensionsRequired')
    assert len(doc['buffers']) == 1 and 'uri' not in doc['buffers'][0]
    assert len(binary) - doc['buffers'][0]['byteLength'] in range(4)
    views = doc['bufferViews']
    used_views = set()
    def view_bytes(index):
        used_views.add(index)
        view = views[index]
        assert view['buffer'] == 0
        assert not (set(view) - {'buffer', 'byteOffset', 'byteLength', 'byteStride', 'target', 'name'})
        start = view.get('byteOffset', 0); end = start + view['byteLength']
        assert 0 <= start <= end <= doc['buffers'][0]['byteLength']
        return memoryview(binary)[start:end]
    types = {5120:'i1', 5121:'u1', 5122:'<i2', 5123:'<u2', 5125:'<u4', 5126:'<f4'}
    widths = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4}
    accessors = []; rounded = []
    for source in doc['accessors']:
        assert not (set(source) - {'componentType', 'type', 'bufferView', 'count', 'byteOffset', 'normalized', 'min', 'max', 'name'})
        assert 'sparse' not in source and source['type'] in widths
        dtype = np.dtype(types[source['componentType']]); width = widths[source['type']]
        view = views[source['bufferView']]; data = view_bytes(source['bufferView'])
        stride = view.get('byteStride', width * dtype.itemsize)
        assert stride >= width * dtype.itemsize
        start = source.get('byteOffset', 0); count = source['count']
        assert count >= 0 and start >= 0
        assert start + max(0, count - 1)*stride + (width*dtype.itemsize if count else 0) <= len(data)
        array = np.ndarray((count, width), dtype=dtype, buffer=data, offset=start, strides=(stride, dtype.itemsize))
        record = {key: value for key, value in source.items() if key not in {'bufferView', 'byteOffset'}}
        record['decoded'] = array_record(array); accessors.append(record)
        rounded.append({str(decimals): digest(np.round(array.astype('<f8'), decimals).tobytes())
                        for decimals in (9, 7, 5)} if dtype.kind == 'f' else None)
    images = []; encoded = []
    for source in doc.get('images', []):
        assert 'uri' not in source and source['mimeType'] == 'image/png'
        assert not (set(source) - {'bufferView', 'mimeType', 'name'})
        data = view_bytes(source['bufferView'])
        with Image.open(io.BytesIO(data)) as picture:
            assert picture.format == 'PNG'
            picture.load()
            pixels = np.asarray(picture.convert('RGBA'))
            images.append({'mimeType': source['mimeType'], 'name': source.get('name'),
                           'size': list(picture.size), 'rgba8': array_record(pixels)})
        encoded.append(digest(data))
    assert used_views == set(range(len(views))), "Unhandled binary bufferView"
    semantic = copy.deepcopy(doc)
    semantic['accessors'] = accessors; semantic['images'] = images
    semantic.pop('bufferViews'); semantic.pop('buffers')
    semantic['asset'].pop('generator', None)
    return {'raw_sha256':digest(raw), 'semantic_sha256':digest(canonical(semantic)),
            'semantic':semantic, 'encoded_image_sha256':encoded,
            'float_rounded_hashes_diagnostic_only':rounded,
            'excluded_container_fields':['GLB chunk alignment/padding', 'buffers and bufferViews byte layout',
                                         'accessor byteOffset/bufferView', 'image PNG encoding', 'asset.generator'],
            'strict_contract':'Every decoded accessor value and accessor declaration, RGBA8 texel, node transform, mesh/material/texture binding, and remaining scene JSON must agree exactly.'}


def inspect_npz(path):
    semantic = {}
    with np.load(path, allow_pickle=False) as archive:
        for key in sorted(archive.files):
            array = archive[key]
            if key == 'metadata':
                assert array.shape == () and array.dtype.kind in 'US'
                semantic[key] = {'canonical_json':json.loads(str(array.item()))}
            else:
                semantic[key] = array_record(array)
    return {'raw_sha256':digest(path.read_bytes()), 'semantic_sha256':digest(canonical(semantic)),
            'semantic':semantic, 'excluded_container_fields':['ZIP member timestamps, compression and ordering', 'metadata JSON key ordering/whitespace']}


def inspect(root):
    return {'schema':'cybr-whole-region-decoded-base-v1',
            'sector.glb':inspect_glb(root / 'sector.glb'),
            'measured-terrain-state.npz':inspect_npz(root / 'measured-terrain-state.npz')}


def differences(left, right, path=''):
    if type(left) is not type(right):
        return [{'path':path, 'expected':left, 'actual':right}]
    if isinstance(left, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                result.append({'path':path + '/' + key, 'expected':left.get(key), 'actual':right.get(key)})
            else: result += differences(left[key], right[key], path + '/' + key)
        return result
    if isinstance(left, list):
        if len(left) != len(right): return [{'path':path + '/length', 'expected':len(left), 'actual':len(right)}]
        return sum((differences(a, b, path + '/' + str(i)) for i,(a,b) in enumerate(zip(left,right))), [])
    return [] if left == right else [{'path':path, 'expected':left, 'actual':right}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('evidence/full-iv-roofs'))
    parser.add_argument('--write-baseline', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    actual = inspect(args.root)
    if args.write_baseline:
        assert not args.write_baseline.exists(), 'Baseline is immutable; choose a new path'
        args.write_baseline.write_text(json.dumps(actual, indent=2) + '\n')
    if args.baseline:
        expected = json.loads(args.baseline.read_text()); comparisons = {}
        for name in ('sector.glb', 'measured-terrain-state.npz'):
            a, e = actual[name], expected[name]
            diff = differences(e['semantic'], a['semantic'])
            comparisons[name] = {'raw_bytes_equal':a['raw_sha256'] == e['raw_sha256'],
                                 'strict_decoded_semantics_equal':not diff,
                                 'semantic_differences':diff,
                                 'expected_raw_sha256':e['raw_sha256'],
                                 'actual_raw_sha256':a['raw_sha256'],
                                 'expected_semantic_sha256':e['semantic_sha256'],
                                 'actual_semantic_sha256':a['semantic_sha256']}
            if name == 'sector.glb':
                comparisons[name]['encoded_image_equal'] = [x == y for x,y in zip(e['encoded_image_sha256'],a['encoded_image_sha256'])]
                comparisons[name]['rounded_accessor_equal_diagnostic_only'] = [x == y for x,y in zip(e['float_rounded_hashes_diagnostic_only'],a['float_rounded_hashes_diagnostic_only'])]
        passed = all(item['strict_decoded_semantics_equal'] for item in comparisons.values())
        result = {'passed':passed, 'comparisons':comparisons, 'actual':actual,
                  'scope':'Diagnostic strict decoded comparison. No numerical tolerance and no changed raw-byte baseline.'}
        assert args.report, '--report is required for comparison'
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'passed':passed, 'comparisons':comparisons}, indent=2))
        return 0 if passed else 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
