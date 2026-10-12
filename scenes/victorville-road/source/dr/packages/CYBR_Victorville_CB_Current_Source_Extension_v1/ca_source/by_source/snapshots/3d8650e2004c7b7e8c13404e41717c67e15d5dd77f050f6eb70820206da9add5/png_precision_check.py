"""Read native PNG channels in Blender without PIL's RGB16-to-RGB8 conversion."""
import pathlib
import bpy,numpy as np
def _read(path):
 p=pathlib.Path(path);header=p.read_bytes()[:26];assert header[:8]==b'\x89PNG\r\n\x1a\n';depth=header[24];assert depth in (8,16)
 im=bpy.data.images.load(str(p),check_existing=False);im.colorspace_settings.name='Non-Color';w,h=im.size;a=np.empty(w*h*4,'f4');im.pixels.foreach_get(a);bpy.data.images.remove(im);a=a.reshape(h,w,4)
 return depth,np.rint(np.clip(a,0,1)*((1<<depth)-1)).astype('u4')
def compare_opaque_pngs(raw,passthrough):
 da,a=_read(raw);db,b=_read(passthrough);assert da==db and a.shape==b.shape,'PNG bridge shape/precision mismatch';maximum=(1<<da)-1
 opaque=bool(np.all(a[:,:,3]==maximum));assert opaque,'Nonopaque alpha requires an alpha-preserving bridge'
 err=np.abs(a[:,:,:3].astype('i4')-b[:,:,:3].astype('i4'))
 return {'bit_depth':da,'max_error_native':int(err.max()),'mean_error_native':float(err.mean()),'opaque':opaque}
