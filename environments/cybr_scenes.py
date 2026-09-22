#!/usr/bin/env python3
"""Build and render six recovered 3D environments through one CPU workflow.

The recovered renderers remain separate, audited backends. This front end has no
network requirement, no image-generation dependency, and no renderer substitute.
"""
from __future__ import annotations
import argparse, contextlib, datetime, hashlib, http.server, importlib.metadata
import json, os, platform, shutil, signal, socketserver, struct, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REGISTRY=json.loads((ROOT/'scenes.json').read_text())
SCENES={s['id']:s for s in REGISTRY['scenes']}
SOURCES={
 'geo':'engines/geo/cybr-geo/native/spectral_scenes.cpp',
 'hot':'engines/hot/cybr-geo/native/spectral_desert.cpp',
 'geode':'engines/geode/src/cathedral_v3.cpp',
 'obsidian':'engines/obsidian/src/render.cpp',
}

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()

def atomic_json(path:Path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2)+'\n');os.replace(tmp,path)

def relative(path):
    try:return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:return str(path)

# Project-local, disk-backed execution; compatible with recovered receipts.
from execution_runtime import owned_lock as exclusive, run_recorded as run
from execution_runtime import thread_environment, atomic_json as _durable_json
atomic_json = _durable_json

def environment(threads: int):
    env = thread_environment(threads)
    env['CYBR_SURFACE_ATLAS'] = str(ROOT/'assets/mineral_detail.cdt')
    return env


def dependency_fingerprint(engine:str,original:bool=False)->str:
    h=hashlib.sha256()
    for directory in [ROOT/'shared',ROOT/'engines'/engine]:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix in {'.hpp','.h','.cpp','.c'}:
                h.update(str(path.relative_to(ROOT)).encode())
                backup=ROOT/'provenance/native-before'/path.relative_to(ROOT)
                h.update((backup if original and backup.exists() else path).read_bytes())
    return h.hexdigest()


def compile_engine(engine:str,threads:int=4,force=False):
    compiler=shutil.which(os.environ.get('CXX','g++'))
    if not compiler:raise RuntimeError('C++ compiler missing. Install g++ with OpenMP support.')
    (ROOT/'build').mkdir(exist_ok=True)
    binary=ROOT/'build'/f'{engine}_r2';receipt=binary.with_suffix('.build.json')
    command=[compiler,'-std=c++17','-O3','-march=native','-fno-math-errno','-fopenmp','-Ishared']
    if engine=='obsidian':command+=['-Iengines/obsidian/include']
    if engine=='geode':command+=['-mavx2','-ffp-contract=off']
    command += [SOURCES[engine],'-o',str(binary)]
    fingerprint=dependency_fingerprint(engine)
    if receipt.exists() and binary.exists() and not force:
        info=json.loads(receipt.read_text())
        if info.get('source_fingerprint')==fingerprint and info.get('executable_sha256')==sha(binary):return binary
    with exclusive(ROOT/'build'/f'.{engine}.lock'):
        result=run(command,ROOT,ROOT/'evidence'/f'compile-{engine}.log',threads)
        result.update(source_fingerprint=fingerprint,executable_sha256=sha(binary),
             compiler_version=subprocess.check_output([compiler,'--version'],text=True).splitlines()[0])
        atomic_json(receipt,result)
        if engine!='obsidian':run([binary,'--self-test'],ROOT,ROOT/'evidence'/f'self-test-{engine}.log',threads)
    return binary


def mesh_valid(scene:dict,path:Path)->bool:
    if not path.is_file():return False
    from tools.enhance_geometry import layout
    try:
        offset,count,stride,_=layout(path,scene['id'])
        return 0<count<30000000 and path.stat().st_size==offset+count*stride*4
    except (ValueError,struct.error):return False


