"""Persist component-filter scope and all non-temporary source/output evidence."""
import json,sys,hashlib
from pathlib import Path
from capture_modes import capture_mode,final_image,component_filter_policy
from transport_components import LIGHT_PASSES

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def create(report_path):
 r=json.loads(Path(report_path).read_text());j=r['job'];assert capture_mode(j)=='component-recombined' and r['engine']=='CYCLES';policy=component_filter_policy(j);both=policy=='filter_both';raw=Path(j['output']);out=final_image(j);g=raw.parent/(raw.stem+'_guides')/'components'
 c=json.loads((g/'component_receipt.json').read_text());assert c['output']==str(out) and c['output_sha256']==sha(out) and c['source_sha256']==sha(j['source'])==r['source_sha256'];assert c['identity_exact_float32'] and c['feature_contract']['valid'] and c['delta64_untouched'] and c['clipping'] is False
 assert c.get('component_filter_policy','retain_transmission')==policy and c['transmission_emission_untouched'] is (not both)
 if both:assert c.get('signed_transmission_terms_untouched') is True and c['signed_transmission_accounting']['signed_terms_untouched'] is True and c.get('both_components_filtered') is True and c['transmission_feature_contract']['valid'] and not c['transmission_feature_contract']['violations']
 assert set(r['transport_paths'])==set(LIGHT_PASSES)
 files=[raw,out,*map(Path,r['guide_paths']),*map(Path,r['transport_paths'].values()),g/'linear_component_accounting.npz',g/'denoised_remainder_linear.exr',g/'component_recombined_linear.exr',g/'export_receipt.json',g/'component_receipt.json',g/'identity_raw_passthrough.png',g/'REVIEW_retained_signal.png',g/'REVIEW_raw_remainder.png',g/'REVIEW_filtered_remainder.png']
 if both:files.extend([g/'denoised_transmission_linear.exr',g/'REVIEW_filtered_transmission.png'])
 assert not out.with_suffix('.png.json').exists(),'Refuse stale component receipt'
 r.update(capture_mode='component-recombined',component_filter_policy=policy,postprocess=('OIDN2.5.1 CPU RT high independently on positive transmission/emission and physical remainder; untouched signed transmission roundoff and float64 reconstruction residual' if both else 'OIDN2.5.1 CPU RT high on physical surface remainder only; untouched transmission/emission and explicit float64 reconstruction residual'),oidn_executed=True,raw_path=str(raw),component_path=str(out),image_path=str(out),noise_acceptance=False,quality_acceptance=False,requires_visual_detail_QA=True,raw_guides_retained=True,raw_hdr_retained=True,physical_lighting_evaluated=True,color_bridge_native_precision=c['native16_identity_roundtrip'],component_filter=c,files_sha256={str(p):sha(p) for p in files})
 out.with_suffix('.png.json').write_text(json.dumps(r,indent=2));print('COMPONENT_RECOMBINED_CANDIDATE',out)
if __name__=='__main__':create(sys.argv[1])
