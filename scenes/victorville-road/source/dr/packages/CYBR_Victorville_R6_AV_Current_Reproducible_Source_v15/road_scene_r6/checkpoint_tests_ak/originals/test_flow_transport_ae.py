"""Small CPU-only AE diagnostics, no scenes/renders or saved-field mutation.

Run: OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python src/test_flow_transport_ae.py
The actual terrain comparison uses only 768 samples. Resolution sensitivity is
measured on the same analytic inclined plane, not claimed as triangle resampling.
"""
from pathlib import Path
from dataclasses import replace
import hashlib
import json
import resource
import time
import unittest
import numpy as np
import flow_transport_ae as ae
import flow_sediment_model_z as zmod

ROOT = Path(__file__).resolve().parents[1]
REPORT = {'status': 'Numerical source-only tests; no render or visual acceptance',
          'tests': {}, 'comparisons': {}}
START = time.monotonic()


def shape_metrics(z):
    c = z[1:-1, 1:-1]
    pits = ((c < z[:-2, 1:-1]) & (c < z[2:, 1:-1])
            & (c < z[1:-1, :-2]) & (c < z[1:-1, 2:]))
    return {'local_four_neighbor_pits': int(pits.sum()),
            'curvature_rms_mm': float(1000 * np.sqrt((
                np.mean(np.diff(z, axis=0, n=2)**2)
                + np.mean(np.diff(z, axis=1, n=2)**2)) / 2))}


def config(**kwargs):
    values = dict(exchange_diameter_m=.15, boundary_band_m=.1,
                  max_erosion_m=.045, max_deposition_m=.030,
                  max_event_erosion_m=.010, rainfall_m=(.020, .035, .025))
    values.update(kwargs)
    return zmod.FlowConfig(**values)


def run(model, x, y, z, cfg):
    initial = np.full(z.shape + (3,), .060) * np.array(cfg.substrate_fractions)
    cap = np.full(z.shape, .030)
    return model.simulate_shoulder(x, y, z, cfg,
        initial_mobile_class_thickness_m=initial,
        maximum_deposited_thickness_m=cap)


