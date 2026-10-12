"""Portable synthetic AK tests. No saved fields, scene or rendering required.
These do not replace the retained actual-foundation historical test receipt.
"""
import unittest
import numpy as np
from substrate_history_ak import HistorySpec, substrate_fields, summary
from flow_transport_ae import solve_context
from visible_shoulder_flow_ad import ContextSpec
from flow_sediment_model_z import FlowConfig

class PortableHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        x=np.linspace(-6.2,-3.25,60);y=np.linspace(-.6,8.2,177)
        xx,yy=np.meshgrid(x,y)
        cls.f=dict(x_m=x,y_m=y,foundation_z_m=.012*xx+.001*yy)
        cls.xy=np.stack((xx,yy),axis=-1)
        cls.v=substrate_fields(cls.xy,cls.f)
    def test_finite_bounded_partition(self):
        for key,v in self.v.items():
            self.assertTrue(np.isfinite(v).all(),key);self.assertGreaterEqual(v.min(),0,key)
        self.assertLessEqual(self.v['prior_fine_cover_m'].max(),.0025)
        np.testing.assert_allclose(self.v['unit_weights'].sum(-1),self.v['domain_strength'],atol=1e-15)
        for key in ('armor_exposure','compaction','unit_weights','historical_wash','historical_winnowing','historical_sand_opportunity','grading_strength','domain_strength'):
            self.assertLessEqual(self.v[key].max(),1,key)
    def test_recent_storm_independence_and_no_mutation(self):
        before={k:v.tobytes() for k,v in self.f.items()}
        f=dict(self.f,sediment_delta_m=np.ones(self.xy.shape[:-1])*99,
               retained_deposit_by_class_m=np.ones(self.xy.shape[:-1]+(3,))*88)
        for k,v in substrate_fields(self.xy,f).items():np.testing.assert_array_equal(v,self.v[k])
        self.assertEqual(before,{k:v.tobytes() for k,v in self.f.items()})
    def test_outside_and_rim_zero(self):
        p=np.array([[-6.3,1],[-3.2,1],[-4,-.7],[-4,8.3],[-6.2,1]])
        for v in substrate_fields(p,self.f).values():np.testing.assert_array_equal(v,0)
    def test_chunk_and_order_invariance(self):
        p=self.xy.reshape(-1,2)[::13];a=substrate_fields(p,self.f)
        b=[substrate_fields(q,self.f) for q in np.array_split(p,7)]
        c=substrate_fields(p[::-1],self.f)
        for k in a:
            np.testing.assert_array_equal(a[k],np.concatenate([v[k] for v in b]))
            np.testing.assert_array_equal(a[k],c[k][::-1])
    def test_gradient_changes_response(self):
        f=dict(self.f,foundation_z_m=-self.f['foundation_z_m'])
        a=substrate_fields(self.xy,f)
        self.assertGreater(np.max(abs(a['armor_exposure']-self.v['armor_exposure'])),.1)
    def test_downhill_routes_on_known_plane(self):
        for r in summary(self.f)['drainage_routes']:
            self.assertGreater(r['net_foundation_drop_m'],0)
            self.assertLess(r['maximum_local_uphill_increment_m'],1e-10)
    def test_no_new_geometry_or_physics_claim(self):
        r=summary(self.f)
        self.assertEqual(r['geometry_height_added_m'],0)
        self.assertFalse(r['conservation_claim']);self.assertFalse(r['calibrated_physics'])
        self.assertFalse(r['surveyed_history']);self.assertFalse(r['recent_storm_inputs_used'])
    def test_invalid_inputs_rejected(self):
        for p,s in ((np.array([[np.nan,1.]]),HistorySpec()),(self.xy,HistorySpec(maximum_prior_cover_m=.005)),(self.xy,HistorySpec(drainage_reaches=()))):
            with self.assertRaises(ValueError):substrate_fields(p,self.f,s)
        with self.assertRaises(ValueError):substrate_fields(self.xy,dict(self.f,foundation_z_m=np.zeros((2,2))))
    def test_spatial_initial_mix_preserves_layer_and_balance(self):
        x=np.linspace(-1,0,21);y=np.linspace(0,1,21);xx,yy=np.meshgrid(x,y);z=.03*xx+.012*yy
        spec=ContextSpec(bounds_m=(-1,0,0,1),spacing_m=.05,protected_bounds_m=(100,101,100,101),
            protected_contact_x_min_m=0,transition_m=.1,mesh_guard_m=.07,
            loose_layer_m=.018,retained_deposit_cap_m=.012,
            flow=FlowConfig(exchange_diameter_m=.15,boundary_band_m=.1,max_erosion_m=.018,
                max_deposition_m=.012,max_event_erosion_m=.003,rainfall_m=(.01,)))
        mix=np.empty(z.shape+(3,));mix[...,0]=.5+.1*np.sin(xx);mix[...,1]=.3;mix[...,2]=1-mix[...,0]-mix[...,1]
        result=solve_context(x,y,z,spec=spec,initial_class_fractions=mix)
        self.assertTrue(result.receipt['initial_total_layer_unchanged'])
        self.assertTrue(result.receipt['no_additional_height_sheets'])
        self.assertLess(abs(result.flow.receipt['sediment_balance_error_m3']),1e-11)
        self.assertLess(max(abs(v) for v in result.flow.receipt['stock_balance_by_class_m3']),1e-11)
        np.testing.assert_allclose(result.flow.initial_mobile_class_thickness_m.sum(-1),result.mobility*.018,atol=1e-16)
        np.testing.assert_allclose(result.flow.initial_mobile_class_thickness_m,result.mobility[...,None]*.018*mix,atol=1e-16)
        with self.assertRaises(ValueError):solve_context(x,y,z,spec=spec,initial_class_fractions=mix*2)

if __name__=='__main__':unittest.main()
