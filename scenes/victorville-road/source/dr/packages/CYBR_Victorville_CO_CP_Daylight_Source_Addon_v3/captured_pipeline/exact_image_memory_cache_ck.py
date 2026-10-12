"""Exact typed builtin image cache; drops redundant packed PNG bytes in RAM.

Qualified isolated Cycles control: packed repeat and typed cache RGB16 pixels
exactly equal for all six real maps. File-backed loading was NOT equivalent and
is not used. Source .blend and external native files are never written.
"""
from pathlib import Path
import bpy,hashlib,array,gc,json
NAMES=('BaseColor.png','Normal_Object_RGB16.png','Roughness.png','R5D_BaseColor.png','R5D_Normal.png','R5D_Roughness.png')
def file_sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pixel_sha(im):
 h=hashlib.sha256()
 for k in range(0,len(im.pixels),262144):h.update(array.array('f',im.pixels[k:k+262144]).tobytes())
 return h.hexdigest()
def apply(scene,cfg,out):
 assert cfg=={'revision':1,'map_tier':1024};rows=[]
 trees=list(bpy.data.node_groups)+[m.node_tree for m in bpy.data.materials if m.use_nodes]+[w.node_tree for w in bpy.data.worlds if w.use_nodes]+[s.node_tree for s in bpy.data.scenes if s.use_nodes]
 for name in NAMES:
  im=bpy.data.images.get(name);assert im and im.source=='FILE' and im.packed_file
  assert list(im.size)==[1024,1024],'Use only after established context mip preparation'
  path=Path(bpy.path.abspath(im.filepath)).resolve();source_sha=file_sha(path);assert hashlib.sha256(im.packed_file.data).hexdigest()==source_sha
  row=dict(name=name,source_path=str(path),source_file_sha256=source_sha,packed_bytes=im.packed_file.size,colorspace=im.colorspace_settings.name,alpha_mode=im.alpha_mode,is_float=im.is_float,source_channels=im.channels,size=list(im.size),decoded_f32_sha256=pixel_sha(im),nodes=[])
  vals=array.array('f',[0])*len(im.pixels);im.pixels.foreach_get(vals)
  new=bpy.data.images.new(name+' / exact typed render cache',width=1024,height=1024,alpha=True,float_buffer=im.is_float)
  new.colorspace_settings.name=im.colorspace_settings.name;new.alpha_mode=im.alpha_mode;new.pixels.foreach_set(vals);new.update();del vals
  assert pixel_sha(new)==row['decoded_f32_sha256'] and new.is_float==row['is_float'] and new.alpha_mode==row['alpha_mode'] and new.colorspace_settings.name==row['colorspace']
  new['cybr_exact_memory_cache']=True;new['cybr_original_path']=str(path);new['cybr_original_sha256']=source_sha;new['cybr_pixel_f32_sha256']=row['decoded_f32_sha256'];new['cybr_original_image_name']=name
  for tree in trees:
   if tree:
    for n in tree.nodes:
     if hasattr(n,'image') and n.image==im:
      row['nodes'].append(dict(tree=tree.name,node=n.name,interpolation=getattr(n,'interpolation',None),extension=getattr(n,'extension',None),projection=getattr(n,'projection',None)));n.image=new
  for tex in bpy.data.textures:
   if hasattr(tex,'image') and tex.image==im:tex.image=new
  if im.use_fake_user:new.use_fake_user=True;im.use_fake_user=False
  assert im.users==0,('Unmapped image users',name,im.users)
  bpy.data.images.remove(im);new.name=name;assert new.source=='GENERATED' and new.packed_file is None;rows.append(row);gc.collect()
 report=dict(revision='CK exact typed image memory cache',images=rows,redundant_packed_bytes_released=sum(r['packed_bytes']for r in rows),decoded_f32_pixels_storage_type_colorspace_alpha_exact=True,shader_node_interpolation_extension_projection_unchanged=True,map_tier=1024,geometry_material_parameters_source_files_changed=False,qualification='Isolated actual Cycles RGB16 emission-sampling control equals packed baseline and repeat exactly. Full scene is subsequently inspected; no native4096 sampling claim. File-backed texture path rejected after unequal pixels.',scope='In-memory generated image cache with original source file SHA and full decoded pixel hash retained. Removes original packed bytes only from derivative memory, never source files.')
 (Path(out)/'EXACT_IMAGE_MEMORY_CACHE_CK.json').write_text(json.dumps(report,indent=2)+'\n');print('EXACT_IMAGE_MEMORY_CACHE_CK',json.dumps({k:v for k,v in report.items()if k!='images'}),flush=True);return report
