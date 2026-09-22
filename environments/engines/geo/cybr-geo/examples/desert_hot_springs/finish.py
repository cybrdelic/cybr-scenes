"""Geometry-guided linear-light filtering and verified PNG export.

This does not generate imagery or composite a photograph. Raw native radiance,
unfiltered beauty and the exact guides remain available for inspection.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from numba import njit, prange, set_num_threads


def read_pfm(path: Path):
    with path.open('rb') as f:
        if f.readline().strip()!=b'PF':raise ValueError('RGB PFM required')
        w,h=map(int,f.readline().split());scale=float(f.readline())
        raw=np.fromfile(f,dtype='<f4' if scale<0 else '>f4')
        if raw.size!=w*h*3:raise ValueError('Truncated PFM')
    return np.flipud(raw.reshape(h,w,3)).copy()


@njit(parallel=True,cache=True)
def guided_pass(rgb,normal,albedo,depth,variance,material,step):
    h,w,_=rgb.shape;out=np.empty_like(rgb)
    weights=np.array([1.,4.,6.,4.,1.],np.float32)
    for y in prange(h):
        for x in range(w):
            result=np.zeros(3,np.float32);total=0.
            lum=.2126*rgb[y,x,0]+.7152*rgb[y,x,1]+.0722*rgb[y,x,2]
            for dy in range(-2,3):
                yy=y+dy*step
                if yy<0 or yy>=h:continue
                for dx in range(-2,3):
                    xx=x+dx*step
                    if xx<0 or xx>=w:continue
                    if material[y,x]!=material[yy,xx]:continue
                    na=0.;da=0.
                    for c in range(3):
                        na+=normal[y,x,c]*normal[yy,xx,c]
                        d=albedo[y,x,c]-albedo[yy,xx,c];da+=d*d
                    if material[y,x]<0:na=1.
                    if na<.4:continue
                    ld=.2126*rgb[yy,xx,0]+.7152*rgb[yy,xx,1]+.0722*rgb[yy,xx,2]-lum
                    lv=variance[y,x]+variance[yy,xx]+.0001+.003*lum*lum
                    dw=abs(depth[y,x]-depth[yy,xx])/(.035+.022*min(depth[y,x],depth[yy,xx]))
                    weight=weights[dx+2]*weights[dy+2]*max(na,0.)**28
                    weight*=np.exp(-da/.012-dw*dw-.5*ld*ld/(lv*5))
                    total+=weight
                    for c in range(3):result[c]+=weight*rgb[yy,xx,c]
            for c in range(3):out[y,x,c]=result[c]/max(total,1.e-12)
    return out


def preserve_opaque_residual(raw, filtered, guide_material, sample_counts, ordinary_spp,
                             water_spp, strength):
    """Reduce filtering of opaque sediment/crust; never infer water from refracted guides.

    The native sample-budget map classifies the center camera ray. Guide rays
    continue through water and therefore cannot identify primary water hits.
    This is a convex radiance blend, not sharpening or synthesized detail.
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError('Opaque filter strength must be within [0,1]')
    if water_spp <= ordinary_spp:
        # Equal budgets do not encode primary water identity. Leave the filter
        # unchanged instead of accidentally treating the submerged bed as land.
        return filtered.copy(), np.zeros(guide_material.shape, dtype=bool)
    mask = ((guide_material == 0) | (guide_material == 4)) & (sample_counts == ordinary_spp)
    out = filtered.copy()
    out[mask] = raw[mask] * np.float32(1.0-strength) + filtered[mask] * np.float32(strength)
    return out, mask


def camera_white(temperature):
    """Normalized RGB of the sampled blackbody camera white; a display transform."""
    from verify import matching
    w=(380+(np.arange(16)+.5)*25)*1e-9
    spectrum=1e-28/(w**5*np.expm1(.01438776877/(w*temperature)))
    xyz=spectrum@matching()
    transform=np.array([[3.2406,-1.5372,-.4986],[-.9689,1.8758,.0415],[.0557,-.204,1.057]])
    return transform@(xyz/xyz[1])

def encode(rgb,white,exposure):
    a=np.maximum(rgb/np.asarray(white)*exposure,0)
    # Global toe only; no texture synthesis or local feature creation.
    a=a*a/(a+.035)
    peak=np.maximum(a.max(axis=-1,keepdims=True),1e-7)
    a*=(-np.expm1(-peak))/peak
    a=np.clip(a,0,1)
    a=np.where(a<=.0031308,12.92*a,1.055*a**(1/2.4)-.055)
    return np.clip(np.rint(a*255),0,255).astype(np.uint8)