def build_geometry(scene,threads=4):
    path=ROOT/scene['mesh']
    if mesh_valid(scene,path):return path
    engine=scene['engine'];prefix=ROOT/'engines'/engine
    if engine=='geo':
        examples=prefix/'cybr-geo/examples/three_scenes'
        if scene['member']=='forest':cmd=[sys.executable,examples/'fernwater_r6.py','--out',ROOT/'geometry']
        else:cmd=[sys.executable,examples/'rebuild_scenes.py','--out',ROOT/'geometry','--scene',scene['member'],'--no-glb']
    elif engine=='hot':cmd=[sys.executable,prefix/'cybr-geo/examples/desert_hot_springs/build_scene.py','--out',ROOT/'geometry/hot','--seed','20260914','--no-glb']
    elif engine=='obsidian':cmd=[sys.executable,prefix/'build_scene.py']
    else:cmd=[sys.executable,prefix/'build_v3.py']
    with exclusive(ROOT/'build'/f'.geometry-{scene["id"]}.lock'):
        run(cmd,prefix,ROOT/'evidence'/f'build-{scene["id"]}.log',threads)
        if not mesh_valid(scene,path):raise RuntimeError(f'Builder returned an invalid mesh: {path}')
    return path


def prepare_scene(scene,threads=4):
    original=build_geometry(scene,threads)
    from tools.enhance_geometry import enhance
    target=ROOT/scene['upgraded_mesh']
    enhance(scene['id'],original,target)
    return target


def comma(values):return ','.join(map(str,values))

def render_command(scene,binary,mesh,stem,width,height,spp,water_spp,threads,baseline=False):
    engine=scene['engine'];prefix=ROOT/'engines'/engine;depth=scene['depth']
    common=['--w',width,'--h',height,'--spp',spp,'--depth',depth,'--threads',threads]
    if engine=='obsidian':
        return [binary,mesh,stem,width,height,spp,0,depth],prefix,[sys.executable,prefix/'finish_v4.py',stem,'--exposure',scene['exposure'],'--passes',3]
    if engine=='geode':
        return [binary,mesh,stem,*common,'--seed',735041,'--exposure',scene['exposure']],prefix,[sys.executable,prefix/'finish_v3.py',stem,'--exposure',scene['exposure']]
    assets=prefix/'cybr-geo/examples/desert_hot_springs/assets'
    flags=[*common,'--water-spp',water_spp,'--indirect-clamp',0,'--no-clouds','--grain',assets/'gravel_periodic.pgm','--relief',assets/'granular_relief.bin']
    if engine=='hot':
        flags+=['--view','hero','--seed',20260914,'--exposure',scene['exposure'],'--sun','-0.80,0.40,0.28','--aperture',.001,'--water-absorption',1]
        finish=[sys.executable,ROOT/'tools/finish_r2.py','--backend','hot',stem,'--passes',2,'--white-balance',5750,'--opaque-filter-strength',.5]
    else:
        c=json.loads((ROOT/scene['camera']).read_text())
        flags+=['--scene',scene['member'],'--camera',comma(c['camera']),'--target',comma(c['target']),'--fov',c['fov'],
          '--sun',comma(c['sun']),'--exposure',c['exposure'],'--sun-scale',c.get('sun_scale',1),'--sky-scale',c.get('sky_scale',1),
          '--aperture',.0008,'--seed',20260915,'--water-absorption',c.get('water_absorption',1),'--no-steam']
        if scene['member']=='canyon':flags+=['--no-water']
        finish=[sys.executable,ROOT/'tools/finish_r2.py','--backend','geo',stem,'--passes',2,'--sky-passes',2,
            '--white-balance',c.get('white_balance',6000),'--opaque-filter-strength',.4]
        if scene['member']=='forest':finish+=['--foliage']
    return [binary,mesh,stem,*flags],prefix,finish


def read_pfm(path):
    import numpy as np
    with Path(path).open('rb') as f:
        header=f.readline().strip()
        if header not in [b'PF',b'Pf']:raise ValueError('Invalid PFM')
        shape=f.readline()
        while shape.startswith(b'#'):shape=f.readline()
        w,h=map(int,shape.split());scale=float(f.readline());channels=3 if header==b'PF' else 1
        a=np.fromfile(f,dtype='<f4' if scale<0 else '>f4')
    if len(a)!=w*h*channels:raise ValueError('PFM dimensions/data mismatch')
    return np.flipud(a.reshape(h,w,channels))


