"""Align the inherited Nishita sky azimuth with the actual Sun, Blender4.3.2.
No energy/exposure/color, geometry or material recipe edits. Sky disc stays off.
"""
import math,json
from pathlib import Path
import numpy as np

def sky_direction(elevation,rotation):
    lon=(2*math.pi-rotation)%(2*math.pi)+math.pi/2
    return np.array([math.cos(elevation)*math.cos(lon),math.cos(elevation)*math.sin(lon),math.sin(elevation)])

def apply(scene,config,out):
    import bpy
    if config!={'mode':'align_sky_to_existing_sun'}:raise ValueError('Explicit supported daylight alignment required')
    if bpy.app.version[:2]!=(4,3):raise ValueError('Direction convention qualified for Blender4.3')
    scene.view_layers.update() if hasattr(scene.view_layers,'update') else None
    sun=scene.objects.get('Daylight / sun')
    if sun is None or sun.type!='LIGHT' or sun.data.type!='SUN':raise ValueError('Expected Sun missing')
    for layer in scene.view_layers:layer.update()
    world=scene.world;nodes=world.node_tree.nodes
    skies=[q for q in nodes if q.type=='TEX_SKY'];backgrounds=[q for q in nodes if q.type=='BACKGROUND']
    if len(skies)!=1 or len(backgrounds)!=1:raise ValueError('Expected single physical sky/background')
    sky=skies[0]
    if sky.sky_type!='NISHITA' or sky.sun_disc or sky.inputs['Vector'].is_linked:raise ValueError('Expected unrotated Nishita with disc off')
    if not np.allclose(sky.texture_mapping.rotation,[0,0,0]) or not np.allclose(sky.texture_mapping.scale,[1,1,1]):raise ValueError('Unexpected sky texture transform')
    direction=np.asarray(sun.matrix_world)[:3,2].astype(float);direction/=np.linalg.norm(direction)
    elevation=math.asin(direction[2]);rotation=(math.pi/2-math.atan2(direction[1],direction[0]))%(2*math.pi)
    before=sky_direction(sky.sun_elevation,sky.sun_rotation);old_rotation=float(sky.sun_rotation)
    if abs(sky.sun_elevation-elevation)>1e-5 or abs(old_rotation-math.radians(225))>1e-5:raise ValueError('Inherited daylight state changed')
    energy=float(sun.data.energy);strength=float(backgrounds[0].inputs['Strength'].default_value);exposure=scene.view_settings.exposure
    sky.sun_rotation=rotation
    after=sky_direction(sky.sun_elevation,sky.sun_rotation)
    error=math.degrees(math.acos(float(np.clip(np.dot(direction,after),-1,1))))
    if error>1e-4 or sky.sun_disc or float(sun.data.energy)!=energy or float(backgrounds[0].inputs['Strength'].default_value)!=strength or scene.view_settings.exposure!=exposure:raise ValueError('Daylight alignment contract failed')
    result={'operation':'Align sky azimuth only to existing Sun','prior_sky_rotation_degrees':math.degrees(old_rotation),'corrected_sky_rotation_degrees':math.degrees(sky.sun_rotation),'elevation_degrees':math.degrees(sky.sun_elevation),'prior_direction_error_degrees':math.degrees(math.acos(float(np.clip(np.dot(direction,before),-1,1)))),'corrected_direction_error_degrees':error,'toward_sun_world':direction.tolist(),'sky_disc_enabled':False,'sun_energy_unchanged':energy,'sky_strength_unchanged':strength,'view_exposure_unchanged':exposure,'world_color_model_unchanged':True,'no_additional_light':True,'source_reference':'Blender4.3.2 Cycles shader_nodes.cpp simplify_settings + kernel/svm/sky.h geographical_to_direction','limitation':'Directionally consistent authored daylight; no claim of measured Victorville time/weather or calibrated solar irradiance.'}
    Path(out,'DAYLIGHT_ALIGNMENT.json').write_text(json.dumps(result,indent=2)+'\n');return result
