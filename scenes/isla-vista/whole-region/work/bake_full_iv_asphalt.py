"""Bounded native-resolution evaluation of retained CYBR MATERIALS asphalt."""
from pathlib import Path
import sys,json,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(r/'original/cybr-material-asphalt'))
sys.path.insert(0,str(r/'whole-iv-vendor'))
from reference_construction import construction
from cybr_terrain.materials import write_pfm
spec=json.loads((r/'original/cybr-material-asphalt/material.json').read_text())
n=1024;fields,report=construction(spec,n)
out=r/'evidence/full-iv-materials';out.mkdir(exist_ok=True)
rgb=fields['BaseColor'];linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
# Estimated weathered coastal asphalt mean; preserve correlated aggregate
# pigment. This is an explicit finish adaptation, not photographed local data.
target=np.array([.052,.055,.054]);mean=linear.mean(axis=(0,1),dtype=np.float64)
linear=np.minimum(.9,linear*(target/mean))
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
M=np.asarray(day['native_basis_to_linear_rgb']);white=M@np.ones(3);controls=(linear*white)@np.linalg.inv(M).T
assert controls.min()>=0
height=(fields['Height']-.5)*spec['height_scale_m']
write_pfm(out/'asphalt_color_native.pfm',controls.astype('f4'))
write_pfm(out/'asphalt_height_metres.pfm',np.repeat(height[:,:,None],3,axis=2))
write_pfm(out/'asphalt_roughness.pfm',np.repeat(fields['Roughness'][:,:,None],3,axis=2))
report.update({'source_commit':'12848c82f60bc58fa88640545868009b90298b32','source':'asphalt-reviewed-20261009/source/reference_construction.py','resolution':[n,n],'tile_m':spec['tile_m'],'mean_linear_rgb':target.tolist(),'native_evaluation':True,'upscaled':False,'production_4k_or_selected_slab_parity':False,'normal_transport':'Full physical scalar height differentiated in actual reciprocal UV basis; no object-normal image reused as a tangent residual. No microdisplacement silhouette claim.','height_range_m':[float(height.min()),float(height.max())],'color_contract':'sRGB decoded once, mean exterior finish adapted explicitly, fitted to native three-control reflectance basis','input_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (r/'original/cybr-material-asphalt').glob('*') if p.is_file()}})
(out/'ASPHALT_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