def verify_render(stem:Path,width=None,height=None):
    import numpy as np
    from PIL import Image
    native=json.loads(stem.with_suffix('.json').read_text())
    rgb=read_pfm(stem.with_suffix('.pfm'));im=np.asarray(Image.open(stem.with_suffix('.png')).convert('RGB'))
    expected=[width or rgb.shape[1],height or rgb.shape[0]]
    invalid=native.get('nonfinite_path_samples',native.get('invalid_samples',0))
    spectral_path=stem.with_suffix('.spectral')
    spectral_info=None
    spectral_nonnegative=True
    if spectral_path.exists():
        with spectral_path.open('rb') as f:
            hdr=np.fromfile(f,dtype='<u4',count=4)
            if len(hdr)!=4 or int(hdr[0])!=0x36315053 or list(map(int,hdr[1:3]))!=expected:
                raise ValueError('Spectral film header does not match the rendered image')
            bands=np.fromfile(f,dtype='<f4')
        if bands.size!=expected[0]*expected[1]*int(hdr[3]):raise ValueError('Truncated spectral film')
        spectral_nonnegative=bool(np.isfinite(bands).all() and bands.min()>=-1e-6)
        spectral_info={'bands':int(hdr[3]),'minimum':float(bands.min()),'maximum':float(bands.max()),
            'sha256':sha(spectral_path)}
    else:spectral_nonnegative=bool(np.min(rgb)>=-1e-6)
    tests={'finite_radiance':bool(np.isfinite(rgb).all()),'nonnegative_transport_radiance':spectral_nonnegative,
      'dimensions_match':list(im.shape[1::-1])==expected and list(rgb.shape[1::-1])==expected,
      'nonblank_image':bool(np.std(im.astype(float))>5),'no_invalid_reported_paths':invalid==0,
      'positive_triangle_count':native.get('triangles',native.get('actual_triangles',0))>0,
      'image_generation_disabled':native.get('image_generation') is False}
    result={'passed':all(tests.values()),'tests':tests,'dimensions':expected,'radiance_min':float(rgb.min()),
      'radiance_max':float(rgb.max()),'spectral_film':spectral_info,
      'negative_linear_rgb_components':int(np.count_nonzero(rgb<0)),
      'rgb_note':'Spectral-to-XYZ-to-display-RGB conversion may produce negative out-of-gamut RGB components. Positivity is checked in the transported spectral bands when present, not in display RGB.',
      'mean_linear_rgb':rgb.mean((0,1)).tolist(),
      'png_sha256':sha(stem.with_suffix('.png')),'raw_pfm_sha256':sha(stem.with_suffix('.pfm')),
      'native_metadata_sha256':sha(stem.with_suffix('.json')),'renderer_metadata':native,
      'scope':'Execution, finite radiance, dimensions, traceable geometry; not an aesthetic or physical-reference validation.',
      'checked_at':now()}
    atomic_json(stem.parent/'verification.json',result)
    if not result['passed']:raise RuntimeError(f'Render verification failed: {tests}')
    return result


