"""Compile and render the three native CYBR GEO scenes; retain raw evidence."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,time,os,platform
from pathlib import Path
from build_scenes import sha
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]

def compile_renderer():
    """Rebuild native-CPU binaries when source, compiler, CPU, or file integrity changes."""
    binary=REPO.parent/'spectral_scenes';native=REPO/'native'
    files=sorted([native/'spectral_scenes.cpp']+list(native.glob('*.h')))
    digest=hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest();stamp=binary.with_suffix('.build.json')
    compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0]
    flags=''
    cpuinfo=Path('/proc/cpuinfo')
    if cpuinfo.is_file():
        flags=next((line.split(':',1)[1].strip() for line in cpuinfo.read_text().splitlines()
                    if line.startswith(('flags','Features')) and ':' in line),'')
    cxx_flags=['-std=c++17','-O3','-march=native','-fno-math-errno','-fno-trapping-math','-fopenmp']
    host={'cxx_flags':cxx_flags,'system':platform.system(),'machine':platform.machine(),'compiler':compiler,'cpu_flags':flags}
    try: previous=json.loads(stamp.read_text())
    except (FileNotFoundError,json.JSONDecodeError): previous={}
    reusable=(binary.is_file() and os.access(binary,os.X_OK)
              and previous.get('source_sha256')==digest
              and previous.get('build_host')==host
              and previous.get('binary_sha256')==sha(binary))
    if not reusable:
        cmd=['g++']+cxx_flags+[str(native/'spectral_scenes.cpp'),'-o',str(binary)]
        subprocess.run(cmd,check=True)
        stamp.write_text(json.dumps({'source_sha256':digest,'binary_sha256':sha(binary),
                                     'command':cmd,'compiler':compiler,'build_host':host},indent=2))
    return binary,json.loads(stamp.read_text())

def render(root,scene,width=1920,height=1280,spp=128,water_spp=320,stem='hero',threads=4,exr=True):
    binary,build=compile_renderer();folder=root/scene;config=json.loads((folder/'camera.json').read_text());output=folder/stem
    if config.get('r6_local_material_frames',False):
        frame_path=folder/'surface_frames.bin'
        geometry=json.loads((folder/'geometry.json').read_text())
        if not frame_path.is_file() or sha(frame_path)!=geometry.get('surface_frames_sha256'):
            raise RuntimeError('Missing or mismatched R6 surface-coordinate table; rebuild the scene')
    command=[str(binary),str(folder/'scene.meshbin'),str(output),'--scene',scene,'--camera',','.join(map(str,config['camera'])),'--target',','.join(map(str,config['target'])),'--fov',str(config['fov']),
             '--sun',','.join(map(str,config['sun'])),'--exposure',str(config['exposure']),'--sun-scale',str(config.get('sun_scale',1)),'--sky-scale',str(config.get('sky_scale',1)),
             '--w',str(width),'--h',str(height),'--spp',str(spp),'--water-spp',str(water_spp),'--threads',str(threads),'--depth','12','--seed','20260915','--aperture','0.0008','--indirect-clamp','0',
             '--guide-spp',str(64 if scene=='forest' else 16),'--water-absorption',str(config.get('water_absorption',1)),'--no-clouds','--no-steam',
             '--grain',str(REPO/'examples/desert_hot_springs/assets/gravel_periodic.pgm'),
             '--relief',str(REPO/'examples/desert_hot_springs/assets/granular_relief.bin')]
    if scene=='coast': command.remove('--no-clouds')
    if scene=='canyon':command+=['--no-water']
    certificate=None
    if scene=='forest':
        from ground_occlusion import build_ground_certificate
        certificate=build_ground_certificate(folder)
        command+=['--ground-occlusion',str(certificate)]
    started=time.monotonic()
    with (folder/(stem+'_render.log')).open('w') as log:
        print('RENDER',scene,stem,width,height,spp,flush=True);subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    receipt={'command':command,'build':build,'mesh_sha256':sha(folder/'scene.meshbin'),'camera':config,'wall_seconds':time.monotonic()-started,
             'grain_sha256':sha(REPO/'examples/desert_hot_springs/assets/gravel_periodic.pgm'),
             'relief_sha256':sha(REPO/'examples/desert_hot_springs/assets/granular_relief.bin'),
             'active_material_header':'fernwater_materials_r6.h','image_generation':False,
             'surface_frames_sha256':sha(folder/'surface_frames.bin') if (folder/'surface_frames.bin').exists() else None,
             'ground_occlusion_certificate_sha256':sha(certificate) if certificate else None,
             'ground_occlusion_certificate':json.loads(certificate.with_suffix('.json').read_text()) if certificate else None}
    (folder/(stem+'_execution.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    subprocess.run([sys.executable,str(HERE/'noise_resolve.py'),'--linear',str(output)+'.pfm','--guides',str(output)+'.guides','--support',str(output)+'.support','--metadata',str(output)+'.json','--guide-metadata',str(output)+'.json','--output',str(output),'--white-balance',str(config['white_balance']),'--threads',str(threads)],check=True,stdout=subprocess.DEVNULL)
    if exr:subprocess.run([sys.executable,str(HERE/'export_exr.py'),str(output)+'.pfm',str(output)+'_linear.exr'],check=True,stdout=subprocess.DEVNULL)
    print('COMPLETED',scene,stem,time.monotonic()-started,flush=True);return receipt

def build_scene_geometry(root:Path,scene:str):
    """Keep the standalone --build-scenes path on the same active R6 forest recipe."""
    for name in (['canyon','coast','forest'] if scene=='all' else [scene]):
        if name=='forest':
            command=[sys.executable,str(HERE/'fernwater_r6.py'),'--out',str(root)]
        else:
            command=[sys.executable,str(HERE/'rebuild_scenes.py'),'--out',str(root),'--scene',name,'--no-glb']
        subprocess.run(command,check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--scene',choices=['canyon','coast','forest','all'],default='all');p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1280);p.add_argument('--spp',type=int,default=128);p.add_argument('--water-spp',type=int,default=320);p.add_argument('--stem',default='hero');p.add_argument('--threads',type=int,default=4);p.add_argument('--build-scenes',action='store_true');p.add_argument('--no-exr',action='store_true')
    a=p.parse_args()
    if min(a.width,a.height,a.spp,a.threads)<1:p.error('Positive dimensions, samples, and threads required')
    if Path(a.stem).name!=a.stem:p.error('Stem must be a simple filename')
    if a.build_scenes:build_scene_geometry(a.root,a.scene)
    for scene in (['canyon','coast','forest'] if a.scene=='all' else [a.scene]):render(a.root,scene,a.width,a.height,a.spp,a.water_spp,a.stem,a.threads,exr=not a.no_exr)
if __name__=='__main__':main()
