#!/usr/bin/env python3
"""A new authored native comparison scene, not one of the six original scenes.
Uses the existing GEO Builder/Assembly serializer, mineral meshes and attached
leaf/tube geometry. No engine or image implementation is copied here.
"""
from pathlib import Path
import argparse, hashlib, json, sys
import numpy as np
ENV = Path(__file__).resolve().parents[1]
SOURCE = ENV / 'engines/geo/cybr-geo/examples/three_scenes'
sys.path.insert(0, str(SOURCE))
from build_scenes import Builder, Water, rock_mesh, grid_faces

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    for profile in ['geo','hot']:
        b=Builder('shared_core_'+profile,20261023)
        x=np.linspace(-9,9,81); y=np.linspace(-7,17,97)
        xx,yy=np.meshgrid(x,y)
        depression=np.exp(-((xx/2.1)**4+((yy-2)/2.9)**4))
        zz=.28+.07*np.sin(xx*1.1)*np.cos(yy*.8)-.95*depression
        v=np.stack((xx,yy,zz),-1).reshape(-1,3)
        b.add('Continuous_authored_ground',v,grid_faces(len(y),len(x)),mat=0)
        for i,(px,py,sx,sy,sz) in enumerate([(-3,3,1.6,1.1,2.1),(3.3,4,1.4,1.8,1.6),(-2,7,2,1.4,1),(1.8,8,.9,1,2.5),(-4,10,2.3,1.8,2.8)]):
            v,f=rock_mesh(315+i,(sx,sy,sz),sub=3,angular=True)
            v+=np.array([px,py,sz*.6]);b.add('Mineral_columns',v,f,mat=1+i%2)
        for i,(px,py) in enumerate([(-3.4,.2),(3.5,1.2),(-2.7,5.5)]):
            path=np.array([[px,py,.3],[px+.15,py+.1,.9],[px+.25,py+.2,1.7]])
            b.tube('Attached_woody_stems',path,np.array([.055,.04,.018]),mat=8,sides=10,bark=True)
            for j in range(9):
                t=j/10; base=path[0]*(1-t)+path[-1]*t
                angle=j*2.4+i;direction=np.array([np.cos(angle),np.sin(angle),.45])
                b.leaf('Attached_native_leaves',base,direction,.75,.3,mat=9)
        if profile=='geo':
            Water('coast').add(b,np.linspace(-1.7,1.7,65),np.linspace(-.4,4.4,81),bottom=-.6)
        config={'camera':[2.1,-5.65,1.52],'target':[-.15,3.15,.15],'fov':72,'sun':[-.8,.4,.28],'exposure':1.9,'white_balance':5750}
        report=b.finish(a.out/profile,config,glb=False)
        report.update(scope='New bounded comparison scene, not an original environment rerender',profile=profile,water_geometry='Existing coast wave enclosure' if profile=='geo' else 'No water surface; hot optical component tests cover water separately',generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (a.out/profile/'geometry.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__': main()
