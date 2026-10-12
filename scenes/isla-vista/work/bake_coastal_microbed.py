"""Reuse original CYBR mineral contacts with an explicit coastal finish estimate."""
from pathlib import Path
import sys,subprocess,json,numpy as np,hashlib
r=Path(__file__).resolve().parent.parent
from scene_io import write_pfm
source=r/'original/cybr-road-microbed';(source/'prototypes').mkdir(exist_ok=True);subprocess.run([sys.executable,str(source/'src/compacted_microbed.py')],check=True)
field=np.load(source/'prototypes/microbed.npz');height=field['height'];color=field['color'];target=np.array([.205,.188,.158]);ratio=target/color.mean(axis=(0,1),dtype=np.float64);adapted=color*ratio
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);native=(adapted*(M@np.ones(3)))@np.linalg.inv(M).T
assert native.min()>=0 and native.max()<1
# Slight linked contact roughness variation; the .84 matrix value comes from
# the original road diagnostic, while this continuous correlation is authored.
rough=np.clip(.84+.04*(1-height/max(float(height.max()),1e-9)),.82,.89)
out=r/'evidence/full-iv-materials';out.mkdir(exist_ok=True)
for name,a in [('coastal_soil_color_native',native),('coastal_soil_height_metres',np.repeat(height[:,:,None],3,axis=2)),('coastal_soil_roughness',np.repeat(rough[:,:,None],3,axis=2))]:write_pfm(out/(name+'.pfm'),a.astype('f4'))
report={'source':json.loads((source/'PROVENANCE.json').read_text()),'native_resolution':list(height.shape),'tile_m':float(field['side_m']),'height_range_m':[float(height.min()),float(height.max())],'estimated_mean_linear_rgb':target.tolist(),'linked_roughness_range':[float(rough.min()),float(rough.max())],'color_contract':'Source field is linear RGB; no sRGB decode. Explicit coastal gray-beige finish adaptation preserves per-contact phase variation, then fits native spectral controls. No per-image grading.','height_contract':'Unmodified full metric microbed contact height, differentiated once against actual surface UV derivatives. Broad terrain geometry/normals remain their own scale.','limits':'Compacted interstitial contact field; no loose-grain replacement or silhouette-displacement claim. Coastal pigment/mineral blend and correlated roughness are authored estimates. Source is retained CYBR road material construction, not a newly verified merged-catalogue coastal soil material.'}
(out/'COASTAL_SOIL_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('COASTAL_MICROBED',json.dumps(report),flush=True)
