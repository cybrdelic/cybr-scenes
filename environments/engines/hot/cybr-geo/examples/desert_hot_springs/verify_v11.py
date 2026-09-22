"""Fresh V11 execution evidence. No numerical test certifies photographic realism."""
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
import numpy as np
import trimesh
from finish import read_pfm
from verify import matching,sha
from scene_inputs import fingerprint,current_scene_matches

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
NATIVE_SOURCES=['spectral_desert.cpp','spectral_geometry.h','single_scatter_sky.h','photographic_grain.h','broadband_ripples.h','landscape_materials_v11.h','granular_relief_v11.h','steam_volume_v11.h','exponential_haze_v10.h','cloud_volume_v9.h','specular_reflection_connection.h']
def check_view(root:Path,name:str):
    stem=root/name
    meta=json.loads(stem.with_suffix('.json').read_text())
    receipt=json.loads(Path(str(stem)+'_run_receipt.json').read_text())
    image=json.loads(Path(str(stem)+'_image_verification.json').read_text())
    raw=read_pfm(stem.with_suffix('.pfm'))
    with stem.with_suffix('.spectral').open('rb') as f:
        magic,w,h,bands=map(int,np.fromfile(f,'<u4',4))
    if magic!=0x36315053 or bands!=16 or raw.shape!=(h,w,3):raise ValueError('Inconsistent raw film buffers')
    spectra=np.memmap(stem.with_suffix('.spectral'),dtype='<f4',mode='r',offset=16,shape=(h,w,bands))
    transform=np.array([[3.2406,-1.5372,-.4986],[-.9689,1.8758,.0415],[.0557,-.204,1.057]])
    maximum=0.;summed=0.;finite=True
    for y in range(0,h,32):
        values=np.asarray(spectra[y:y+32],dtype=np.float64)
        reconstructed=(values@matching())@transform.T
        difference=abs(reconstructed-raw[y:y+32]);finite=finite and bool(np.isfinite(values).all())
        maximum=max(maximum,float(np.max(difference/(1+abs(raw[y:y+32])))))
        summed+=float(difference.sum())
    with stem.with_suffix('.samples').open('rb') as f:
        dimensions=np.fromfile(f,'<u4',2);counts=np.fromfile(f,'<u2')
    budget_ok=tuple(dimensions)==(w,h) and len(counts)==w*h and int(counts.sum(dtype=np.uint64))==meta['total_camera_samples']
    source_hash=hashlib.sha256(b''.join((REPO/'native'/n).read_bytes() for n in NATIVE_SOURCES)).hexdigest()
    source_ok=source_hash==receipt['source_hash']
    passed=finite and bool(np.isfinite(raw).all()) and maximum<1e-4 and budget_ok and source_ok and meta['nonfinite_path_samples']==0 and image['png_sha256']==sha(stem.with_suffix('.png'))
    return {'render':meta,'execution':receipt,'image':image,'spectral_reintegration':{'finite':finite,'max_normalized_error':maximum,'mean_absolute_error':summed/(h*w*3),'passed':maximum<1e-4 and finite},'sample_budget_consistent':budget_ok,'renderer_source_matches_receipt':source_ok,'passed':passed}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--views',nargs='+',default=['final']);a=p.parse_args();root=a.out
    geometry=json.loads((root/'geometry_verification.json').read_text())
    meta=json.loads((root/'scene/scene.json').read_text());water=[]
    with np.load(root/'scene/meshes.npz',allow_pickle=False) as archive:
        for item in meta['parts']:
            if not item['name'].startswith('Closed_water'):continue
            key=item['key'];mesh=trimesh.Trimesh(archive[key+'_vertices']*.001,archive[key+'_faces'],process=False)
            mesh.merge_vertices(digits_vertex=7)
            water.append({'name':item['name'],'watertight':bool(mesh.is_watertight),'consistent_winding':bool(mesh.is_winding_consistent),'positive_signed_volume':bool(mesh.volume>0),'boundary':item['metadata']})
            del mesh
    modes=np.asarray(json.loads((HERE/'assets/ripple_modes.json').read_text())['modes_kx_ky_amplitude_phase'])
    header=(REPO/'native/broadband_ripples.h').read_text();block=header.split('RIPPLE_MODES[RIPPLE_COUNT][4]={',1)[1].split('};',1)[0]
    native=np.array([[float(n) for n in row.split(',')] for row in re.findall(r'\{([^{}]+)\}',block)])
    views={name:check_view(root,name) for name in a.views}
    tests={}
    for name in ['scene_io','materials','steam_grid']:
        path=root/'tests'/f'{name}.json'
        if path.exists():tests[name]=json.loads(path.read_text())
    if (root/'optics_tests.json').exists():tests['optics']=json.loads((root/'optics_tests.json').read_text())
    report={'scope':'Newly executed render/geometry/buffer integrity and explicitly named component checks. Not a photorealism, measured-geometry, or reference-integrator certificate.',
      'geometry':geometry,'water_boundaries':water,'scene_inputs_match':current_scene_matches(root,meta['metadata']['seed']),
      'mode_table_matches':modes.shape==native.shape and bool(np.array_equal(modes,native)),
      'views':views,'component_tests':tests,'authored_geometry':True,'measured_geometry':False,
      'image_generation':False,'photographic_backplates':False,'photographic_compositing':False,
      'gravel_asset':'Previously supplied CC0 grayscale photograph; weak albedo detail plus an explicitly authored reconstructed granular support field. This is not measured displacement.',
      'limitations':['16 fixed midpoint bands, not continuous-wavelength or measured material spectra','Constant water IOR; wavelength-dependent absorption but no dispersion','One-root transmitted/reflected solar connections approximate water caustics','Authored waves and steam, not coupled fluid/thermal simulation','Quadrature-refined reduced single-scattering sky, not a reference multiple-scattering atmosphere','Conditional non-neural radiance denoising; raw image and radiance preserved'],
      'upstream_render_defaults_changed':False,'github_push':False,'numerical_checks_certify_photorealism':False}
    report['listed_checks_passed']=report['scene_inputs_match'] and report['mode_table_matches'] and len(water)==2 and all(w['watertight'] and w['consistent_winding'] and w['positive_signed_volume'] for w in water) and all(v['passed'] for v in views.values()) and all(t['passed'] for t in tests.values()) and len(tests)==4
    comparison=root/'tests/comparison_alignment.json'
    if comparison.exists() and 'previous_lighting' in views:
        report['comparison_settings']=json.loads(comparison.read_text())
        report['listed_checks_passed']=report['listed_checks_passed'] and report['comparison_settings']['stated_setting_checks_passed']
    visual=root/'visual_review.json'
    if visual.exists():report['visual_review']=json.loads(visual.read_text())
    (root/'verification_v11.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'listed_checks_passed':report['listed_checks_passed'],'views':list(views),'water_boundaries':water},indent=2))
    if not report['listed_checks_passed']:raise SystemExit(1)
if __name__=='__main__':main()
