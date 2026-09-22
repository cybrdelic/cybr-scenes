"""Verify execution/buffer integrity; never certify photorealism using unit tests."""
from __future__ import annotations
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
from PIL import Image
from finish import read_pfm
from verify import matching
from build_scenes import sha

def verify_scene(folder:Path,stem:str='hero')->dict:
    meta=json.loads((folder/(stem+'.json')).read_text())
    geometry=json.loads((folder/'geometry.json').read_text())
    execution=json.loads((folder/(stem+'_execution.json')).read_text())
    rgb=read_pfm(folder/(stem+'.pfm'));h,w,_=rgb.shape
    matrix=np.array([[3.2406,-1.5372,-.4986],[-.9689,1.8758,.0415],[.0557,-.204,1.057]])
    matching_matrix=matching()
    spectral_finite=True;spectral_nonnegative=True;max_abs=0.;max_relative=0.;sum_error=0.
    # Stream strips so validation does not duplicate the entire spectrum as float64.
    # Each strip is independently integrated before comparison to native RGB.
    with (folder/(stem+'.spectral')).open('rb') as f:
        header=np.fromfile(f,'<u4',4)
        if tuple(header)!=(0x36315053,w,h,16):raise ValueError('Spectral buffer header differs')
        for y in range(0,h,32):
            rows=min(32,h-y);a=np.fromfile(f,'<f4',rows*w*16)
            if a.size!=rows*w*16:raise ValueError('Truncated spectral buffer')
            bands=a.reshape(rows,w,16)
            spectral_finite=spectral_finite and bool(np.isfinite(bands).all())
            spectral_nonnegative=spectral_nonnegative and bool((bands>=0).all())
            reintegrated=(bands.astype(np.float64)@matching_matrix)@matrix.T
            error=np.abs(reintegrated-rgb[y:y+rows]);relative=error/(1+np.abs(rgb[y:y+rows]))
            max_abs=max(max_abs,float(error.max()));max_relative=max(max_relative,float(relative.max()));sum_error+=float(error.sum())
        if f.read(1):raise ValueError('Trailing spectral buffer bytes')
    with (folder/(stem+'.samples')).open('rb') as f:
        dims=np.fromfile(f,'<u4',2);counts=np.fromfile(f,'<u2').reshape(h,w)
    assert tuple(dims)==(w,h)
    assert int(counts.sum(dtype=np.uint64))==meta['total_camera_samples']
    image=np.asarray(Image.open(folder/(stem+'.png')).convert('RGB'))
    checks={
        'dimensions_agree':image.shape==(h,w,3) and [w,h]==[meta['width'],meta['height']],
        'raw_and_spectral_radiance_finite':bool(np.isfinite(rgb).all() and spectral_finite),
        'spectral_radiance_nonnegative':spectral_nonnegative,
        'spectral_reintegration_passed':bool(max_relative<5e-5),
        'sample_counts_match':int(counts.sum(dtype=np.uint64))==meta['total_camera_samples'],
        'zero_nonfinite_path_samples':meta['nonfinite_path_samples']==0,
        'contribution_clamping_disabled':meta['indirect_contribution_clamp_Y']==0 and meta['clamped_indirect_contributions']==0,
        'mesh_hash_matches_execution':execution['mesh_sha256']==geometry['mesh_sha256']==sha(folder/'scene.meshbin'),
        'png_present_and_decodable':True,
    }
    if not all(checks.values()):raise RuntimeError(checks)
    return {'scene':geometry['scene'],'render':meta,'geometry':geometry,'checks':checks,
            'spectral_reintegration':{'maximum_absolute_error':max_abs,'maximum_error_over_one_plus_abs_rgb':max_relative,'mean_absolute_error':sum_error/(h*w*3)},
            'files':{n:sha(folder/n) for n in [stem+'.png',stem+'_raw.png',stem+'.pfm',stem+'.spectral',stem+'_linear.exr'] if (folder/n).is_file()},
            'execution':execution,'image_finish':json.loads((folder/(stem+'_image_verification.json')).read_text()),
            'visual_acceptance_is_separate':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--stem',default='hero');a=p.parse_args()
    report={'scope':'Actual render completion, geometry serialization and numerical buffer integrity. Not photorealism, geological simulation, measured materials, or reference-integrator validation.',
       'renderer_architecture':'CYBR GEO Assembly/Part -> native mesh stream -> original binned SAH BVH and triangle intersection -> 16 fixed wavelength transport bands -> CIE integration -> non-neural geometry-guided filtering',
       'image_generation_used':False,'generated_image_textures_used':False,'photographic_backplates_used':False,'neural_denoising_used':False,
       'material_spectra':'Authored reference-calibrated RGB-anchor spectra, not measured',
       'spectral_quadrature':'16 fixed 25-nm midpoint bands over 380-780 nm; not continuous wavelength sampling',
       'water_dispersion':False,'water_ior':1.334,
       'water_motion':'Authored deterministic wave modes; not a fluid simulation',
       'caustic_approximation':'One-root macro-interface solar connections; not a complete unbiased all-path solution',
       'sky_approximation':'Wavelength-resolved single-scattering sky LUT; not full multiple-scattering atmosphere',
       'upstream_changes_or_github_push':False,'scenes':[]}
    for name in ['canyon','coast','forest']:report['scenes'].append(verify_scene(a.root/name,a.stem))
    report['all_integrity_checks_passed']=all(all(x['checks'].values()) for x in report['scenes'])
    (a.root/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({n['scene']:{'resolution':[n['render']['width'],n['render']['height']],'checks':n['checks']} for n in report['scenes']},indent=2))
if __name__=='__main__':main()
