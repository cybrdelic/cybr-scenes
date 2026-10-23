#!/usr/bin/env python3
"""Capture native shared-header regression films; does not replace original renders."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def compare(out):
    before=json.loads((out/'before-capture.json').read_text())
    after=json.loads((out/'after-capture.json').read_text())
    assert [r['engine'] for r in before]==[r['engine'] for r in after]==['geo','hot']
    rows=[]
    for old,new in zip(before,after):
        engine=old['engine']
        for key in ['mesh_sha256','atlas_sha256','grain_sha256','relief_sha256']:
            assert old[key]==new[key], (engine,key)
        assert old['returncode']==new['returncode']==0
        assert old['command'][3:]==new['command'][3:], (engine,'settings')
        assert old['outputs']==new['outputs'], (engine,'raw output mismatch')
        metadata=[]
        for phase in ['before','after']:
            meta=json.loads((out/phase/engine/'native.json').read_text())
            assert meta['nonfinite_path_samples']==0
            meta.pop('seconds',None)
            metadata.append(meta)
            for name,record in old['outputs'].items():
                path=out/phase/engine/name
                assert path.stat().st_size==record['bytes'] and sha(path)==record['sha256']
        assert metadata[0]==metadata[1], (engine,'metadata')
        rows.append({'engine':engine,'byte_identical':True,'buffers':old['outputs'],
                     'nonfinite_path_samples':0,'triangles':metadata[0]['triangles']})
    result={'scope':'New authored 320x200 16-spp diagnostic scenes; not original-environment rerenders or final-quality images',
            'same_input_hashes':True,'same_render_settings':True,'cases':rows,'passed':True}
    (out/'parity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase',choices=['before','after','compare'])
    ap.add_argument('--build',type=Path)
    ap.add_argument('--out',type=Path,default=Path('outputs/shared-native-core'))
    ap.add_argument('--width',type=int,default=320)
    ap.add_argument('--height',type=int,default=200)
    ap.add_argument('--spp',type=int,default=16)
    a=ap.parse_args(); out=ROOT/a.out
    if a.phase=='compare':
        compare(out);return
    if a.build is None: ap.error('--build is required for capture')
    build=ROOT/a.build
    env=os.environ.copy(); env['CYBR_SURFACE_ATLAS']=str(ROOT/'environments/assets/mineral_detail.cdt')
    env['OMP_NUM_THREADS']='1'
    records=[]
    for engine in ['geo','hot']:
        mesh=out/'new-scene'/engine/'scene.meshbin'
        dest=out/a.phase/engine;dest.mkdir(parents=True,exist_ok=True)
        exe=build/(engine+'_r2'+('.exe' if os.name=='nt' else ''))
        assets=ROOT/'environments/engines'/engine/'cybr-geo/examples/desert_hot_springs/assets'
        args=[str(exe),str(mesh),str(dest/'native'),'--w',str(a.width),'--h',str(a.height),'--spp',str(a.spp),'--water-spp',str(a.spp),'--depth','12','--threads','1','--seed','20261023','--indirect-clamp','0','--no-clouds','--sun','-0.8,0.4,0.28','--exposure','1.9','--grain',str(assets/'gravel_periodic.pgm'),'--relief',str(assets/'granular_relief.bin')]
        if engine=='geo': args+=['--scene','coast','--camera','2.1,-5.65,1.52','--target','-0.15,3.15,0.15','--fov','72','--no-steam']
        else: args+=['--view','hero']
        started=time.monotonic()
        with (dest/'native.log').open('w') as log:
            proc=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        record={'engine':engine,'returncode':proc.returncode,'seconds':time.monotonic()-started,'executable_sha256':sha(exe),'mesh_sha256':sha(mesh),'atlas_sha256':sha(Path(env['CYBR_SURFACE_ATLAS'])),'grain_sha256':sha(assets/'gravel_periodic.pgm'),'relief_sha256':sha(assets/'granular_relief.bin'),'command':[s.replace(str(ROOT)+os.sep,'').replace(os.sep,'/') for s in args],'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in dest.iterdir() if p.suffix not in ['.log','.json']}}
        records.append(record)
        (out/(a.phase+'-capture.json')).write_text(json.dumps(records,indent=2)+'\n')
        print(json.dumps(record),flush=True)
        if proc.returncode: raise SystemExit(proc.returncode)
if __name__=='__main__': main()
