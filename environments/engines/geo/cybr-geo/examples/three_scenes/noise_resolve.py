"""R5 variance-aware, non-neural reconstruction of native CYBR GEO radiance.

No image synthesis, upscaling, exposure change, or raw-noise blend. This is a
biased spatial display reconstruction, not an unbiased/converged reference.
Raw PFM/EXR files are read-only. Optional guide-only passes use the exact scene
and camera. Their variance is NEVER mistaken for path-sample variance.

The spatial wavelet/variance idea is related to Schied et al. (HPG 2017), but
this implementation has no temporal reprojection and does not claim to be SVGF.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault('OPENCV_IO_ENABLE_OPENEXR', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import cv2
import numpy as np
from scipy.ndimage import median_filter, uniform_filter, gaussian_filter
from numba import njit, prange, set_num_threads
from PIL import Image
from finish import read_pfm, encode, camera_white


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def read_linear(path: Path) -> np.ndarray:
    if path.suffix.lower()=='.pfm':a=read_pfm(path)
    elif path.suffix.lower()=='.exr':
        a=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
        if a is None or a.ndim!=3 or a.shape[2]!=3:raise ValueError('Expected RGB EXR')
        a=a[:,:,::-1].copy()
    else:raise ValueError('Noise reconstruction requires a scene-linear PFM or EXR, not an encoded PNG')
    a=np.ascontiguousarray(a,dtype=np.float32)
    if not np.isfinite(a).all():raise ValueError('Nonfinite input: repair transport before filtering')
    return a


def read_buffer(path: Path, channels: int, shape: tuple[int,int]) -> np.ndarray:
    with path.open('rb') as f:
        size=np.fromfile(f,'<u4',2)
        if tuple(size)!=(shape[1],shape[0]):raise ValueError(f'Dimensions disagree: {path}')
        a=np.fromfile(f,'<f4')
    if a.size!=shape[0]*shape[1]*channels:raise ValueError(f'Truncated auxiliary buffer: {path}')
    a=a.reshape(*shape,channels)
    if not np.isfinite(a).all():raise ValueError(f'Nonfinite guide: {path}')
    return np.ascontiguousarray(a)


@njit(parallel=True,cache=True)
def isolated_outliers(rgb, normal, depth, material, coverage):
    """Conservative one-pixel HDR firefly suppression, display only.

    At least 12 geometry-compatible neighbours and an 8x local luminance ratio
    are required. Thin coverage boundaries, multi-pixel highlights and dark
    pixels are not replaced. The exact replacement mask is returned.
    """
    h,w,_=rgb.shape;out=rgb.copy();mask=np.zeros((h,w),np.uint8)
    for y in prange(2,h-2):
        for x in range(2,w-2):
            if coverage[y,x]<.94:continue
            center=.2126*rgb[y,x,0]+.7152*rgb[y,x,1]+.0722*rgb[y,x,2]
            if center<.20:continue
            vals=np.empty(24,np.float32);col=np.empty((24,3),np.float32);n=0
            for dy in range(-2,3):
                for dx in range(-2,3):
                    if dx==0 and dy==0:continue
                    yy=y+dy;xx=x+dx
                    if material[yy,xx]!=material[y,x] or coverage[yy,xx]<.90:continue
                    if abs(depth[yy,xx]-depth[y,x])>.025+.04*max(depth[y,x],1.):continue
                    nd=0.
                    for c in range(3):nd+=normal[y,x,c]*normal[yy,xx,c]
                    if material[y,x]>=0 and nd<.65:continue
                    for c in range(3):col[n,c]=rgb[yy,xx,c]
                    vals[n]=.2126*col[n,0]+.7152*col[n,1]+.0722*col[n,2];n+=1
            if n<12:continue
            med=np.median(vals[:n]);mad=np.median(np.abs(vals[:n]-med))*1.4826
            # Keep single-pixel high contrast that is not an extreme radiance spike.
            if center<=max(.20,8*med,med+12*max(mad,.002)):continue
            high=0
            for i in range(n):
                if vals[i]>.3*center:high+=1
            if high:continue
            for c in range(3):out[y,x,c]=np.median(col[:n,c])
            mask[y,x]=1
    return out,mask


@njit(parallel=True,cache=True)
def wavelet_pass(rgb, normal, albedo, depth, variance, material, support, demod, step, strength):
    h,w,_=rgb.shape;out=np.empty_like(rgb);vout=np.empty_like(variance)
    taps=np.array([1.,4.,6.,4.,1.],np.float32)
    for y in prange(h):
        for x in range(w):
            centerY=.2126*rgb[y,x,0]+.7152*rgb[y,x,1]+.0722*rgb[y,x,2]
            result=np.zeros(3,np.float32);total=0.;varsum=0.
            dp=depth[y,x];mat=material[y,x];cov=support[y,x,0]
            water=mat==6 or mat==7;sky=mat<0
            # One-sided least-jump depth derivatives avoid widening silhouette gates.
            gx=0.;gy=0.
            if x>0 and x+1<w:
                a=dp-depth[y,x-1];b=depth[y,x+1]-dp;gx=a if abs(a)<abs(b) else b
            if y>0 and y+1<h:
                a=dp-depth[y-1,x];b=depth[y+1,x]-dp;gy=a if abs(a)<abs(b) else b
            for j in range(-2,3):
                yy=y+j*step
                if yy<0 or yy>=h:continue
                for i in range(-2,3):
                    xx=x+i*step
                    if xx<0 or xx>=w:continue
                    mq=material[yy,xx]
                    if mq!=mat or demod[yy,xx]!=demod[y,x]:continue
                    # Never average radiance and demodulated irradiance. Mixed
                    # representations otherwise create bright edge halos.
                    weight=taps[j+2]*taps[i+2]
                    if not sky:
                        normalDot=0.;ad=0.;amag=0.
                        for c in range(3):
                            normalDot+=normal[y,x,c]*normal[yy,xx,c]
                            dd=albedo[y,x,c]-albedo[yy,xx,c];ad+=dd*dd
                            amag+=albedo[y,x,c]*albedo[y,x,c]+albedo[yy,xx,c]*albedo[yy,xx,c]
                        reliability=max(.12,1-3*(support[y,x,1]+support[yy,xx,1]))
                        # Coherent mesh normals preserve shape; high-frequency bump
                        # normals are intentionally not used as no-filter barriers.
                        weight*=max(0.,normalDot)**(8*reliability)
                        scale=.0015+.12*amag
                        if water:scale=1.
                        weight*=np.exp(-ad/scale)
                        de=abs((depth[yy,xx]-dp)-gx*i*step-gy*j*step)
                        dz=.012+.006*min(dp,depth[yy,xx])+2*(support[y,x,2]+support[yy,xx,2])
                        weight*=np.exp(-de/max(dz,.005))
                        weight*=np.exp(-8*abs(cov-support[yy,xx,0]))
                    neighborY=.2126*rgb[yy,xx,0]+.7152*rgb[yy,xx,1]+.0722*rgb[yy,xx,2]
                    diff=centerY-neighborY;vv=variance[y,x]+variance[yy,xx]
                    # Statistical range gate. Noise is subtracted from the squared
                    # distance; it does not get protected as surface contrast.
                    signal=max(0.,diff*diff-vv)
                    floor=.0005+.012*max(abs(centerY),abs(neighborY))
                    weight*=np.exp(-signal/(strength*strength*vv+floor*floor))
                    total+=weight;varsum+=weight*weight*variance[yy,xx]
                    for c in range(3):result[c]+=rgb[yy,xx,c]*weight
            for c in range(3):out[y,x,c]=result[c]/max(total,1e-20)
            vout[y,x]=varsum/max(total*total,1e-20)
    return out,vout


def spatial_noise_variance(signal: np.ndarray) -> np.ndarray:
    """Robust spatial estimate, not fabricated per-path moments."""
    lum=signal@np.array([.2126,.7152,.0722],np.float32)
    med=median_filter(lum,size=3,mode='reflect')
    residual=np.abs(lum-med)
    sigma=median_filter(residual,size=7,mode='reflect')*np.float32(1.65)
    # Gently pool noise estimates so a noisy pixel cannot self-protect using a
    # zero local estimate; local material edges are still gated by the wavelet.
    variance=gaussian_filter(sigma*sigma,.8)
    # A robust median alone underestimates rare high-leverage samples and can
    # protect them as edges. Include the unexplained one-pixel residual after
    # albedo demodulation. This is explicitly a display-only noise model, not
    # a new claim about path-sample statistics.
    variance=np.maximum(variance,.35*(lum-med)**2)
    return np.maximum(variance,np.float32(2e-8)).astype(np.float32)


def resolve(rgb, guide, support, *, measured_variance: bool, passes=3, strength=2.5):
    if not 1<=passes<=4:raise ValueError('passes must be 1..4')
    if strength<=0 or not np.isfinite(strength):raise ValueError('Invalid strength')
    start=time.monotonic();shape=rgb.shape[:2]
    m=guide[:,:,8].astype(np.int32);normal=guide[:,:,:3].copy();albedo=guide[:,:,3:6].copy();depth=guide[:,:,6].copy()
    # Raw radiance remains untouched. Negative out-of-gamut RGB only gets clipped
    # in the display reconstruction, just as it was in the original tone mapper.
    work=np.maximum(rgb,0).astype(np.float32)
    work,mask=isolated_outliers(work,normal,depth,m,support[:,:,0])
    diffuse=(m>=0)&(m!=6)&(m!=7)&(m!=3)&(m!=9)&(support[:,:,0]>=.94)&(support[:,:,1]<.30)
    factor=np.ones_like(work)
    factor[diffuse]=np.maximum(albedo[diffuse],.035)
    illum=work/factor
    spatial=spatial_noise_variance(illum)
    if measured_variance:
        # Scalar CIE-Y variance is an approximation to RGB-luminance variance.
        fa=factor@np.array([.2126,.7152,.0722],np.float32)
        sampled=np.maximum(guide[:,:,7],0)/np.maximum(fa*fa,1e-10)
        sampled=median_filter(sampled,size=3,mode='reflect')
        var=np.maximum(sampled,.75*spatial).astype(np.float32)
        variance_source='Native mean-radiance variance, with robust spatial floor'
    else:
        var=spatial;variance_source='Robust spatial estimate; original path moments unavailable'
    v_initial=var.copy()
    for k in range(passes):
        step=2**k
        # A-trous supports overlap. A small covariance floor avoids treating
        # correlated filtered samples as independent on later passes.
        var=np.maximum(var,v_initial*(.045/(1+k))).astype(np.float32)
        illum,var=wavelet_pass(illum,normal,albedo,depth,var,m,support,diffuse,step,strength)
    filtered=np.maximum(illum*factor,0).astype(np.float32)
    if not np.isfinite(filtered).all():raise RuntimeError('Nonfinite reconstructed radiance')
    return filtered,mask,{'method':'R5 non-neural variance-aware spatial wavelet with albedo demodulation',
         'raw_noise_reinjection':False,'cross_representation_filtering':False,'guide_space':'Multisampled primary-surface albedo and unperturbed mesh normal',
         'variance_source':variance_source,'wavelet_steps':[2**i for i in range(passes)],'strength':strength,
         'isolated_hdr_outlier_pixels':int(mask.sum()),'radiance_clamp_in_integrator_added':False,
         'display_reconstruction_is_biased':True,'neural_filter':False,'image_generation':False,
         'upscaling':False,'mean_absolute_linear_change':float(np.mean(abs(filtered-rgb))),
         'seconds':time.monotonic()-start}


def save_png_atomic(path: Path, pixels: np.ndarray) -> None:
    temporary=path.with_name(path.stem+'.pending.png')
    Image.fromarray(pixels).save(temporary,compress_level=6)
    with Image.open(temporary) as check:
        if not np.array_equal(np.asarray(check),pixels):raise RuntimeError('PNG verification failed')
    os.replace(temporary,path)


def run(linear: Path, guides: Path, output: Path, metadata: Path,
        *, guide_metadata: Path|None=None, support_path: Path|None=None,
        white_balance=6000., exposure: float|None=None, passes=3, strength=2.5):
    before_hash=sha(linear);rgb=read_linear(linear);h,w=rgb.shape[:2]
    guide=read_buffer(guides,9,(h,w))
    support=np.zeros((h,w,4),np.float32);support[:,:,0]=1
    if support_path is not None:support=read_buffer(support_path,4,(h,w))
    md=json.loads(metadata.read_text());md=md.get('render',md)
    gmd=json.loads(guide_metadata.read_text()) if guide_metadata else md
    same_raw_moments=not gmd.get('guides_only',False)
    if gmd.get('guides_only') and np.any(guide[:,:,7]!=0):
        raise ValueError('Guide-only pass unexpectedly contains path variance')
    if int(md['width'])!=w or int(md['height'])!=h:raise ValueError('Metadata dimensions do not match')
    filtered,mask,audit=resolve(rgb,guide,support,measured_variance=same_raw_moments,passes=passes,strength=strength)
    exp=float(md['exposure'] if exposure is None else exposure);white=camera_white(white_balance)
    output.parent.mkdir(parents=True,exist_ok=True)
    encoded=encode(filtered,white,exp);raw_encoded=encode(rgb,white,exp)
    save_png_atomic(Path(str(output)+'.png'),encoded)
    save_png_atomic(Path(str(output)+'_raw.png'),raw_encoded)
    exr_tmp=Path(str(output)+'_denoised_linear.pending.exr')
    if not cv2.imwrite(str(exr_tmp),filtered[:,:,::-1]):raise RuntimeError('EXR write failed')
    os.replace(exr_tmp,Path(str(output)+'_denoised_linear.exr'))
    np.save(str(output)+'_outlier_mask.npy',mask)
    audit.update({'input_linear':str(linear),'input_sha256':before_hash,'raw_unchanged':before_hash==sha(linear),
                  'guides_sha256':sha(guides),'guide_spp':gmd.get('guide_spp'),
                  'width':w,'height':h,'display_exposure':exp,'white_balance_kelvin':white_balance,
                  'output_png_sha256':sha(Path(str(output)+'.png')),
                  'source_sha256':sha(Path(__file__)),
                  'input_is_native_linear_render':True,
                  'scope':'Noise reconstruction only; not a photorealism or unbiased-light-transport certificate'})
    Path(str(output)+'_noise_report.json').write_text(json.dumps(audit,indent=2)+'\n')
    Path(str(output)+'_image_verification.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2),flush=True)
    return audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linear',type=Path,required=True);p.add_argument('--guides',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--guide-metadata',type=Path);p.add_argument('--support',type=Path)
    p.add_argument('--white-balance',type=float,default=6000);p.add_argument('--exposure',type=float)
    p.add_argument('--passes',type=int,default=3);p.add_argument('--strength',type=float,default=2.5)
    p.add_argument('--threads',type=int,default=4);a=p.parse_args()
    set_num_threads(a.threads)
    run(a.linear,a.guides,a.output,a.metadata,guide_metadata=a.guide_metadata,support_path=a.support,
        white_balance=a.white_balance,exposure=a.exposure,passes=a.passes,strength=a.strength)
if __name__=='__main__':main()
