"""Read only the frozen camera object; export exact Blender projection parameters."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import bpy
from mathutils import Vector
O=Path(__file__).resolve().parent;R=O.parent;sys.path[:0]=[str(O),str(R/'low_ground_dp_native/runtime/src')]
from approved_density_lod import CameraProjection
from support_context import Support
S=R/'current_cache_source/checkpoint/COMMON_THROUGH_CM.blend';receipt=json.loads((R/'current_cache_source/checkpoint/CHECKPOINT.json').read_text())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
assert sha(S)=='e7e0ac8a1bcc1a03872296f1c6dabc711040bc956163bdcdb76a807a938d27ca'
name='Whole road with foreground material'
with bpy.data.libraries.load(str(S),link=False)as(src,dst):assert name in src.objects;dst.objects=[name]
scene=bpy.context.scene;camera=dst.objects[0];scene.collection.objects.link(camera);scene.camera=camera;scene.render.pixel_aspect_x=1;scene.render.pixel_aspect_y=1
s=Support();centre=np.array([-4.9,5.5]);height=s.sample(s.co[:,2],centre[None])[0]
views=[('normal_2000',2000,1334,[-5.5,4.8,.65],[-3.5,8.,.15],32),('macro_1800',1800,1350,[-4.835,5.32,float(height)+.18],[-4.9,5.5,float(height)],50)]
result={}
for key,w,h,loc,target,lens in views:
 scene.render.resolution_x=w;scene.render.resolution_y=h;scene.render.resolution_percentage=100;camera.location=(Vector(target)+Vector((.065,-.18,.18)))if key.startswith('macro')else Vector(loc);camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=lens;bpy.context.view_layer.update();p=CameraProjection(scene,w,h)
 result[key]={'width':p.width,'height':p.height,'inverse':p.inverse.tolist(),'f':p.f.tolist(),'offset':p.offset.tolist(),'near':p.near,'name':p.name,'lens':p.lens,'camera_location':list(camera.location),'camera_rotation':list(camera.rotation_euler),'blender_version':bpy.app.version_string}
result['source_camera_sha256']=sha(S);(O/'VIEW_PROJECTIONS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
