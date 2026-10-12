from pathlib import Path
import subprocess,sys,json,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Meshlets
out=r/'evidence/full-iv-house-component';out.mkdir(exist_ok=True)
a=np.zeros((2,36),'<f4');a[0,:9]=[0,0,0,1,0,0,0,1,0];a[1,:9]=[2,0,0,3,0,0,2,1,0];a[:,9:18]=[0,0,1]*3;a[:,19]=[10,11];a[:,26:35]=1
with Meshlets(out/'test.clm') as w:w.add(a)
material='material diffuse .4 .4 .4 .8 1.5 0 .25 .6 1.2 3.5 2.8 2 0 0 0 0 6500\n'
for kind in ['all','skip']:(out/(kind+'.cys')).write_text(material+('meshlets' if kind=='all' else 'meshlets_excluding')+' "test.clm"'+('' if kind=='all' else ' 1 10')+'\n')
exe=out/'component_test';subprocess.run(['g++','-std=c++17','-O2','-I'+str(r/'work/iv-component-runtime/cybr_light/native/include'),str(r/'work/meshlet_component_test.cpp'),'-ldl','-o',str(exe)],check=True);subprocess.run([str(exe),str(out/'all.cys'),str(out/'skip.cys')],check=True)
subprocess.run([sys.executable,str(r/'work/build_house_component.py')],check=True)
