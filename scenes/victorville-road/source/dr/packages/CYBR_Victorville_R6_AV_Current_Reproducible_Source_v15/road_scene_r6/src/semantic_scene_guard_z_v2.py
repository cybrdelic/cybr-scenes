"""Stable, strict Y admission for portable finite-film regeneration.
Protects mesh/instance data as values and hashes, never process-local pointers.
"""
import hashlib,json
import prepare_physical_lenses as u

def scene_snapshot(bpy):
    record=u.protected_snapshot(bpy,list(bpy.data.objects),set(),set())
    if any(o.type not in {'MESH','LIGHT','CAMERA','EMPTY'} for o in bpy.data.objects):
        raise ValueError('Unsupported geometry type in semantic source guard')
    record['mesh_corner_normals']={m.name:u.data_digest(m.corner_normals,'vector',3,'f4') for m in bpy.data.meshes}
    modifiers={}
    for ob in bpy.data.objects:
        rows=[]
        for mod in ob.modifiers:
            if mod.type!='NODES':raise ValueError('Unsupported modifier in source guard: '+ob.name+'/'+mod.type)
            rows.append(dict(name=mod.name,type=mod.type,show_render=mod.show_render,show_viewport=mod.show_viewport,node_group=mod.node_group.name if mod.node_group else None,inputs={k:u.stable_value(v) for k,v in mod.items()}))
        modifiers[ob.name]=rows
    record['object_modifiers']=modifiers
    record['collection_instance_order']={c.name:dict(objects=[o.name for o in c.objects],children=[v.name for v in c.children],hide_render=c.hide_render) for c in bpy.data.collections}
    # Every image is a pinned packed input in this scene. Fail closed for a new
    # unpacked dependency rather than trusting a path that may resolve elsewhere.
    if any(not v['packed_sha256'] for v in record['images'].values()):raise ValueError('Unpacked image requires an explicit content hash contract')
    return record

def digest_record(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_scene(bpy,guard):
    got=scene_snapshot(bpy);actual=digest_record(got)
    if actual!=guard['semantic_sha256']:
        changed=[k for k in sorted(set(got)|set(guard['snapshot'])) if got.get(k)!=guard['snapshot'].get(k)]
        raise ValueError('Rebuilt Y semantic source differs: '+', '.join(changed))
    return actual
