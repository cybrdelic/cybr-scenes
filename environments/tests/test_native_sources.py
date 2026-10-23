"""Shared-source resolution and build-cache invalidation regression tests."""
from pathlib import Path
import hashlib
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_sources


class NativeSourceTests(unittest.TestCase):
    def test_moved_name_uses_shared_bytes_even_if_old_copy_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, shared = root / 'native', root / 'shared'
            native.mkdir()
            shared.mkdir()
            (native / 'spectral_geometry.h').write_bytes(b'old engine copy')
            (shared / 'spectral_geometry.h').write_bytes(b'shared owner')
            with patch.object(native_sources, 'SHARED_DIRECTORY', shared):
                resolved = native_sources.native_source(native, 'spectral_geometry.h')
                self.assertEqual(resolved, shared / 'spectral_geometry.h')
                self.assertEqual(resolved.read_bytes(), b'shared owner')
                (shared / 'spectral_geometry.h').unlink()
                with self.assertRaises(FileNotFoundError):
                    native_sources.native_source(native, 'spectral_geometry.h').read_bytes()

    def test_receipt_logical_source_order_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, shared = root / 'native', root / 'shared'
            native.mkdir()
            shared.mkdir()
            names = ('spectral_desert.cpp', 'spectral_geometry.h', 'local.h')
            contents = (b'entrypoint', b'unchanged geometry', b'local policy')
            for name, content in zip(names, contents):
                owner = shared if name in native_sources.SHARED_HEADERS else native
                (owner / name).write_bytes(content)
            expected = hashlib.sha256(b''.join(contents)).hexdigest()
            with patch.object(native_sources, 'SHARED_DIRECTORY', shared):
                actual = hashlib.sha256(b''.join(
                    native_sources.native_source(native, name).read_bytes()
                    for name in names)).hexdigest()
            self.assertEqual(actual, expected)

    def test_shared_changes_invalidate_the_standalone_build_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, shared = root / 'native', root / 'shared'
            native.mkdir()
            shared.mkdir()
            (native / 'spectral_scenes.cpp').write_bytes(b'entrypoint')
            (native / 'scene_policy.h').write_bytes(b'local policy')
            (shared / 'spectral_geometry.h').write_bytes(b'geometry v1')
            (shared / 'surface_detail.hpp').write_bytes(b'surface v1')
            with patch.object(native_sources, 'SHARED_DIRECTORY', shared):
                def digest():
                    return hashlib.sha256(b''.join(path.read_bytes() for path in
                        native_sources.dependency_files(native, 'spectral_scenes.cpp'))).hexdigest()
                baseline = digest()
                (shared / 'spectral_geometry.h').write_bytes(b'geometry v2')
                changed_header = digest()
                self.assertNotEqual(baseline, changed_header)
                (shared / 'surface_detail.hpp').write_bytes(b'surface v2')
                self.assertNotEqual(changed_header, digest())
                self.assertEqual(native_sources.shared_include_flags(), ['-I', str(shared)])


    def test_historical_build_uses_overlays_and_removes_stale_relocated_copies(self):
        source = Path(__file__).resolve().parents[1] / 'tools' / 'compile_originals.py'
        spec = importlib.util.spec_from_file_location('original_build_fixture', source)
        original = importlib.util.module_from_spec(spec)
        # Exercise file reconstruction only; native execution is tested separately.
        runtime = ModuleType('cybr_scenes')
        for name in ('SOURCES', 'run', 'sha', 'atomic_json', 'dependency_fingerprint'):
            setattr(runtime, name, None)
        with patch.dict(sys.modules, cybr_scenes=runtime):
            spec.loader.exec_module(original)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = Path('engines/geo/cybr-geo/native/spectral_scenes.cpp')
            (root / relative).parent.mkdir(parents=True)
            (root / relative).write_bytes(b'current scene')
            (root / 'shared').mkdir()
            (root / 'shared/spectral_geometry.h').write_bytes(b'unchanged geometry')
            (root / 'shared/surface_detail.hpp').write_bytes(b'current surface')
            overlay = root / 'provenance/native-before'
            (overlay / relative).parent.mkdir(parents=True)
            (overlay / relative).write_bytes(b'historical scene')
            (overlay / 'shared').mkdir()
            (overlay / 'shared/surface_detail.hpp').write_bytes(b'historical surface')
            output = root / 'build/original-engines/geo/cybr-geo/native'
            output.mkdir(parents=True)
            stale = output / 'spectral_geometry.h'
            stale.write_bytes(b'stale generated copy')
            with patch.multiple(original, ROOT=root, SOURCES={'geo': str(relative)}), \
                 patch.object(original.shutil, 'which', return_value='fixture-compiler'), \
                 patch.object(original, 'run', return_value={}) as run, \
                 patch.object(original, 'sha', return_value='fixture-hash'), \
                 patch.object(original, 'dependency_fingerprint', return_value='fixture-fingerprint'), \
                 patch.object(original, 'atomic_json'):
                original.main()
                self.assertFalse(stale.exists())
                self.assertEqual((output / 'spectral_scenes.cpp').read_bytes(), b'historical scene')
                shared = root / 'build/original-shared'
                self.assertEqual((shared / 'spectral_geometry.h').read_bytes(), b'unchanged geometry')
                self.assertEqual((shared / 'surface_detail.hpp').read_bytes(), b'historical surface')
                self.assertIn('-I' + str(shared), run.call_args_list[0].args[0])
                # An explicit pre-upgrade policy must still override shared ownership.
                (overlay / relative.parent / 'spectral_geometry.h').write_bytes(b'historical geometry')
                original.main()
                self.assertEqual(stale.read_bytes(), b'historical geometry')


if __name__ == '__main__':
    unittest.main()
