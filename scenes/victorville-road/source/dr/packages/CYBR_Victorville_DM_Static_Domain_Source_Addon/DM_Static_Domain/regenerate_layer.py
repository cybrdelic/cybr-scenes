"""DM static-cap reassignment: exact prior total, continuous authored AP support.
No event transport or terrain changes. The former per-cell static allocation is
replaced, not claimed recovered; original mixed reserves remain at their cells.
"""
from pathlib import Path
import numpy as np,json,hashlib
import argparse
p=argparse.ArgumentParser();p.add_argument('--dl-layer',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a0=p.parse_args();src=a0.dl_layer.resolve();D=a0.out.resolve();D.mkdir(parents=True,exist_ok=True);f=np.load(src);data={k:f[k] for k in f.files};a=f['area'].astype(float);w=f['cap_area_fraction'].astype(float);oldcap=f['cap_m'].astype(float);reserve=f['original_mixed_reserve'].astype(float);oldoriginal=f['original_surviving'].astype(float)
# Reconcile serialization at the cap + reserve basis once, retain its exact
# scalar bulk volume rather than pretending .f32 subtraction is byte-exact.
oldbasis=reserve.copy();oldbasis[:,0]+=oldcap
bulk=oldcap@a;depth=float(bulk/(w@a));cap=depth*w;neworiginal=reserve.copy();neworiginal[:,0]+=cap
closure=(neworiginal-oldbasis)*a[:,None];assert np.max(abs(closure.sum(0)))<1e-10
assert np.all(neworiginal>=0) and np.array_equal(f['surviving_event'],data['surviving_event']);assert cap.max()<.013
# Float64 owns the exact accounting. Geometry continues Blender float32 as before.
data['cap_m']=cap;data['original_surviving']=neworiginal;data['original_mixed_reserve']=reserve;data['optical_layer_thickness_m']=np.full(len(cap),depth);data['previous_original_surviving']=oldoriginal;data['previous_cap_m']=oldcap
out=D/'STATIC_FINE_LAYER.npz';assert not out.exists();np.savez_compressed(out,**data)
h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();report={'revision':'DM continuous static cap allocation, unchanged global class inventories','source_sha256':h(src),'output_sha256':h(out),'cap_depth_when_fully_covered_m':depth,'cap_bulk_volume_before_m3':float(bulk),'cap_bulk_volume_after_m3':float(cap@a),'original_class_bulk_before_m3':(oldbasis*a[:,None]).sum(0).tolist(),'original_class_bulk_after_m3':(neworiginal*a[:,None]).sum(0).tolist(),'class_volume_residual_m3':closure.sum(0).tolist(),'source_f32_basis_reconciliation_max_m':float(abs(oldbasis-oldoriginal).max()),'source_f32_basis_reconciliation_bulk_m3':((oldbasis-oldoriginal)*a[:,None]).sum(0).tolist(),'geographic_static_reassignment_half_L1_m3':float(.5*(abs(cap-oldcap)@a)),'old_event_and_mixed_reserve_arrays_unchanged':True,'cap_max_m':float(cap.max()),'added_new_geology_inventory':False,'new_transport_or_terrain':False,'model':'Replace DL static cap distribution with the same total fine bulk spread using its exact continuous retained AP area field; retain every mixed reserve and event cell. This is authored static initial-condition reassignment, not a transport trajectory or recovered stratigraphy.','optics':'Same AP fractional coverage with a spatially constant fully-covered layer thickness; mean-column geometry depth equals depth times coverage. No image blending or scatter changes.','limits':['Per-vertex original fine allocation changes; only original class totals, mixed reserves and events are fixed.','Existing CE terrain/erosion and matrix fields remain; this isolates the static cap source-domain correction.','A mean-column support and fractional-coverage model, not resolved packing.','Input float32 partition is reconciled explicitly at its cap-plus-reserve basis.']};(D/'STATIC_FINE_LAYER.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
