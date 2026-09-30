"""Render retained scene builders with the pinned CYBR LIGHT spectral engine."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
import struct
import subprocess
import sys
import numpy as np
from cybr_light import Scene, Meshlets, render, compile_renderer

ROOT=Path(__file__).resolve().parents[1]
ENV=ROOT/'environments'
OBS=ROOT/'scenes/observatory-iv'
sys.path.insert(0,str(ENV))
from execution_runtime import atomic_json, owned_lock, run_recorded


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8<<20),b''):h.update(block)
    return h.hexdigest()


def environments():
    spec=importlib.util.spec_from_file_location('cybr_light_environment_builders',ENV/'cybr_scenes.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def pfm(path,image):
    image=np.asarray(image,dtype='<f4');path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as stream:
        stream.write(f'PF\n{image.shape[1]} {image.shape[0]}\n-1.0\n'.encode());stream.write(image[::-1].tobytes())
    return path


def cvtex(path,output):
    with Path(path).open('rb') as stream:
        w,h,stride=struct.unpack('<III',stream.read(12));a=np.fromfile(stream,dtype='<f4')
    if stride!=7 or a.size!=w*h*7:raise ValueError('Invalid material map')
    a=a.reshape(h,w,7)
    color=pfm(output.with_suffix('.pfm'),a[:,:,:3])
    normal=pfm(output.with_name(output.name+'_normal.pfm'),a[:,:,3:6]*.5+.5)
    return color,normal,float(np.median(a[:,:,6]))


def material_for(scene,kind,texture,texture_dir,converted,observatory=False):
    colors=[(.24,.22,.18),(.13,.14,.12),(.30,.25,.17),(.62,.38,.12),(.4,.42,.44),(.35,.38,.4),(.7,.75,.7),(.6,.65,.6),(.98,.98,.98),(.95,.93,.9),(.022,.017,.009),(.06,.07,.055),(.8,.82,.78)]
    base='plastic';rough=.7;color=colors[min(kind,len(colors)-1)];ior=1.5;dispersion=0;absorption=(0,0,0)
    if kind in ([3,4,5] if observatory else []):base='metal';rough=.27
    if kind in ([8] if observatory else [8,9]):base='roughglass';rough=.016;ior=1.45;dispersion=.004;absorption=(.025,.015,.03);color=(1,1,1)
    if not observatory and kind==6:base='glass';rough=0;ior=1.334;color=(1,1,1);absorption=(.17,.045,.025)
    if observatory and kind==12:base='difftrans';rough=.86
    tex=None;normal=None
    if texture>=0:
        if texture not in converted:converted[texture]=cvtex(texture_dir/f'{texture}.cvtex',converted['directory']/str(texture))
        tex,normal,rough=converted[texture]
        color=(1,1,1)
    index=scene.material(base,color,rough,ior,dispersion,absorption=absorption,anisotropy=.45 if base=='metal' else 0,texture=tex)
    if normal and base not in ('glass','roughglass'):
        wrapper=scene.material('normalmap',texture=normal);scene.emit('nested',wrapper,index,-1,.5);index=wrapper
    return index


def convert_cvr(source,target,scene,observatory):
    with source.open('rb') as stream:
        magic,count=struct.unpack('<4sI',stream.read(8))
    if magic!=b'CVR2' or source.stat().st_size!=8+count*144:raise ValueError('Invalid CVR2 geometry')
    original=np.memmap(source,mode='r',offset=8,dtype='<f4',shape=(count,36))
    palette={};converted={'directory':target.parent/'textures'}
    texture_dir=source.parent/'textures'
    # Prepared geode meshes retain texture maps beside the original input.
    if not texture_dir.exists():texture_dir=ENV/'engines/geode/assets/built_v3/textures'
    with Meshlets(target) as writer:
        for start in range(0,count,24000):
            a=np.array(original[start:start+24000],copy=True)
            source_keys=a[:,[18,35]].copy();keys=np.unique(source_keys.astype(np.int32),axis=0)
            for kind,tex in keys:
                key=(int(kind),int(tex))
                if key not in palette:palette[key]=material_for(scene,*key,texture_dir,converted,observatory)
                selected=(source_keys[:,0]==kind)&(source_keys[:,1]==tex);a[selected,18]=palette[key]
            a[:,19]+=1;a[:,35]=1;writer.add(a)
    return writer


def convert_landscape(source,target,scene,identifier):
    with source.open('rb') as stream:count=struct.unpack('<I',stream.read(4))[0]
    if source.stat().st_size!=4+count*80:raise ValueError('Invalid landscape mesh')
    original=np.memmap(source,mode='r',offset=4,dtype='<f4',shape=(count,20))
    forest=identifier=='fernwater';sand=identifier in ('sandstone-passage','desert-hot-springs')
    palette={}
    for kind in range(17):
        color=(.28,.17,.09) if sand else (.09,.10,.085)
        rough=.8;base='plastic';ior=1.49;absorption=(0,0,0)
        if kind in (6,7):base='glass';ior=1.334;color=(1,1,1);rough=0;absorption=(.17,.045,.025)
        elif forest:
            if kind in (3,9,11,13):color=(.05,.15,.015);rough=.45
            elif kind in (8,12,14):color=(.065,.040,.022)
            elif kind==10:color=(.03,.07,.01)
            elif kind in (0,4):color=(.04,.025,.012)
        elif not sand and kind==13:color=(.04,.07,.025)
        palette[kind]=scene.material(base,color,rough,ior,absorption=absorption)
    with Meshlets(target) as writer:
        for start in range(0,count,24000):
            src=np.array(original[start:start+24000]);a=np.zeros((len(src),36),'<f4');a[:,:20]=src;a[:,19]+=1;a[:,26:35]=1
            for kind,index in palette.items():a[src[:,18]==kind,18]=index
            # Authored, geometry-space strata and mineral variation. This is
            # real surface reflectance, never a background/reference image.
            p=src[:,:9].reshape(-1,3,3)
            variation=1+.075*np.sin(p[:,:,0]*11.2+p[:,:,1]*7.1)*np.sin(p[:,:,2]*31.7)
            if sand:variation*=.90+.10*np.sin(p[:,:,2]*74+p[:,:,1]*.7)
            tint=np.repeat(variation[:,:,None],3,axis=2);water=np.isin(src[:,18],[6,7]);tint[water]=1
            a[:,26:35]=tint.reshape(-1,9);writer.add(a)
    return writer


def convert_obsidian(source,target,scene):
    assets=ENV/'engines/obsidian/assets'
    with source.open('rb') as stream:
        magic,nm,count,stride=struct.unpack('<4I',stream.read(16));raw=np.frombuffer(stream.read(nm*36),dtype='<f4').reshape(nm,9).copy()
    if magic!=0x3253424f or stride!=104 or source.stat().st_size!=16+nm*36+count*104:raise ValueError('Invalid OBS2 mesh')
    original=np.memmap(source,mode='r',offset=16+nm*36,dtype='<f4',shape=(count,26))
    kinds=raw[:,8].view('<i4');palette={};bounds=None
    for index,row in enumerate(raw):
        emission=float(np.max(row[3:6]));color=row[:3];base='plastic'
        if kinds[index]==10000:
            with (assets/'lava_skin.bin').open('rb') as stream:
                w,h,*bounds=struct.unpack('<II4f',stream.read(24));thermal=np.fromfile(stream,'<f4').reshape(h,w,8)[:,:,2]
            texture=pfm(target.parent/'textures/temperature.pfm',np.repeat(thermal[:,:,None],3,axis=2))
            material=scene.material('plastic',(.025,.026,.028),.35,emission=19,kelvin=0)
            scene.emit('emission_temperature',material,json.dumps(str(texture.resolve())))
        elif emission>0:
            material=scene.material('plastic',color,row[6],emission=emission,kelvin=1250)
        else:material=scene.material(base,color,row[6])
        palette[index]=material
    with Meshlets(target) as writer:
        for start in range(0,count,24000):
            src=np.array(original[start:start+24000]);a=np.zeros((len(src),36),'<f4');a[:,:18]=src[:,:18];a[:,20:26]=src[:,18:24]
            mat=src[:,24].view('<i4');a[:,19]=src[:,25].view('<i4')+1;a[:,26:35]=1
            for index,mapped in palette.items():
                selected=mat==index;a[selected,18]=mapped
                if kinds[index]==10000:
                    points=a[selected,:9].reshape(-1,3,3);z=points[:,:,2];center=3.7*np.sin(z*.090)+1.10*np.sin(z*.153+.7)
                    uv=np.stack(((points[:,:,0]-center-bounds[0])/(bounds[1]-bounds[0]),(z-bounds[2])/(bounds[3]-bounds[2])),axis=2)
                    a[selected,20:26]=uv.reshape(-1,6)
            writer.add(a)
    return writer


def prepare(identifier,threads,timeout):
    if identifier!='observatory-iv':
        module=environments();record=module.SCENES[identifier]
        return module.prepare_scene(record,threads),record
    directory=OBS/'build/scene';stamp=directory/'light-build.json'
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [OBS/'build_scene.py',OBS/'assets/observatory_interior_source.glb']}
    if stamp.exists():
        old=json.loads(stamp.read_text())
        if old.get('inputs')==inputs and old.get('files') and all((directory/name).is_file() and sha(directory/name)==digest for name,digest in old['files'].items()):return directory/'observatory.cvr2',{'aspect':[3,2],'depth':14,'spp':192}
    directory.mkdir(parents=True,exist_ok=True)
    run_recorded([sys.executable,OBS/'build_scene.py','--out',directory],OBS,OBS/'build/logs/light-prepare.log',threads,timeout)
    run_recorded([sys.executable,OBS/'verify.py','--geometry-only','--scene-dir',directory,'--out',OBS/'build/verification/light-geometry.json'],OBS,OBS/'build/logs/light-geometry.log',threads,timeout)
    atomic_json(stamp,{'inputs':inputs,'files':{str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file() and p!=stamp and p.name!='build-receipt.json'}})
    return directory/'observatory.cvr2',{'aspect':[3,2],'depth':14,'spp':192}


def render_scene(args):
    identifier=args.scene;out=args.output.expanduser().resolve()/identifier/'hero';out.mkdir(parents=True,exist_ok=True)
    stem=out/'hero';receipt=out/'receipt.json'
    quality={'smoke':(64,4,4),'preview':(800,64,8),'production':(1800,192,12)}[args.quality]
    with owned_lock(ROOT/'build'/f'.light-{identifier}.lock'):
        source,record=prepare(identifier,args.threads,args.timeout)
        width=args.width or quality[0];height=args.height or max(1,round(width*record['aspect'][1]/record['aspect'][0]))
        spp=args.spp or quality[1];bands=args.bands or quality[2];depth=args.depth or record['depth']
        if args.water_spp is not None:raise ValueError('CYBR LIGHT uses one spectral packet budget; use --spp')
        _,engine=compile_renderer()
        settings={'width':width,'height':height,'spp':spp,'bands':bands,'depth':depth,'threads':args.threads,
                  'mesh':sha(source),'adapter':sha(Path(__file__)),'runtime':sha(Path(__file__).parent/'cybr_light/runtime.py'),'finishing':sha(Path(__file__).parent/'cybr_light/finishing.py'),'engine':engine,'scene_configuration':{'preset':record,'camera_sha256':sha(ENV/record['camera']) if record.get('camera') else None},'material_inputs':{str(p.relative_to(ROOT)):sha(p) for p in sorted((source.parent if identifier=='observatory-iv' else ENV/'engines'/record['engine']).rglob('*')) if p.is_file() and p.suffix in ('.cvtex','.bin') and (identifier=='observatory-iv' or not any(v in p.parts for v in ('build','evidence','provenance')))}}
        if not args.force and receipt.exists():
            previous=json.loads(receipt.read_text())
            if previous.get('settings')==settings and previous.get('files') and all((out/name).is_file() and sha(out/name)==digest for name,digest in previous['files'].items()):
                print(f'Cached CYBR LIGHT render: {stem}.png');return
        receipt.unlink(missing_ok=True)
        scene=Scene();exposure=1.25 if identifier=='observatory-iv' else record.get('exposure',1.3)
        scene.settings(width,height,spp,depth,args.threads,bands,20260915,exposure)
        target=out/'scene.clm'
        # Resolution/sampling changes reuse the already checked meshlet pack.
        # Only geometry, converter or material inputs invalidate conversion.
        conversion_key={key:settings[key] for key in ('mesh','adapter','material_inputs')}
        conversion_receipt=out/'meshlet-receipt.json';cached=None
        if conversion_receipt.exists():
            previous=json.loads(conversion_receipt.read_text())
            if previous.get('inputs')==conversion_key and previous.get('files') and all((out/name).is_file() and sha(out/name)==digest for name,digest in previous['files'].items()):cached=previous
        if cached:
            scene.lines.extend(cached['material_lines']);scene.materials=cached['material_count'];geometry=cached['geometry']
        else:
            conversion_receipt.unlink(missing_ok=True);materials=Scene()
            if identifier in ('observatory-iv','drowned-geode'):writer=convert_cvr(source,target,materials,identifier=='observatory-iv')
            elif identifier=='obsidian-reach':writer=convert_obsidian(source,target,materials)
            else:writer=convert_landscape(source,target,materials,identifier)
            geometry={'triangles':writer.triangles,'meshlets':writer.meshlets,'indexed_vertices':writer.vertices,
                      'bytes':target.stat().st_size,'unindexed_bytes':16+144*writer.triangles}
            files={str(p.relative_to(out)):sha(p) for p in [target,*sorted((out/'textures').rglob('*.pfm'))]}
            # Cache paths are relative to the output, as in the native scene.
            lines=[re.sub(r'"([^"]+)"',lambda m:json.dumps(str(Path(m.group(1)).relative_to(out))),line) for line in materials.lines]
            atomic_json(conversion_receipt,{'inputs':conversion_key,'files':files,'material_lines':lines,'material_count':materials.materials,'geometry':geometry})
            scene.lines.extend(materials.lines);scene.materials=materials.materials
        origin=(-.95,-3.28,2.38);look=(-.20,.43,1.51);hfov=62;up=(0,0,1);sun=(.52,.81,.335)
        if record.get('camera'):
            camera=json.loads((ENV/record['camera']).read_text());origin=camera['camera'];look=camera['target'];hfov=camera['fov'];sun=camera['sun']
        elif identifier=='desert-hot-springs':origin=(2.1,-5.65,1.52);look=(-.15,3.15,.15);hfov=72;sun=(-.8,.4,.28)
        elif identifier=='drowned-geode':origin=(-3.8,-10.3,2.6);look=(.6,12.8,6.3);hfov=82;sun=(-.6,.4,.7)
        elif identifier=='obsidian-reach':origin=(-2.8,7,-15);look=(.5,1.8,12);hfov=math.degrees(2*math.atan(math.tan(math.radians(41/2))*width/height));up=(0,1,0);sun=(-.62,.44,.65)
        vfov=math.degrees(2*math.atan(math.tan(math.radians(hfov/2))*height/width))
        scene.camera(origin,look,up,fov=vfov,aperture=.0008)
        sun=np.asarray(sun);sun/=np.linalg.norm(sun)
        scene.emit('environment',(.55,.65,.8),.65 if identifier!='obsidian-reach' else .05);scene.emit('environment_flat')
        scene.emit('delta_light',1,(0,0,0),-sun,(1,1,1),3.0,0,0)
        if identifier=='observatory-iv':
            # Broad daylight sources outside the actual modeled windows.
            for corner,u,v,power in [((.5,3.35,.87),(1.7,0,0),(0,0,2.65),24),((-2.6,-4.0,1.08),(1.58,0,0),(0,0,2.54),10)]:
                material=scene.material('emitter',(1,1,1),emission=power,kelvin=6200)
                # Front source faces +Y; rear source faces -Y.
                if corner[1]<0:corner=tuple(np.asarray(corner)+np.asarray(u));u=tuple(-np.asarray(u))
                scene.emit('quad',material,16777001,corner,u,v,(0,0,0))
            scene.emit('volume',0,(-3.6,-3.6,0),(3.6,2.77,5),(.006,.006,.006),(.85,.85,.85),.36,1,1)
            scene.emit('phase',0,0)
        scene.mesh(target)
        report=render(scene,stem,runner=lambda command:run_recorded(command,ROOT,ROOT/'build/logs'/f'light-{identifier}.log',args.threads,args.timeout))
        report.update(scene=identifier,geometry=geometry,source_mesh_sha256=settings['mesh'],
                      material_adapter='Preserved geometry, UVs, vertex tint and component IDs; general CYBR LIGHT BSDF/volume models replace bespoke transport estimators.')
        atomic_json(stem.with_suffix('.json'),report)
        files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p!=receipt}
        atomic_json(receipt,{'passed':True,'renderer':'CYBR LIGHT 0.2','settings':settings,'geometry':geometry,'files':files})
    print(f'CYBR LIGHT: {identifier} {width}x{height} / {spp} packets x {bands} wavelengths -> {stem}.png')
