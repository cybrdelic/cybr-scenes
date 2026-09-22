"""Create Amber Passage: a newly framed sandstone postcard from original geometry."""
from pathlib import Path
from argparse import Namespace
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cybr_scenes import ROOT, SCENES, prepare_scene, render_scene, exclusive

def main():
    output = ROOT / 'demo-output/amber-passage'
    output.mkdir(parents=True, exist_ok=True)
    scene = dict(SCENES['sandstone-passage'])
    with exclusive(ROOT/'build/.execution-lane.flock'):
        prepare_scene(scene, 2)
        original = json.loads((ROOT/scene['camera']).read_text())
        camera = dict(original)
        camera['fov'] *= .78
        camera['white_balance'] = 5200
        camera_path = output/'camera.json'
        camera_path.write_text(json.dumps(camera, indent=2))
        scene['camera'] = str(camera_path)
        result = render_scene(scene, Namespace(
            baseline=False, output=output, force=True, threads=2, timeout=5400,
            width=640, height=400, spp=32, water_spp=48, quality='production'))
        (output/'creation.json').write_text(json.dumps({
            'title': 'Amber Passage', 'source_scene': scene['id'],
            'changes': 'Narrower field of view, 16:10 composition, 5200K finishing white balance',
            'original_camera': original, 'new_camera': camera, 'verification': result,
            'new_geometry': False, 'image_generation': False,
        }, indent=2))

if __name__ == '__main__':
    main()
