"""Bounded synthetic AO receiver-gate tests; solves use 99 cells maximum."""
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
import io
from contextlib import redirect_stdout
from apply_refined_film_an import image_payload
from unittest.mock import patch
import numpy as np
import flow_sediment_model_z as baseline
import flow_sediment_model_ao as model
import refined_film_event_an as an
import refined_film_event_ao as ao


def line_adjacency(n):
    return abs(np.arange(n)[:, None] - np.arange(n)[None, :]) == 1


def gate(heights, stage=1., weights=None, adjacency=None, center=0):
    heights=np.asarray(heights,float)
    if weights is None: weights=np.full(len(heights),1/len(heights))
    if adjacency is None: adjacency=line_adjacency(len(heights))
    wet,_,_=model._connected_wet_contact(heights,stage,np.asarray(weights,float),adjacency,center)
    return model._nonincreasing_deposition_contact(heights,wet,adjacency,center)


def fixture():
    x=np.arange(-5,6)*.025; y=np.arange(-4,5)*.025
    xx,yy=np.meshgrid(x,y); z=.18*np.maximum(xx,0.)+.002*yy**2
    p=xx>=0.; initial,caps,_=ao.initial_inventory(x,y,p,np.zeros(len(y)))
    return x,y,z,initial,caps


class ReceiverGateTests(unittest.TestCase):
    def test_downhill_and_flat_all_reachable_with_exact_original_weights(self):
        weights=np.array([.1,.2,.3,.4])
        for heights in ([.4,.3,.2,.1],[.4,.4,.4,.4],[.4,.3,.3,.1]):
            contact,reached=gate(heights,weights=weights)
            np.testing.assert_array_equal(reached,True)
            np.testing.assert_array_equal(contact,weights)

    def test_submerged_uphill_face_is_rejected_without_renormalization(self):
        contact,reached=gate([0.,.0001,.0002],stage=.004,weights=[.2,.3,.5])
        np.testing.assert_array_equal(reached,[True,False,False])
        np.testing.assert_array_equal(contact,[.2,0.,0.])
        self.assertEqual(contact.sum(),.2)

    def test_lower_target_behind_uphill_bump_is_not_reachable(self):
        _,reached=gate([.003,.001,.002,0.],stage=.004)
        np.testing.assert_array_equal(reached,[True,True,False,False])

    def test_no_isolated_or_diagonal_jump(self):
        # Flat 2x2 stencil, but the only two wet cells share just a corner.
        adjacency=np.array([[0,1,1,0],[1,0,0,1],[1,0,0,1],[0,1,1,0]],bool)
        contact,reached=gate([.002,.005,.005,0.],stage=.004,adjacency=adjacency)
        np.testing.assert_array_equal(reached,[True,False,False,False])
        np.testing.assert_array_equal(contact,[.25,0.,0.,0.])

    def test_zero_weight_gap_and_dry_source_block_paths(self):
        contact,reached=gate([.003,.002,.001],stage=.004,weights=[.3,0.,.7])
        np.testing.assert_array_equal(reached,[True,False,False])
        np.testing.assert_array_equal(contact,[.3,0.,0.])
        contact,reached=gate([.004,.003,.002],stage=.004)
        np.testing.assert_array_equal(contact,0.)
        np.testing.assert_array_equal(reached,False)

    def test_each_current_bed_step_matters_after_preceding_deposit(self):
        heights=np.array([.003,.002,.001]); weights=np.array([.2,.3,.5])
        np.testing.assert_array_equal(gate(heights,stage=.004,weights=weights)[1],True)
        heights[1]=.0031  # Still wet, but previous deposition creates a rise.
        contact,reached=gate(heights,stage=.004,weights=weights)
        np.testing.assert_array_equal(reached,[True,False,False])
        np.testing.assert_array_equal(contact,[.2,0.,0.])

    def test_alternate_shared_face_route_can_reach_receiver(self):
        adjacency=np.array([[0,1,1,0],[1,0,0,1],[1,0,0,1],[0,1,1,0]],bool)
        _,reached=gate([.003,.0035,.002,.001],stage=.004,adjacency=adjacency)
        np.testing.assert_array_equal(reached,[True,False,True,True])


