"""Regression for conservative radiance blending, not image-quality certification."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
from finish import preserve_opaque_residual

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('output/tests/filter_policy.json'));a=p.parse_args()
    rng=np.random.default_rng(83109)
    raw=rng.random((32,32,3),dtype=np.float32)*3
    filtered=rng.random((32,32,3),dtype=np.float32)*3
    material=np.zeros((32,32),dtype=np.float32);material[:8]=-1;material[24:]=5
    budgets=np.full((32,32),96,dtype=np.uint16);budgets[8:16]=256
    mixed,mask=preserve_opaque_residual(raw,filtered,material,budgets,96,256,.35)
    at_zero,_=preserve_opaque_residual(raw,filtered,material,budgets,96,256,0.)
    at_one,_=preserve_opaque_residual(raw,filtered,material,budgets,96,256,1.)
    equal,equal_mask=preserve_opaque_residual(raw,filtered,material,budgets,96,96,.35)
    checks={
        'zero_strength_returns_raw_opaque':bool(np.array_equal(at_zero[mask],raw[mask])),
        'one_strength_returns_filtered_everywhere':bool(np.array_equal(at_one,filtered)),
        'non_sediment_opaque_unchanged':bool(np.array_equal(mixed[24:],filtered[24:])),
        'sky_unchanged':bool(np.array_equal(mixed[:8],filtered[:8])),
        'primary_water_unchanged_despite_opaque_floor_guide':bool(np.array_equal(mixed[8:16],filtered[8:16])),
        'equal_budget_disables_unavailable_primary_classification':bool(not equal_mask.any() and np.array_equal(equal,filtered)),
        'convex_range_no_overshoot':bool(np.all(mixed>=np.minimum(raw,filtered)-1e-6) and np.all(mixed<=np.maximum(raw,filtered)+1e-6)),
        'finite_results':bool(np.isfinite(mixed).all()),
    }
    report={'scope':'Radiance blend endpoints, primary-water/sky exclusion and convexity; not denoising accuracy or photographic realism',
        'seed':83109,'pixels':1024,'opaque_pixels':int(mask.sum()),'opaque_filter_strength':.35,
        'postprocess_source_sha256':hashlib.sha256(Path(__file__).with_name('finish.py').read_bytes()).hexdigest(),
        'checks':checks,'passed':all(checks.values())}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
