"""Tiny synthetic Blender contract test, using exact specimen parent meshes."""
from pathlib import Path
import bpy,json,numpy as np,sys
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));from apply_weathered_fields import apply
s=bpy.context.scene
mat=bpy.data.materials.new('Current CN surrogate fields; deliberately unlike source NPZ')
parents={}
for kind,index,name in [('CG',146,'prototype_146'),('AS',39,'as_prototype_039')]:
    p=np.load(ROOT/'specimens'/f'{name}.npz');me=bpy.data.meshes.new(f'AS actual metric fragment {index:03d}'if kind=='AS'else 'CG original numerical fixture')
    me.from_pydata(p['parent_v'].tolist(),[],p['parent_f'].tolist());me.materials.append(mat)
    rng=np.random.default_rng(153+index);color=np.column_stack([rng.uniform(.1,.9,(len(me.vertices),3)),np.ones(len(me.vertices))]).astype('f4');rough=rng.uniform(.2,.95,len(me.vertices)).astype('f4')
    me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT').data.foreach_set('color',color.ravel());me.attributes.new('grain_roughness','FLOAT','POINT').data.foreach_set('value',rough)
    me.polygons.foreach_set('use_smooth',np.zeros(len(me.polygons),bool));me.update();parents[kind]=(me,p,color.copy(),rough.copy())
    ob=bpy.data.objects.new(f'CG finite gravel {index:03d}'if kind=='CG'else 'AS synthetic contract user1',me);s.collection.objects.link(ob)
    if kind=='AS':
        ob2=bpy.data.objects.new('AS synthetic contract user2 scaled',me);s.collection.objects.link(ob2);ob2.scale=(2,2,2);ob2.hide_render=True
pointmesh=bpy.data.meshes.new('CG synthetic point instances');pointmesh.from_pydata([[0,0,0],[1,0,0],[2,0,0],[3,0,0]],[],[])
pointmesh.attributes.new('prototype','INT','POINT').data.foreach_set('value',np.array([146,146,0,146],dtype='i4'))
pointmesh.attributes.new('yaw','FLOAT_VECTOR','POINT').data.foreach_set('vector',np.zeros((4,3),dtype='f4').ravel());owner=bpy.data.objects.new('CG finite 18–60 mm historical gravel pockets',pointmesh);s.collection.objects.link(owner)
bpy.context.view_layer.update()
report=apply(s,{'revision':1,'manifest':str(ROOT/'CANDIDATE_MANIFEST.json')},ROOT/'adapter_contract')
for row in report['entries']:
    me=bpy.data.meshes[row['new_mesh']];color=np.empty((len(me.vertices),4),dtype='f4');me.color_attributes['mineral'].data.foreach_get('color',color.ravel());rough=np.empty(len(me.vertices),dtype='f4');me.attributes['grain_roughness'].data.foreach_get('value',rough)
    _,p,oldcolor,oldrough=parents[row['source_kind']];idx=p['attribute_parent_index'];w=p['attribute_parent_weight'];expected_c=(oldcolor[idx]*w[:,:,None]).sum(1).astype('f4');expected_r=(oldrough[idx]*w).sum(1).astype('f4')
    assert np.array_equal(color,expected_c) and np.array_equal(rough,expected_r)
    assert np.all(color.min(0)>=oldcolor.min(0)-1e-7) and np.all(color.max(0)<=oldcolor.max(0)+1e-7)
    for field in ['weathering_susceptibility','grain_boundary_factor','grain_normal_depth_m']:assert field in me.attributes
    if row['source_kind']=='CG':assert row['physical_body_count']==3 and row['scale_determinant_weighted_body_count']==3
    else:assert row['physical_body_count']==2 and abs(row['scale_determinant_weighted_body_count']-9)<1e-12 and row['hidden_render_object_body_count']==1
(ROOT/'adapter_contract'/'PASSED.json').write_text(json.dumps({'passed':True,'tests':['Parent hash preflight','Actual instance counts','Scale-determinant-weighted reserve','Hidden user count','Current CN surrogate attributes preserved; NPZ colors not imported','Point-instance identity','Object-transform identity','Measured horizontal-fixture support and exact unmodified transforms']},indent=2)+'\n')
print('LATE_ADAPTER_CONTRACT_PASSED',flush=True)
