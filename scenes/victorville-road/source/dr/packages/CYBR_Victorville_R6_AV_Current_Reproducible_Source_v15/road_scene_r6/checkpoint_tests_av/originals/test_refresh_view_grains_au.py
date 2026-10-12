"""Small pure tests: no Blender, render, source scene loading or external writes."""
import unittest
from types import SimpleNamespace
import numpy as np
import approved_density_lod as lod
from context_mesh_refine_ab import SourceSampler
from refresh_view_grains_au import (CurrentTriangleSurface, plan_reallocation,
    readonly_projection, population_weights, field_noise, buried_origins, _height, _quotas, _validate_instance_graph, _point_arrays, _check_rigid_counts)


def fixture():
    x=y=np.linspace(0.,.4,9)
    fields=dict(x_m=x,y_m=y,sediment_delta_m=np.full((9,9),.002),
                retained_deposit_by_class_m=np.tile([.001,.0007,.0003],(9,9,1)),
                surface_fraction=np.tile([.68,.24,.08],(9,9,1)),lag=np.zeros((9,9)))
    co=np.array([[0,0,0],[.4,0,.008],[.4,.4,.012],[0,.4,.004]],float)
    tri=np.array([[0,1,2],[0,2,3]],np.int32)
    surface=CurrentTriangleSurface(SourceSampler(co,tri,np.arange(2)),np.full(4,.002))
    frame=np.array([[-.692307,-.461538,-1],[.692307,-.461538,-1],[.692307,.461538,-1],[-.692307,.461538,-1]])
    camera=SimpleNamespace(name='fixture',matrix_world=np.eye(4),data=SimpleNamespace(
        type='PERSP',view_frame=lambda scene:frame,sensor_fit='HORIZONTAL',clip_start=.01,lens=26.))
    scene=SimpleNamespace(camera=camera,render=SimpleNamespace(pixel_aspect_x=1.,pixel_aspect_y=1.))
    config=dict(camera_location=[.2,-.35,.25],camera_target=[.2,.2,0.],lens=26.,width=300,height=200)
    projection=readonly_projection(scene,config)
    records=[]
    for i,source_id in enumerate(lod.VERIFIED_BANK_IDS):
        r=.0015 if i<48 else .0005
        # Simple area vectors suffice for allocation tests; no fake production bank is loaded.
        records.append(dict(index=i,source_id=source_id,band='chips' if i<48 else 'grit',radius=r,
            area_vectors=np.tile([[0.,0.,np.pi*r*r]],(8,1)),diameter=2*r,vertices=np.array([[0,0,-r],[r,0,r]])))
    pi=np.repeat(np.arange(64,dtype=np.int32),4)
    rng=np.random.default_rng(19)
    p=np.c_[rng.uniform(2,3,(len(pi),2)),np.zeros(len(pi))].astype('f4')
    yaw=np.zeros((len(pi),3),np.float32); yaw[:,2]=rng.uniform(0,6.28,len(pi))
    args=dict(records=records,original_points=np.empty((0,3)),original_prototype=np.empty(0,np.int32),
              old_points=p,old_prototype=pi,old_yaw=yaw,surface=surface,fields=fields,projection=projection,
              cell_size=.1,max_instances=190)
    return args,scene,config