def main():
    p=argparse.ArgumentParser();p.add_argument('stem',type=Path);p.add_argument('--passes',type=int,default=2)
    p.add_argument('--exposure',type=float);p.add_argument('--white-balance',type=float,default=5000.);p.add_argument('--sky-passes',type=int,default=3);p.add_argument('--opaque-filter-strength',type=float,default=.35);a=p.parse_args();stem=a.stem
    if not 0<=a.sky_passes<=3:p.error('Sky passes must be in [0,3]')
    if not 0<=a.passes<=3:p.error('Filter passes must be in [0,3]')
    if not 0<=a.opaque_filter_strength<=1:p.error('Opaque filter strength must be in [0,1]')
    if not 2000<=a.white_balance<=20000:p.error('White balance must be in [2000,20000] K')
    metadata=json.loads(Path(str(stem)+'.json').read_text())
    rgb=read_pfm(Path(str(stem)+'.pfm'));h,w,_=rgb.shape
    if not np.isfinite(rgb).all():raise RuntimeError('Nonfinite native radiance')
    with Path(str(stem)+'.guides').open('rb') as f:
        dim=np.fromfile(f,dtype='<u4',count=2)
        if tuple(dim)!=(w,h):raise RuntimeError('Guide dimensions differ')
        guide=np.fromfile(f,dtype='<f4').reshape(h,w,9)
    exposure=a.exposure if a.exposure is not None else metadata['exposure']
    white=camera_white(a.white_balance)
    raw=encode(rgb,white,exposure)
    Image.fromarray(raw).save(Path(str(stem)+'_raw.png'))
    set_num_threads(5);filtered=rgb.copy()
    for step in [1,2,4][:a.passes]:
        filtered=guided_pass(filtered,guide[:,:,:3],guide[:,:,3:6],guide[:,:,6],guide[:,:,7],guide[:,:,8],step)
    # Extra stochastic-atmosphere denoising only for rays whose geometry guide
    # misses every opaque surface. Material gating prevents landscape-edge bleed.
    # Ground, stones, foliage and underwater-floor pixels are not modified here.
    sky_mask=guide[:,:,8]<0
    for step in [2,4,8][:a.sky_passes]:
        sky_filtered=guided_pass(filtered,guide[:,:,:3],guide[:,:,3:6],guide[:,:,6],guide[:,:,7],guide[:,:,8],step)
        filtered[sky_mask]=sky_filtered[sky_mask]
    with Path(str(stem)+'.samples').open('rb') as f:
        dims=np.fromfile(f,dtype='<u4',count=2)
        if tuple(dims)!=(w,h):raise RuntimeError('Sample-map dimensions differ')
        counts=np.fromfile(f,dtype='<u2')
        if counts.size!=w*h:raise RuntimeError('Truncated sample-budget map')
        counts=counts.reshape(h,w)
    filtered,opaque_mask=preserve_opaque_residual(
        rgb,filtered,guide[:,:,8],counts,metadata['spp'],metadata['water_spp'],a.opaque_filter_strength)
    final=encode(filtered,white,exposure)
    output=Path(str(stem)+'.png');Image.fromarray(final).save(output,optimize=True)
    decoded=np.asarray(Image.open(output).convert('RGB'))
    if not np.array_equal(decoded,final):raise RuntimeError('PNG round-trip mismatch')
    audit={
        'source':'Native spectral radiance, not an image-generation model',
        'resolution':[w,h], 'guided_filter_steps':[1,2,4][:a.passes],
        'sky_only_filter_steps':[2,4,8][:a.sky_passes],
        'sky_filter_pixel_count':int(sky_mask.sum()),
        'sky_filter_mask':'Negative first-opaque-surface material guide only; no landscape pixel changes in sky-only passes',
        'filter_space':'Linear scene-referred RGB after 16-band CIE integration',
        'opaque_filter_strength':a.opaque_filter_strength,
        'opaque_residual_preserved_fraction':1-a.opaque_filter_strength,
        'opaque_policy_pixel_count':int(opaque_mask.sum()),
        'opaque_mask':'Center-ray budget equals ordinary spp and sediment/crust material 0 or 4; disabled if water budget is not higher',
        'opaque_policy':'Sediment/crust only: convex native/filtered radiance blend, not sharpening or detail synthesis; other materials retain full filtering',
        'postprocess_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'raw_radiance_finite':True,'raw_radiance_min':float(rgb.min()),'raw_radiance_max':float(rgb.max()),
        'mean_linear_rgb':rgb.mean(axis=(0,1)).tolist(),
        'png_round_trip_exact':True,
        'png_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'exposure':exposure,'camera_white_balance_K':a.white_balance,'display_white_rgb':white.tolist(),'toe_parameter':.035,'added_grain':False,'upscaling':False,'photo_compositing':False,
        'mean_linear_filter_change':float(np.mean(np.abs(filtered-rgb)))}
    Path(str(stem)+'_image_verification.json').write_text(json.dumps(audit,indent=2)+'\n')
    np.savez_compressed(Path(str(stem)+'_linear_evidence.npz'),raw=rgb,filtered=filtered,
                        normal=guide[:,:,:3],albedo=guide[:,:,3:6],depth=guide[:,:,6],variance=guide[:,:,7])
    print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
