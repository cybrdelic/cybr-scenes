#!/usr/bin/env python3
"""Verify approved binary inputs without generating or changing any files.

The packaged copy lives beside PINNED_INPUTS.json and regenerate.sh. Any missing
or changed pinned cache is a hard failure; this verifier never regenerates it.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {
    'discrete_grains_r5/prototypes/microbed.npz': {
        'bytes': 3913561,
        'sha256': '7a09007d50e444c28231fd30cddda185d2f01146f3b1a47b014ebd25c0b415c4',
    },
}


def verify(root):
    root = Path(root).resolve()
    manifest_path = root / 'PINNED_INPUTS.json'
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError('Cannot read pinned-input manifest: ' + str(manifest_path)) from error
    if manifest.get('schema_version') != 1 or manifest.get('files') != EXPECTED:
        raise ValueError('Pinned-input manifest differs from the embedded approved identities')
    for name, expected in EXPECTED.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Missing or unsafe pinned input: ' + name)
        if path.stat().st_size != expected['bytes']:
            raise ValueError('Pinned-input byte count mismatch: ' + name)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != expected['sha256']:
            raise ValueError('Pinned-input SHA256 mismatch: ' + name)
    return EXPECTED


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except ValueError as error:
        parser.exit(1, 'Pinned-input verification failed: ' + str(error) + '\n')
    print(json.dumps({'pinned_inputs_verified': result}, sort_keys=True))


if __name__ == '__main__':
    main()
