from pathlib import Path
import sys,json
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor']:sys.path.insert(0,str(p))
from cybr_ucsb.ingest import ingest
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.roof_details import RoofBuilder
from cybr_ucsb.geometry import export_batched_glb
s=Sector(longitude=-119.8614,latitude=34.413,extent=2600);d=ingest(r/'data/full-iv-20261011',s);out=r/'evidence/full-iv-roofs';b=RoofBuilder(d,out,513);g,report=b.build();export_batched_glb(g,out/'sector.glb')
(out/'TAGGED_ROOFS.json').write_text(json.dumps({'count':len(b.roof_adaptations),'details':b.roof_adaptations},indent=2)+'\n');print('TAGGED_ROOFS',len(b.roof_adaptations),flush=True)
