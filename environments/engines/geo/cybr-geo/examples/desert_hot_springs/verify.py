"""Execution/integrity checks; not a photorealism or reference-transport certificate."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
import numpy as np
import trimesh
from finish import read_pfm

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def gaussian(w,mean,left,right):
    return np.exp(-.5*((w-mean)*np.where(w<mean,left,right))**2)

def matching():
    w=380+(np.arange(16)+.5)*25
    x=1.056*gaussian(w,599.8,.0264,.0323)+.362*gaussian(w,442,.0624,.0374)-.065*gaussian(w,501.1,.049,.0382)
    y=.821*gaussian(w,568.8,.0213,.0247)+.286*gaussian(w,530.9,.0613,.0322)
    z=1.217*gaussian(w,437,.0845,.0278)+.681*gaussian(w,459,.0385,.0725)
    return np.stack([x,y,z],axis=-1)/y.sum()

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--view',default='hero');p.add_argument('--geometry-only',action='store_true');a=p.parse_args();root=a.out
    checks_root=root/'tests' if (root/'tests/native_component_checks.json').is_file() else root
    metadata={} if a.geometry_only else json.loads((root/(a.view+'.json')).read_text())
    geometry=json.loads((root/'geometry_verification.json').read_text())
    scene=json.loads((root/'scene/scene.json').read_text())
    # Only two water meshes are loaded; avoid duplicating the multi-million triangle scene.
    checks=[]
    carbonate_checks=[]
    with np.load(root/'scene/meshes.npz') as data:
        for i,item in enumerate(scene['parts']):
            if item['name']=='Broken_porous_carbonate_shelves':
                prefix=f'p{i:05d}'
                solid=trimesh.Trimesh(data[prefix+'_vertices']*.001,data[prefix+'_faces'],process=False)
                carbonate_checks.append({'name':item['name'],'vertices':len(solid.vertices),'triangles':len(solid.faces),'finite':bool(np.isfinite(solid.vertices).all()),'watertight':bool(solid.is_watertight),'winding_consistent':bool(solid.is_winding_consistent),'signed_volume_m3':float(solid.volume),'builder_metadata':item.get('metadata',{})})
                del solid
            if not item['name'].startswith('Closed_water_'):continue
            prefix=f'p{i:05d}'
            mesh=trimesh.Trimesh(data[prefix+'_vertices']*.001,data[prefix+'_faces'],process=False)
            mesh.merge_vertices(digits_vertex=7)
            checks.append({'name':item['name'],'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),'signed_volume_m3':float(mesh.volume),'boundary_metadata':item.get('metadata',{})})
    report={'scope':'Execution/geometry/limited optical checks, not photorealism, hydrothermal simulation, calibrated material spectra, or reference light-transport validation.',
            'geometry':geometry,'water_boundary_checks':checks,'carbonate_shelf_checks':carbonate_checks,'texture_sha256':sha(HERE/'assets/gravel_periodic.pgm'),
            'authored_geometry':True,'measured_geometry':False,'photographic_grayscale_albedo_detail':True,
            'photo_guided_microrelief':False,
            'ripple_model':'32 authored modes scaled by 0.22, not CFD; same coefficient table for mesh and native LUT',
            'water_solar_connection':'Residual-checked damped Newton with finite-difference solid-angle Jacobian; one root, not all multi-path caustics',
            'water_ior':1.334,'dispersion_modeled':False,'spectral_bands':16,'material_spectra':'Reference-illuminant-calibrated RGB-anchor reconstruction, not measured',
            'photorealism_certified_by_test':False,
            'water_scattering':'Homogeneous sampled free flights, authored sigma_s=0.032/m and HG g=0.74',
      'water_microfacet_reflection': 'Primary camera-side reflection: GGX VNDF and solar-disc MIS; indirect reflected solar caustics: exclusively owned one-root macro manifold',
      'water_microfacet_test':json.loads((checks_root/'water_microfacet_tests.json').read_text()) if (checks_root/'water_microfacet_tests.json').exists() else {'passed':False,'missing':True},
      'indirect_path_clamping': {'luminance_threshold': metadata.get('indirect_contribution_clamp_Y'), 'clamped_contributions': metadata.get('clamped_indirect_contributions'), 'biased_when_applied': True},
      'actual_camera_samples': metadata.get('total_camera_samples'),
      'indirect_caustic_limit': 'One-root macro manifolds approximate reflected and transmitted solar connections; not all-root or full rough-lobe integration',
            'shoreline_continuity':json.loads((checks_root/'shoreline_continuity.json').read_text()) if (checks_root/'shoreline_continuity.json').exists() else None,
            'generated_images_used':False,'photographic_backplates':False,'photo_compositing':False,
            'upstream_defaults_modified':False,'github_push':False}
    for filename,key in [('cloud_volume_tests.json','cloud_volume_checks'),('reflectance_calibration_tests.json','reflectance_calibration'),('reflected_connection_tests.json','reflected_solar_connection'),('connected_vegetation.json','leaf_attachment'),('legacy_water_connection_comparison.json','legacy_solver_comparison'),('v5_optical_regression.json','water_connection_regression'),('ripple_tests.json','ripple_lookup_test'),('water_medium_tests.json','water_medium_test'),('grain_tests.json','grayscale_texture_test')]:
        if (checks_root/filename).is_file():report[key]=json.loads((checks_root/filename).read_text())
    table=json.loads((HERE/'assets/ripple_modes.json').read_text())['modes_kx_ky_amplitude_phase']
    header=(REPO/'native/broadband_ripples.h').read_text()
    block=header.split('RIPPLE_MODES[RIPPLE_COUNT][4]={',1)[1].split('};',1)[0]
    embedded=np.array([[float(x) for x in row.split(',')] for row in re.findall(r'\{([^{}]+)\}',block)])
    coefficients_equal=embedded.shape==np.shape(table) and bool(np.array_equal(embedded,np.asarray(table)))
    report['ripple_coefficient_table_matches_native_header']=coefficients_equal
    from v9_landforms import RIPPLE_SCALE
    native_scale=float(re.search(r'RIPPLE_SCALE\s*=\s*([.0-9]+)',header).group(1))
    report['ripple_amplitude_scale_matches']=abs(native_scale-RIPPLE_SCALE)<1e-12
    if not report['ripple_amplitude_scale_matches']:raise RuntimeError('Wave amplitudes differ between geometry and renderer')
    if not coefficients_equal:raise RuntimeError('Scene ripple JSON differs from native mode table')
    if not a.geometry_only:
        stem=root/a.view
        raw=read_pfm(Path(str(stem)+'.pfm'))
        with Path(str(stem)+'.spectral').open('rb') as f:
            magic,w,h,bands=np.fromfile(f,'<u4',4)
            if magic!=0x36315053 or bands!=16:raise ValueError('Invalid spectral buffer')
            spectra=np.fromfile(f,'<f4').reshape(h,w,bands)
        if raw.shape!=(h,w,3):raise ValueError('Inconsistent output dimensions')
        with Path(str(stem)+'.samples').open('rb') as sample_file:
            sample_dims=np.fromfile(sample_file,'<u4',2);sample_map=np.fromfile(sample_file,'<u2')
        if tuple(sample_dims)!=(w,h) or sample_map.size!=int(w)*int(h):raise ValueError('Invalid sample map')
        expected_counts={metadata['spp'],max(metadata['spp'],metadata['water_spp'])}
        counts,count_pixels=np.unique(sample_map,return_counts=True)
        sample_ok=set(counts.tolist()).issubset(expected_counts) and int(sample_map.sum(dtype=np.uint64))==int(metadata['total_camera_samples'])
        report['sample_map']={'samples_per_pixel':counts.tolist(),'pixels_at_each_budget':count_pixels.tolist(),'total_camera_samples':int(sample_map.sum(dtype=np.uint64)),'passed':bool(sample_ok)}
        if not sample_ok:raise ValueError('Sample budget and radiance metadata differ')
        # Independent float64 wavelength integration from stored bands.
        xyz=spectra@matching()
        matrix=np.array([[3.2406,-1.5372,-.4986],[-.9689,1.8758,.0415],[.0557,-.204,1.057]])
        reconstructed=xyz@matrix.T
        error=np.abs(raw-reconstructed)
        normalized=float(np.max(error/(1+np.abs(raw))))
        report['spectral_reintegration']={'finite':bool(np.isfinite(spectra).all() and np.isfinite(raw).all()),'minimum_band_radiance':float(spectra.min()),'max_absolute_rgb_error':float(error.max()),'mean_absolute_rgb_error':float(error.mean()),'maximum_error_divided_by_one_plus_abs_rgb':normalized,'passed':normalized<.0001}
        for suffix,key in [('.json','render'),('_image_verification.json','image'),('_execution.json','execution')]:
            path=Path(str(stem)+suffix)
            if suffix=='_execution.json' and not path.exists():path=Path(str(stem)+'_run_receipt.json')
            report[key]=json.loads(path.read_text())
        report['optical_smoke_tests']=json.loads((root/'optics_tests.json').read_text())
        filter_path=checks_root/'filter_policy.json'
        filter_test=json.loads(filter_path.read_text()) if filter_path.is_file() else {'passed':False,'missing':True}
        report['filter_policy_test']=filter_test
        report['image_fingerprint_matches_file']=report['image'].get('png_sha256')==sha(Path(str(stem)+'.png'))
        report['postprocess_source_matches_test_and_image']=report['image'].get('postprocess_source_sha256')==sha(HERE/'finish.py')==filter_test.get('postprocess_source_sha256')
        exr_path=Path(str(stem)+'_linear.exr.json')
        if exr_path.is_file():report['linear_exr_export']=json.loads(exr_path.read_text())
        report['passed']=len(checks)==2 and all(c['watertight'] and c['winding_consistent'] and c['signed_volume_m3']>0 for c in checks) and report['spectral_reintegration']['passed'] and report['optical_smoke_tests']['passed']
    else:report['passed']=len(checks)==2 and all(c['watertight'] and c['winding_consistent'] and c['signed_volume_m3']>0 for c in checks)
    report['passed']=report['passed'] and len(carbonate_checks)==1 and all(c['finite'] and c['watertight'] and c['winding_consistent'] and c['signed_volume_m3']>0 for c in carbonate_checks)
    report['passed']=report['passed'] and geometry.get('finite_vertices',False) and geometry.get('valid_indices',False) and geometry.get('unique_names',False)
    if not a.geometry_only:
        required_checks=['cloud_volume_checks','reflectance_calibration','reflected_solar_connection','leaf_attachment','legacy_solver_comparison','water_connection_regression','water_medium_test','grayscale_texture_test','ripple_lookup_test','water_microfacet_test']
        report['required_component_reports_present']=all(key in report for key in required_checks)
        suite=json.loads((checks_root/'native_component_checks.json').read_text())
        report['test_renderer_source_hash_matches_render']=suite.get('renderer_source_hash')==report['execution'].get('source_hash')
        report['passed']=report['passed'] and report['test_renderer_source_hash_matches_render']
        report['passed']=report['passed'] and all(report.get(key,{}).get('passed',False) for key in required_checks)
        report['passed']=report['passed'] and report['sample_map']['passed'] and report.get('shoreline_continuity',{}).get('passed',False)
        report['passed']=report['passed'] and report['render'].get('nonfinite_path_samples',-1)==0 and report['image'].get('png_round_trip_exact',False)
        report['passed']=report['passed'] and report['filter_policy_test'].get('passed',False) and report['image_fingerprint_matches_file'] and report['postprocess_source_matches_test_and_image']
    report['passed_scope']='Execution integrity, named topology checks and the required optical/attachment regressions. Not all geometric correctness or photorealism.'
    if (root/'carbonate_contact_audit.json').is_file():
        report['diagnostic_carbonate_ground_clearance']=json.loads((root/'carbonate_contact_audit.json').read_text())
        report['ground_clearance_is_not_part_of_pass_flag']=True
        if not report['diagnostic_carbonate_ground_clearance']['all_positive_volume_components_grounded']:
            report['known_geometric_warning']='Some tiny disconnected carbonate surface components do not contact the terrain within 3 mm. Watertightness does not establish physical support.'
    if (root/'visual_review.json').is_file():
        report['visual_review']=json.loads((root/'visual_review.json').read_text())
    output=root/('geometry_audit.json' if a.geometry_only else a.view+'_verification.json')
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    if not report['passed']:sys.exit(1)

if __name__=='__main__':main()
