"""Bounded static sorting of already retained original fines; no new transport."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import argparse
a=argparse.ArgumentParser();a.add_argument('--baseline',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args();D=Path(__file__).resolve().parent;B=args.baseline.resolve();OUT=args.out.resolve();OUT.mkdir(exist_ok=False);sys.path.insert(0,str(B/'runtime/src'))
from visible_shoulder_flow_ad import sample_field
job=json.loads((B/'job.json').read_text());ce=job['coupled_shoulder_ce'];hc=job['fixed_gravel_support_ci']
p=np.load(ce['payload']);h=np.load(hc['historical_fields']);e=np.load(D/'CURRENT_EVALUATED_FIELDS.npz')
assert hashlib.sha256(Path(ce['payload']).read_bytes()).hexdigest()==ce['payload_sha256']
xy=p['source_coordinates'][:,:2].astype(float);inside=(xy[:,0]>=h['x_m'][0])&(xy[:,0]<=h['x_m'][-1])&(xy[:,1]>=h['y_m'][0])&(xy[:,1]<=h['y_m'][-1]);prior=np.zeros_like(p['stock'],dtype=float);prior[inside]=sample_field(h['retained_deposit_by_class_m'],xy[inside],h['x_m'],h['y_m'])
stock=p['stock'].astype(float);removed=p['removed'].astype(float);dep=p['deposited'].astype(float);original=stock-prior
# CE serialized stock is float32; independently recomputed AH samples are float64.
error=float(original.min());assert error>=-2e-8,('Original/deposited basis mismatch',error)
negative=np.minimum(original,0);original=np.maximum(original,0);prior=stock-original
old_debit=np.minimum(prior,removed);original_debit=removed-old_debit;remain=original-original_debit
assert remain.min()>=-2e-8,('Original stock overdrawn',remain.min());roundoff=np.minimum(remain,0);remain=np.maximum(remain,0)
event=prior-old_debit+dep;final=stock-removed+dep;residual=remain+event-final;assert abs(residual).max()<2e-8
# Existing fine-area field supplies a historical grading/receiver tendency.
# Cap is a vertical partition INSIDE the current fine inventory and terrain;
# its complement remains in the mixed substrate. It adds no ground elevation.
coverage=np.clip(e['ap_fines'].astype(float),0,1)*p['gate'];cap=remain[:,0]*coverage;reserve=remain.copy();reserve[:,0]-=cap
assert reserve.min()>-2e-8 and np.all(cap<=remain[:,0]+1e-15)
area=p['area'].astype(float);r=dict(revision='DL static original-fine cap candidate',cap_bulk_volume_m3=float(cap@area),original_surviving_bulk_m3=(remain*area[:,None]).sum(0).tolist(),event_surviving_bulk_m3=(event*area[:,None]).sum(0).tolist(),complementary_mixed_reserve_bulk_m3=(reserve*area[:,None]).sum(0).tolist(),inventory_residual_m3=(residual*area[:,None]).sum(0).tolist(),maximum_float32_reconciliation_error_m=float(abs(residual).max()),roundoff_correction_original_bulk_m3=(-negative*area[:,None]).sum(0).tolist(),roundoff_correction_after_debit_m3=(-roundoff*area[:,None]).sum(0).tolist(),cap_max_m=float(cap.max()),area_cap_gt_1mm_m2=float(area[cap>.001].sum()),area_cap_gt_4mm_m2=float(area[cap>.004].sum()),source_fields=['ap_fines evaluated on original AP geometry','CE gate/remaining original class stock','AH old deposited classes, debited first by CE removal'],model='Authored static stratigraphy inside the already-retained current terrain. Spatially varying original fine stock is partitioned into an effective surface cap using existing historical fine-area coverage. Pre-existing clasts descend relative to that cap; recent finite deposited representatives keep their source roles. No new mass, terrain elevation, transport, rainfall or measured chronology.',optical_interpretation='Original cap coverage is bounded ap_fines times current CE gate and finite-thickness saturation. It joins the existing event fine closure by bounded union; no independent BW overcoat is restored.',limits=['Mean-column support depth and area-fraction optics are authored approximations, not resolved grain packing or measured stratigraphy.','Original intrinsic embedding remains; this is a static support interpretation rather than an inferred weathering age.','Old original/matrix and event populations are separated on the same CE vertex basis before interpolating.','Roundoff corrections are reported explicitly; strict20nm per-class tolerance only covers float32 stock serialization.'])
O=OUT/'STATIC_FINE_LAYER.npz';assert not O.exists();np.savez_compressed(O,co=e['co'],tri=e['tri'],source_vertex_ids=e['source_vertex_ids'],cap_m=cap.astype('f4'),cap_area_fraction=coverage.astype('f4'),original_surviving=remain.astype('f4'),original_mixed_reserve=reserve.astype('f4'),surviving_event=event.astype('f4'),historical_matrix=e['ak_historical_matrix'],historical_compaction=e['ak_historical_compaction'],gate=p['gate'],area=p['area'])
r['output_sha256']=hashlib.sha256(O.read_bytes()).hexdigest();(OUT/'STATIC_FINE_LAYER.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