class TestAE(unittest.TestCase):
    def check_inventory(self, r):
        self.assertGreaterEqual(float(r.remaining_initial_mobile_class_thickness_m.min()), 0)
        self.assertGreaterEqual(float(r.retained_deposit_by_class_m.min()), 0)
        self.assertLessEqual(float(r.final_deposit_m.max()), .030 + 1e-12)
        for name in ('sediment_balance_error_m3', 'net_bed_plus_export_error_m3',
                     'water_balance_error_m3'):
            self.assertLess(abs(r.receipt[name]), 1e-11)
        self.assertLess(max(abs(v) for v in r.receipt['stock_balance_by_class_m3']), 1e-11)

    def test_01_metric_material_coincident_grid_and_crop(self):
        x = np.linspace(-6.2, -5.2, 21); y = np.linspace(.15, 1.15, 21)
        xf = np.linspace(x[0], x[-1], 41); yf = np.linspace(y[0], y[-1], 41)
        coarse = ae.metric_resistance_field(x, y)
        fine = ae.metric_resistance_field(xf, yf)[::2, ::2]
        crop = ae.metric_resistance_field(x[3:-4], y[5:-2])
        error = float(np.max(abs(coarse-fine)))
        self.assertLess(error, 1e-13)
        self.assertTrue(np.array_equal(crop, coarse[5:-2, 3:-4]))
        REPORT['tests']['metric_material'] = {'coincident_refinement_error': error,
                                              'crop_identical': True}

    def test_02_low_footprint_donor_cannot_be_blindly_excavated(self):
        zz = np.array([[.03, .02, .03], [.02, .00, .02], [.03, .02, .03]])
        neighbors, distances = zmod._neighbors(zz.shape, .05, .05, np.ones(zz.shape, bool))
        room, drain = ae.donor_scour_room(zz.ravel(), np.array([4, 0]),
                                        neighbors, distances, ae.TransportOptions())
        self.assertEqual(room[0], 0)
        self.assertFalse(drain[0])
        self.assertGreater(room[1], 0)
        self.assertLessEqual(room[1], .0015)
        # A low diagonal behind higher N/S/E/W neighbors is inaccessible.
        zz[0,0] = -.01
        blocked, _ = ae.donor_scour_room(zz.ravel(), np.array([4]),
            neighbors, distances, ae.TransportOptions())
        self.assertEqual(blocked[0], 0)
        REPORT['tests']['pit_donor'] = {'pit_scour_allowance_m': float(room[0]),
                                       'draining_donor_allowance_m': float(room[1])}

    def test_03_zero_rain_does_not_regrade_source(self):
        x = np.linspace(0, .6, 13); y = np.linspace(0, .5, 11)
        xx, yy = np.meshgrid(x, y)
        z = .04*xx + .003*np.sin(13*yy)
        r = run(ae, x, y, z, config(rainfall_m=(0.,)))
        self.assertTrue(np.array_equal(r.height_delta_m, np.zeros_like(z)))
        self.check_inventory(r)
        REPORT['tests']['zero_rain'] = 'Bitwise zero height change; no hidden terrain filter'

    def test_04_actual_saved_crop(self):
        file = ROOT/'captures/ad_visible_shoulder_context_preview/AD_SOLVED_FIELDS.npz'
        a = np.load(file)
        x, y = a['x_m'][4:28], a['y_m'][10:42]
        z = a['source_z_m'][10:42, 4:28]
        saved = z.copy()
        report = {'source_file': str(file.relative_to(ROOT)),
                  'source_sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                  'crop_yx': [[10,42],[4,28]], 'shape_yx': list(z.shape),
                  'source': shape_metrics(z), 'results': {}}
        for label, model in [('Z', zmod), ('AE', ae)]:
            start = time.monotonic(); r = run(model, x, y, z, config())
            self.check_inventory(r)
            report['results'][label] = dict(shape_metrics(z+r.height_delta_m),
                wall_seconds=time.monotonic()-start,
                height_min_max_m=[float(r.height_delta_m.min()), float(r.height_delta_m.max())],
                erosion_m3=r.receipt['cumulative_erosion_m3'],
                export_m3=r.receipt['boundary_export_m3'],
                mass_error_m3=r.receipt['sediment_balance_error_m3'],
                no_downhill_donor_contacts=r.receipt.get('ae_no_downhill_donor_contacts'))
        self.assertTrue(np.array_equal(z, saved))
        old, new = report['results']['Z'], report['results']['AE']
        self.assertLess(new['curvature_rms_mm'], old['curvature_rms_mm'] * .70)
        self.assertLess(new['local_four_neighbor_pits'], old['local_four_neighbor_pits'])
        REPORT['comparisons']['actual_crop'] = report

    def test_05_same_material_isolates_scour_limiter(self):
        a = np.load(ROOT/'captures/ad_visible_shoulder_context_preview/AD_SOLVED_FIELDS.npz')
        x, y = a['x_m'][4:28], a['y_m'][10:42]; z = a['source_z_m'][10:42,4:28]
        cfg = config(heterogeneity_strength=0.)
        old, new = (run(model, x, y, z, cfg) for model in (zmod, ae))
        self.check_inventory(new)
        om, nm = shape_metrics(z+old.height_delta_m), shape_metrics(z+new.height_delta_m)
        self.assertLess(nm['curvature_rms_mm'], om['curvature_rms_mm'] * .75)
        REPORT['comparisons']['limiter_only_no_heterogeneity'] = {'Z': om, 'AE': nm}

    def test_06_resolution_same_physical_plane(self):
        results = []
        for spacing in (.05, .025):
            x = np.linspace(-1.2, 0, round(1.2/spacing)+1)
            y = np.linspace(0, .8, round(.8/spacing)+1)
            xx, yy = np.meshgrid(x, y)
            z = .025*xx + .014*yy
            r = run(ae, x, y, z, config(rainfall_m=(.020, .025), heterogeneity_strength=0.))
            self.check_inventory(r)
            results.append(r)
        error = results[0].height_delta_m[3:-3, 3:-3] - results[1].height_delta_m[::2,::2][3:-3,3:-3]
        rms = float(np.sqrt(np.mean(error**2)))
        REPORT['tests']['resolution_sensitivity'] = {
            'spacings_m': [.05,.025], 'test_surface': 'Same plane at both resolutions',
            'interior_delta_rms_m': rms,
            'warning': 'This does not prove convergence on the actual terrain or remove all D8 anisotropy'}
        self.assertLess(rms, .004)

    def test_07_routing_directional_diagnostic(self):
        x = np.linspace(0, 1, 21); y=x.copy(); xx,yy=np.meshgrid(x,y)
        nbr, distances = zmod._neighbors(xx.shape,.05,.05,np.ones(xx.shape,bool))
        offsets=np.array(zmod._OFFSETS)[:,::-1]*.05
        errors=[]
        for deg in (0,15,30,45,60,75,90):
            angle=np.deg2rad(deg); downhill=np.array([np.cos(angle),np.sin(angle)])
            z=-(xx*downhill[0]+yy*downhill[1])*.04
            weights,*_=zmod._flow_routes(z.ravel(),np.ones(xx.shape,bool),nbr,distances,1.35)
            vector=(weights@offsets).reshape(xx.shape+(2,))[3:-3,3:-3].mean(axis=(0,1))
            error=float(np.rad2deg(np.arccos(np.clip(np.dot(vector,downhill)/np.linalg.norm(vector),-1,1))))
            errors.append(error)
        REPORT['tests']['retained_mfd_angular_bias']={'angles_degrees':[0,15,30,45,60,75,90],
            'errors_degrees':errors,'maximum_error_degrees':max(errors),
            'interpretation':'Residual MFD grid bias remains; not presented as fixed by donor CFL'}
        self.assertLess(max(errors), 10.)


    def test_08_context_adapter_keeps_projection_collar_locked(self):
        from visible_shoulder_flow_ad import ContextSpec, context_axes, sample_displacement
        spec = ContextSpec(bounds_m=(-1., 0., 0., 1.), spacing_m=.05,
            protected_bounds_m=(100.,101.,100.,101.),
            protected_contact_x_min_m=0., transition_m=.1, mesh_guard_m=.07,
            loose_layer_m=.060, retained_deposit_cap_m=.030,
            flow=config(rainfall_m=(.025,)))
        x,y=context_axes(spec);xx,yy=np.meshgrid(x,y);z=.05*xx+.015*yy
        r=ae.solve_context(x,y,z,spec=spec)
        self.check_inventory(r.flow)
        locked=r.mobility==0
        self.assertTrue(np.array_equal(r.flow.height_delta_m[locked], np.zeros(locked.sum())))
        self.assertEqual(float(sample_displacement(r,np.array([[0.,.5]]))[0]),0.)
        REPORT['tests']['context_adapter']={'locked_cells':int(locked.sum()),
            'locked_cells_exactly_unchanged':True,'AD_sample_displacement_compatible':True}


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestAE)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    REPORT.update(passed=result.wasSuccessful(), tests_run=result.testsRun,
        wall_seconds=time.monotonic()-START,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        resource_limits={'cpu_threads':1,'maximum_test_grid_samples':1617,
                         'full_saved_domain_solver_rerun':False,'blender_or_render':False},
        api={'module':'src/flow_transport_ae.py',
             'context':'solve_context(x_m, y_m, triangle_z_m, spec=existing_ContextSpec)',
             'core':'simulate_shoulder(..., transport_options=TransportOptions(scour_cfl=0.45, max_local_erosion_step_m=0.0015))'})
    (ROOT/'receipts/ae_transport_tests.json').write_text(json.dumps(REPORT,indent=2)+'\n')
    print(json.dumps(REPORT,indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
