"""Transport-separated, non-neural image finishing.

The renderer writes radiance, primary-water reflection and forced atmospheric
scattering separately. The remainder includes opaque-surface illumination and
water transmission. Each term is filtered with its own appropriate geometry
features, then recombined in scene-linear space. Raw inputs are never changed.
"""
from __future__ import annotations
import argparse, json, os, struct
from pathlib import Path
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, median_filter
from finish import read_pfm, display

LUMA=np.array([.2126,.7152,.0722],np.float32)

def read_component(stem:Path,suffix:str='')->np.ndarray:
    pfm=Path(str(stem)+suffix+'.pfm')
    if pfm.exists():return read_pfm(pfm)
    exr=Path(str(stem)+suffix+'_raw.exr')
    a=cv2.imread(str(exr),cv2.IMREAD_UNCHANGED)
    if a is None:raise FileNotFoundError(f'No PFM or raw EXR for {stem}{suffix}')
    return a[:,:,::-1].copy()


def read_guide(path:Path)->np.ndarray:
    with path.open('rb') as f:
        w,h=struct.unpack('<II',f.read(8))
        a=np.frombuffer(f.read(),'<f4').reshape(h,w,9).copy()
    if not np.isfinite(a).all():raise ValueError(f'Non-finite guide: {path}')
    return a

def save_exr(path:Path, rgb:np.ndarray)->None:
    if not cv2.imwrite(str(path),np.ascontiguousarray(rgb[:,:,::-1],dtype=np.float32)):
        raise RuntimeError(f'EXR write failed: {path}')