class RefreshTests(unittest.TestCase):
    def test_bounded_plan_identity_yaw_and_determinism(self):
        args,_,_=fixture(); before={k:v.tobytes() for k,v in args.items() if isinstance(v,np.ndarray)}
        a=plan_reallocation(**args); b=plan_reallocation(**args)
        self.assertGreater(len(a.points),0); self.assertLessEqual(len(a.points),190)
        self.assertEqual(len(np.unique(a.source_rows)),len(a.points))
        np.testing.assert_array_equal(a.points,b.points)
        np.testing.assert_array_equal(a.prototype,args['old_prototype'][a.source_rows])
        np.testing.assert_array_equal(a.yaw,args['old_yaw'][a.source_rows])
        self.assertEqual(before,{k:v.tobytes() for k,v in args.items() if isinstance(v,np.ndarray)})
        self.assertEqual(a.receipt['unspent_budget'],190-len(a.points))
        self.assertTrue(args['projection'].visible(a.points).all())
        self.assertEqual(a.receipt['before_count'],256)
        self.assertEqual(sum(v['after'] for v in a.receipt['per_identity']),len(a.points))

    def test_metric_nonintersection_and_triangle_burial(self):
        args,_,_=fixture(); a=plan_reallocation(**args)
        radius=np.array([r['radius'] for r in args['records']])[a.prototype]
        d=np.linalg.norm(a.points[:,None,:2]-a.points[None,:,:2],axis=2)
        np.fill_diagonal(d,np.inf)
        self.assertTrue(np.all(d+1e-7>=radius[:,None]+radius[None,:]))
        z=args['surface'].height(a.points[:,:2])
        np.testing.assert_allclose(a.points[:,2],z-.0017,atol=1e-7)

    def test_density_targets_leave_unspent_budget(self):
        args,_,_=fixture()
        # Identical finite identities do not force all old points into view.
        view=args['projection']; view.f=view.f*.0001
        a=plan_reallocation(**args)
        self.assertEqual(len(a.points),0); self.assertEqual(a.receipt['unspent_budget'],190)

    def test_coarse_retained_originals_exclude_new_points(self):
        args,_,_=fixture()
        p=np.array([[.2,.2,.006]],dtype=np.float32)
        args.update(original_points=p,original_prototype=np.array([0],np.int32))
        a=plan_reallocation(**args); radius=np.array([r['radius'] for r in args['records']])[a.prototype]
        self.assertTrue(np.all(np.linalg.norm(a.points[:,:2]-p[0,:2],axis=1)+1e-7>=radius+.0015))

    def test_source_weighting_uses_current_lag_fraction(self):
        args,_,_=fixture(); f=args['fields']; xy=np.array([[.1,.1],[.2,.3]])
        first=population_weights(xy,f); f['lag'][:]=.8; f['surface_fraction'][:]=[.20,.35,.45]
        second=population_weights(xy,f)
        self.assertTrue(np.all(second[:,0]>=first[:,0])); self.assertTrue(np.all(second[:,1]>=first[:,1]))
        px,py=xy.T; d=np.clip(.46+.32*field_noise(px,py,.031,8)+.16*field_noise(px,py,.008,28),.07,.94)
        expected=np.stack((np.clip((.10+.92*(1-d)**1.8)/.38*np.clip(.60+5*.45+.55*.8,.25,2.2),.08,2.5),
                           np.clip((.26+.78*(1-d))/.68*np.clip(.58+1.9*.35,.35,1.6),.1,2.2)),-1)
        np.testing.assert_array_equal(second,expected)

    def test_readonly_actual_view_override(self):
        _,scene,config=fixture(); before=scene.camera.matrix_world.copy()
        config.update(camera_location=[-5.12,2,.4],camera_target=[-3.6,8.5,.1],width=1000,height=667)
        p=readonly_projection(scene,config)
        uv,d=p.project(np.array([config['camera_target']]))
        np.testing.assert_allclose(uv[0],[500,333.5],atol=1e-8)
        np.testing.assert_array_equal(before,scene.camera.matrix_world)
        self.assertEqual(scene.camera.data.lens,26.)
        self.assertGreater(d[0],0)

    def test_union_under_same_budget_with_per_view_counts(self):
        args,scene,config=fixture(); config.update(camera_location=[.2,.75,.25],camera_target=[.2,.2,0])
        args['extra_projections']=(readonly_projection(scene,config),)
        a=plan_reallocation(**args)
        self.assertLessEqual(len(a.points),190); self.assertEqual(a.receipt['view_count'],2)
        self.assertEqual(len(a.receipt['per_view']),2)
        self.assertTrue(np.logical_or(args['projection'].visible(a.points),args['extra_projections'][0].visible(a.points)).all())

    def test_no_unsupported_extrapolation(self):
        args,_,_=fixture(); surface=args['surface']
        with self.assertRaises(ValueError): _height(surface,np.array([[.8,.8]]))
        self.assertTrue(np.isnan(_height(surface,np.array([[.8,.8]]),missing=True)[0]))
        class Broken:
            def height(self,xy): raise ValueError('Sampler query-product cap exceeded')
        with self.assertRaisesRegex(ValueError,'cap exceeded'): _height(Broken(),np.array([[0.,0.]]),missing=True)

    def test_actual_triangle_delta_not_bilinear_blanket(self):
        args,_,_=fixture(); surface=args['surface']; surface.sediment_at_vertices=np.array([0.,.003,.007,.001])
        q=np.array([[.30,.10],[.1,.3]])
        expected=np.array([.003*.5+.007*.25,.007*.25+.001*.5])
        np.testing.assert_allclose(surface.sediment_delta(q),expected)
        np.testing.assert_allclose(buried_origins(np.ones(3),[-.1,0,.1]),[1,1,.915])

    def test_quota_caps_identity_and_demand_without_filling_budget(self):
        d=np.zeros((3,64)); d[:,0]=[.1,.4,.6]; d[:,1]=[9,12,3]
        inventory=np.ones(64,dtype=int)*2
        q=_quotas(d,inventory,100,np.random.default_rng(1))
        self.assertLessEqual(q.sum(),4); self.assertTrue(np.all(q.sum(0)<=inventory))
        self.assertTrue(np.all(q<=np.ceil(d)))

    def test_unit_scale_and_direct_identity_graph_gate(self):
        def socket(value,links=()):
            return SimpleNamespace(default_value=value,is_linked=bool(links),links=links)
        def attr(name):
            node=SimpleNamespace(bl_idname='GeometryNodeInputNamedAttribute',inputs={'Name':socket(name)})
            return socket(None,[SimpleNamespace(from_node=node)])
        node=SimpleNamespace(bl_idname='GeometryNodeInstanceOnPoints',inputs={
            'Scale':socket([1.,1.,1.]),'Pick Instance':socket(True),
            'Instance Index':attr('prototype'),'Rotation':attr('yaw')})
        group=SimpleNamespace(nodes=[node])
        _validate_instance_graph(group)
        node.inputs['Scale'].default_value=[1.,1.,2.]
        with self.assertRaisesRegex(ValueError,'unit scale'): _validate_instance_graph(group)

    def test_empty_face_schema_retained_or_readonly_skipped(self):
        class Data:
            def __init__(self,values): self.values=np.asarray(values)
            def __len__(self): return len(self.values)
            def foreach_get(self,name,out): out[:]=self.values.ravel()
        def attr(name,kind,domain,values):
            return SimpleNamespace(name=name,data_type=kind,domain=domain,data=Data(values))
        mesh=SimpleNamespace(edges=[],polygons=[],shape_keys=None,vertices=Data([[0,0,0]]),attributes=[
            attr('prototype','INT','POINT',[0]),attr('yaw','FLOAT_VECTOR','POINT',[[0,0,.2]]),
            attr('sharp_face','BOOLEAN','FACE',[])])
        ob=SimpleNamespace(type='MESH',data=mesh,matrix_world=np.eye(4))
        _,readonly=_point_arrays(ob,readonly=True)
        self.assertNotIn('sharp_face',readonly)
        _,replaceable=_point_arrays(ob)
        self.assertEqual(replaceable['sharp_face'][3],'FACE')
        self.assertEqual(len(replaceable['sharp_face'][2]),0)

    def test_real_source_rigid_counts_accepted_with_bounded_limit(self):
        _check_rigid_counts(1045220,2036376)
        with self.assertRaisesRegex(ValueError,'global read cap'): _check_rigid_counts(1100001,2036376)
        with self.assertRaisesRegex(ValueError,'global read cap'): _check_rigid_counts(1045220,2100001)

    def test_changed_bank_or_invalid_budget_fails(self):
        args,_,_=fixture(); args['max_instances']=294364
        with self.assertRaisesRegex(ValueError,'cap'): plan_reallocation(**args)
        args,_,_=fixture(); args['records'][0]['source_id']=999
        with self.assertRaisesRegex(ValueError,'identity'): plan_reallocation(**args)


if __name__=='__main__': unittest.main()
