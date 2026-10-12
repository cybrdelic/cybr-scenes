"""Late source-pinned continuous weathered-clast adapter. Baseline CI stays baseline-only."""
from pathlib import Path
import hashlib,json
import numpy as np

def _hash(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def _array(data,name,width,dtype='f4'):
    a=np.empty((len(data),width),dtype=dtype) if width>1 else np.empty(len(data),dtype=dtype)
    data.foreach_get(name,a.ravel());return a
def _volume(v,f):
    t=(v.astype(float)-v.mean(0))[f]
    return float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)

def apply(scene,config,output_dir):
    import bpy
    assert config['revision']==1
    manifest_path=Path(config['manifest']);manifest_bytes=manifest_path.read_bytes();manifest_sha=hashlib.sha256(manifest_bytes).hexdigest()
    if config.get('manifest_sha256'):assert manifest_sha==config['manifest_sha256'],'Pinned manifest bytes differ'
    manifest=json.loads(manifest_bytes);assert manifest['revision']==1
    # Admit all targets before mutating any mesh. Nothing is keyed to camera,
    # pixel coordinate or physical instance position.
    prepared=[]
    cg=scene.objects['CG finite 18–60 mm historical gravel pockets']
    cg_points=_array(cg.data.vertices,'co',3);cg_ids=_array(cg.data.attributes['prototype'].data,'value',1,'i4');cg_yaw=_array(cg.data.attributes['yaw'].data,'vector',3)
    instance_witness=_hash(np.frombuffer(cg_points.tobytes()+cg_ids.tobytes()+cg_yaw.tobytes(),dtype='u1'))
    all_matrices={o.name:[list(row)for row in o.matrix_world]for o in scene.objects}
    for entry in manifest['entries']:
        path=manifest_path.parent/entry['npz'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['npz_sha256']
        arrays=np.load(path,allow_pickle=False)
        if entry['source_kind']=='CG':
            ob=scene.objects[f'CG finite gravel {entry["prototype_index"]:03d}'];old=ob.data
            assert ob.name in scene.collection.all_objects
            count=int(np.count_nonzero(cg_ids==entry['prototype_index']))
            assert np.array_equal(np.asarray(cg.matrix_world),np.eye(4)) and np.array_equal(np.asarray(ob.matrix_world),np.eye(4)),'CG unit-scale source contract changed'
            weighted_count=float(count);hidden_count=count if cg.hide_render else 0
        else:
            old=bpy.data.meshes[entry['mesh_name']];source_users=[o for o in scene.objects if o.type=='MESH' and o.data==old];count=len(source_users)
            weighted_count=sum(abs(float(np.linalg.det(np.asarray(o.matrix_world)[:3,:3])))for o in source_users)
            hidden_count=sum(o.hide_render for o in source_users)
        v=_array(old.vertices,'co',3);assert _hash(v)==entry['parent_coordinates_sha256'],('parent mesh mismatch',old.name)
        assert len(old.materials)>=1
        material_ids=_array(old.polygons,'material_index',1,'i4');assert len(np.unique(material_ids))==1,'Mixed source material IDs need an explicit face map'
        assert not any(p.use_smooth for p in old.polygons),'Parent normal policy changed'
        old.calc_loop_triangles();faces=_array(old.loop_triangles,'vertices',3,'i4')
        assert old.color_attributes['mineral'].domain=='POINT' and old.attributes['grain_roughness'].domain=='POINT'
        color=_array(old.color_attributes['mineral'].data,'color',4);rough=_array(old.attributes['grain_roughness'].data,'value',1)
        idx=arrays['attribute_parent_index'];weights=arrays['attribute_parent_weight'];assert idx.min()>=0 and idx.max()<len(v)
        new_color=(color[idx]*weights[:,:,None]).sum(1).astype('f4');new_rough=(rough[idx]*weights).sum(1).astype('f4')
        oldvol=_volume(v,faces);newvol=_volume(arrays['v'],arrays['f']);assert newvol>0 and oldvol>0
        newv=arrays['v'];assert np.all(newv.min(0)>=v.min(0)) and np.all(newv.max(0)<=v.max(0))
        assert np.isfinite(weights).all() and np.all(weights>=0) and np.allclose(weights.sum(1),1)
        support=entry['support'];assert support['stable_on_declared_horizontal_fixture'] and support['buried_depth_m']>0
        prepared.append((entry,arrays,old,list(old.materials),int(material_ids[0]),new_color,new_rough,oldvol,newvol,count,weighted_count,hidden_count))
    rows=[]
    for entry,arrays,old,materials,material_id,color,rough,oldvol,newvol,count,weighted_count,hidden_count in prepared:
        old_name=old.name
        me=bpy.data.meshes.new(old_name+' / authored continuous fracture body DH3')
        me.from_pydata(arrays['v'].tolist(),[],arrays['f'].tolist())
        for material in materials:me.materials.append(material)
        me.polygons.foreach_set('material_index',np.full(len(me.polygons),material_id,dtype='i4'))
        me.polygons.foreach_set('use_smooth',np.ones(len(me.polygons),bool))
        me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT').data.foreach_set('color',color.ravel())
        me.attributes.new('grain_roughness','FLOAT','POINT').data.foreach_set('value',rough)
        for name in ['weathering_susceptibility','grain_boundary_factor','grain_normal_depth_m']:
            me.attributes.new(name,'FLOAT','POINT').data.foreach_set('value',arrays[name])
        me.update()
        users=[o for o in scene.objects if o.type=='MESH'and o.data==old]
        for o in users:o.data=me
        rows.append({'source_kind':entry['source_kind'],'prototype_index':entry['prototype_index'],'old_mesh':old_name,'new_mesh':me.name,
                     'source_mesh_users':[o.name for o in users],'physical_body_count':count,'hidden_render_object_body_count':hidden_count,'scale_determinant_weighted_body_count':weighted_count,'parent_true_solid_per_body_m3':oldvol,
                     'candidate_true_solid_per_body_m3':newvol,'representation_reserve_increment_per_body_m3':oldvol-newvol,
                     'representation_reserve_increment_all_bodies_m3':(oldvol-newvol)*weighted_count,'support_anchors_byte_exact':False,'fixture_support':entry['support'],'whole_road_contact_validated':False,'representation_overlap':entry['representation_overlap'],'added_representation_volume_estimate_all_bodies_m3':entry['representation_overlap']['measurements'][-1]['added_representation_volume_estimate_m3']*weighted_count,'removed_representation_volume_estimate_all_bodies_m3':entry['representation_overlap']['measurements'][-1]['removed_representation_volume_estimate_m3']*weighted_count,
                     'material_slots_preserved':[m.name for m in materials],'current_material_fields_interpolated':True})
        arrays.close()
    after=_hash(np.frombuffer(_array(cg.data.vertices,'co',3).tobytes()+_array(cg.data.attributes['prototype'].data,'value',1,'i4').tobytes()+_array(cg.data.attributes['yaw'].data,'vector',3).tobytes(),dtype='u1'))
    assert after==instance_witness
    assert {o.name:[list(row)for row in o.matrix_world]for o in scene.objects}==all_matrices
    report={'revision':1,'manifest_sha256':manifest_sha,'entries':rows,
            'removed_rendered_solid_representation_reserve_m3':sum(r['representation_reserve_increment_all_bodies_m3']for r in rows),
            'all_object_transforms_unchanged':True,'CG_point_instances_ids_yaws_byte_exact':True,
            'historical_transport_ledgers_modified':False,'CI_exposure_applies_to_baseline_only':True,
            'candidate_exposure_estimate':None,'negative_per_body_reserve_requires_feasibility_review':any(r['representation_reserve_increment_per_body_m3']<0 for r in rows),'limits':['Two reviewed prototypes only; every instance sharing either prototype changes.',
                'Authored morphology alternatives, not a time-resolved weathering event or physical mass-flux conservation claim.',
                'Removed explicit solid is retained only in this separate representation-reserve account.',
                'Old convex CI exposure numbers describe the baseline; no convex-hull fill or candidate exposure claim.',
                'Old extremal/support vertices are not frozen. Original transforms remain unchanged; measured fixture contact is recorded. Whole-road slope contact is not validated.',
                'The original metric envelope and current material attributes are retained, but the new body does not inherit the old silhouette or sockets. Local represented additions/removals are estimated separately; exact net reserve is the closed-volume difference.',
                'Current pigment and roughness are weighted transfers from old surface samples, including newly occupied space; this is authored extrapolation, not measured internal mineral structure.',
                'Primary body lobes, unequal fracture planes, edge transition, grain spacing and susceptibility relief are authored and not measured Victorville calibration. No weathering-time claim.']}
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True);(out/'WEATHERED_CLAST_FIELDS_DH.json').write_text(json.dumps(report,indent=2)+'\n')
    print('WEATHERED_CLAST_FIELDS_DH',json.dumps(report),flush=True);return report
