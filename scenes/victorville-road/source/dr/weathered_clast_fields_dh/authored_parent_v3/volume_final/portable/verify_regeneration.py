from pathlib import Path
import numpy as np,json,hashlib
ROOT=Path(__file__).resolve().parent;FINAL=ROOT.parent;OUT=ROOT/'verification_output'
rows=[]
for name in ['prototype_146.npz','as_prototype_039.npz']:
 a=np.load(FINAL/'specimens'/name);b=np.load(OUT/name);assert set(a.files)==set(b.files)
 for key in a.files:assert np.array_equal(a[key],b[key]),(name,key,float(np.max(abs(a[key]-b[key]))))
 rows.append({'specimen':name,'all_arrays_byte_equal':True,'coordinate_sha256':hashlib.sha256(b['v'].tobytes()).hexdigest()})
(ROOT/'REGENERATION_VERIFIED.json').write_text(json.dumps({'passed':True,'results':rows,'original_coarse_audit_folder_used':False,'road_scene_loaded':False},indent=2)+'\n')
print('PORTABLE_REGENERATION_VERIFIED',flush=True)
