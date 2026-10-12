from pathlib import Path
import sys,json,hashlib,numpy as np
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'src'))
from coupled_shoulder_ce import evaluate
out=Path(__file__).resolve().parent
s=np.load(out/'actual_shoulder.npz');h=np.load(R/'captures/av_integrated_road_outer_view/AH_FIELDS.npz');payload,report=evaluate(s['co'],s['tri'],h)
payload.update(source_vertex_ids=s['source_vertex_ids'],source_coordinates=s['co'],tri=s['tri'])
p=out/'payload.npz';assert not p.exists();np.savez_compressed(p,**payload)
report['payload_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();report['source']=json.loads((out/'actual_shoulder.json').read_text());(out/'payload.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
