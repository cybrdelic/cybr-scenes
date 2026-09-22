"""Independent integrity checks for the V10 delivery, not a realism certificate."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
import numpy as np
import trimesh
from finish import read_pfm
from verify import matching
from scene_inputs import current_scene_matches

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(8*1024*1024),b''):h.update(c)
    return h.hexdigest()

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--views',nargs='+',default=['hero'])
    ap.add_argument('--report',type=Path)
    args=ap.parse_args();out=args.out
    geometry=json.loads((out/'geometry_verification.json').read_text())
    scene_manifest=json.loads((out/'scene_inputs.json').read_text())
    native_names=('spectral_desert.cpp','spectral_geometry.h','single_scatter_sky.h','photographic_grain.h','broadband_ripples.h','scale_aware_landscape_v10.h','exponential_haze_v10.h','cloud_volume_v9.h','specular_reflection_connection.h')
    native_hash=hashlib.sha256(b''.join((REPO/'native'/n).read_bytes() for n in native_names)).hexdigest()
    scene=json.loads((out/'scene/scene.json').read_text())
    waters=[]
    with np.load(out/'scene/meshes.npz') as data:
        for i,part in enumerate(scene['parts']):
            if not part['name'].startswith('Closed_water_'):continue
            k=f'p{i:05d}'
            m=trimesh.Trimesh(data[k+'_vertices']*.001,data[k+'_faces'],process=False)
            m.merge_vertices(digits_vertex=7)
            waters.append(dict(name=part['name'],watertight=bool(m.is_watertight),winding_consistent=bool(m.is_winding_consistent),signed_volume_m3=float(m.volume),finite_vertices=bool(np.isfinite(m.vertices).all())))
            del m
    modes=np.asarray(json.loads((HERE/'assets/ripple_modes.json').read_text())['modes_kx_ky_amplitude_phase'])
    header=(REPO/'native/broadband_ripples.h').read_text()
    block=header.split('RIPPLE_MODES[RIPPLE_COUNT][4]={',1)[1].split('};',1)[0]
    compiled=np.array([[float(t) for t in row.split(',')] for row in re.findall(r'\{([^{}]+)\}',block)])
    from v10_landforms import RIPPLE_SCALE
    scale=float(re.search(r'RIPPLE_SCALE\s*=\s*([.0-9]+)',header).group(1))
    ripple_ok=compiled.shape==modes.shape and np.array_equal(compiled,modes) and scale==RIPPLE_SCALE
    report={
      'scope':'Completed CYBR GEO geometry and native 16-band path-tracing integrity checks; no calibrated-material, surveyed-terrain, complete-light-transport or photorealism certification.',
      'geometry':geometry,'water_boundaries':waters,
      'scene_input_fingerprint_matches_current':current_scene_matches(out,scene_manifest['scene_seed']),
      'current_native_source_hash':native_hash,
      'ripple_geometry_and_native_table_identical':bool(ripple_ok),
      'ripple_mode_count':len(modes),'ripple_quadrature_rms_m':float(np.sqrt(np.sum((modes[:,2]*scale)**2)/2)),
      'authored_geometry':True,'measured_geometry':False,
      'image_generation_used':False,'photo_compositing':False,'photo_backplate':False,
      'existing_grayscale_photo_as_material_only':True,
      'upstream_defaults_modified':False,'github_push':False,
      'limits':[
        'All terrain, geology, scrub, mineral growth and steam shapes are authored, not surveyed or a calibrated formation simulation.',
        'Sixteen fixed 25 nm wavelength bins; RGB-anchor material spectra, not measured spectra.',
        'Water refractive index is constant 1.334; dispersion is not modeled.',
        'One-root macro-surface caustic connectors omit other roots and full rough-lobe integration; no unbiased reference claim.',
        'Water waves are prescribed directional modes, not CFD.',
        'Geometry-guided non-neural denoising is applied only to the display image. Unfiltered linear radiance is also provided.',
        'No claim that every scatter fragment has static support or that vegetation represents a botanically identified species.'
      ],'views':{},'fresh_component_tests':{},
    }
    for file in sorted((out/'current_tests').glob('*.json')):
        report['fresh_component_tests'][file.stem]=json.loads(file.read_text())
    for name in args.views:
        stem=out/name;meta=json.loads(stem.with_suffix('.json').read_text())
        rgb=read_pfm(stem.with_suffix('.pfm'))
        with stem.with_suffix('.spectral').open('rb') as f:
            magic,w,h,bands=np.fromfile(f,'<u4',4)
            if (int(magic),int(bands))!=(0x36315053,16):raise ValueError('Incorrect spectral header')
            spectra=np.fromfile(f,'<f4').reshape(int(h),int(w),16)
        if rgb.shape!=(int(h),int(w),3):raise ValueError('RGB and spectral dimensions differ')
        # CIE fits, wavelength quadrature and XYZ-to-linear-RGB independently in float64.
        matrix=np.array([[3.2406,-1.5372,-.4986],[-.9689,1.8758,.0415],[.0557,-.204,1.057]])
        reconstructed=(spectra@matching())@matrix.T
        err=np.abs(rgb-reconstructed)
        normalized=float(np.max(err/(1+np.abs(rgb))))
        with stem.with_suffix('.samples').open('rb') as f:
            dims=np.fromfile(f,'<u4',2);counts=np.fromfile(f,'<u2')
        if tuple(dims)!=(w,h) or counts.size!=w*h:raise ValueError('Invalid sample map')
        finite=bool(np.isfinite(rgb).all() and np.isfinite(spectra).all())
        budgets,n_pixels=np.unique(counts,return_counts=True)
        sample_ok=int(counts.sum(dtype=np.uint64))==meta['total_camera_samples']
        v={'render':meta,'spectral_reintegration':dict(finite=finite,maximum_absolute_error=float(err.max()),mean_absolute_error=float(err.mean()),maximum_normalized_error=normalized,minimum_band_radiance=float(spectra.min()),passed=finite and normalized<1e-4),
        'sample_map':dict(budgets=budgets.tolist(),pixels=n_pixels.tolist(),total=int(counts.sum(dtype=np.uint64)),passed=bool(sample_ok)),
        'files':{}}
        for suffix in ['.png','_raw.png','.pfm','.spectral','.guides','.samples','.json','_image_verification.json','_linear.exr','_linear.exr.json']:
            file=Path(str(stem)+suffix)
            if file.exists():v['files'][file.name]=dict(bytes=file.stat().st_size,sha256=sha(file))
        post=Path(str(stem)+'_image_verification.json')
        if post.exists():v['display_transform']=json.loads(post.read_text())
        receipt=Path(str(stem)+'_execution.json')
        if not receipt.exists():receipt=Path(str(stem)+'_run_receipt.json')
        if not receipt.exists():raise RuntimeError(f'No execution receipt for {name}')
        v['execution']=json.loads(receipt.read_text())
        v['execution_source_matches_current']=v['execution']['source_hash']==native_hash
        exr_report=Path(str(stem)+'_linear.exr.json')
        if exr_report.exists():
            v['linear_exr_export']=json.loads(exr_report.read_text())
            if v['linear_exr_export']['sha256']!=sha(Path(str(stem)+'_linear.exr')):raise RuntimeError('EXR fingerprint changed')
        report['views'][name]=v
    required_tests={'optical_smoke','test_broadband_ripples','test_water_medium','test_reflectance_calibration_v9','test_water_microfacet','test_exponential_haze_v10','implicit_rocks'}
    report['required_component_reports_present']=required_tests.issubset(report['fresh_component_tests'])
    report['tested_integrity_checks_passed']=bool(report['required_component_reports_present'] and report['scene_input_fingerprint_matches_current'] and ripple_ok and len(waters)==2 and all(w['watertight'] and w['winding_consistent'] and w['signed_volume_m3']>0 and w['finite_vertices'] for w in waters) and all(v['spectral_reintegration']['passed'] and v['sample_map']['passed'] and v['execution_source_matches_current'] for v in report['views'].values()) and all(t.get('passed',False) for t in report['fresh_component_tests'].values()))
    review=out/'visual_review.json'
    report['visual_review']=json.loads(review.read_text()) if review.exists() else {'review_complete':False}
    report['photorealism_certified_by_tests']=False
    dest=args.report or out/'verification_v10.json';dest.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(dest),'tested_integrity_checks_passed':report['tested_integrity_checks_passed'],'completed_views':list(report['views']),'photorealism_certified_by_tests':False},indent=2))
    if not report['tested_integrity_checks_passed']:sys.exit(1)

if __name__=='__main__':main()
