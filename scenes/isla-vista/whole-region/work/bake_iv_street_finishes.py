"""Metric CYBR catalogue lime plaster and area-integrated street linen.

The original source functions are pinned and byte-verified separately. This
adapts their fields to native spectra; it is not selected Blender-slab parity.
"""
from pathlib import Path
import hashlib,json,sys
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'geo-deps'),str(r/'original/cybr-material-finishes/source'),str(r/'whole-iv-vendor')]
import numpy as np
from scipy.ndimage import gaussian_filter
from generate_materials import plaster,linen
from cybr_terrain.materials import write_pfm
out=r/'evidence/full-iv-street-finishes';out.mkdir(exist_ok=True)
n=512;x=((np.arange(n)+.5)/n)[None,:];y=x.T
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
M=np.asarray(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inverse=np.linalg.inv(M)
def linear(rgb):return np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
def native(rgb):return np.maximum(0,(rgb*white)@inverse.T)
rgb,h,rough,ao,metal,wear=plaster(x,y,n)
linear_rgb=linear(rgb);variation=linear_rgb/linear_rgb.mean(axis=(0,1))
for name,mean in [('6570_tan_stucco',(.47,.405,.31)),('6574_cream_stucco',(.52,.47,.38)),('6584_gray_stucco',(.34,.355,.335)),('6574_panel_infill',(.56,.40,.31))]:
 write_pfm(out/(name+'_native.pfm'),native(np.minimum(.95,variation*mean)))
height=(np.clip(gaussian_filter(h,.35,mode='wrap'),0,1)-.5)*.002
write_pfm(out/'lime_height_metres.pfm',np.repeat(height[:,:,None],3,axis=2))
write_pfm(out/'lime_roughness.pfm',np.repeat(rough[:,:,None],3,axis=2))
lime_roughness_range=[float(rough.min()),float(rough.max())]
rgb,h,rough,ao,metal,wear,opacity=linen(x,y,n)
# A street pixel covers many 0.708 mm yarn pitches. Integrate source yarn
# reflectance and occupancy separately; never enlarge the weave to show it.
occupancy=float(opacity.mean());occupied_rgb=(linear(rgb)*opacity[:,:,None]).sum(axis=(0,1))/opacity.sum()
record={'source_commit':'12848c82f60bc58fa88640545868009b90298b32','source_receipt':'original/cybr-material-finishes/SOURCE_RECEIPT.json','resolution':[n,n],
 'lime':{'tile_m':.65,'height_scale_m':.002,'height_range_m':[float(height.min()),float(height.max())],'uv_chart_m_per_unit':1.25,'texture_frequency':1.25/.65,'roughness_range':lime_roughness_range,'color':'Original correlated field; prior explicitly estimated building pigment means retained. sRGB decoded once, then native spectral-control fit. AO is not baked into pigment.'},
 'linen':{'tile_m':.085,'yarn_pitch_m':.085/120,'source_mean_coverage':occupancy,'occupied_mean_linear_rgb':occupied_rgb.tolist(),'native_reflectance_controls':native(occupied_rgb).tolist(),'mean_roughness':float(rough.mean()),'representation':'Source-integrated yarn occupancy and color on actual pleated cloth geometry. Native Lambertian reflection/transmission mixture, authored 0.18 diffuse-transmission fraction and no resolved weave bump at this street LOD. No native sheen equivalence claim.'},
 'qualification':'Original CYBR catalogue function reuse and metric field conversion; selected material preview parity has not been established.'}
record['outputs']={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.glob('*.pfm')}
(out/'FINISH_RECEIPT.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
