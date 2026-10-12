"""Run with Blender to exercise actual HDR serialization and PNG display paths."""
import bpy,sys,json,hashlib,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from component_image_bridge import save,read_exr,read_pfm
from png_precision_check import compare_opaque_pngs
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=False)
s=bpy.context.scene;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='16';s.render.image_settings.exr_codec='PIZ';s.render.dither_intensity=0
values=np.array([-0.25,0,.00001,.001,.01,.18,.5,1,2,10,100,1e4],dtype='f4');a=np.repeat(values[:,None],3,axis=1).reshape(3,4,3)
cases={'signed_hdr':a}
if len(sys.argv)>sys.argv.index('--')+2:cases['retained_filtered_remainder']=read_pfm(Path(sys.argv[sys.argv.index('--')+2]))
results={}
for name,a in cases.items():
 before={k:getattr(s.render.image_settings,k) for k in ['file_format','color_mode','color_depth','exr_codec']}
 save(a,out/(name+'_direct.png'),s)
 save(a,out/(name+'_with_exr.png'),s,out/(name+'.exr'))
 after={k:getattr(s.render.image_settings,k) for k in before}
 roundtrip=read_exr(out/(name+'.exr'));assert np.array_equal(roundtrip,a),name
 png=compare_opaque_pngs(out/(name+'_direct.png'),out/(name+'_with_exr.png'));assert png['max_error_native']==0,name
 assert before==after,'Save changed display output settings'
 results[name]={'linear_float32_exact':True,'display_png_exact':True,'native_png_comparison':png,'scene_settings_restored':True,'min':float(a.min()),'max':float(a.max())}
report={'bridge_sha256':hashlib.sha256((Path(__file__).parent/'component_image_bridge.py').read_bytes()).hexdigest(),'blender_version':bpy.app.version_string,'cases':results}
(out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
