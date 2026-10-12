"""Correct illuminant conversion and native environment longitude, preserving A.

One luminance scalar preserves the established horizontal gray-card exposure.
No channel grading or exposure adjustment is applied to scene output.
"""
from rebuild_lagoon_v11b import *
OUT_B=R/'evidence/lagoon-restoration-v11b';OUT_B.mkdir(exist_ok=True)

def corrected_light():
 sky=read_pfm(R/'evidence/coherent-daylight/native_sky.pfm');h,w=sky.shape[:2]
 theta=(np.arange(h)+.5)*np.pi/h;phi=(np.arange(w)+.5)*2*np.pi/w
 world_z=np.sin(theta)[:,None]*np.sin(phi)[None,:]
 # Integrate exactly over each lat-long pixel's horizontal projected solid angle.
 t=np.linspace(0,np.pi,h+1);p=np.linspace(0,2*np.pi,w+1)
 weights=(.5*np.diff(t)-.25*np.diff(np.sin(2*t)))[:,None]*np.maximum(np.cos(p[:-1])-np.cos(p[1:]),0)[None,:]
 assert abs(weights.sum()-np.pi)<1e-12
 # This is illuminant radiance. Reflectance-relative WHITE must not be applied.
 rgb=np.array([1.,1.015,1.035]);control=np.linalg.solve(M,rgb)
 assert control.min()>0 and np.max(abs(M@control-rgb))<1e-12
 shape=np.where(world_z>0,(1+2*world_z)/3,.16)
 over=shape[:,:,None]*control
 new=.2*sky+.8*over;sun=.2*np.asarray(DAY['native_solar_irradiance_controls'])
 oldE=(sky*weights[:,:,None]).sum((0,1))+np.asarray(DAY['native_solar_irradiance_controls'])*DAY['sun_direction'][2]
 newE=(new*weights[:,:,None]).sum((0,1))+sun*DAY['sun_direction'][2]
 lum=np.array([.2126729,.7151522,.072175]);factor=float((M@oldE)@lum/((M@newE)@lum))
 new*=factor;sun*=factor
 write_pfm(OUT_B/'coastal_diffuse_sky.pfm',new)
 result={'longitude_convention':'u = atan2(world_z,world_x)/(2*pi), wrapped into [0,1); phi = 2*pi*u',
 'corrections_to_v11a':['Removed erroneous pi longitude offset; upper sky now occupies world_z > 0','Converted illuminant radiance directly through inverse observer matrix, without reflectance white scaling'],
 'clear_fraction':.2,'overcast_fraction':.8,'upper_angular_luminance':'(1+2*world_z)/3',
 'single_horizontal_luminance_scalar':factor,'native_sun':sun.tolist(),'linear_rgb_irradiance':(M@(newE*factor)).tolist(),
 'reference_linear_rgb_irradiance':(M@oldE).tolist(),'expected_gray_card_rgb':(M@(newE*factor)*.18/np.pi).tolist(),
 'direct_illuminant_colorimetric_error':float(abs(M@control-rgb).max()),'map_sha256':digest(OUT_B/'coastal_diffuse_sky.pfm'),
 'source':'CIE overcast angular shape plus retained Nishita field; authored cloud mixture, no measured weather or volumetric cloud claim','exposure':1.05}
 (OUT_B/'LIGHT.json').write_text(json.dumps(result,indent=2));return result

def fixture():
 info=corrected_light();s=Scene();s.settings(48,48,256,3,2,16,20261012,1.05)
 s.camera((0,0,3),(0,0,0),(0,1,0),30);mat=s.material('diffuse',(.18,.18,.18));s.emit('quad',mat,1,(-2,-2,0),(4,0,0),(0,4,0),(0,0,0))
 s.emit('observer',json.dumps(str(R/'work/cybr-light/data/CIE_xyz_1931_2deg.csv')))
 s.emit('environment',(0,0,0),1);s.emit('envmap',json.dumps(str(OUT_B/'coastal_diffuse_sky.pfm')),0)
 s.emit('environment_sun',DAY['sun_direction'],info['native_sun'],DAY['solar_radius_radians'])
 report=render(s,OUT_B/'horizontal_card');film=read_pfm(OUT_B/'horizontal_card.pfm');mean=film.mean((0,1));expected=np.asarray(info['expected_gray_card_rgb'])
 ratio=mean/expected;assert np.max(abs(ratio-1))<.025,ratio
 info['native_card']={'mean_linear_rgb':mean.tolist(),'expected':expected.tolist(),'channel_ratios':ratio.tolist(),'passed':True,'render_seconds':report['render_seconds']}
 (OUT_B/'LIGHT.json').write_text(json.dumps(info,indent=2));(OUT_B/'DAYLIGHT_FIXTURE.json').write_text(json.dumps(info,indent=2));print('DAYLIGHT_FIXTURE',json.dumps(info),flush=True)

if __name__=='__main__':fixture()
