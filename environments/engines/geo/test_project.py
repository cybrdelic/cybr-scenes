#!/usr/bin/env python3
"""Compile and execute recovery tests without referring to a previous workspace."""
from pathlib import Path
import json, os, subprocess, sys
import numpy as np
ROOT=Path(__file__).resolve().parent
TOOLS=ROOT/'cybr-geo/examples/three_scenes'
NATIVE=ROOT/'cybr-geo/native'
OUT=ROOT/'verification';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(TOOLS))
from render_scenes import compile_renderer
from build_scenes import Water,unit,sha
binary,build=compile_renderer()
reports={'scope':'Input activation, traversal parity, wave agreement, and named optical equations; not photorealism', 'source_sha256':build['source_sha256'],'components':{}}
env=dict(os.environ,OPENBLAS_NUM_THREADS='1')
for name in ['test_recovery','test_wave_parity','test_thin_leaf_r4','test_fernwater_r6']:
    flags=['g++','-std=c++17','-O3','-march=native','-fopenmp',str(NATIVE/(name+'.cpp')),'-o',str(OUT/name)]
    subprocess.run(flags,check=True,env=env)
asset=ROOT/'cybr-geo/examples/desert_hot_springs/assets'
reports['components']['materials_and_traversal']=json.loads(subprocess.check_output([str(OUT/'test_recovery'),str(asset)],text=True,env=env))
reports['components']['r6_material_frames_and_sky_mis']=json.loads(subprocess.check_output([str(OUT/'test_fernwater_r6')],text=True,env=env))
reports['components']['optics']=json.loads(subprocess.check_output([str(binary),'--self-test'],text=True,env=env))
subprocess.run([str(OUT/'test_wave_parity'),str(OUT/'wave_samples.bin')],check=True,env=env)
points=np.fromfile(OUT/'wave_samples.bin','<f4').reshape(-1,7)
wave={}
for style,name in [(1,'coast'),(2,'forest')]:
    q=points[points[:,0]==style];h,dx,dy=Water(name).sample(q[:,1],q[:,2]);n=unit(np.c_[-dx,-dy,np.ones(len(q))])
    e=float(np.max(abs(h-q[:,3])));ne=float(np.max(np.linalg.norm(n-q[:,4:7],axis=1)))
    wave[name]={'samples':len(q),'max_height_error_m':e,'max_unit_normal_error':ne,'passed':e<1e-4 and ne<1e-3}
reports['components']['waves']={'passed':all(x['passed'] for x in wave.values()),'scenes':wave}
reports['components']['thin_leaf_bsdf']=json.loads(subprocess.check_output([str(OUT/'test_thin_leaf_r4')],text=True,env=env))
from test_formation_geometry_r4 import run as formation_geometry_test
reports['components']['formation_geometry']=formation_geometry_test()
from namespace_regression import run as namespace_test
reports['components']['material_namespace']=namespace_test()
from display_filter_regression import run as display_filter_test
reports['components']['display_filter']=display_filter_test()
from test_ground_occlusion import run as ground_occlusion_test
reports['components']['ground_occlusion']=ground_occlusion_test(ROOT)
from test_noise_resolve import run as noise_test
reports['components']['noise_resolve']=noise_test()
from test_noise_guides import run as guide_test
reports['components']['noise_guides']=guide_test()
reports['passed']=all(x['passed'] for x in reports['components'].values())
(OUT/'recovery_tests.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports,indent=2))
if not reports['passed']:raise SystemExit(1)
