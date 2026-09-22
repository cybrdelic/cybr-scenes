#!/usr/bin/env python3
"""Albedo-demodulated native-radiance filtering; no synthesis or image references.

This is a biased display filter, not a new transport estimate. The raw PFM and
spectral films are not altered. Primary water is identified from the native
sample-budget map rather than refracted guides, and is not demodulated.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys, os
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def demodulate_pass(core, rgb, normal, albedo, depth, variance, material, step, mask):
    denominator=np.maximum(albedo,.075).astype(np.float32)
    lum_d=np.maximum(denominator@np.array([.2126,.7152,.0722],np.float32),.075)
    irradiance=(rgb/denominator).astype(np.float32)
    ivar=(variance/(lum_d*lum_d)).astype(np.float32)
    normal_result=core(rgb,normal,albedo,depth,variance,material,step)
    diffuse_result=core(irradiance,normal,albedo,depth,ivar,material,step)*denominator
    return np.where(mask[...,None],diffuse_result,normal_result).astype(np.float32)

def main():
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=['geo','hot'],required=True);p.add_argument('--foliage',action='store_true')
    a,rest=p.parse_known_args()
    if not rest:raise ValueError('Supply native output stem and finishing flags')
    stem=Path(rest[0]);meta=json.loads(stem.with_suffix('.json').read_text())
    sub='three_scenes' if a.backend=='geo' else 'desert_hot_springs'
    path=ROOT/'engines'/a.backend/'cybr-geo/examples'/sub/'finish.py'
    sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('cybr_original_finish',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    with stem.with_suffix('.guides').open('rb') as f:
        w,h=np.fromfile(f,dtype='<u4',count=2);guide=np.fromfile(f,dtype='<f4').reshape(int(h),int(w),9)
    with stem.with_suffix('.samples').open('rb') as f:
        dims=np.fromfile(f,dtype='<u4',count=2);counts=np.fromfile(f,dtype='<u2').reshape(int(h),int(w))
    if list(dims)!=[w,h]:raise ValueError('Mismatched native guide and sample map dimensions')
    canyon=meta.get('scene')=='canyon' or 'sandstone-passage' in str(stem)
    ordinary=int(meta['spp']);water=int(meta['water_spp'])
    if canyon:opaque=guide[:,:,8]>=0
    elif water>ordinary:opaque=(counts==ordinary)&(guide[:,:,8]>=0)
    else:opaque=np.zeros((h,w),bool)
    core=module.guided_pass
    if a.foliage:
        from foliage_filter import leaf_pass
        ordinary_core=core
        leafmask=(guide[:,:,8]==9)|(guide[:,:,8]==3)
        def core(rgb,normal,albedo,depth,variance,material,step):
            conventional=ordinary_core(rgb,normal,albedo,depth,variance,material,step)
            foliage=leaf_pass(rgb,normal,albedo,depth,variance,material,step)
            return np.where(leafmask[...,None],foliage,conventional).astype(np.float32)
    module.guided_pass=lambda rgb,normal,albedo,depth,var,mat,step:demodulate_pass(core,rgb,normal,albedo,depth,var,mat,step,opaque)
    import numba
    # Recovered hot finish requested five threads even in a four-thread runtime.
    # Respect the caller's actual thread budget without altering original files.
    finish_threads=max(1,min(numba.config.NUMBA_NUM_THREADS,int(os.environ.get('OMP_NUM_THREADS', '4'))))
    module.set_num_threads=lambda n:numba.set_num_threads(min(int(n),finish_threads))
    sys.argv=[str(path),*rest];module.main()
    auditpath=Path(str(stem)+'_image_verification.json')
    audit=json.loads(auditpath.read_text());audit.update({
      'r2_display_filter':'Primary-opaque albedo demodulation, guide-filtered irradiance, remodulation by the actual native albedo AOV',
      'finishing_threads':finish_threads,'demodulation_pixels':int(opaque.sum()),'demodulation_albedo_floor':.075,
      'demodulation_excludes_primary_water':True,'new_filter_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'raw_radiance_changed':False,'reference_image_input':False,
      'foliage_two_sided_filter':a.foliage,'foliage_filter_source_sha256':hashlib.sha256((ROOT/'tools/foliage_filter.py').read_bytes()).hexdigest() if a.foliage else None,
      'limitation':'Biased non-neural display denoising; guide albedo is not a diffuse/specular decomposition.'})
    auditpath.write_text(json.dumps(audit,indent=2)+'\n')
    print('R2_ALBEDO_DEMODULATION',int(opaque.sum()),'pixels; raw radiance unchanged')

if __name__=='__main__':main()
