"""Repository entry point and output separation contracts."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
    return loaded


runner=module('cybr_root_workflow',ROOT/'cybr_scenes.py')


class WorkflowTests(unittest.TestCase):
    def test_seven_scenes_share_root_registry(self):
        self.assertEqual(len(runner.SCENES),7)
        self.assertIn('observatory-iv',runner.SCENES)

    def test_nonpositive_budget_is_rejected(self):
        for option in ['--width','--height','--spp','--threads','--timeout']:
            with self.assertRaises(SystemExit) as error:
                runner.parser().parse_args(['render','observatory-iv',option,'0'])
            self.assertEqual(error.exception.code,2)

    def test_missing_dependency_prevents_creation(self):
        with patch.object(runner,'doctor',return_value={'ready':False,'issues':['missing compiler']}),patch.object(runner,'observatory_render') as render:
            self.assertEqual(runner.main(['render','observatory-iv']),2)
            render.assert_not_called()

    def test_light_preflight_uses_actual_scene_aspect(self):
        with patch.object(runner,'doctor',return_value={'ready':True}),patch.object(runner,'observatory_render') as render:
            self.assertEqual(runner.main(['render','observatory-iv','--width','3000']),0)
            render.assert_called_once()
            self.assertEqual(runner.main(['render','observatory-iv','--width','4000']),2)
            self.assertEqual(runner.main(['render','observatory-iv','--bands','129']),2)
            self.assertEqual(runner.main(['render','observatory-iv','--water-spp','4']),2)

    def test_all_scenes_continue_and_return_failure(self):
        names=[]
        def render(args):
            names.append(args.scene)
            if args.scene=='fernwater':raise RuntimeError('intentional')
        with patch.object(runner,'doctor',return_value={'ready':True}),patch.object(runner,'environment_render',render),patch.object(runner,'observatory_render',render):
            self.assertEqual(runner.main(['render','all']),1)
        self.assertEqual(names,list(runner.SCENES))

    def test_backend_output_is_explicit_and_keeps_requested_settings(self):
        args=runner.parser().parse_args(['render','fernwater','--renderer','authored','--quality','smoke','--width','80','--spp','7'])
        with patch.object(runner.subprocess,'run') as run:
            runner.environment_render(args)
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('--width')+1],'80')
        self.assertEqual(command[command.index('--spp')+1],'7')
        self.assertEqual(command[command.index('--output')+1],str(ROOT/'outputs'))

    def test_observatory_export_preserves_all_object_records(self):
        import numpy as np
        import trimesh
        builder=module('cybr_observatory_builder',ROOT/'scenes/observatory-iv/build_scene.py')
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            part=trimesh.creation.icosphere(subdivisions=1)
            parts=[('first',part,0,-1,np.ones(3),None),('last',part.copy(),0,-1,np.ones(3),None)]
            with patch.object(builder,'SCENE',out),patch.object(builder,'PARTS',parts):
                builder.export_scene()
            mesh=out/'observatory.cvr2'
            with mesh.open('rb') as source:
                self.assertEqual(source.read(4),b'CVR2')
                count=struct.unpack('<I',source.read(4))[0]
                records=np.frombuffer(source.read(),dtype='<f4').reshape(-1,36)
            self.assertEqual(mesh.stat().st_size,8+count*144)
            self.assertEqual(count,2*len(part.faces))
            self.assertEqual(set(records[:,19]),{0.,1.})
            self.assertFalse(mesh.with_suffix('.cvr2.partial').exists())

    def test_geometry_only_verification_requires_no_authored_renderer(self):
        import sys
        verify=module('cybr_observatory_verify',ROOT/'scenes/observatory-iv/verify.py')
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'geometry.json'
            with patch.object(sys,'argv',['verify.py','--geometry-only','--out',str(out)]),patch.object(verify,'geometry',return_value={'passed':True}),patch.object(verify.subprocess,'check_output',side_effect=AssertionError('Authored renderer must not run')):
                self.assertEqual(verify.main(),0)
            report=json.loads(out.read_text())
            self.assertTrue(report['passed']);self.assertNotIn('numeric_transport',report)

    def test_readme_local_targets_exist(self):
        import re
        for name in ['README.md','docs/RUNNING.md']:
            path=ROOT/name
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
                if '://' in target or target.startswith('#'):continue
                self.assertTrue((path.parent/target.split('#')[0]).exists(),target)


if __name__=='__main__':unittest.main()
