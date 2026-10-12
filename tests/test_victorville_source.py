"""Verify the portable DR execution closure without starting Blender."""
from pathlib import Path
import hashlib
import json
import os
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('CYBR_ROAD_SOURCE', str(ROOT / 'scenes/victorville-road/source/dr')))

class RoadSourceTests(unittest.TestCase):
    def test_payload_and_symlinks(self):
        manifest = json.loads((SOURCE / 'PUBLIC_MANIFEST.json').read_text())
        self.assertEqual(manifest['selected_scene'], 'DR')
        for item in manifest['files']:
            path = SOURCE / item['path']
            self.assertTrue(path.resolve().is_relative_to(SOURCE.resolve()), item['path'])
            if item['git_mode'] == '120000':
                self.assertTrue(path.is_symlink(), item['path'])
                self.assertTrue(path.exists(), item['path'])
                data = os.readlink(path).encode()
            else:
                self.assertTrue(path.is_file(), item['path'])
                data = path.read_bytes()
            self.assertEqual(len(data), item['bytes'], item['path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'], item['path'])

    def test_split_input_bytes(self):
        manifest = json.loads((SOURCE / 'SPLIT_INPUTS.json').read_text())
        for item in manifest['inputs']:
            digest = hashlib.sha256()
            size = 0
            for part in item['parts']:
                data = (SOURCE / part['path']).read_bytes()
                digest.update(data)
                size += len(data)
            self.assertEqual(size, item['bytes'])
            self.assertEqual(digest.hexdigest(), item['sha256'])

    def test_recorded_execution_scope(self):
        result = json.loads((SOURCE / 'VALIDATION.json').read_text())
        self.assertEqual(result['selected'], 'DR')
        self.assertTrue(result['recovered_DR_RGB_pixels_identical_to_saved_2000x1334'])
        self.assertTrue(result['installed_220000_ID_and_XYZ_bitwise_identity_passed'])
        self.assertFalse(result['lost_I_recovered'])
        self.assertEqual(result['second_from_zero_public_rebuild'], 'not run')

if __name__ == '__main__':
    unittest.main()
