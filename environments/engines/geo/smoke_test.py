#!/usr/bin/env python3
"""End-to-end native render tests of three SMALL fixtures, not full-scene rebuilds."""
from pathlib import Path
import sys,os,json,argparse
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OPENCV_IO_ENABLE_OPENEXR','1')
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cybr-geo/examples/three_scenes'))
import numpy as np
from build_scenes import Builder,Water,sha
from rebuild_scenes import fracture_block
from render_scenes import render
from verify_outputs import verify_scene

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'verification/smoke')
    args=parser.parse_args();reports=[]
    for scene in ('canyon','coast','forest'):
        b=Builder(scene,90678);x,y=np.meshgrid(np.linspace(-3,3,25),np.linspace(-2,4,25))
        z=np.full_like(x,-.18 if scene!='canyon' else -.06)
        z+=.015*np.sin(x*8)*np.cos(y*7)
        b.surface('Real_geometry_substrate',np.stack([x,y,z],-1),0)
        v,f=fracture_block(827,(.65,.45,.50),'block',2);v+=[0,.6,.2]
        b.add('Fractured_test_stone',v,f,mat=2)
        if scene=='forest':
            b.tube('Attached_bark_test',[[1,1,0],[1,1.1,.8],[1.1,1.2,1.8]],[.15,.10,.03],8,18,True,.37)
            b.leaf('Attached_leaf_test',[1.08,1.18,1.5],[-1,0,.1],.18,.10,9,.25,.11)
        if scene!='canyon':Water(scene).add(b,np.linspace(-2.8,2.8,31),np.linspace(-1.8,3.8,31),bottom=-1)
        cfg={'scene':scene,'title':'Small native integration fixture','camera':[2,-3.5,1.5],'target':[0,.6,.3],'fov':54,'sun':[-.4,-.4,.8], 'sun_scale':1,'sky_scale':1,'exposure':2.0,'white_balance':6200,'water_absorption':1}
        folder=args.output/scene;b.finish(folder,cfg,False)
        render(args.output,scene,96,64,4,8,'smoke',2,True)
        reports.append(verify_scene(folder,'smoke'))
    report={'scope':__doc__,'fixtures':reports,'all_integrity_checks_passed':all(all(r['checks'].values()) for r in reports)}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'integration.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({r['scene']:all(r['checks'].values()) for r in reports},indent=2))
if __name__=='__main__':main()
