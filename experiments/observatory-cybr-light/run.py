#!/usr/bin/env python3
"""Run the preserved Observatory renderer and pinned CYBR LIGHT separately."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from export_scene import export,sha256
from compare import make_comparison

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PIN=json.loads((HERE/'dependency.json').read_text())

def object_id(kind:bytes,data:bytes):
    return hashlib.sha1(kind+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()

def verify_engine(path:Path):
    headers=path/'include/cybr';data=b''
    for p in sorted(headers.glob('*.hpp')):
        data+=b'100644 '+p.name.encode()+b'\0'+bytes.fromhex(object_id(b'blob',p.read_bytes()))
    tree=object_id(b'tree',data);main=object_id(b'blob',(path/'src/main.cpp').read_bytes())
    if tree!=PIN['include_tree'] or main!=PIN['main_blob']:
        raise RuntimeError('CYBR LIGHT source differs from dependency.json; do not silently substitute another engine')
    return {'repository':PIN['repository'],'commit':PIN['commit'],'include_tree':tree,'main_blob':main}

def run(args,cwd:Path,log:Path):
    t=time.monotonic();args=list(map(str,args));print('+',' '.join(args),flush=True)
    with log.open('w') as f:
        subprocess.run(args,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,check=True)
    return {'command':args,'working_directory':str(cwd),'seconds':time.monotonic()-t,'log':str(log)}

def snapshot(root:Path):
    return {str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file() and not any(x in p.relative_to(root).parts for x in ('build','__pycache__','.venv')) and p.suffix not in ('.cvr2','.cvtex','.pyc')}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,default=ROOT/'scenes/observatory-iv')
    p.add_argument('--light-checkout',type=Path,default=ROOT/'engines/cybr-light')
    p.add_argument('--work',type=Path,default=ROOT/'build/observatory-light-comparison')
    p.add_argument('--width',type=int,default=720);p.add_argument('--height',type=int,default=480)
    p.add_argument('--spp',type=int,default=48);p.add_argument('--bands',type=int,default=8);p.add_argument('--threads',type=int,default=4)
    p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args()
    if min(a.width,a.height,a.spp,a.bands,a.threads)<1 or a.bands>128 or a.width*a.height>8000000:p.error('Invalid render settings')
    baseline=a.baseline.resolve();engine=a.light_checkout.resolve();work=a.work.resolve()
    if not (baseline/'build_scene.py').is_file():p.error('Missing preserved baseline source')
    if not (engine/'src/main.cpp').is_file():p.error('Missing CYBR LIGHT checkout. Run git submodule update --init engines/cybr-light, or pass --light-checkout.')
    if work==baseline or baseline in work.parents or work==engine or engine in work.parents:p.error('Work directory must not modify either source tree')
    if work.exists():p.error('Use a new work directory; existing comparison outputs are never overwritten')
    work.mkdir(parents=True);logs=work/'logs';logs.mkdir();(work/'renders').mkdir();commands=[]
    before=snapshot(baseline);provenance=verify_engine(engine)
    (work/'baseline_before.json').write_text(json.dumps(before,indent=2)+'\n')
    copied=work/'baseline_source'
    shutil.copytree(baseline,copied,ignore=shutil.ignore_patterns('build','__pycache__','.venv','*.cvr2','*.cvtex','*.groups'))
    commands.append(run([sys.executable,'build_scene.py'],copied,logs/'geometry.log'))
    commands.append(run(['cmake','-S',copied,'-B',work/'baseline_build','-DCMAKE_BUILD_TYPE=Release'],work,logs/'baseline-configure.log'))
    commands.append(run(['cmake','--build',work/'baseline_build','--parallel',min(a.threads,4)],work,logs/'baseline-build.log'))
    commands.append(run(['ctest','--test-dir',work/'baseline_build','--output-on-failure'],work,logs/'baseline-tests.log'))
    # The real upstream main program and all renderer headers are used directly.
    light=work/'cybr-light'
    commands.append(run(['g++','-std=c++17','-O3','-fopenmp','-I'+str(engine/'include'),engine/'src/main.cpp','-ldl','-o',light],work,logs/'light-build.log'))
    test=work/'cybr-scene-io-tests'
    commands.append(run(['g++','-std=c++17','-O2','-I'+str(engine/'include'),engine/'tests/scene_io_binary.cpp','-ldl','-o',test],work,logs/'light-test-build.log'))
    commands.append(run([test],work,logs/'light-tests.log'))
    converted=export(copied,work/'native_scene',a.width,a.height,a.spp,a.bands,threads=a.threads)
    provenance.update({'binary_sha256':sha256(light),'adapter_sha256':sha256(HERE/'export_scene.py'),'scene_export':converted})
    if not a.prepare_only:
        sa=work/'renders/baseline';sb=work/'renders/cybr_light'
        commands.append(run([work/'baseline_build/observatory','--mesh',copied/'scene/observatory.cvr2','--out',sa,'--width',a.width,'--height',a.height,'--spp',a.spp,'--depth',12,'--threads',a.threads,'--aperture',.004],work,logs/'baseline-render.log'))
        commands.append(run([light,'--scene',work/'native_scene/scene.cys','--out',sb,'--size',a.width,a.height,'--spp',a.spp,'--bands',a.bands,'--threads',a.threads],work,logs/'light-render.log'))
        make_comparison(sa,sb,work/'comparison',baseline/'renders/Observatory_IV.png')
    after=snapshot(baseline)
    if before!=after:raise RuntimeError('The original baseline changed during reproduction')
    receipt={'status':'prepared' if a.prepare_only else 'rendered','baseline_unchanged':True,'engine':provenance,'commands':commands,
             'note':'Packet counts do not represent equal path counts or equal work across engines. Models differ.'}
    (work/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Prepared source only.' if a.prepare_only else 'Completed native comparison: '+str(work/'comparison/comparison.html'),flush=True)

if __name__=='__main__':main()