def render_scene(scene,args):
    label='baseline' if args.baseline else 'hero'
    out=ROOT/'renders'/scene['id']/label if args.output is None else args.output.expanduser().resolve()/scene['id']/label
    out.mkdir(parents=True,exist_ok=True);stem=out/label
    if stem.with_suffix('.png').exists() and not args.force:
        if not stem.with_suffix('.pfm').exists():
            raise RuntimeError('A display PNG is installed without its native film. Extract the Raw Proof archive to verify it, or pass --force to render afresh (or --output renders/my-run for a separate run).')
        print(f'Existing result: {stem}.png (use --force to rerender)',flush=True)
        verification=verify_render(stem)
        if not (out/'receipt.json').exists():
            mesh=ROOT/scene['mesh'] if args.baseline else ROOT/scene['upgraded_mesh']
            binary=ROOT/'build'/f'{scene["engine"]}_{"original" if args.baseline else "r2"}'
            command_file=out/'render.command.json'
            if not command_file.exists():raise RuntimeError('Missing execution record; cannot reconstruct a receipt')
            record=json.loads(command_file.read_text())
            if record.get('returncode')!=0:raise RuntimeError('Native execution did not complete successfully')
            build=json.loads(binary.with_suffix('.build.json').read_text())
            if build.get('executable_sha256')!=sha(binary):raise RuntimeError('Executable no longer matches its build record')
            receipt={'scene':scene['id'],'revision':'baseline' if args.baseline else 'R2',
                'started_at':record['started_at'],'native_finished_at':record.get('finished_at'),
                'receipt_created_at':now(),'receipt_reconstructed_after_verifier_fix':True,
                'mesh_sha256':sha(mesh),'executable_sha256':sha(binary),
                'source_fingerprint':build['source_fingerprint'],
                'material_atlas_sha256':sha(ROOT/'assets/mineral_detail.cdt'),'render':record,'verification':verification,
                'reference_image_used_as_render_input':False,'camera_orbit_animation':False,'simulation':scene.get('simulation',False)}
            atomic_json(out/'receipt.json',receipt)
        return verification
    mesh=ROOT/scene['mesh'] if args.baseline else ROOT/scene['upgraded_mesh']
    if not mesh_valid(scene,mesh):
        mesh=build_geometry(scene,args.threads) if args.baseline else prepare_scene(scene,args.threads)
    if args.baseline:
        binary=ROOT/'build'/f'{scene["engine"]}_original'
        if not binary.exists():raise RuntimeError('Compile the preserved originals with python tools/compile_originals.py first.')
    else:binary=compile_engine(scene['engine'],args.threads)
    width=args.width if args.width is not None else (640 if args.quality=='preview' else 1280)
    height=args.height if args.height is not None else (round(width*scene['aspect'][1]/scene['aspect'][0]/2)*2)
    spp=args.spp if args.spp is not None else (24 if args.quality=='preview' else scene['spp'])
    water=args.water_spp if args.water_spp is not None else (48 if args.quality=='preview' else scene['water_spp'])
    if min(width,height,spp,water,args.threads)<1:raise ValueError('Dimensions, sample budgets and threads must be positive')
    command,cwd,finish=render_command(scene,binary,mesh,stem,width,height,spp,water,args.threads,args.baseline)
    with exclusive(out/'.render.lock'):
        started=now();record=run(command,cwd,out/'render.log',args.threads,args.timeout)
        native_meta=Path(str(stem)+'_render.json') if scene['engine']=='obsidian' else stem.with_suffix('.json')
        shutil.copy2(native_meta,out/'native-metadata.json')
        finish_record=run(finish,cwd,out/'finish.log',args.threads,args.timeout)
        if scene['engine']=='geode':
            shutil.copy2(Path(str(stem)+'_unfiltered.png'),Path(str(stem)+'_raw.png'))
        if scene['engine']=='obsidian':
            native=json.loads(Path(str(stem)+'_render.json').read_text())
            # Canonical adapter preserves the native file; it does not infer a successful run.
            import re
            hits=re.findall(r'NONFINITE_SAMPLES (\d+)',(out/'render.log').read_text())
            if len(hits)!=1:raise RuntimeError('Obsidian native nonfinite counter was not recorded')
            native.update(nonfinite_path_samples=int(hits[0]),image_generation=False,
                native_metadata_file=relative(Path(str(stem)+'_render.json')),
                image_generation_evidence='Executed native C++ renderer; full recorded command and source build')
            atomic_json(stem.with_suffix('.json'),native)
        verification=verify_render(stem,width,height)
        receipt={'scene':scene['id'],'revision':'baseline' if args.baseline else 'R2','started_at':started,'finished_at':now(),
            'mesh_sha256':sha(mesh),'executable_sha256':sha(binary),'source_fingerprint':json.loads(binary.with_suffix('.build.json').read_text())['source_fingerprint'],
            'material_atlas_sha256':sha(ROOT/'assets/mineral_detail.cdt'),'render':record,'postprocess':finish_record,'verification':verification,
            'reference_image_used_as_render_input':False,'camera_orbit_animation':False,'simulation':scene.get('simulation',False)}
        atomic_json(out/'receipt.json',receipt)
    allocation=f'{spp}/{water}' if scene['engine'] in ['geo','hot'] else str(spp)
    print(f'RENDER VERIFIED: {scene["id"]} {width}x{height} {allocation} spp -> {stem}.png',flush=True)
    return verification


