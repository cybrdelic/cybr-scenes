"""CO single-source Nishita daylight candidate. Materials/geometry/view untouched."""
from pathlib import Path
import math,json,hashlib
import bpy
import numpy as np
from align_context_daylight_bt import sky_direction

def apply(scene,cfg,out):
 assert set(cfg)=={'revision','card','card_sha256'} and cfg['revision']==1
 p=Path(cfg['card']);assert hashlib.sha256(p.read_bytes()).hexdigest()==cfg['card_sha256'];cal=json.loads(p.read_text());c=cal['candidate']
 sun=scene.objects['Daylight / sun'];skies=[n for n in scene.world.node_tree.nodes if n.type=='TEX_SKY'];bgs=[n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND'];assert len(skies)==len(bgs)==1
 sk,bg=skies[0],bgs[0];assert sk.sky_type=='NISHITA' and not sk.sun_disc and not sk.inputs['Vector'].is_linked
 assert np.allclose(sk.texture_mapping.rotation,[0,0,0]) and np.allclose(sk.texture_mapping.scale,[1,1,1])
 assert abs(math.degrees(sk.sun_elevation)-34)<1e-4 and abs(bg.inputs['Strength'].default_value-.11)<1e-7 and abs(sun.data.energy-3.4)<1e-6
 view=[scene.view_settings.view_transform,scene.view_settings.look,scene.view_settings.exposure,scene.view_settings.gamma]
 lights={o.name:{'hidden':o.hide_render,'type':o.data.type,'energy':o.data.energy}for o in scene.objects if o.type=='LIGHT'};assert set(lights)=={'Daylight / sun'}
 before={'elevation_deg':math.degrees(sk.sun_elevation),'toward_sun':sky_direction(sk.sun_elevation,sk.sun_rotation).tolist(),'separate_sun_energy':sun.data.energy,'separate_sun_rgb':list(sun.data.color),'separate_sun_diameter_deg':math.degrees(sun.data.angle),'sky_strength':bg.inputs['Strength'].default_value,'disc':sk.sun_disc}
 sun.hide_render=True;sun.data.energy=0
 sk.sun_disc=True;sk.sun_intensity=1.;sk.sun_size=math.radians(c['sun_diameter_deg']);sk.sun_elevation=math.radians(c['elevation_deg']);sk.sun_rotation=math.radians((90-c['azimuth_deg'])%360);bg.inputs['Strength'].default_value=c['world_strength']
 for k in('altitude','air_density','dust_density','ozone_density'):
  expected=c['altitude_m']if k=='altitude'else c[k];assert abs(getattr(sk,k)-expected)<1e-5
 after={'elevation_deg':math.degrees(sk.sun_elevation),'toward_sun':sky_direction(sk.sun_elevation,sk.sun_rotation).tolist(),'native_solar_diameter_deg':math.degrees(sk.sun_size),'native_sun_intensity':sk.sun_intensity,'sky_strength':bg.inputs['Strength'].default_value,'sky_model':'NISHITA','disc_enabled':sk.sun_disc,'separate_sun_disabled':sun.hide_render and sun.data.energy==0,'air_density':sk.air_density,'dust_density':sk.dust_density,'ozone_density':sk.ozone_density,'altitude_m':sk.altitude}
 assert view==[scene.view_settings.view_transform,scene.view_settings.look,scene.view_settings.exposure,scene.view_settings.gamma]
 rec={'revision':'CO1','before':before,'after':after,'card_calibration':cal,'unchanged':['CN reflectance','all scene geometry and placements','original mountain shapes','existing fixed mountain material-airlight approximation','camera','exposure and view transform','path-tracing bounce counts','texture tier'],'one_solar_source':True,'sun_sampling':'Cycles4.3 native Nishita dedicated solar-disc guiding; exactly one untransformed sky texture; separate SUN disabled.','normalization':'Scalar source energy only matches horizontal diffuse-card luminance. Native solar/sky ratio and spectral variation remain model outputs, not separately tuned or post-graded.','limitations':['Authored daytime direction and atmospheric settings; not measured weather/time at a Victorville site.','Inherited far-ridge airlight remains a surface approximation, not true volumetric atmosphere.','This changes source lighting only; no contrast enhancement or final-image color grading.']}
 (Path(out)/'DAYLIGHT_MODEL_CO.json').write_text(json.dumps(rec,indent=2)+'\n');print('DAYLIGHT_MODEL_CO',json.dumps(rec),flush=True);return rec
