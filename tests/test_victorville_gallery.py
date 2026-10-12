"""Retained external-renderer study: honest provenance and complete local links."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / 'scenes/victorville-road'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src') and value:
                self.targets.append(value)


class VictorvilleGalleryTests(unittest.TestCase):
    def test_exact_render_and_renderer(self):
        meta = json.loads((SCENE / 'scene.json').read_text())
        self.assertEqual(meta['renderer']['name'], 'Blender Cycles')
        self.assertEqual(meta['renderer']['device'], 'CPU')
        self.assertFalse(meta['renderer']['denoised'])
        self.assertEqual(meta['status'], 'work-in-progress')
        image = (SCENE / meta['render']['path']).read_bytes()
        self.assertEqual(hashlib.sha256(image).hexdigest(), meta['render']['sha256'])
        self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', image[16:24]), (1000, 667))
        self.assertEqual(image[24:26], bytes([16, 2]))  # RGB16, not a re-encoded thumbnail.

    def test_gallery_local_links_and_explicit_backend(self):
        path = ROOT / 'docs/victorville-road-gallery.html'
        markup = path.read_text()
        self.assertIn('Blender 4.3.2 Cycles', markup)
        self.assertIn('CPU preview', markup)
        parser = Links(); parser.feed(markup)
        for target in parser.targets:
            parts = urlsplit(target)
            if parts.scheme or not parts.path:
                continue
            resolved = (path.parent / unquote(parts.path)).resolve()
            self.assertTrue(resolved.is_relative_to(ROOT), target)
            self.assertTrue(resolved.is_file(), target)

    def test_native_scene_registry_is_not_given_a_fake_port(self):
        records = json.loads((ROOT / 'environments/scenes.json').read_text())
        self.assertNotIn('victorville-road', [s['id'] for s in records['scenes']])


if __name__ == '__main__':
    unittest.main()