def doctor():
    modules={}
    for name in ['numpy','scipy','Pillow','trimesh','numba','scikit-image','opencv-python-headless']:
        try:modules[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:modules[name]=None
    return {'python':sys.version,'platform':platform.platform(),'compiler':shutil.which('g++'),
       'logical_cpus':os.cpu_count(),'modules':modules,
       'container_cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None,
       'container_memory_limit_bytes':Path('/sys/fs/cgroup/memory.max').read_text().strip() if Path('/sys/fs/cgroup/memory.max').exists() else None,
       'notes':['Native geometry can use several GB. Run the six scenes sequentially.',
                'Linux/WSL tested; g++ OpenMP required; geode build uses AVX2.',
                'No neural denoiser, image model, GPU service, or Blender required.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('list');sub.add_parser('doctor');a=sub.add_parser('compile');a.add_argument('--force',action='store_true')
    a=sub.add_parser('prepare');a.add_argument('scene',choices=[*SCENES,'all']);a.add_argument('--threads',type=int,default=4)
    a=sub.add_parser('verify');a.add_argument('--root',type=Path,default=ROOT/'renders')
    a=sub.add_parser('serve');a.add_argument('--host',default='127.0.0.1');a.add_argument('--port',type=int,default=8000)
    a=sub.add_parser('render');a.add_argument('scene',choices=[*SCENES,'all']);a.add_argument('--quality',choices=['preview','production'],default='production')
    a.add_argument('--width',type=int);a.add_argument('--height',type=int);a.add_argument('--spp',type=int);a.add_argument('--water-spp',type=int)
    a.add_argument('--threads',type=int,default=4);a.add_argument('--timeout',type=int,default=14400);a.add_argument('--force',action='store_true')
    a.add_argument('--baseline',action='store_true');a.add_argument('--output',type=Path)
    args=p.parse_args()
    try:
        if args.command=='list':print(json.dumps(REGISTRY,indent=2))
        elif args.command=='doctor':print(json.dumps(doctor(),indent=2))
        elif args.command=='compile':
            for engine in SOURCES:compile_engine(engine,force=args.force)
        elif args.command in ['prepare','render']:
            selected=list(SCENES.values()) if args.scene=='all' else [SCENES[args.scene]]
            outcomes=[]
            failed = False
            for scene in selected:
                outcome={'scene':scene['id'], 'state':'running', 'started_at':now()}
                outcomes.append(outcome)
                atomic_json(ROOT/'evidence'/f'{args.command}-batch.json',outcomes)
                try:
                    result=prepare_scene(scene,args.threads) if args.command=='prepare' else render_scene(scene,args)
                    outcome.update(state='succeeded',result=str(result) if isinstance(result,Path) else result)
                except Exception as exc:
                    failed=True
                    outcome.update(state='failed',error=f'{type(exc).__name__}: {exc}')
                    print(f'FAILED {scene["id"]}: {exc}',file=sys.stderr,flush=True)
                finally:
                    outcome['finished_at']=now()
                    atomic_json(ROOT/'evidence'/f'{args.command}-batch.json',outcomes)
            if failed:return 1
        elif args.command=='verify':
            verified=[]
            for path in sorted(args.root.glob('*/hero/hero.png')):verified.append({'scene':path.parent.parent.name,'result':verify_render(path.with_suffix(''))})
            result={'passed':len(verified)==6 and all(x['result']['passed'] for x in verified),'scenes':verified}
            atomic_json(ROOT/'evidence/all-scenes-verification.json',result);print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
        elif args.command=='serve':
            import functools
            handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
            with http.server.ThreadingHTTPServer((args.host,args.port),handler) as server:
                print(f'Local gallery: http://{args.host}:{args.port}/gallery.html',flush=True);server.serve_forever()
        return 0
    except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as exc:
        print(f'ERROR: {exc}',file=sys.stderr);return 1

if __name__=='__main__':
    # Enforce one full-geometry workload per project. Short status/doctor calls
    # remain independent of this lock and cannot block behind a long render.
    if len(sys.argv)>1 and sys.argv[1] in {'prepare','render','compile'}:
        try:
            with exclusive(ROOT/'build'/'.execution-lane.flock'):
                raise SystemExit(main())
        except RuntimeError as exc:
            print(f'ERROR: {exc}',file=sys.stderr)
            raise SystemExit(1)
    raise SystemExit(main())
