#!/usr/bin/env python3
"""Fresh, SMALL native R6 geometry/coordinate/transport integration fixture.

This is not a second full-forest rebuild or a perceptual-quality test.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OPENCV_IO_ENABLE_OPENEXR','1')
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cybr-geo/examples/three_scenes'))
import numpy as np
from fernwater_r6 import WoodlandBuilder,fern
from build_scenes import Water,sha
from render_scenes import render,compile_renderer,build_scene_geometry
from unittest.mock import patch
from verify_outputs import verify_scene


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'verification/r6_integration')
    args=parser.parse_args();out=args.output.resolve();folder=out/'forest'
    dispatched=[]
    with patch('render_scenes.subprocess.run',side_effect=lambda command,**kwargs:dispatched.append(command)):
        build_scene_geometry(out/'dispatch_probe','all')
    dispatch_valid=[Path(c[1]).name for c in dispatched]==['rebuild_scenes.py','rebuild_scenes.py','fernwater_r6.py'] and all(Path(c[1]).is_file() for c in dispatched)
    b=WoodlandBuilder(87313)
    x,y=np.meshgrid(np.linspace(-3,3,32),np.linspace(-2,5,40))
    z=-.16+.36/(1+np.exp(-(x-.9)*5))+.012*np.sin(x*9)*np.cos(y*11)
    b.terrain=z;b.terrain_bounds=(-3,3,-2,5)
    b.surface('Fixture_substrate',np.stack([x,y,z],-1),0)
    path=np.array([[1.2,.8,.16],[1.23,.84,.9],[1.31,.87,1.8]])
    b.tube('Fixture_cylindrical_bark',path,[.11,.075,.028],8,20,True,.7)
    b.tube('Fixture_attached_petiole',[path[-1],path[-1]+[-.04,0,.005]],[.002,.0006],8,5)
    b.leaf('Fixture_local_lamina',path[-1]+[-.04,0,.005],[-1,.05,-.22],.43,.23,9,.78,.09,detail=True)
    b.leaf('Fixture_ground_litter',[-1.,.3,float(b.ground(-1,.3))+.006],[.7,.4,.03],.18,.11,11,.1,.04,detail=True)
    fern(b,1.7,1.3,.42)
    Water('forest').add(b,np.linspace(-2.7,2.7,30),np.linspace(-1.7,4.7,30),bottom=-1)
    cfg={'scene':'forest','title':'R6 small local-coordinate fixture','camera':[1.9,-2.4,1.5],
         'target':[.4,1.,.70],'fov':49,'sun':[-.4,-.4,.8],'sun_scale':1.,'sky_scale':1.,
         'exposure':2.35,'white_balance':6100,'water_absorption':.85,'r6_local_material_frames':True}
    geometry=b.finish(folder,cfg,False)
    render(out,'forest',96,64,8,16,'test',2,True)
    report=verify_scene(folder,'test')
    render(out,'forest',96,64,8,16,'repeat',2,True)
    checks=report['checks']
    checks['all_entrypoints_select_r6_forest_recipe']=dispatch_valid
    checks['local_frames_loaded']=report['render']['r6_surface_coordinate_frames']==geometry['surface_coordinate_frames']>1
    checks['sky_nee_active']=report['render']['sky_next_event_sampling']
    checks['surface_sidecar_receipt_matches']=report['execution']['surface_frames_sha256']==sha(folder/'surface_frames.bin')
    checks['deterministic_pfm']=sha(folder/'test.pfm')==sha(folder/'repeat.pfm')
    checks['deterministic_spectral']=sha(folder/'test.spectral')==sha(folder/'repeat.spectral')
    frames=np.fromfile(folder/'surface_frames.bin','<f4',offset=8).reshape(-1,16)
    mesh=np.memmap(folder/'scene.meshbin','<f4',mode='r',offset=4,shape=(geometry['triangles'],20))
    indices=mesh[:,19].astype(np.int64)
    checks['native_frame_indices_bounded']=bool((indices>=0).all() and (indices<len(frames)).all())
    cursor=0;tested_leaf_triangles=0;coordinates_correct=True
    scene_description=json.loads((folder/'assembly/scene.json').read_text())
    with np.load(folder/'assembly/meshes.npz') as source_meshes:
        for part in scene_description['parts']:
            count=len(source_meshes[part['key']+'_faces'])
            if 'lamina' in part['name'].lower() or 'pinnules' in part['name'].lower():
                ids=indices[cursor:cursor+count]
                coordinates_correct=coordinates_correct and bool((ids>0).all() and np.isin(frames[ids,14],[3,5,6]).all())
                tested_leaf_triangles+=count
            cursor+=count
    checks['live_leaf_triangle_has_local_coordinates']=coordinates_correct and tested_leaf_triangles>1000
    fern_frames=frames[frames[:,14]==5]
    checks['fern_frames_follow_curved_fronds']=bool(len(fern_frames)>500 and fern_frames[:,11].min()<.85 and fern_frames[:,11].max()>.95)
    coordinates=np.load(folder/'assembly/surface_coordinates.npz')
    checks['assembly_coordinate_table_exact']=bool(np.array_equal(coordinates['frames'],frames))
    # An intentional corrupt sidecar must be rejected rather than silently ignored.
    bad=out/'deliberately_invalid';bad.mkdir(parents=True,exist_ok=True)
    (bad/'surface_frames.bin').write_bytes(b'BAD!'+np.array([1],'<u4').tobytes()+bytes(64))
    (bad/'scene.meshbin').write_bytes((folder/'scene.meshbin').read_bytes())
    binary,_=compile_renderer()
    bad_cmd=[str(binary),str(bad/'scene.meshbin'),str(bad/'bad'),'--scene','forest','--w','8','--h','8','--spp','1','--threads','1','--no-clouds','--no-steam']
    result=subprocess.run(bad_cmd,capture_output=True,text=True)
    (out/'invalid_frame_rejection.log').write_text(result.stdout+result.stderr)
    checks['invalid_sidecar_rejected']=result.returncode!=0 and 'surface-frame' in result.stderr
    report.update({'scope':__doc__,'checks':checks,'passed':all(checks.values()),
                   'fixture_triangle_count':geometry['triangles'],'full_forest_rebuilt':False})
    (out/'integration.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(checks,indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
