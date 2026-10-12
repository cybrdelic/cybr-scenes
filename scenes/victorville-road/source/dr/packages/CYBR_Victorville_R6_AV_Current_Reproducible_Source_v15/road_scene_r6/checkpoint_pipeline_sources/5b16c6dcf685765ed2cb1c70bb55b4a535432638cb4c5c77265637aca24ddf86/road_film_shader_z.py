"""Replace only local legacy road-dust masks with finite transported-film stock.
Intrinsic original asphalt, approved ground maps, paint alpha, geometry and
normal calibration remain untouched. Film opacity is explicitly uncalibrated.
"""
import bpy,numpy as np
DUST=(.308221809,.255643471,.183828350,1)
def apply(scene,image,axes):
    x,y=axes;copies={};records=[]
    objects=[o for o in scene.objects if o.name=='Crowned asphalt crust / longitudinal rise' or o.name.startswith('Original asphalt native tile ')]
    for ob in objects:
        for slot,old in enumerate(ob.data.materials):
            # Objects may share mesh datablocks; changing one slot already
            # updates every instance using that mesh. Do not patch twice.
            if old in copies.values():continue
            if old.name in copies:ob.data.materials[slot]=copies[old.name];continue
            ma=old.copy();ma.name=old.name+' / Z finite-film event';copies[old.name]=ma;ob.data.materials[slot]=ma;n=ma.node_tree.nodes;l=ma.node_tree.links
            def val(q,i,v):l.new(v,q.inputs[i]) if hasattr(v,'node') else setattr(q.inputs[i],'default_value',v)
            def math(op,a,b=0):
                q=n.new('ShaderNodeMath');q.operation=op;q.label='Z finite mass road film';val(q,0,a);val(q,1,b);return q.outputs[0]
            def mix(a,b,f):
                q=n.new('ShaderNodeMixRGB');val(q,0,f);val(q,1,a);val(q,2,b);return q.outputs[0]
            def smooth(v,a,b):
                q=n.new('ShaderNodeMapRange');q.clamp=True;q.interpolation_type='SMOOTHERSTEP';val(q,0,v);q.inputs['From Min'].default_value=a;q.inputs['From Max'].default_value=b;return q.outputs[0]
            geom=n.new('ShaderNodeNewGeometry');geom.name='Z actual world hit';sep=n.new('ShaderNodeSeparateXYZ');l.new(geom.outputs['Position'],sep.inputs[0])
            gate=math('MULTIPLY',math('MULTIPLY',smooth(sep.outputs['X'],x[0],x[0]+.1),math('SUBTRACT',1,smooth(sep.outputs['X'],x[-1]-.1,x[-1]))),math('MULTIPLY',smooth(sep.outputs['Y'],y[0],y[0]+.12),math('SUBTRACT',1,smooth(sep.outputs['Y'],y[-1]-.12,y[-1]))))
            origin=(float(x[0]-(x[1]-x[0])/2),float(y[0]-(y[1]-y[0])/2),0)
            sub=n.new('ShaderNodeVectorMath');sub.operation='SUBTRACT';l.new(geom.outputs['Position'],sub.inputs[0]);sub.inputs[1].default_value=origin
            scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';l.new(sub.outputs[0],scale.inputs[0]);scale.inputs[1].default_value=(1/((x[-1]-x[0])+(x[1]-x[0])),1/((y[-1]-y[0])+(y[1]-y[0])),0)
            tex=n.new('ShaderNodeTexImage');tex.name='Z finite film final initial mobile matrix plus deposited matrix';tex.image=image;tex.extension='EXTEND';tex.interpolation='Linear';l.new(scale.outputs[0],tex.inputs[0]);split=n.new('ShaderNodeSeparateColor');split.mode='RGB';l.new(tex.outputs['Color'],split.inputs[0])
            # Film opacity is an art-directed particulate extinction length,
            # not a claim of calibrated Beer-Lambert optical transport.
            opacity=math('MINIMUM',.94,math('SUBTRACT',1,math('EXPONENT',math('MULTIPLY',split.outputs[0],-1/.000080))))
            # Suppress the old full-soil edge replacement inside this event.
            # The immutable source depth table is shared and never edited.
            legacy=[]
            for node in list(n):
                if node.bl_idname=='ShaderNodeAttribute' and node.attribute_name=='road_deposit_depth_m':legacy.append(node.outputs['Fac'])
                if node.name=='Tint, edge inset, deposit depth':legacy.append(node.outputs[2])
            changed_legacy=0
            for source in legacy:
                links=list(source.links)
                if not links:continue
                reduced=math('MULTIPLY',source,math('SUBTRACT',1,gate))
                for link in links:l.new(reduced,link.to_socket);changed_legacy+=1
            changed=[]
            for bs in list(n):
                if bs.bl_idname!='ShaderNodeBsdfPrincipled' or not bs.inputs['Base Color'].is_linked:continue
                color=bs.inputs['Base Color'].links[0].from_node
                if color.bl_idname!='ShaderNodeMixRGB' or color.inputs[2].is_linked or np.max(np.abs(np.array(color.inputs[2].default_value)-DUST))>1e-6:continue
                assert color.inputs[0].is_linked
                source=color.inputs[0].links[0].from_socket;links=list(source.links)
                # The original height-derived shelter term can still modulate
                # opacity, but there is no repeated island/noise shape mask.
                ret=None
                for q in n:
                    if q.bl_idname=='ShaderNodeMapRange' and q.inputs[0].is_linked:
                        from_node=q.inputs[0].links[0].from_node
                        if from_node.bl_idname=='ShaderNodeTexImage' and from_node.image and from_node.image.name=='Original metric aggregate / shelter height':ret=q.outputs[0];break
                local=math('MINIMUM',.94,math('MULTIPLY',opacity,ret if ret is not None else 1))
                new=mix(source,local,gate)
                for link in links:l.new(new,link.to_socket)
                changed.append(bs.name)
            assert changed and changed_legacy,'Audited road film graph hooks were not found'
            records.append({'source_material':old.name,'new_material':ma.name,'principled_film_hooks':changed,'legacy_depth_links_gated':changed_legacy,'opacity_extinction_length_m':.000080,'max_opacity':.94,'source_material_unchanged':True})
    return records
