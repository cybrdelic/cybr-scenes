"""Filter symmetry/constant-field checks, not a scene convergence benchmark."""
from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from finish_v3 import atrous
r=np.random.default_rng(71822);a=np.exp(r.uniform(-9,8,20000));b=np.exp(r.uniform(-9,8,20000));va=np.exp(r.uniform(-12,17,20000));vb=np.exp(r.uniform(-12,17,20000))
difference=np.abs(np.log1p(4*a)-np.log1p(4*b))
old_sigma_ab=.055+2.3*np.sqrt(va+vb)*4/(1+4*a)
old_sigma_ba=.055+2.3*np.sqrt(va+vb)*4/(1+4*b)
old_delta=float(np.max(np.abs(np.exp(-difference/old_sigma_ab)-np.exp(-difference/old_sigma_ba))))
new_sigma_ab=.065+2.6*np.sqrt(va*(4/(1+4*a))**2+vb*(4/(1+4*b))**2)
new_sigma_ba=.065+2.6*np.sqrt(vb*(4/(1+4*b))**2+va*(4/(1+4*a))**2)
new_delta=float(np.max(np.abs(np.exp(-difference/new_sigma_ab)-np.exp(-difference/new_sigma_ba))))
g=np.zeros((19,23,9),dtype='f4');g[:,:,2]=1;g[:,:,3:6]=.3;g[:,:,6]=3;g[:,:,8]=0
im=np.full((19,23,3),.41,dtype='f4');var=np.full((19,23),.02,dtype='f4')
out=atrous(im,g,var,'base',g,3)
error=float(np.max(np.abs(out-im)))
report={'weight_pairs_tested':len(a),'legacy_max_directional_weight_difference':old_delta,'new_max_directional_weight_difference':new_delta,'constant_surface_max_absolute_error':error,'outlier_control_used':False,'passed':bool(new_delta<1e-12 and error<2e-6),'scope':'Pairwise luminance-weight symmetry and preservation of a constant field; not a noise benchmark'}
(ROOT/'verification_v3/filter_test.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
assert report['passed']
