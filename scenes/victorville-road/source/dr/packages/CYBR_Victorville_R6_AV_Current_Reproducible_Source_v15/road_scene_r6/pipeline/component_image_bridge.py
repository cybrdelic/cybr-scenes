"""Guarded component-recombined bridge; render and OIDN are operator-owned stages."""
import bpy,sys,json,hashlib,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from capture_modes import capture_mode,final_image,component_filter_policy
from transport_components import LIGHT_PASSES,split,recombine,partition_transmission
from png_precision_check import compare_opaque_pngs
from oidn_contract import validate_stats

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_exr(p):
 im=bpy.data.images.load(str(p),check_existing=False);w,h=im.size;a=np.empty(w*h*4,'f4');im.pixels.foreach_get(a);bpy.data.images.remove(im);a=a.reshape(h,w,4)[:,:,:3].copy();assert np.isfinite(a).all();return a

def write_pfm(p,a):
 h,w,c=a.shape;assert c==3
 with p.open('xb') as f:f.write(f'PF\n{w} {h}\n-1.0\n'.encode());f.write(a.astype('<f4').tobytes())

def read_pfm(p):
 with p.open('rb') as f:
  assert f.readline().strip()==b'PF';w,h=map(int,f.readline().split());scale=float(f.readline());assert abs(scale)==1;a=np.frombuffer(f.read(),dtype='<f4' if scale<0 else '>f4').reshape(h,w,3).copy()
 assert np.isfinite(a).all();return a

def stats(a):return {'min':float(a.min()),'max':float(a.max()),'mean':float(a.mean()),'finite':bool(np.isfinite(a).all()),'nonzero_pixel_fraction':float(np.mean(np.any(a!=0,axis=2))),'size':[a.shape[1],a.shape[0]]}

def save(a,path,scene,linear=None):
 h,w,c=a.shape;im=bpy.data.images.new(path.stem,width=w,height=h,float_buffer=True);rgba=np.ones((h,w,4),'f4');rgba[:,:,:3]=a;im.pixels.foreach_set(rgba.ravel());im.update()
 try:
  if linear:
   # Image.save() applies its image-save color space, even to an EXR. Use
   # the scene's explicit linear32 render-output route and verify readback.
   settings=scene.render.image_settings
   previous={k:getattr(settings,k) for k in ['file_format','color_mode','color_depth','exr_codec']}
   try:
    settings.file_format='OPEN_EXR';settings.color_mode='RGB';settings.color_depth='32';settings.exr_codec='ZIP'
    im.save_render(str(linear),scene=scene)
   finally:
    for k,v in previous.items():setattr(settings,k,v)
   assert np.array_equal(read_exr(linear),np.asarray(a,dtype=np.float32)),'Linear EXR must preserve every float32 component'
  im.save_render(str(path),scene=scene)
 finally:bpy.data.images.remove(im)

