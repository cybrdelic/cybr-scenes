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
    # Scene-level bindings and visibility must not slip through a datablock-only
    # check. Reject unsupported time-dependent evaluation instead of omitting it.
    animation_ids=list(bpy.data.objects)+list(bpy.data.meshes)+list(bpy.data.materials)+list(bpy.data.worlds)+list(bpy.data.scenes)+list(bpy.data.node_groups)+list(bpy.data.cameras)+list(bpy.data.lights)
    for block in animation_ids:
        if getattr(block,'animation_data',None) is not None:
            raise ValueError('Animation/drivers unsupported in semantic admission: '+block.name)
    if any(m.shape_keys is not None for m in bpy.data.meshes):raise ValueError('Shape keys unsupported in semantic admission')
    if any(len(o.constraints) for o in bpy.data.objects):raise ValueError('Object constraints unsupported in semantic admission')
    def fields(value,names):
        return {name:u.stable_value(getattr(value,name)) for name in names if hasattr(value,name)}
    def scalar_rna(value):
        return {p.identifier:u.stable_value(getattr(value,p.identifier)) for p in value.bl_rna.properties
                if p.identifier!='rna_type' and not p.is_readonly and p.type in {'BOOLEAN','INT','FLOAT','ENUM'}}
    def layer_tree(layer):
        return dict(name=layer.name,collection=layer.collection.name,exclude=layer.exclude,
                    holdout=layer.holdout,indirect_only=layer.indirect_only,hide_viewport=layer.hide_viewport,
                    children=[layer_tree(c) for c in layer.children])
    record['object_render_bindings']={o.name:dict(
        visibility=fields(o,('visible_camera','visible_diffuse','visible_glossy','visible_transmission','visible_volume_scatter','visible_shadow','is_holdout','is_shadow_catcher','show_instancer_for_render','instance_type')),
        instance_collection=o.instance_collection.name if o.instance_collection else None,
        parent=o.parent.name if o.parent else None,parent_type=o.parent_type,parent_bone=o.parent_bone,
        material_slots=[dict(link=s.link,material=s.material.name if s.material else None) for s in o.material_slots]) for o in bpy.data.objects}
    record['camera_depth_of_field']={c.name:scalar_rna(c.dof)|{'focus_object':c.dof.focus_object.name if c.dof.focus_object else None} for c in bpy.data.cameras}
    record['material_render_flags']={m.name:fields(m,('use_nodes','use_backface_culling','surface_render_method','use_transparency_overlap','use_transparent_shadow','diffuse_color','metallic','roughness')) for m in bpy.data.materials}
    record['world_bindings']={w.name:dict(use_nodes=w.use_nodes,color=list(w.color)) for w in bpy.data.worlds}
    scenes={}
    for scene in bpy.data.scenes:
        editor=scene.sequence_editor
        if editor is not None:
            if hasattr(editor,'sequences_all'):sequence_count=len(editor.sequences_all)
            elif hasattr(editor,'strips'):sequence_count=len(editor.strips)
            else:raise ValueError('Cannot inspect sequencer contents')
            if sequence_count:raise ValueError('Active sequencer evaluation unsupported in semantic admission')
        else:sequence_count=0
        rigid=scene.rigidbody_world
        if rigid is not None:
            collections=[getattr(rigid,name,None) for name in ('collection','constraints')]
            if any(c is not None and len(c.all_objects) for c in collections):
                raise ValueError('Active rigidbody evaluation unsupported in semantic admission')
        if any(getattr(o,'rigid_body',None) is not None or getattr(o,'rigid_body_constraint',None) is not None for o in scene.objects):
            raise ValueError('Object rigidbody evaluation unsupported in semantic admission')
        if scene.node_tree and scene.node_tree.animation_data is not None:raise ValueError('Animated compositor unsupported')
        if getattr(scene,'use_nodes',False):
            compositor=u.graph_signature(scene.node_tree)
        else:compositor=None
        scenes[scene.name]=dict(empty_evaluation_containers=dict(sequence_editor_present=editor is not None,sequence_count=sequence_count,rigidbody_world_present=rigid is not None),world=scene.world.name if scene.world else None,
            camera=scene.camera.name if scene.camera else None,frame_current=scene.frame_current,
            frame_subframe=scene.frame_subframe,frame_start=scene.frame_start,frame_end=scene.frame_end,
            root_collection=dict(name=scene.collection.name,objects=[o.name for o in scene.collection.objects],children=[c.name for c in scene.collection.children]),
            view_layers=[dict(name=v.name,use=v.use,material_override=v.material_override.name if v.material_override else None,
                pass_settings=scalar_rna(v),collection_tree=layer_tree(v.layer_collection)) for v in scene.view_layers],
            render=scalar_rna(scene.render),image_settings=scalar_rna(scene.render.image_settings),
            cycles=scalar_rna(scene.cycles),view_settings=scalar_rna(scene.view_settings),
            view_curve_mapping=u.stable_value(scene.view_settings.curve_mapping) if scene.view_settings.use_curve_mapping else None,
            display_settings=scalar_rna(scene.display_settings),unit_settings=scalar_rna(scene.unit_settings),
            use_nodes=scene.use_nodes,compositor_graph_sha256=compositor)
    record['scene_state']=dict(active_scene=bpy.context.scene.name,active_view_layer=bpy.context.view_layer.name,scenes=scenes)
    return record

def digest_record(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_scene(bpy,guard):
    got=scene_snapshot(bpy);actual=digest_record(got)
    if actual!=guard['semantic_sha256']:
        changed=[k for k in sorted(set(got)|set(guard['snapshot'])) if got.get(k)!=guard['snapshot'].get(k)]
        raise ValueError('Rebuilt Y semantic source differs: '+', '.join(changed))
    return actual