class SolverScopeAndInvariantTests(unittest.TestCase):
    def test_identical_event_recipe_and_initial_stock(self):
        self.assertEqual(asdict(ao.fixed_event_config()),asdict(an.fixed_event_config()))
        x,y,z,initial,caps=fixture();xx,_=np.meshgrid(x,y)
        old=an.initial_inventory(x,y,xx>=0.,np.zeros(len(y)))
        new=ao.initial_inventory(x,y,xx>=0.,np.zeros(len(y)))
        for a,b in zip(old,new): np.testing.assert_array_equal(a,b)
        self.assertEqual(ao.EventConfig().strides,(1,))

    def test_ao_gate_removed_recovers_all_z_output_arrays_exactly(self):
        x,y,z,initial,caps=fixture()
        kwargs=dict(initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
        old=baseline.simulate_shoulder(x,y,z,an.fixed_event_config(),**kwargs)
        with patch.object(model,'_nonincreasing_deposition_contact',lambda h,w,a,c:(w,w>0)):
            new=model.simulate_shoulder(x,y,z,ao.fixed_event_config(),**kwargs)
        for f in fields(old):
            if f.name!='receipt':
                with self.subTest(field=f.name): np.testing.assert_array_equal(getattr(old,f.name),getattr(new,f.name))

    def test_active_gate_mass_nonnegative_caps_and_inputs_unchanged(self):
        x,y,z,initial,caps=fixture();caps[:,:3]=0.;caps[:,3:]=.000003
        arrays=[x,y,z,initial,caps];saved=[a.copy() for a in arrays]
        flow=model.simulate_shoulder(x,y,z,ao.fixed_event_config(),initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
        ledger=ao.validate_balances(flow,initial,caps,.025,.025)
        self.assertTrue(ledger['passed']);self.assertEqual(ledger['maximum_retained_cap_excess_m'],0.)
        self.assertGreater(flow.receipt['nonincreasing_path_blocked_receiver_contacts'],0)
        self.assertGreater(flow.receipt['boundary_export_m3'],0.)
        np.testing.assert_array_equal(flow.retained_deposit_by_class_m[caps==0.],0.)
        for a,b in zip(arrays,saved):np.testing.assert_array_equal(a,b)

    def test_rejected_deposition_load_remains_conserved_in_routing_export(self):
        x,y,z,initial,caps=fixture()
        with patch.object(model,'_nonincreasing_deposition_contact',lambda h,w,a,c:(np.zeros_like(w),np.zeros(len(w),bool))):
            flow=model.simulate_shoulder(x,y,z,ao.fixed_event_config(),initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
        self.assertTrue(ao.validate_balances(flow,initial,caps,.025,.025)['passed'])
        np.testing.assert_array_equal(flow.retained_deposit_by_class_m,0.)
        self.assertGreater(flow.receipt['unplaced_deposition_requests_m3'],0.)
        self.assertGreater(flow.receipt['boundary_export_m3'],0.)
        self.assertAlmostEqual(flow.receipt['boundary_export_m3'],flow.receipt['cumulative_erosion_m3'],places=16)

    def test_zero_initial_stock_cannot_be_created(self):
        x,y,z,initial,caps=fixture();initial[:]=0.
        flow=model.simulate_shoulder(x,y,z,ao.fixed_event_config(),initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
        self.assertTrue(ao.validate_balances(flow,initial,caps,.025,.025)['passed'])
        np.testing.assert_array_equal(flow.retained_deposit_by_class_m,0.)
        np.testing.assert_array_equal(flow.remaining_initial_mobile_class_thickness_m,0.)

    def test_serialized_tiny_ao_field_preserves_an_application_contract(self):
        x=-3.25+np.arange(11)*.00625; y=.9+np.arange(9)*.00625
        xx,yy=np.meshgrid(x,y); z=.02*(xx+3.2)+.01*(yy-.9); p=xx>=-3.22
        with tempfile.TemporaryDirectory() as folder:
            surface=Path(folder)/'synthetic_source.npz'
            np.savez_compressed(surface,x_m=x,y_m=y,actual_surface_z_m=z,pavement=p,
                owner=p.astype(np.uint8),road_edge_x_m=np.full(len(y),-3.22))
            # Only the fixed actual-surface shape validator is mocked. This is
            # a 99-cell synthetic serialized run, never another real event.
            with patch.object(ao,'_validate_source',return_value=(x,y)),redirect_stdout(io.StringIO()):
                ao.run(surface,Path(folder)/'event',dict(strides=(1,)))
            with np.load(Path(folder)/'event/AO_FILM_6p25mm.npz',allow_pickle=False) as f:
                out={k:f[k] for k in f.files}
            self.assertEqual(str(out['experiment_id']),'AO_NONINCREASING_CURRENT_BED_DEPOSITION_V1')
            px,py,payload=image_payload(out)
            np.testing.assert_array_equal(px,x);np.testing.assert_array_equal(py,y)
            self.assertEqual(payload.shape,z.shape+(4,))
            np.testing.assert_array_equal(payload[...,0],out['pavement_owned_class_thickness_m'][...,0].astype(np.float32))

    def test_immutable_an_z_sources_and_results_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'receipts/ao_immutable_baselines.json').read_text())
        for name,sha in manifest.items():
            with self.subTest(path=name):self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),sha)

if __name__=='__main__': unittest.main(verbosity=2)
