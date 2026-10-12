import bpy,sys,pathlib,json,hashlib,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from png_precision_check import compare_opaque_pngs, _read as read_native_png
from capture_modes import capture_mode
from oidn_contract import validate_stats
args=sys.argv[sys.argv.index('--')+1:];mode,report_path=args[:2];rep=json.load(open(report_path));job=rep['job'];capture_kind=capture_mode(job);assert hashlib.sha256(pathlib.Path(job['source']).read_bytes()).hexdigest()==rep['source_sha256'];bpy.ops.wm.open_mainfile(filepath=job['source']);s=bpy.data.scenes[job['scene']] if job.get('scene') else bpy.context.scene;bpy.context.window.scene=s
out=pathlib.Path(job['output']);gd=out.parent/(out.stem+'_guides');s.render.image_settings.file_format='PNG';s.render.image_settings.color_depth=str(out.read_bytes()[24]);s.render.image_settings.color_mode='RGB'
names=['beauty','albedo','normal'];recorded=rep.get('guide_paths');guide_paths=dict(zip(names,map(pathlib.Path,recorded))) if recorded else {n:gd/(n+'_'+str(rep.get('frame',s.frame_current)).zfill(4)+'.exr') for n in names}
if mode!='inspect_png':assert set(guide_paths)==set(names) and all(p.is_file() for p in guide_paths.values()),'Missing recorded guide files'
for k,v in rep.get('display_settings',{}).items():setattr(s.view_settings,k,v)
if 'dither_intensity' in job:s.render.dither_intensity=job['dither_intensity']
if mode=='inspect_png':
 assert capture_kind=='unfiltered' and rep['engine']=='BLENDER_WORKBENCH'
 depth,pixels=read_native_png(out);maximum=(1<<depth)-1;opaque=bool(np.all(pixels[:,:,3]==maximum));assert opaque
 native={'bit_depth':depth,'opaque':opaque,'width':pixels.shape[1],'height':pixels.shape[0],'validation':'Native PNG decode only; Workbench geometry study, no radiometric bridge'}
 out.with_suffix('.png.native.json').write_text(json.dumps(native,indent=2));print('VALIDATED_GEOMETRY_PNG',json.dumps(native),flush=True)
elif mode=='export':
 stats={}
 for name in ['beauty','albedo','normal']:
  p=guide_paths[name];im=bpy.data.images.load(str(p),check_existing=False);w,h=im.size;a=np.empty(w*h*4,np.float32);im.pixels.foreach_get(a);a=a.reshape(h,w,4)[:,:,:3].copy();finite=np.isfinite(a)
  if name=='beauty' or capture_kind=='guided':assert finite.all()
  values=a[finite]
  with open(gd/(name+'.pfm'),'wb') as f:f.write(f'PF\n{w} {h}\n-1.0\n'.encode());f.write(a.astype('<f4').tobytes())
  stats[name]={'size':[w,h],'min':float(values.min()) if values.size else 0.,'max':float(values.max()) if values.size else 0.,'mean':float(values.mean()) if values.size else 0.,'finite_value_count':int(values.size),'colorspace':im.colorspace_settings.name,'finite':bool(np.isfinite(a).all()),'nonzero_pixel_fraction':float(np.count_nonzero(np.any(a!=0,axis=2))/(w*h))}
  if name=='beauty':
   im.save_render(str(gd/'raw_passthrough.png'),scene=s);check=compare_opaque_pngs(out,gd/'raw_passthrough.png');(gd/'png_roundtrip_check.json').write_text(json.dumps(check,indent=2));assert check['max_error_native']<=1,'Native-precision PNG color bridge mismatch'
 (gd/'guide_stats.json').write_text(json.dumps(stats,indent=2));opaque_features=(job.get('guide_albedo_pass')=='OIDN_SurfaceReflectivity' and job.get('guide_normal_pass')=='OIDN_SurfaceNormal');contract=validate_stats(stats,require_nonzero_features=opaque_features);contract['nonzero_coverage_required']=opaque_features;(gd/'guide_contract.json').write_text(json.dumps(contract,indent=2));
 if capture_kind=='guided':assert contract['valid'],'OIDN input contract violation: '+str(contract['violations'])
 print('EXPORTED_GUIDES',json.dumps(stats),flush=True)
elif mode=='import':
 assert capture_kind=='guided','Unfiltered capture must never import OIDN output'
 p=gd/'denoised.pfm'
 with open(p,'rb') as f:
  assert f.readline().strip()==b'PF';w,h=map(int,f.readline().split());scale=float(f.readline());a=np.frombuffer(f.read(),dtype='<f4' if scale<0 else '>f4').reshape(h,w,3).copy()
 assert np.isfinite(a).all();im=bpy.data.images.load(str(guide_paths['beauty']),check_existing=False);rgba=np.ones((h,w,4),np.float32);rgba[:,:,:3]=a;im.pixels.foreach_set(rgba.ravel());im.update();im.filepath_raw=str(gd/'denoised_linear.exr');im.file_format='OPEN_EXR';im.save();clean=out.parent/('CLEAN_OIDN_'+out.stem.removeprefix('INTERNAL_')+'.png');im.save_render(str(clean),scene=s);print('DENOISED_PNG',str(clean),flush=True)

else:raise ValueError('Unsupported bridge mode: '+mode)
