"""Offline, light-weight replay contracts; no renderer or network is started.

Run from the scene root: python -m unittest discover -s verification -p 'test_*.py'
Fetched inputs are checked when present; fetch them first for a full local audit.
"""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import public_inputs


def encoded(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode()


class PublicInputContracts(unittest.TestCase):
    def setUp(self):
        self.document = {
            'fields': [{'name': 'OBJECTID', 'type': 'esriFieldTypeOID'}],
            'spatialReference': {'wkid': 4326, 'latestWkid': 4326},
            'features': [
                {'attributes': {'OBJECTID': 1, 'Name': 'sample', 'Height': 4.0},
                 'geometry': {'rings': [[[1., 2.], [3., 2.], [3., 4.], [1., 2.]]]}},
                {'attributes': {'OBJECTID': 2, 'Name': None},
                 'geometry': {'x': 2.5, 'y': 3.5}},
            ],
        }
        self.data = encoded(self.document)
        self.row = {'path': 'data/fixture.json', 'kind': 'geographic',
                    'url': 'https://example.invalid/fixture',
                    'sha256': hashlib.sha256(self.data).hexdigest(),
                    'consumed_features_sha256': public_inputs.canonical(self.document)}

    def changed(self, edit):
        document = copy.deepcopy(self.document)
        edit(document)
        return encoded(document)

    def assert_rejected(self, edit):
        with self.assertRaises(ValueError):
            public_inputs.validate(self.changed(edit), self.row)

    def test_raw_bytes_match(self):
        self.assertEqual(public_inputs.validate(self.data, self.row)['match'], 'raw_sha256')

    def test_unconsumed_schema_and_formatting_may_change(self):
        document = copy.deepcopy(self.document)
        document['fields'][0]['type'] = 'esriFieldTypeInteger'
        document['geometryType'] = 'unconsumed-service-schema'
        data = json.dumps(document, indent=3).encode()
        self.assertEqual(public_inputs.validate(data, self.row)['match'], 'ordered_features_and_crs')

    def test_integral_float_encoding_may_change(self):
        data = self.changed(lambda d: d['features'][0]['attributes'].update(Height=4))
        self.assertEqual(public_inputs.validate(data, self.row)['match'], 'ordered_features_and_crs')

    def test_reject_coordinate_drift(self):
        self.assert_rejected(lambda d: d['features'][0]['geometry']['rings'][0][0].__setitem__(0, 1.000001))

    def test_reject_attribute_drift(self):
        self.assert_rejected(lambda d: d['features'][0]['attributes'].update(Name='changed'))
        self.assert_rejected(lambda d: d['features'][0]['attributes'].update(Height=4.001))
        self.assert_rejected(lambda d: d['features'][1]['attributes'].update(Name=''))

    def test_reject_feature_order_or_membership_drift(self):
        self.assert_rejected(lambda d: d['features'].reverse())
        self.assert_rejected(lambda d: d['features'].pop())
        self.assert_rejected(lambda d: d['features'].append(copy.deepcopy(d['features'][0])))

    def test_reject_crs_drift(self):
        self.assert_rejected(lambda d: d['spatialReference'].update(wkid=3857))

    def test_reject_nonfinite_coordinates(self):
        self.assert_rejected(lambda d: d['features'][1]['geometry'].update(x=float('nan')))

    def test_failed_download_does_not_install(self):
        changed = self.changed(lambda d: d['features'][0]['attributes'].update(Name='changed'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'INPUTS.json').write_text(json.dumps({'files': [self.row]}))
            with patch.object(public_inputs, 'ROOT', root), patch.object(public_inputs.urllib.request, 'urlopen', return_value=io.BytesIO(changed)):
                with self.assertRaises(ValueError):
                    public_inputs.resolve(root, download=True)
            self.assertFalse((root/self.row['path']).exists())
            self.assertFalse((root/'PUBLIC_INPUT_VALIDATION.json').exists())
            self.assertEqual(list(root.rglob('*.partial')), [])

    def test_reject_outside_destination(self):
        row = dict(self.row, path='../escaped.json')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'INPUTS.json').write_text(json.dumps({'files': [row]}))
            with patch.object(public_inputs, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Unsafe input path'):
                    public_inputs.resolve(root)


class SourceClosureContracts(unittest.TestCase):
    def test_extracted_definitions_match_recorded_ast_hashes(self):
        for row in json.loads((ROOT/'SCENE_SOURCE.json').read_text())['extractions']:
            with self.subTest(path=row['destination']):
                tree = ast.parse((ROOT/row['destination']).read_text())
                nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in row['definitions']]
                self.assertEqual([node.name for node in nodes], row['definitions'])
                digest = hashlib.sha256(''.join(ast.dump(node, include_attributes=False) for node in nodes).encode()).hexdigest()
                self.assertEqual(digest, row['definition_ast_sha256'])

    def test_present_input_files_validate(self):
        checked = 0
        for row in json.loads((ROOT/'INPUTS.json').read_text())['files']:
            path = ROOT/row['path']
            if path.is_file():
                with self.subTest(path=row['path']):
                    public_inputs.validate(path.read_bytes(), row)
                    checked += 1
        if not checked:
            self.skipTest('Fetch public inputs to exercise this local-file check.')

    def test_source_has_no_legacy_runtime_import(self):
        for path in (ROOT/'work').rglob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('cybr_light', 'cybr_terrain')), path)
                if isinstance(node, ast.Import):
                    self.assertFalse(any(name.name.startswith(('cybr_light', 'cybr_terrain')) for name in node.names), path)


if __name__ == '__main__':
    unittest.main()
