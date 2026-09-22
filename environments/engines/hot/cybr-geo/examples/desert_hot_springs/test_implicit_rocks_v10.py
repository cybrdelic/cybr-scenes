"""Topology and concavity checks for the new local implicit-rock construction."""
from pathlib import Path
import argparse,json
import numpy as np
import trimesh
from implicit_rocks_v10 import implicit_rock

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
reports=[]
for i in [0,4,8]:
    seed=20260914+500+i
    v,f,n=implicit_rock(seed,112)
    m=trimesh.Trimesh(v,f,process=False)
    hull=float(m.convex_hull.volume);volume=float(m.volume)
    reports.append(dict(seed=seed,triangles=len(f),vertices=len(v),watertight=bool(m.is_watertight),winding_consistent=bool(m.is_winding_consistent),signed_volume=volume,convex_hull_volume=hull,volume_to_convex_hull=volume/hull,finite=bool(np.isfinite(v).all() and np.isfinite(n).all())))
result={'scope':'Three of the nine unplaced implicit rock templates: closed topology, winding and geometric non-convexity. Not scanned likeness, erosion validation, all placements or static support.','templates':reports,'passed':all(r['watertight'] and r['winding_consistent'] and r['signed_volume']>0 and r['finite'] and r['volume_to_convex_hull']<.99 for r in reports)}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if not result['passed']:raise SystemExit(1)