def atrous(rgb:np.ndarray, guide:np.ndarray, variance:np.ndarray,
           kind:str, primary:np.ndarray, iterations:int)->np.ndarray:
    """Variance-aware wavelet filter; no learned model or texture synthesis."""
    normals=guide[:,:,:3].copy();depth=np.maximum(guide[:,:,6],0)
    material=guide[:,:,8].copy();albedo=np.clip(guide[:,:,3:6],0,1)
    # Rough dielectric pixels must be guided by their first optical surface,
    # not a distant opaque object found by an achromatic perfect refraction ray.
    glass=(primary[:,:,8]==8)|(primary[:,:,8]==9)
    if kind=='base':
        normals=np.where(glass[:,:,None],primary[:,:,:3],normals)
        depth=np.where(glass,primary[:,:,6],depth)
        material=np.where(glass,primary[:,:,8],material)
        albedo=np.where(glass[:,:,None],1.,albedo)

    # Geometry normals, not high-frequency normal-map shading normals, guide
    # the filter. Reflections never inherit the floor's diffuse/albedo texture.
    water=primary[:,:,8]==6
    if kind=='base':
        relief=np.clip(albedo+.13,.13,.85)
        relief=np.where((water|glass)[:,:,None],1.,relief).astype(np.float32)
    else:relief=np.ones_like(rgb)
    data=np.maximum(rgb,0)/relief
    variance=np.maximum(variance,0).astype(np.float32)
    # Noise estimates are smoothed, not the beauty image or its actual geometry.
    variance=gaussian_filter(variance,1.1)
    hh,ww=depth.shape;kernel=np.array([1,4,6,4,1],np.float32)
    for iteration in range(iterations):
        step=1<<iteration;pad=step*2
        luminance=np.maximum(np.sum(data*relief*LUMA,axis=-1),0)
        loglum=np.log1p(luminance*4)
        # Symmetric log-domain uncertainty: the former center-only derivative
        # let an impulse reject its neighbors while contaminating theirs.
        # With spaced wavelet taps that produced a visible dotted-grid halo.
        logvariance=variance*(4/(1+luminance*4))**2
        arrays=[data,normals,depth,material,variance,loglum,albedo,logvariance]
        padded=[np.pad(v,((pad,pad),(pad,pad))+((0,0),)*(v.ndim-2),mode='edge') for v in arrays]
        total=np.zeros_like(data);weights=np.zeros((hh,ww),np.float32);next_variance=np.zeros_like(variance)
        for ky in range(-2,3):
            for kx in range(-2,3):
                sl=(slice(pad+ky*step,pad+ky*step+hh),slice(pad+kx*step,pad+kx*step+ww))
                c,n,d,m,var,ll,a,lv=(v[sl] for v in padded)
                if kind=='volume':
                    wn=1.;wd=np.exp(-np.abs(depth-d)/(.45+.10*np.maximum(depth,d)*step))
                    wm=np.where((material<0)==(m<0),1.,.03)
                else:
                    wn=np.exp(-np.maximum(0,1-np.sum(normals*n,axis=-1))*18.)
                    wd=np.exp(-np.abs(depth-d)/(.12+.018*np.maximum(depth,d)*step))
                    wm=np.where(material==m,1.,np.where((material<6)&(m<6)&(material>=0)&(m>=0),.6,.015))
                sigma=.065+2.6*np.sqrt(np.maximum(logvariance+lv,0))
                # Preserve genuine illumination boundaries; sample variance opens
                # the filter in poorly converged regions instead of freezing noise.
                wl=np.exp(-np.abs(loglum-ll)/np.maximum(.065,sigma))
                wa=np.exp(-np.mean(np.abs(albedo-a),axis=-1)*1.7) if kind=='base' else 1.
                w=kernel[ky+2]*kernel[kx+2]*wn*wd*wm*wl*wa
                total+=c*w[:,:,None];weights+=w;next_variance+=var*w*w
        den=np.maximum(weights,1.e-12)
        data=total/den[:,:,None]
        # Conservative floor avoids overconfidence from correlated wavelet taps.
        variance=np.maximum(next_variance/(den*den),variance*.30)
    return np.maximum(data*relief,0)

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument('stem',type=Path)
    ap.add_argument('--exposure',type=float);ap.add_argument('--no-outlier-control',action='store_true')
    args=ap.parse_args();stem=args.stem;meta=json.loads(stem.with_suffix('.json').read_text())
    rgb=read_component(stem);refl=read_component(stem,'_reflection');vol=read_component(stem,'_volume')
    if not all(np.isfinite(a).all() for a in [rgb,refl,vol]):raise ValueError('Non-finite raw transport output')
    base=rgb-refl-vol
    if stem.with_suffix('.guides').exists():
        guide=read_guide(stem.with_suffix('.guides'))
        rg=Path(str(stem)+'_reflection.guides');pg=Path(str(stem)+'_primary.guides')
        reflection_guide=read_guide(rg) if rg.exists() else guide.copy()
        primary=read_guide(pg) if pg.exists() else guide.copy()
    else:
        with np.load(str(stem)+'_guides.npz') as z:
            guide=z['surface'];reflection_guide=z['reflection'];primary=z['primary']
    exposure=meta['exposure'] if args.exposure is None else args.exposure;white=meta['film_white_rgb']
    # Lossless raw RGB and AOVs are exported before any viewing operation.
    for name,a in [('raw',rgb),('reflection_raw',refl),('volume_raw',vol),('base_raw',base)]:
        save_exr(Path(str(stem)+'_'+name+'.exr'),a)
    Image.fromarray(display(rgb,white,exposure)).save(str(stem)+'_unfiltered.png')
    variance=np.maximum(guide[:,:,7],0);controlled=0;factor=np.ones(rgb.shape[:2],np.float32)
    if not args.no_outlier_control:
        peak=np.maximum(rgb,0).max(-1);local=median_filter(peak,size=5,mode='reflect')
        lum=np.maximum(rgb@LUMA,1e-8);ceiling=np.maximum(local*8,local+.35)
        bad=(variance>.30*lum*lum)&(peak>ceiling)
        factor=np.where(bad,ceiling/np.maximum(peak,1e-8),1).astype(np.float32);controlled=int(bad.sum())
    variance*=factor*factor
    # Independent component filters share read-only guides. NumPy operations
    # release the GIL; this changes execution time, not filter arithmetic.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        fb=pool.submit(atrous,base*factor[:,:,None],guide,variance,'base',primary,3)
        fr=pool.submit(atrous,refl*factor[:,:,None],reflection_guide,variance,'reflection',primary,4)
        fv=pool.submit(atrous,vol*factor[:,:,None],primary,variance,'volume',primary,5)
        base=fb.result();reflection=fr.result();volume=fv.result()
    out=base+reflection+volume
    save_exr(Path(str(stem)+'_denoised.exr'),out)
    Image.fromarray(display(out,white,exposure)).save(str(stem)+'.png')
    for name,a in [('reflection',reflection),('volume',volume),('transmission_and_surfaces',base)]:
        Image.fromarray(display(a,white,exposure)).save(str(stem)+'_'+name+'.png')
    # Guides and counts are included for independent reconstruction/inspection.
    np.savez_compressed(str(stem)+'_guides.npz',surface=guide,reflection=reflection_guide,primary=primary)
    countfile=stem.with_suffix('.samples');stats={};counts=None
    if countfile.exists():
        with countfile.open('rb') as f:
            w,h=struct.unpack('<II',f.read(8));counts=np.frombuffer(f.read(),'<u4').reshape(h,w)
    elif Path(str(stem)+'_sample_counts.npy').exists():
        counts=np.load(str(stem)+'_sample_counts.npy',allow_pickle=False)
    if counts is not None:
        if counts.shape != rgb.shape[:2] or np.any(counts < 1):
            raise ValueError('Sample-count dimensions or values are invalid')
        values,freq=np.unique(counts,return_counts=True)
        stats={'minimum':int(counts.min()),'mean':float(counts.mean()),'maximum':int(counts.max()),'camera_samples_total':int(counts.sum()),'histogram':{str(int(v)):int(n) for v,n in zip(values,freq)},'allocation':'deterministic primary-material/depth allocation; no noisy stopping rule'}
        np.save(str(stem)+'_sample_counts.npy',counts)
    meta['sampling_v3']={'sampler':'per-pixel digital shift over linearly scrambled 1024-dimensional Sobol nets','water_camera_interface':'both Fresnel reflection and transmission evaluated','quartz_bsdf':'GGX visible-normal dielectric with Fresnel reflection/transmission, matching PDF, spectral index and direct sun/sky NEE','water_sky_nee':'actual triangle interface, Snell refraction, Fresnel/absorption/scattering transmittance and MIS','primary_haze':'forced first collision, exact homogeneous transmittance, full continuation',**stats}
    meta['finishing']={'method':'symmetric log-variance, first-interface-aware component wavelet filtering; non-neural','iterations':{'base':3,'reflection':4,'volume':5},'raw_modified':False,'outlier_control':{'enabled':not args.no_outlier_control,'affected_pixels':controlled,'biased_viewing_regularization':True,'peak_ratio':8,'absolute_margin':.35},'display_transform':'ACES fit / exact sRGB','exposure':exposure,'image_generation':False,'neural_denoiser':False}
    meta['finite_raw']=True;meta['aov_reconstruction_max_abs_error']=float(np.max(np.abs(rgb-(rgb-refl-vol+refl+vol))))
    stem.with_suffix('.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps({'finished':str(stem),'sampling':stats,'outliers':controlled},indent=2),flush=True)

if __name__=='__main__':main()
