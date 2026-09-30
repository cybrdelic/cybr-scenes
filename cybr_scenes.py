#!/usr/bin/env python3
"""List, diagnose and render every CYBR scene from the repository root."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ENVIRONMENTS=ROOT/'environments'
OBSERVATORY=ROOT/'scenes/observatory-iv'
REGISTRY=json.loads((ENVIRONMENTS/'scenes.json').read_text())['scenes']
SCENES={scene['id']:scene for scene in REGISTRY}
SCENES['observatory-iv']={'id':'observatory-iv','title':'Quiet Observatory IV','engine':'observatory'}


def positive_int(value):
    number=int(value)
    if number<1:raise argparse.ArgumentTypeError('Value must be positive')
    return number


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('list',help='Show scene names and native backends')
    d=sub.add_parser('doctor',help='Check the selected scene before expensive work')
    d.add_argument('scene',nargs='?',choices=[*SCENES,'all'],default='all')
    r=sub.add_parser('render',help='Prepare, compile, render, finish and check in one command')
    r.add_argument('scene',choices=[*SCENES,'all'])
    r.add_argument('--renderer',choices=['light','authored'],default='light',help='CYBR LIGHT spectral engine; authored retains the scene-specific historical transport')
    r.add_argument('--bands',type=positive_int,help='Wavelengths per CYBR LIGHT sample packet')
    r.add_argument('--quality',choices=['smoke','preview','production'],default='preview')
    r.add_argument('--width',type=positive_int);r.add_argument('--height',type=positive_int)
    r.add_argument('--spp',type=positive_int);r.add_argument('--water-spp',type=positive_int)
    r.add_argument('--threads',type=positive_int,default=2)
    r.add_argument('--depth',type=positive_int,help='CYBR LIGHT path depth; authored environment depth stays in its scene preset')
    r.add_argument('--output',type=Path,default=ROOT/'outputs')
    r.add_argument('--force',action='store_true');r.add_argument('--timeout',type=positive_int,default=14400)
    return p


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(8<<20),b''):h.update(block)
    return h.hexdigest()


def fingerprint(paths):
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}


def doctor(scene='all',renderer='light'):
    selected=list(SCENES) if scene=='all' else [scene]
    packages=['numpy','scipy','Pillow','trimesh','opencv-python-headless']
    if renderer=='light':packages+=['numba']
    if any(name!='observatory-iv' for name in selected):packages+=['scikit-image','shapely']
    if renderer=='authored' and any(name!='observatory-iv' for name in selected):packages+=['numba']
    versions={}
    for name in packages:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    programs={'g++':shutil.which(os.environ.get('CXX','g++'))}
    if renderer=='authored' and 'observatory-iv' in selected:programs['cmake']=shutil.which('cmake')
    issues=[]
    if not sys.platform.startswith('linux'):issues.append('Use Linux or WSL2; native process supervision uses Linux /proc and flock.')
    if not (3,11)<=sys.version_info[:2]<(3,14):issues.append('Use Python 3.11, 3.12 or 3.13.')
    for name,version in versions.items():
        if version is None:issues.append(f'Missing {name}; run python -m pip install -r requirements.txt')
    for name,path in programs.items():
        if not path:issues.append(f'Missing {name}; on Ubuntu/WSL run sudo apt install g++ cmake')
    flags=Path('/proc/cpuinfo').read_text() if Path('/proc/cpuinfo').exists() else ''
    if renderer=='authored' and any(name in selected for name in ['observatory-iv','drowned-geode']):
        if 'avx2' not in flags or ('observatory-iv' in selected and 'fma' not in flags):
            issues.append('This scene requires an x86-64 CPU with AVX2 (and FMA for Observatory).')
    # The full finish/export pipeline requires a working EXR codec, not just import cv2.
    if renderer=='authored' and 'observatory-iv' in selected and versions.get('opencv-python-headless'):
        os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
        try:
            import cv2
            import numpy as np
            if not cv2.imencode('.exr',np.zeros((1,1,3),np.float32))[0]:raise RuntimeError('encoder returned false')
        except Exception as exc:issues.append(f'OpenCV EXR support unavailable: {exc}. Install requirements.txt in a fresh venv.')
    return {'ready':not issues,'platform':platform.platform(),'python':platform.python_version(),
            'scenes':selected,'packages':versions,'programs':programs,'issues':issues,
            'notes':['CPU-only native rendering; full geometry builds can require several GB of RAM.',
                     'Outputs and fresh logs go to ignored outputs/ and build/ directories.']}


def authored_observatory_render(args):
    # Use the existing durable execution controller for all stages and locks.
    sys.path.insert(0,str(ENVIRONMENTS))
    from execution_runtime import atomic_json,owned_lock,run_recorded
    quality={'smoke':(64,48,4,6),'preview':(640,426,24,8),'production':(1800,1200,96,12)}[args.quality]
    width=args.width or quality[0]
    height=args.height or (quality[1] if args.width is None else max(1,round(width*2/3)))
    spp=args.spp or quality[2];depth=args.depth or quality[3]
    out=args.output.expanduser().resolve()/'observatory-iv/hero';out.mkdir(parents=True,exist_ok=True)
    stem=out/'hero';receipt=out/'receipt.json'
    logs=OBSERVATORY/'build/logs';scene_dir=OBSERVATORY/'build/scene'
    binary=OBSERVATORY/'build/observatory'
    source_files=[OBSERVATORY/'CMakeLists.txt',*list((OBSERVATORY/'src').rglob('*'))]
    source_files=[p for p in source_files if p.is_file()]
    build_stamp=OBSERVATORY/'build/source-fingerprint.json'
    inputs=[OBSERVATORY/'build_scene.py',OBSERVATORY/'assets/observatory_interior_source.glb']
    input_key=fingerprint(inputs);asset_stamp=scene_dir/'build-receipt.json'
    settings={'width':width,'height':height,'spp':spp,'depth':depth,'threads':args.threads,
              'source':fingerprint(source_files),'inputs':input_key,
              'pipeline':fingerprint([Path(__file__),OBSERVATORY/'finish.py',OBSERVATORY/'verify.py'])}
    def run(command,name):
        return run_recorded(command,OBSERVATORY,logs/f'{name}.log',args.threads,args.timeout)
    with owned_lock(OBSERVATORY/'build/.workflow.lock'):
        if not binary.exists() or not build_stamp.exists() or json.loads(build_stamp.read_text()).get('sources')!=settings['source'] or json.loads(build_stamp.read_text()).get('binary_sha256')!=sha(binary):
            run(['cmake','-S',OBSERVATORY,'-B',OBSERVATORY/'build','-DCMAKE_BUILD_TYPE=Release'],'configure')
            run(['cmake','--build',OBSERVATORY/'build','--parallel',str(args.threads)],'compile')
            run(['ctest','--test-dir',OBSERVATORY/'build','--output-on-failure'],'numeric-tests')
            atomic_json(build_stamp,{'sources':settings['source'],'binary_sha256':sha(binary)})
        assets_ok=False
        if asset_stamp.exists():
            previous=json.loads(asset_stamp.read_text())
            assets_ok=previous.get('inputs')==input_key and all((scene_dir/path).is_file() and sha(scene_dir/path)==digest for path,digest in previous.get('files',{}).items()) and bool(previous.get('files'))
        if not assets_ok:
            asset_stamp.unlink(missing_ok=True)
            run([sys.executable,OBSERVATORY/'build_scene.py','--out',scene_dir],'prepare')
            run([sys.executable,OBSERVATORY/'verify.py','--geometry-only','--scene-dir',scene_dir,
                 '--out',OBSERVATORY/'build/verification/geometry.json'],'geometry-tests')
            assets={str(p.relative_to(scene_dir)):sha(p) for p in sorted(scene_dir.rglob('*')) if p.is_file()}
            atomic_json(asset_stamp,{'inputs':input_key,'files':assets})
        settings['assets']=json.loads(asset_stamp.read_text())['files'];settings['binary_sha256']=sha(binary)
        if not args.force and receipt.exists():
            old=json.loads(receipt.read_text())
            if old.get('settings')==settings and old.get('passed') and all((out/path).is_file() and sha(out/path)==digest for path,digest in old.get('files',{}).items()) and old.get('files'):
                print(f'Cached matching render: {stem}.png');return
        receipt.unlink(missing_ok=True)
        # Optional production film must not survive into a new preview run.
        stem.with_suffix('.spectral').unlink(missing_ok=True)
        command=[binary,'--mesh',scene_dir/'observatory.cvr2','--out',stem,'--width',width,
                 '--height',height,'--spp',spp,'--depth',depth,'--threads',args.threads,'--aperture','.004']
        if args.quality=='production':command+=['--adaptive','--bands']
        render=run(command,'render')
        run([binary,'--mesh',scene_dir/'observatory.cvr2','--out',stem,'--width',width,
             '--height',height,'--threads',args.threads,'--guides-only'],'guides')
        run([sys.executable,OBSERVATORY/'finish.py',stem],'finish')
        report=out/'verification.json'
        run([sys.executable,OBSERVATORY/'verify.py','--scene-dir',scene_dir,'--stem',stem,'--out',report],'verify')
        files={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}
        atomic_json(receipt,{'passed':True,'scene':'observatory-iv','settings':settings,'render':render,
                             'verification':json.loads(report.read_text()),'files':files})
    print(f'RENDER VERIFIED: Observatory {width}x{height} {spp} spp -> {stem}.png')


def authored_environment_render(args):
    command=[sys.executable,ENVIRONMENTS/'cybr_scenes.py','render',args.scene,
             '--quality','production' if args.quality=='production' else 'preview',
             '--threads',str(args.threads),'--timeout',str(args.timeout),'--output',str(args.output.expanduser().resolve())]
    values={key:getattr(args,key) for key in ('width','height','spp','water_spp')}
    if args.quality=='smoke':
        for key,value in {'width':64,'spp':4,'water_spp':4}.items():
            if values[key] is None:values[key]=value
    for key,value in values.items():
        if value is not None:command+=['--'+key.replace('_','-'),str(value)]
    if args.force:command+=['--force']
    subprocess.run(command,cwd=ROOT,check=True)


def light_render(args):
    sys.path.insert(0,str(ROOT/'rendering'))
    from light_render import render_scene
    return render_scene(args)


def observatory_render(args):
    return light_render(args) if args.renderer=='light' else authored_observatory_render(args)


def environment_render(args):
    return light_render(args) if args.renderer=='light' else authored_environment_render(args)


def main(argv=None):
    args=parser().parse_args(argv)
    if args.command=='list':
        for scene in SCENES.values():print(f'{scene["id"]:22} {scene["title"]} ({scene["engine"]})')
        return 0
    if args.command=='render' and args.renderer=='light':
        if args.water_spp is not None:
            print('CYBR LIGHT uses one spectral packet budget; use --spp instead of --water-spp',file=sys.stderr);return 2
        if args.bands is not None and args.bands>128:
            print('--bands must be at most 128',file=sys.stderr);return 2
        width=args.width or {'smoke':64,'preview':800,'production':1800}[args.quality]
        selected=list(SCENES) if args.scene=='all' else [args.scene]
        if any(width*(args.height or max(1,round(width*SCENES[name].get('aspect',[3,2])[1]/SCENES[name].get('aspect',[3,2])[0])))>8000000 for name in selected):
            print('CYBR LIGHT supports at most 8 million pixels',file=sys.stderr);return 2
    report=doctor(args.scene,getattr(args,'renderer','light'))
    if args.command=='doctor':print(json.dumps(report,indent=2));return 0 if report['ready'] else 2
    if not report['ready']:
        print('\n'.join(report['issues']),file=sys.stderr);return 2
    if args.renderer=='authored' and args.depth is not None and args.scene!='observatory-iv':
        print('--depth applies to observatory-iv; environment depth is in environments/scenes.json',file=sys.stderr);return 2
    try:
        if args.scene=='all':
            # Every scene is attempted sequentially; failed scenes produce a nonzero exit.
            failed=[]
            for name in SCENES:
                single=argparse.Namespace(**vars(args));single.scene=name
                try:observatory_render(single) if name=='observatory-iv' else environment_render(single)
                except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
                    failed.append(name);print(f'{name}: {exc}',file=sys.stderr)
            return 1 if failed else 0
        observatory_render(args) if args.scene=='observatory-iv' else environment_render(args)
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'cybr-scenes: {exc}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
