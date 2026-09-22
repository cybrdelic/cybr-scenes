#!/usr/bin/env python3
"""Build and reproduce Obsidian Reach IV with the native CYBR CPU integration."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def run(command:list[str])->None:
    print('+',' '.join(command),flush=True)
    env=os.environ.copy();env.setdefault('OPENBLAS_NUM_THREADS','1')
    subprocess.run(command,cwd=ROOT,env=env,check=True)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--width',type=int,default=2560);p.add_argument('--height',type=int,default=1120)
    p.add_argument('--spp',type=int,default=192,help='Maximum adaptive samples, or uniform samples with --uniform')
    p.add_argument('--camera',type=int,choices=[0,1],default=0);p.add_argument('--depth',type=int,default=5)
    p.add_argument('--exposure',type=float,default=5.5);p.add_argument('--output',type=Path,default=Path('render/obsidian_reach_iv'))
    p.add_argument('--uniform',action='store_true');p.add_argument('--rebuild-geometry',action='store_true')
    p.add_argument('--new-budget',action='store_true',help='Render a new pilot instead of using the included final-pass budget')
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--skip-tests',action='store_true')
    a=p.parse_args()
    if min(a.width,a.height)<16 or not 1<=a.spp<=65535 or a.depth<1 or a.exposure<=0:p.error('Invalid render configuration')
    compiler=shutil.which('g++')
    if not compiler:raise RuntimeError('A C++17 compiler with OpenMP support is required (g++ was used for this delivery).')
    prefix=a.output if a.output.is_absolute() else ROOT/a.output;prefix.parent.mkdir(parents=True,exist_ok=True)
    if a.rebuild_geometry or not (ROOT/'assets/scene.bin').exists():run([sys.executable,'build_scene.py'])
    run([compiler,'-O3','-march=native','-fno-math-errno','-fopenmp','-std=c++17','-Iinclude','src/render.cpp','-o','render_cpu'])
    if not a.skip_tests:
        run([sys.executable,'tests/check_scene.py'])
        for name in ['core_smoke','renderer_checks','sampling_consistency','bvh_regression']:
            run([compiler,'-O2','-fopenmp','-std=c++17','-Iinclude',f'tests/{name}.cpp','-o',f'tests/{name}'])
            run([str(ROOT/'tests'/name)])
    if a.prepare_only:return 0
    budget=None
    supplied=ROOT/'reference/hero_budget.bin'
    same_shot=(a.width,a.height,a.spp,a.camera)==(2560,1120,192,0)
    if not a.uniform:
        if supplied.exists() and same_shot and not a.new_budget:budget=supplied
        else:
            pilot=prefix.parent/(prefix.name+'_pilot')
            pw=1200;ph=max(16,round(pw*a.height/a.width));ps=20
            run([compiler,'-O3','-march=native','-fno-math-errno','-fopenmp','-std=c++17','-DCYBR_SEQUENCE_BASE=197','-Iinclude','src/render.cpp','-o','render_pilot'])
            run([str(ROOT/'render_pilot'),'assets/scene.bin',str(pilot),str(pw),str(ph),str(ps),str(a.camera),str(a.depth)])
            budget=prefix.parent/(prefix.name+'_budget.bin')
            run([sys.executable,'allocate_samples.py',str(pilot),str(budget),'--width',str(a.width),'--height',str(a.height),'--pilot-spp',str(ps),'--maximum',str(a.spp),'--minimum',str(min(48,a.spp))])
    command=[str(ROOT/'render_cpu'),'assets/scene.bin',str(prefix),str(a.width),str(a.height),str(a.spp),str(a.camera),str(a.depth)]
    if budget is not None:command.append(str(budget))
    run(command)
    run([sys.executable,'finish_v4.py',str(prefix),'--exposure',str(a.exposure),'--passes','3'])
    run([sys.executable,'export_exr.py',str(prefix)+'.pfm',str(prefix)+'.exr'])
    run([sys.executable,'tests/verify_exr.py',str(prefix)+'.pfm',str(prefix)+'.exr'])
    print(f'Image: {prefix}.png\nUnfiltered film: {prefix}.exr',flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}',file=sys.stderr);raise SystemExit(1)
