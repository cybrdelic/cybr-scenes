from pathlib import Path
import importlib.util,sys,json
import numpy as np
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
root=args.out;root.mkdir(parents=True,exist_ok=True)
src=Path(__file__).resolve().parent;sys.path.insert(0,str(src))
import build_scene as new
spec=importlib.util.spec_from_file_location('old',src/'build_scene_before_continuity_fix.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
a=np.linspace(0,2*np.pi,1024,endpoint=False);cases=[]
for i,(cx,cy,rx,ry,*_) in enumerate(new.POOLS):
 ux=np.cos(a)*rx;uy=np.sin(a)*ry
 lo=np.full_like(a,.55);hi=np.full_like(a,1.55)
 for _ in range(48):
  r=(lo+hi)/2;q=new.poolq(cx+r*ux,cy+r*uy,i)
  lo=np.where(q<1,r,lo);hi=np.where(q>=1,r,hi)
 r=(lo+hi)/2;scale=np.hypot(ux,uy)
 deltas={}
 for e in [.0001,.00001,.000001]:
  x0=cx+(r-e/scale)*ux;y0=cy+(r-e/scale)*uy
  x1=cx+(r+e/scale)*ux;y1=cy+(r+e/scale)*uy
  deltas[str(e)]={'old_max_jump_m':float(np.abs(old.height(x1,y1)-old.height(x0,y0)).max()),'new_max_difference_m':float(np.abs(new.height(x1,y1)-new.height(x0,y0)).max())}
 cases.append({'pool':i,'radial_samples':len(a),'differences':deltas})
passed=all(c['differences']['1e-06']['new_max_difference_m']<.00001 for c in cases)
report={'test':'Two-sided radial terrain continuity at bank boundary','passed':passed,'cases':cases,'visual_realism_certified':False}
(root/'shoreline_continuity.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
assert passed
