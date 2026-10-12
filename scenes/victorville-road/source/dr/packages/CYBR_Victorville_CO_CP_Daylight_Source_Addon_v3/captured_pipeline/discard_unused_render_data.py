"""Remove only zero-user in-memory render leftovers, without scene/file edits."""
import bpy,gc,json,hashlib

def active_identity(scene):
    rows=[]
    for obj in sorted(scene.objects,key=lambda o:o.name):
        rows.append((obj.name,obj.as_pointer(),None if obj.data is None else obj.data.as_pointer(),[list(row) for row in obj.matrix_world],obj.hide_render,[s.material.as_pointer() if s.material else None for s in obj.material_slots]))
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()

def apply(scene):
    before=active_identity(scene);records=[]
    # Unlinked object/collection cleanup is deliberately excluded. Only data
    # with no users can be removed; fake-user pins therefore remain protected.
    for _ in range(4):
        changed=0
        for kind in ('meshes','curves','materials','node_groups','textures','images'):
            collection=getattr(bpy.data,kind)
            for data in list(collection):
                if data.users!=0 or data.library is not None:continue
                if kind=='images' and data.type in ('RENDER_RESULT','COMPOSITING'):continue
                row={'kind':kind,'name':data.name,'users':0}
                if kind=='meshes':row.update(vertices=len(data.vertices),loops=len(data.loops),polygons=len(data.polygons))
                if kind=='images':row.update(size=list(data.size),source=data.source)
                records.append(row);collection.remove(data);changed+=1
        if not changed:break
    gc.collect()
    if active_identity(scene)!=before:raise ValueError('Active scene identity changed during unused data release')
    return {'removed_unused_datablocks':records,'active_object_data_material_transform_identity_sha256':before,'active_identity_preserved':True,'scene_file_saved':False,'scope':'Zero-user in-memory datablocks only. No active scene geometry, assigned shader or source file was altered.'}