def main(mode,report_path):
 rep=json.loads(Path(report_path).read_text());job=rep['job'];assert capture_mode(job)=='component-recombined' and rep['engine']=='CYCLES';policy=component_filter_policy(job);both=(policy=='filter_both')
 source=Path(job['source']);assert sha(source)==rep['source_sha256'];bpy.ops.wm.open_mainfile(filepath=str(source));scene=bpy.data.scenes[job['scene']] if job.get('scene') else bpy.context.scene
 for k,v in rep['display_settings'].items():setattr(scene.view_settings,k,v)
 scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_depth='16';scene.render.image_settings.color_mode='RGB';scene.render.dither_intensity=0
 raw=Path(job['output']);g=raw.parent/(raw.stem+'_guides');out=g/'components';guides=dict(zip(['beauty','albedo','normal'],rep['guide_paths']));transport=rep['transport_paths'];assert set(transport)==set(LIGHT_PASSES)
 if mode=='export':
  assert not out.exists(),'Fresh component directory required';out.mkdir()
  paths={**guides,**transport};data={k:read_exr(v) for k,v in paths.items()};state=split(data);np.savez_compressed(out/'linear_component_accounting.npz',**state)
  features={'beauty':stats(state['physical_remainder']),'albedo':stats(data['albedo']),'normal':stats(data['normal'])};contract=validate_stats(features,require_nonzero_features=True);assert contract['valid'],contract
  comparison={'available':False,'reason':'No independent comparison requested; exact within-capture identity and source/dependency immutability are checked.'}
  if job.get('component_reference_beauty'):
   ref=job['component_reference_beauty'];assert isinstance(ref,dict) and set(ref)=={'path','sha256'};assert sha(ref['path'])==ref['sha256'];control=read_exr(ref['path']);assert control.shape==data['beauty'].shape
   equal=np.array_equal(control,data['beauty']);comparison={'available':True,'reference':ref,'equal_float32':equal,'max_abs':float(abs(control.astype('f8')-data['beauty']).max())};assert equal,'Independent raw beauty differs; investigate before filtering'
  save(data['beauty'],out/'identity_raw_passthrough.png',scene);native=compare_opaque_pngs(raw,out/'identity_raw_passthrough.png');assert native['bit_depth']==16 and native['opaque'] and native['max_error_native']<=1
  save(state['transmission_emission'],out/'REVIEW_retained_signal.png',scene);save(state['physical_remainder'],out/'REVIEW_raw_remainder.png',scene)
  for n,a in [('remainder',state['physical_remainder']),('albedo',data['albedo']),('normal',data['normal'])]:write_pfm(out/(n+'.pfm'),a)
  transmission_contract=None;signed_accounting=None
  if both:
   transmission,signed=partition_transmission(state);assert np.any(transmission>0),'Two-component filtering requires a nonempty positive transmission input'
   signed_accounting={'negative_channel_count':int((signed<0).sum()),'negative_pixel_count':int(np.any(signed<0,axis=2).sum()),'min':float(signed.min()),'sum':float(signed.astype('f8').sum()),'signed_bytes_sha256':hashlib.sha256(signed.tobytes()).hexdigest(),'signed_terms_untouched':True,'relative_guard':2.**-16,'partition':'Positive T is filtered; original negative T terms remain outside filtering and are added back with untouched delta64.'}
   assert np.array_equal(recombine(state,state['physical_remainder'],transmission),data['beauty']),'Signed-partition identity failed'
   transmission_contract=validate_stats({'beauty':stats(transmission),'albedo':stats(data['albedo']),'normal':stats(data['normal'])},require_nonzero_features=True);assert transmission_contract['valid'],transmission_contract
   write_pfm(out/'transmission.pfm',transmission)
  r={'source_sha256':sha(source),'script_sha256':sha(__file__),'component_state_sha256':sha(out/'linear_component_accounting.npz'),'input_paths':paths,'pass_hashes':{k:sha(v) for k,v in paths.items()},'filter_inputs':{n:sha(out/(n+'.pfm')) for n in (['remainder','albedo','normal','transmission'] if both else ['remainder','albedo','normal'])},'identity_exact_float32':True,'physical_pass_relative_guard':2.**-16,'guard_scope':'Numerical integration threshold tied to native16 relative precision; not a material calibration or universal floating-point error theorem','native16_identity_roundtrip':native,'feature_contract':contract,'independent_comparison':comparison,'transmission_stats':stats(state['transmission_emission']),'physical_remainder_stats':features['beauty'],'roundoff_residual_max_abs':float(abs(state['roundoff_residual']).max()),'samples':rep['effective_capture']['cycles']['samples'],'visual_noise_acceptance':False,'component_filter_policy':policy,'transmission_feature_contract':transmission_contract,'signed_transmission_accounting':signed_accounting,'filter_scope':('Transmission/emission and the diffuse/glossy/environment/volume remainder are filtered separately; signed transmission roundoff and float64 arithmetic residual are retained unchanged.' if both else 'Only physical diffuse/glossy/environment/volume remainder. Transmission/emission and float64 arithmetic residual are retained unchanged.')};(out/'export_receipt.json').write_text(json.dumps(r,indent=2))
 elif mode=='import':
  r=json.loads((out/'export_receipt.json').read_text());assert r['script_sha256']==sha(__file__) and r['source_sha256']==sha(source);assert r.get('component_filter_policy','retain_transmission')==policy
  assert r['component_state_sha256']==sha(out/'linear_component_accounting.npz')
  for k,h in r['pass_hashes'].items():assert sha(r['input_paths'][k])==h
  for k,h in r['filter_inputs'].items():assert sha(out/(k+'.pfm'))==h
  d=read_pfm(out/'denoised_remainder.pfm');state=np.load(out/'linear_component_accounting.npz');filtered_t=read_pfm(out/'denoised_transmission.pfm') if both else None;final=recombine(state,d,filtered_t);image=final_image(job);assert not image.exists()
  save(d,out/'REVIEW_filtered_remainder.png',scene,out/'denoised_remainder_linear.exr')
  if both:save(filtered_t,out/'REVIEW_filtered_transmission.png',scene,out/'denoised_transmission_linear.exr')
  save(final,image,scene,out/'component_recombined_linear.exr')
  r.update(output=str(image),output_sha256=sha(image),linear_output_sha256=sha(out/'component_recombined_linear.exr'),denoised_remainder_sha256=sha(out/'denoised_remainder.pfm'),clipping=False,transmission_emission_untouched=not both,both_components_filtered=both,delta64_untouched=True,signed_transmission_terms_untouched=True,noise_acceptance=False,quality_acceptance=False)
  if both:r['denoised_transmission_sha256']=sha(out/'denoised_transmission.pfm')
  (out/'component_receipt.json').write_text(json.dumps(r,indent=2))
 else:raise ValueError(mode)
 assert sha(source)==rep['source_sha256']
if __name__=='__main__':main(*sys.argv[sys.argv.index('--')+1:])
