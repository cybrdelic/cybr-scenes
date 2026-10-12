"""Public reproducible lagoon entrypoint, using the separate CYBR LIGHT package."""
from pathlib import Path
import argparse,hashlib,json,runpy,sys
ROOT=Path(__file__).resolve().parent

def runtime_contract():
    import cybrlight.scene_compat.runtime as runtime
    location=Path(runtime.__file__).parent
    document=json.loads((location/'DEPENDENCY_MANIFEST.json').read_text())
    contract=json.loads((ROOT/'LIGHT_DEPENDENCY.json').read_text())
    if document['executed_source_hash']!=contract['executed_source_hash']:raise RuntimeError('Unexpected LIGHT compatibility runtime source')
    for name,expected in document['files'].items():
        data=(location/name).read_bytes()
        if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:raise RuntimeError('LIGHT source manifest mismatch: '+name)
    return {'module':'cybrlight.scene_compat','checked_files':len(document['files']),'executed_source_hash':document['executed_source_hash']}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','materials','build','capture','daylight-fixture']);p.add_argument('--width',type=int,default=1000);p.add_argument('--spp',type=int,default=32);p.add_argument('--view',choices=['basin','lagoon-context'],default='basin');a=p.parse_args()
    from public_inputs import resolve
    resolve(ROOT,False);print('LIGHT_DEPENDENCY',json.dumps(runtime_contract()),flush=True)
    if a.action=='verify':return
    out=ROOT/'evidence/lagoon-restoration-v11b';out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'work'))
    if a.action=='daylight-fixture':
        runpy.run_path(str(ROOT/'work/correct_lagoon_daylight_v11.py'),run_name='__main__');return
    sys.argv=[str(ROOT/'work/rebuild_lagoon_v11b.py'),a.action,'--width',str(a.width),'--spp',str(a.spp),'--view',a.view]
    runpy.run_path(sys.argv[0],run_name='__main__')

if __name__=='__main__':main()
