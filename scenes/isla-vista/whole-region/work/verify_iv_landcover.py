"""Check the serialized regional cover, including float32 positions."""
from pathlib import Path
import sys,json,struct,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'whole-iv-vendor']:sys.path.insert(0,str(p))
from iv_shared_ground import SharedGround
out=r/'evidence/full-iv-landcover-contact';ground=SharedGround(r/'evidence/full-iv-roofs/measured-terrain-state.npz');errors=[];tested=0
with (out/'landcover.clm').open('rb') as f:
 magic,total,packets=struct.unpack('<4sQI',f.read(16));assert magic==b'CLM1'
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',f.read(4));v=np.frombuffer(f.read(nv*44),'<f4').reshape(nv,11).astype(float);f.read(nt*11);errors.append(float(np.max(abs(v[:,2]-ground.height(v[:,:2])-.018))));tested+=nv
 assert not f.read(1)
maximum=max(errors);assert maximum<.0001,maximum
report={'serialized_triangles':total,'serialized_vertices_checked':tested,'maximum_error_from18mm_TIN_contact_m':maximum,'passed':True,'method':'Every actual float32 CLM vertex compared with exact two-triangle interpolation of retained visible terrain. Tolerance0.1mm allows coordinate quantization; no terrain refit.'}
(out/'CONTACT_VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
