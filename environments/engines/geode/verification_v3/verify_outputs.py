"""Validate actual outputs and retain the scope of each check explicitly."""
from __future__ import annotations
import os,sys,json,hashlib,struct
from pathlib import Path
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import numpy as np
import cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from finish import read_pfm

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(4*1024*1024):h.update(data)
    return h.hexdigest()

geometry=json.loads((ROOT/'verification_v3/geometry.json').read_text())
optics=json.loads((ROOT/'verification_v3/native_optics.json').read_text())
rough=json.loads((ROOT/'verification_v3/rough_quartz_test.json').read_text())
filter_result=json.loads((ROOT/'verification_v3/filter_test.json').read_text())
results={}
for name in ['Drowned_Geode_V3','Drowned_Geode_V3_Optics']:
    stem=ROOT/'output_v3'/name
    if not stem.with_suffix('.json').exists():continue
    meta=json.loads(stem.with_suffix('.json').read_text())
    im=cv2.imread(str(stem)+'_raw.exr',cv2.IMREAD_UNCHANGED)
    if im is None:raise RuntimeError('Missing raw EXR: '+name)
    im=im[:,:,::-1].copy();h,w=im.shape[:2]
    assert (w,h)==(meta['width'],meta['height'])
    pfm=stem.with_suffix('.pfm');raw_lossless=bool(np.array_equal(im,read_pfm(pfm))) if pfm.exists() else None
    with Image.open(stem.with_suffix('.png')) as pic:png_size=pic.size
    with np.load(str(stem)+'_guides.npz') as g:
        guides_finite=all(np.isfinite(g[k]).all() for k in g.files)
        guide_shapes={k:list(g[k].shape) for k in g.files}
    counts=np.load(str(stem)+'_sample_counts.npy',allow_pickle=False)
    assert counts.shape==(h,w) and np.all(counts>0)
    minimum=None;spectral_finite=None;spectral_header_ok=None
    spectral=stem.with_suffix('.spectral')
    if spectral.exists():
        with spectral.open('rb') as f:magic,sw,sh,bands=struct.unpack('<IIII',f.read(16))
        spectral_header_ok=(magic==0x36315053 and (sw,sh,bands)==(w,h,16) and spectral.stat().st_size==16+w*h*16*4)
        a=np.memmap(spectral,'<f4',mode='r',offset=16,shape=(h,w,16))
        spectral_finite=bool(np.isfinite(a).all());minimum=float(a.min())
    raw_finite=bool(np.isfinite(im).all())
    native_count_matches=meta['triangles']==geometry['triangles']
    results[name]={'width':w,'height':h,'nominal_spp':meta['spp'],'actual_samples':meta['sampling_v3'],
      'raw_finite':raw_finite,'raw_exr_bit_equal_to_native_pfm':raw_lossless,
      'png_dimensions_match':png_size==(w,h),'guide_shapes':guide_shapes,'guides_finite':guides_finite,
      'spectral_header_valid':spectral_header_ok,'spectral_finite':spectral_finite,'minimum_spectral_radiance':minimum,
      'native_count_matches_serialized_mesh':native_count_matches,'nonfinite_path_samples':meta['nonfinite_path_samples'],
      'render_seconds':meta['seconds'],'finishing':meta['finishing'],
      'image_sha256':sha(stem.with_suffix('.png')),'raw_exr_sha256':sha(Path(str(stem)+'_raw.exr')),
      'passed':bool(raw_finite and guides_finite and native_count_matches and meta['nonfinite_path_samples']==0 and raw_lossless is not False and spectral_finite is not False and spectral_header_ok is not False)}
if not results:raise RuntimeError('No final rendered outputs available')
rebuild_path=ROOT/'verification_v3/rebuild.json'
rebuild=json.loads(rebuild_path.read_text()) if rebuild_path.exists() else {'status':'not run'}
replay_path=ROOT/'verification_v3/finish_replay.json'
replay=json.loads(replay_path.read_text()) if replay_path.exists() else {'status':'not run'}
report={'revision':'V3','image_generation':False,'neural_denoiser':False,
 'renderer':'CYBR GEO native C++ / CPU / sixteen-band path transport','geometry':geometry,
 'native_optics':optics,'rough_quartz':rough,'filter_symmetry':filter_result,'renders':results,'independent_rebuild':rebuild,'lossless_finish_replay':replay,
 'scope':'Structural and numerical checks, not a photographic-realism or convergence certificate',
 'limitations':['authored fracture-cell cave, not measured or simulated geology','geometric inclusions, not a calibrated defect-scattering model','finite path depth and finite sampling','ordinary quartz index; no birefringence or polarization','small druse uses achromatic refraction','no general multi-interface caustic solver','non-neural spatial filtering modifies the viewing image only','production viewing image uses limited variance-gated bright-outlier regularization; raw radiance remains untouched'],
 'passed':bool(geometry['mesh_finite'] and geometry['dielectrics_all_closed_outward'] and optics['passed'] and rough['passed'] and filter_result['passed'] and all(v['passed'] for v in results.values()) and rebuild.get('passed',True) and replay.get('byte_identical',True))}
(ROOT/'verification_v3/validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':report['passed'],'renders':list(results),'triangles':geometry['triangles'],'dielectric_objects':geometry['dielectric_objects']},indent=2))
if not report['passed']:raise SystemExit(1)
