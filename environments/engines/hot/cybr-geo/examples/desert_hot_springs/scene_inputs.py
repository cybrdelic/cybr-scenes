"""Fingerprint recipe inputs before accepting an existing geometric scene."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def fingerprint(seed:int)->dict:
    paths=[HERE/name for name in ('build_scene.py','build_scene_v4.py','v8_landforms.py','v9_landforms.py','v10_landforms.py','v11_landforms.py','assets/granular_relief.npy','assets/granular_relief.bin','implicit_rocks_v10.py','contour_water.py','broken_shelves_v9.py','fluvial_detail_v9.py','assets/ripple_modes.json')]
    paths+=sorted((REPO/'src/cybrgeo').glob('*.py'))
    files={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    payload={'schema':'cybr-geo/scene-inputs/1','scene_seed':seed,'files':files}
    payload['fingerprint']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return payload

def current_scene_matches(out:Path,seed:int)->bool:
    path=out/'scene_inputs.json'
    if not path.is_file():return False
    try:
        saved=json.loads(path.read_text())
    except (OSError,ValueError):return False
    return saved.get('fingerprint')==fingerprint(seed)['fingerprint'] and (out/'scene.meshbin').is_file() and (out/'scene/meshes.npz').is_file()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed',type=int,default=20260914)
    a=p.parse_args()
    if not (a.out/'scene.meshbin').is_file():p.error('No completed scene to record')
    # This command is called only immediately after a successful scene build.
    report=fingerprint(a.seed)
    (a.out/'scene_inputs.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['fingerprint'])
