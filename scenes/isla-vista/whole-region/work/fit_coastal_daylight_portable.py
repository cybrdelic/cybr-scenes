"""Fit-only regeneration into the nonnegative CYBR LIGHT spectral basis.

The fit reproduces linear RGB under LIGHT's CIE observer, not a unique physical
spectrum. Sky and solar residual share one luminance-normalization scalar.

After ./run.sh setup and ./run.sh fetch, regenerate the source arrays with
Blender 4.3 (a separate optional dependency), then run the fit from this root:
  blender --background --python work/export_coastal_daylight.py -- evidence/coherent-daylight
  .venv/bin/python work/fit_coastal_daylight_portable.py
Keep the authored COHERENT_DAYLIGHT.json normalization receipt in place first.
This replaces native_sky.pfm and the fit receipt; it does not run native renders.
Independent current native fixture/daylight tests belong to ../tests and the
reviewed runtime snapshot at ../vendor/light-scene-compat. Their results are
not inferred from this RGB fit, which does not establish measured local weather.
"""
from pathlib import Path
import numpy as np,json,math,hashlib
root=Path(__file__).resolve().parent.parent;d=root/'evidence/coherent-daylight';light=root/'work/cybr-light'
# The retained daylight receipt is the normalization input. Its horizontal
# reference irradiance was frozen during the earlier gray-card calibration.
normalization_input=json.loads((d/'COHERENT_DAYLIGHT.json').read_text())
obs=np.loadtxt(light/'data/CIE_xyz_1931_2deg.csv',delimiter=',');nm=obs[:,0];w=np.exp(-.5*((nm[:,None]-[610,545,450])/[43,34,27])**2);w/=w.sum(1)[:,None]
# Exact renderer convention:360..830nm, tabulated CIE1931,106.856917101 normalization.
xyz=np.trapezoid(obs[:,1:,None]*w[:,None,:],nm,axis=0)/106.856917101
xyz_to_rgb=np.array([[3.2404542,-1.5371385,-.4985314],[-.969266,1.8760108,.041556],[.0556434,-.2040259,1.0572252]])
M=xyz_to_rgb@xyz;inverse=np.linalg.inv(M)
rec=json.loads((d/'NISHITA_EXPORT.json').read_text())
from scipy.spatial import cKDTree
source=np.load(d/'panorama_sky_without_solar_disc.npy').astype(float);directions=np.load(d/'panorama_world_directions.npy').astype(float);directions/=np.linalg.norm(directions,axis=2)[...,None]
h,w=512,1024;yy,xx=np.mgrid[0:h,0:w];theta=(yy+.5)*math.pi/h;phi=(xx+.5)*2*math.pi/w;target=np.stack([np.sin(theta)*np.cos(phi),np.cos(theta),np.sin(theta)*np.sin(phi)],-1)
distance,index=cKDTree(directions.reshape(-1,3)).query(target.reshape(-1,3),k=4,workers=2);weight=1/np.maximum(distance,1e-10)**2;weight/=weight.sum(1)[:,None];sky=(source.reshape(-1,3)[index]*weight[...,None]).sum(1).reshape(h,w,3);angle=float(np.degrees(2*np.arcsin(distance[:,0].max()/2)));assert angle<.5,angle;rec['maximum_nearest_direction_resampling_error_deg']=angle
np.save(d/'sky_without_solar_disc.npy',sky)
sun=np.array(rec['solar_residual_irradiance_linear_rgb']);native_sky=sky@inverse.T;native_sun=inverse@sun
minimum=min(native_sky.min(),native_sun.min());assert minimum>=-1e-8,('Unrepresentable daylight; refusing clipping',minimum)
error=max(float(np.max(abs(native_sky@M.T-sky))),float(np.max(abs(M@native_sun-sun))))
assert error<1e-5;native_sky=np.maximum(native_sky,0);native_sun=np.maximum(native_sun,0)
def weights(h,w):
 t=np.linspace(0,math.pi,h+1);p=np.linspace(0,2*math.pi,w+1);a=.5*np.diff(t)-.25*np.diff(np.sin(2*t));b=np.maximum(np.cos(p[:-1])-np.cos(p[1:]),0);q=a[:,None]*b[None,:];assert abs(q.sum()-math.pi)<1e-12;return q
direction=np.array(rec['sun_direction']);oldrgb=np.array(normalization_input['old_horizontal_irradiance_linear_rgb'])
newE=(sky*weights(*sky.shape[:2])[...,None]).sum((0,1))+sun*direction[2]
y=np.array([.2126729,.7151522,.072175]);scale=float(oldrgb@y/(newE@y));native_sky*=scale;native_sun*=scale
assert scale>0 and math.isfinite(scale)
def pfm(path,a):
 a=np.asarray(a,np.float32)
 with path.open('wb') as f:f.write(f'PF\n{a.shape[1]} {a.shape[0]}\n-1.0\n'.encode());np.flipud(a).tofile(f)
pfm(d/'native_sky.pfm',native_sky)
report={**rec,'native_solar_irradiance_controls':native_sun.tolist(),'solar_radius_radians':math.radians(.266),'native_basis_to_linear_rgb':M.tolist(),'linear_rgb_to_native_basis':inverse.tolist(),'minimum_unscaled_spectral_control':float(minimum),'colorimetric_roundtrip_max_absolute_error':error,'one_source_luminance_scale':scale,'old_horizontal_irradiance_linear_rgb':oldrgb.tolist(),'new_horizontal_irradiance_linear_rgb':(newE*scale).tolist(),'luminance_ratio_after_scaling':float(newE@ y*scale/(oldrgb@y)),'normalization':'One positive global source scalar from the unoccluded horizontal18%Lambertian-card limit; same source scalar for sky and solar residual. No exposure, channel grading or material changes.','source_colorimetry':'Blender scene-linear RGB converted by inverse integrated LIGHT basis/CIE matrix. Nonnegative control and round-trip tests gate adoption.','native_sky_sha256':hashlib.sha256((d/'native_sky.pfm').read_bytes()).hexdigest()}
# A successful fit is not an independent native-render validation pass.
report['native_render_validation']={'performed':False,'scope':'Fit-only regeneration. Run the independent current native fixture/daylight tests in ../tests against the reviewed ../vendor/light-scene-compat runtime snapshot.'}
(d/'COHERENT_DAYLIGHT.json').write_text(json.dumps(report,indent=2)+'\n')
print('COHERENT_DAYLIGHT_FIT_ONLY',json.dumps(report),flush=True)
