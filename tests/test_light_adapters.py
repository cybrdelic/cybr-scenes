"""Trace tiny real inputs through every retained mesh format and the new engine."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import argparse
import subprocess
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'rendering'))
import light_render as adapter
from cybr_light import Meshlets, Scene, render, read_pfm


class AdapterTests(unittest.TestCase):
    def trace(self,scene,mesh,stem):
        scene.settings(32,24,4,5,1,4)
        scene.camera((0,0,2),(.3,.3,0),(0,1,0),fov=50)
        scene.emit('environment',(1,1,1),1);scene.emit('environment_flat');scene.mesh(mesh)
        report=render(scene,stem)
        self.assertEqual(report['invalid_path_samples'],0)
        self.assertGreater(report['meshlets'],0)
        self.assertTrue(np.isfinite(read_pfm(stem.with_suffix('.pfm'))).all())
        self.assertGreater(report['mean_linear_luminance'],0)

    def test_cvr_palette_does_not_overwrite_original_material_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.cvr2';mesh=root/'mesh.clm'
            a=np.zeros((2,36),'<f4');a[:,:9]=[0,0,0,1,0,0,0,1,0]
            a[:,9:18]=[0,0,1]*3;a[:,26:35]=1;a[:,35]=-1
            a[:,18]=[1,0];a[:,19]=[2,5]
            source.write_bytes(struct.pack('<4sI',b'CVR2',2)+a.tobytes())
            scene=Scene();writer=adapter.convert_cvr(source,mesh,scene,True)
            self.assertEqual(writer.triangles,2);self.assertEqual(scene.materials,2)
            # Palette iteration maps key 0 first; key 1 must still map separately.
            raw=mesh.read_bytes();nv=struct.unpack_from('<H',raw,16)[0]
            records=np.frombuffer(raw[20+44*nv:],dtype=[('v','u1',(3,)),('m','<u4'),('o','<u4')])
            self.assertEqual(records['m'].tolist(),[1,0]);self.assertEqual(records['o'].tolist(),[3,6])
            self.trace(scene,mesh,root/'film')

    def test_landscape_format_reaches_native_indexed_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.meshbin';mesh=root/'mesh.clm'
            a=np.zeros((1,20),'<f4');a[0,:9]=[0,0,0,1,0,0,0,1,0];a[0,9:18]=[0,0,1]*3
            source.write_bytes(struct.pack('<I',1)+a.tobytes())
            scene=Scene();adapter.convert_landscape(source,mesh,scene,'sandstone-passage')
            self.trace(scene,mesh,root/'film')

    def test_obsidian_retained_temperature_field_reaches_native_emission(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);assets=root/'engines/obsidian/assets';assets.mkdir(parents=True)
            thermal=np.zeros((2,2,8),'<f4');thermal[:,:,2]=1300
            (assets/'lava_skin.bin').write_bytes(struct.pack('<II4f',2,2,-1,1,-1,1)+thermal.tobytes())
            materials=np.zeros((1,9),'<f4');materials[0,:3]=.05;materials[0,6]=.3
            materials[:,8].view('<i4')[:]=10000
            a=np.zeros((1,26),'<f4');a[0,:9]=[0,0,0,1,0,0,0,1,0];a[0,9:18]=[0,0,1]*3
            source=root/'input.bin';mesh=root/'mesh.clm'
            source.write_bytes(struct.pack('<4I',0x3253424f,1,1,104)+materials.tobytes()+a.tobytes())
            scene=Scene()
            with patch.object(adapter,'ENV',root):adapter.convert_obsidian(source,mesh,scene)
            self.assertTrue(any(line.startswith('emission_temperature ') for line in scene.lines))
            self.trace(scene,mesh,root/'film')

    def test_failed_empty_pack_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'empty.clm'
            with self.assertRaises(ValueError):
                with Meshlets(path):pass
            self.assertFalse(path.exists());self.assertFalse(path.with_suffix('.clm.partial').exists())

    def test_resolution_sampling_and_modified_pack_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.cvr2'
            a=np.zeros((1,36),'<f4');a[0,:9]=[0,0,0,1,0,0,0,1,0];a[0,9:18]=[0,0,1]*3
            a[0,26:35]=1;a[0,35]=-1
            source.write_bytes(struct.pack('<4sI',b'CVR2',1)+a.tobytes())
            args=argparse.Namespace(scene='observatory-iv',output=root/'output',quality='smoke',width=32,height=24,spp=4,bands=4,depth=5,threads=1,timeout=60,water_spp=None,force=False)
            record={'aspect':[3,2],'depth':5}
            def run(command,*rest):subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            with patch.object(adapter,'ROOT',root),patch.object(adapter,'prepare',return_value=(source,record)),patch.object(adapter,'run_recorded',run),patch.object(adapter,'convert_cvr',wraps=adapter.convert_cvr) as convert:
                adapter.render_scene(args);self.assertEqual(convert.call_count,1)
                args.width=36;args.spp=5
                adapter.render_scene(args);self.assertEqual(convert.call_count,1)
                mesh=root/'output/observatory-iv/hero/scene.clm';mesh.write_bytes(mesh.read_bytes()+b'X')
                adapter.render_scene(args);self.assertEqual(convert.call_count,2)
                receipt=json.loads(mesh.with_name('receipt.json').read_text())
                self.assertTrue(receipt['passed']);self.assertEqual(receipt['settings']['width'],36)


if __name__=='__main__':unittest.main()
