"""Deterministic noise regression on known synthetic signals (not scene accuracy)."""
from pathlib import Path
import json,sys
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cybr-geo/examples/three_scenes'))
from noise_resolve import resolve,set_num_threads
set_num_threads(2)

def run():
    rng=np.random.default_rng(19503);h,w=128,192;y,x=np.mgrid[:h,:w]
    albedo=np.zeros((h,w,3),np.float32);albedo[:]=[.16,.10,.06]
    # Fine genuine one-pixel detail and a strong reflectance discontinuity.
    albedo*=(1+.13*((x+y)%2*2-1))[...,None]
    albedo[:,96:]*=np.array([1.5,2.,2.5],np.float32)
    truth=albedo*(.6+.25*x/w)[...,None]
    # Preserve a real geometrical/spectral albedo crack, not a noisy dark sample.
    albedo[:,42:44]*=.20;truth[:,42:44]*=.20
    guide=np.zeros((h,w,9),np.float32);guide[:,:,2]=1;guide[:,:,3:6]=albedo
    guide[:,:,6]=3;guide[:,:,8]=0
    sigma=.022;noisy=truth+rng.normal(0,sigma,truth.shape).astype(np.float32)
    guide[:,:,7]=sigma*sigma*(.2126**2+.7152**2+.0722**2)
    support=np.zeros((h,w,4),np.float32);support[:,:,0]=1
    expected=np.zeros((h,w),bool)
    for yy,xx in [(15,15),(34,61),(65,152),(100,32),(89,130)]:noisy[yy,xx]=20;expected[yy,xx]=1
    original=noisy.copy()
    clean,mask,audit=resolve(noisy,guide,support,measured_variance=True)
    mse0=float(np.mean((noisy-truth)**2));mse1=float(np.mean((clean-truth)**2))
    ordinary=~expected
    ordinary_mse0=float(np.mean((noisy[ordinary]-truth[ordinary])**2));ordinary_mse1=float(np.mean((clean[ordinary]-truth[ordinary])**2))
    contrast_ref=float((truth[:,44:46].mean()-truth[:,42:44].mean()))
    contrast=float((clean[:,44:46].mean()-clean[:,42:44].mean()))
    # Same radiance and material with alternating guide reliability. The two
    # filter representations must not cross-contaminate into bright/dark halos.
    hg,wg=32,48;yg,xg=np.mgrid[:hg,:wg]
    flat=np.full((hg,wg,3),.024,np.float32)
    gg=np.zeros((hg,wg,9),np.float32);gg[:,:,2]=1;gg[:,:,3:6]=.04;gg[:,:,6]=2
    ss=np.zeros((hg,wg,4),np.float32);ss[:,:,0]=1;ss[:,:,1]=np.where((xg//3+yg//3)%2==0,.20,.40)
    unhalo,_,_=resolve(flat,gg,ss,measured_variance=False)
    representation_error=float(np.max(np.abs(unhalo-flat)))
    report={'scope':'Known synthetic noise and detail regressions, not photographic quality',
        'raw_input_unchanged':bool(np.array_equal(original,noisy)),
        'finite_nonnegative_result':bool(np.isfinite(clean).all() and (clean>=0).all()),
        'injected_spikes':int(expected.sum()),'injected_spikes_detected':int((mask.astype(bool)&expected).sum()),
        'false_spike_replacements':int((mask.astype(bool)&~expected).sum()),
        'ordinary_noise_mse_before':ordinary_mse0,'ordinary_noise_mse_after':ordinary_mse1,
        'ordinary_noise_mse_reduction':1-ordinary_mse1/ordinary_mse0,
        'all_pixel_mse_before':mse0,'all_pixel_mse_after':mse1,
        'real_fine_crack_contrast_ratio':contrast/contrast_ref,
        'mean_rgb_error':(clean.mean((0,1))-truth.mean((0,1))).tolist(),
        'raw_noise_reinjection':False,'mixed_representation_max_radiance_error':representation_error,
        'mixed_representation_preserves_flat_radiance':representation_error<1e-6,'filter':audit}
    report['passed']=all([report['raw_input_unchanged'],report['finite_nonnegative_result'],
        report['injected_spikes_detected']==5,report['false_spike_replacements']==0,
        ordinary_mse1<ordinary_mse0*.3,.85<contrast/contrast_ref<1.15,representation_error<1e-6])
    folder=ROOT/'verification';folder.mkdir(exist_ok=True)
    (folder/'noise_regression.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    return report
if __name__=='__main__':
    if not run()['passed']:raise SystemExit(1)
