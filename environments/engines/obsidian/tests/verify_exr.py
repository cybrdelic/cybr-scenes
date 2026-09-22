#!/usr/bin/env python3
"""Verify this package's uncompressed scanline EXR against the native PFM.

This is a small independent layout reader, not a general OpenEXR implementation.
Only RGB float32, unit channel sampling and compression NONE are accepted.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import json
import struct
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finish import pfm


def c_string(stream) -> str:
    value = bytearray()
    while True:
        ch = stream.read(1)
        if not ch:
            raise ValueError('Unexpected end of EXR header.')
        if ch == b'\0':
            return value.decode('ascii')
        value.extend(ch)
        if len(value) > 255:
            raise ValueError('Unexpectedly long header identifier.')


def read_uncompressed_rgb(path: Path) -> np.ndarray:
    with path.open('rb') as stream:
        magic, version = struct.unpack('<II', stream.read(8))
        if magic != 20000630 or version != 2:
            raise ValueError('Expected a single-part version-2 EXR.')
        attributes = {}
        while True:
            name = c_string(stream)
            if not name:
                break
            kind = c_string(stream)
            length, = struct.unpack('<I', stream.read(4))
            if length > 1024 * 1024:
                raise ValueError('Unreasonable header attribute size.')
            value = stream.read(length)
            if len(value) != length:
                raise ValueError('Truncated header attribute.')
            attributes[name] = (kind, value)
        if attributes['compression'][1] != b'\0':
            raise ValueError('This verifier supports compression NONE only.')
        xmin, ymin, xmax, ymax = struct.unpack('<iiii', attributes['dataWindow'][1])
        width, height = xmax-xmin+1, ymax-ymin+1
        if xmin != 0 or ymin != 0 or width <= 0 or height <= 0:
            raise ValueError('Unexpected data window.')
        import io
        channels = []
        with io.BytesIO(attributes['channels'][1]) as channel_stream:
            while True:
                name = c_string(channel_stream)
                if not name:
                    break
                typ, linear, xs, ys = struct.unpack('<iB3xii', channel_stream.read(16))
                if typ != 2 or xs != 1 or ys != 1 or name not in 'RGB':
                    raise ValueError('Expected float32 unit-sampling RGB channels.')
                channels.append(name)
        if set(channels) != set('RGB') or len(channels) != 3:
            raise ValueError('Expected exactly R, G, B.')
        offsets = struct.unpack('<'+'Q'*height, stream.read(height*8))
        result = np.empty((height, width, 3), dtype=np.float32)
        seen = set()
        for offset in offsets:
            stream.seek(offset)
            y, size = struct.unpack('<ii', stream.read(8))
            if y in seen or not 0 <= y < height or size != width*12:
                raise ValueError('Unexpected or duplicate scanline.')
            seen.add(y)
            row = np.frombuffer(stream.read(size), dtype='<f4').reshape(3, width)
            for index, name in enumerate(channels):
                result[y, :, 'RGB'.index(name)] = row[index]
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pfm', type=Path)
    parser.add_argument('exr', type=Path)
    args = parser.parse_args()
    native = pfm(args.pfm)
    exported = read_uncompressed_rgb(args.exr)
    assert np.isfinite(native).all(), 'Native film contains nonfinite values.'
    assert np.array_equal(native, exported), 'EXR differs from the native float32 film.'
    print(json.dumps({'status': 'PASS', 'float32_values_exact': True,
                      'dimensions': [native.shape[1], native.shape[0]],
                      'finite_values': True, 'negative_values': int((native < 0).sum()),
                      'linear_min': float(native.min()), 'linear_max': float(native.max()),
                      'maximum_absolute_export_error': float(np.max(np.abs(native-exported))),
                      'reader_scope': 'independent NONE-compressed RGB scanline layout check'}, indent=2))


if __name__ == '__main__':
    main()
