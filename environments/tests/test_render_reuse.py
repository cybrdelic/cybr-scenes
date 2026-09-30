"""Regression tests for settings-sensitive reuse and failed replacement receipts."""
from argparse import Namespace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cybr_scenes as scenes


class ReuseTests(unittest.TestCase):
    def test_failed_native_self_test_is_not_cached_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'build/geo_r2';binary.parent.mkdir();binary.write_bytes(b'binary')
            receipt=binary.with_suffix('.build.json');receipt.write_text('{}')
            def run(command,*unused):
                if '--self-test' in command:raise RuntimeError('intentional failed native test')
                return {'returncode':0}
            with patch.object(scenes,'ROOT',root),patch.object(scenes,'dependency_fingerprint',return_value='changed'),patch.object(scenes,'run',run),patch.object(scenes.subprocess,'check_output',return_value='compiler'):
                with self.assertRaises(RuntimeError):scenes.compile_engine('geo',force=True)
            self.assertFalse(receipt.exists())

    def test_changed_settings_render_and_missing_film_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);mesh=root/'mesh';mesh.write_bytes(b'geometry')
            atlas=root/'assets/mineral_detail.cdt';atlas.parent.mkdir();atlas.write_bytes(b'atlas')
            binary=root/'build/geo_r2';binary.parent.mkdir();binary.write_bytes(b'executable')
            binary.with_suffix('.build.json').write_text(json.dumps({'source_fingerprint':'source'}))
            (root/'cybr_scenes.py').write_text('pipeline')
            (root/'tools').mkdir();(root/'tools/finish_r2.py').write_text('finishing')
            scene={'id':'test','engine':'geo','aspect':[3,2],'spp':96,'water_spp':96}
            args=Namespace(baseline=False,output=root/'output',force=False,threads=2,timeout=60,
                           width=64,height=48,spp=4,water_spp=4,quality='preview')
            stem=root/'output/test/hero/hero';calls=[]
            def command(*a,**k):return ['native'],root,['finish']
            def run(argv,cwd,log,*unused):
                calls.append(argv[0])
                stem.with_suffix('.pfm').write_bytes(b'film')
                stem.with_suffix('.png').write_bytes(b'png')
                stem.with_suffix('.json').write_text('{}')
                return {'returncode':0}
            result={'passed':True,'png_sha256':'png','raw_pfm_sha256':'film',
                    'native_metadata_sha256':'metadata','spectral_film':None}
            with patch.object(scenes,'ROOT',root),patch.object(scenes,'prepare_scene',return_value=mesh),patch.object(scenes,'compile_engine',return_value=binary),patch.object(scenes,'render_command',command),patch.object(scenes,'run',run),patch.object(scenes,'verify_render',return_value=result):
                scenes.render_scene(scene,args);self.assertEqual(calls,['native','finish'])
                scenes.render_scene(scene,args);self.assertEqual(len(calls),2)
                stem.with_suffix('.spectral').write_bytes(b'stale production film')
                args.width=80;scenes.render_scene(scene,args);self.assertEqual(len(calls),4)
                self.assertFalse(stem.with_suffix('.spectral').exists())
                stem.with_suffix('.pfm').unlink()
                scenes.render_scene(scene,args);self.assertEqual(len(calls),6)
                self.assertTrue((stem.parent/'receipt.json').exists())
                args.spp=8
                with patch.object(scenes,'run',side_effect=RuntimeError('intentional')):
                    with self.assertRaises(RuntimeError):scenes.render_scene(scene,args)
                self.assertFalse((stem.parent/'receipt.json').exists())


if __name__=='__main__':unittest.main()
