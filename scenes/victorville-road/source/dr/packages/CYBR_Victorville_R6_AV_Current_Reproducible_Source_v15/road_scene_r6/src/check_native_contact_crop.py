"""Diagnostic only: unfiltered exact native-pixel border of intended close view."""
import bpy,json,time
from pathlib import Path
from mathutils import Vector
r=Path(__file__).resolve().parents[1];bpy.ops.wm.open_mainfile(filepath=str(r/'preview/road_r6_i.blend'));s=bpy.context.scene
s.camera.location=(-3.62,.20,.26);s.camera.rotation_euler=(Vector((-3.2,1.05,.07))-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.lens=40
s.render.resolution_x=1800;s.render.resolution_y=1200;s.render.resolution_percentage=100;s.render.use_border=True;s.render.use_crop_to_border=True;s.render.border_min_x=.80;s.render.border_max_x=1;s.render.border_min_y=.18;s.render.border_max_y=.40
s.cycles.samples=64;s.cycles.use_denoising=False;s.cycles.device='CPU';s.render.threads_mode='FIXED';s.render.threads=2;s.render.image_settings.color_depth='16';s.render.filepath=str(r/'preview/i_contact_native_pixels.png');start=time.time();bpy.ops.render.render(write_still=True)
(r/'receipts/i_contact_native_pixels.json').write_text(json.dumps({'full_camera_raster':[1800,1200],'border_normalized':[.80,1,.18,.40],'samples':64,'denoising':False,'CPU_threads':2,'seconds':time.time()-start},indent=2))
