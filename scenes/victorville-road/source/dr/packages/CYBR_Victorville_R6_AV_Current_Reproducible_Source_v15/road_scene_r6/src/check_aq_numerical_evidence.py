#!/usr/bin/env python3
"""Audit exact archived AQ arrays only; never run transport or load a scene."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'historical_numerical_aq'
SOURCE_SHA='b2d5af4da4c4df4b7a0a5d1c41724ade5a71ace756f53c9eff43092323014c47'
FILM_SHA='d628dabc8caa6a38d1b5c7575f17a83f8082effbe56a65e9a73f3222abe4aed0'

def run():
    source=FOLDER/'AQ_FINAL_SURFACE.npz';film=FOLDER/'AQ_CURRENT_FILM.npz'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA
    assert hashlib.sha256(film.read_bytes()).hexdigest()==FILM_SHA
    receipt=json.loads((ROOT/'historical_captures_aq/aq_continuous_contact_context/AQ_CURRENT_FILM.json').read_text())
    assert receipt['source_sha256']==SOURCE_SHA and receipt['fields_sha256']==FILM_SHA
    with np.load(source,allow_pickle=False) as data:s=dict(data)
    with np.load(film,allow_pickle=False) as data:f=dict(data)
    assert s['actual_surface_z_m'].shape==(1281,89)
    assert np.isfinite(s['actual_surface_z_m']).all()
    assert str(s['surface_schema'])=='AQ_CURRENT_PHYSICAL_V1'
    assert str(f['event_schema'])=='AQ_NEW_CONTINUOUS_CONTACT_EVENT_V1'
    assert str(f['source_fields_sha256'])==SOURCE_SHA
    for key in ('x_m','y_m','actual_surface_z_m','pavement','owner','road_edge_x_m'):
        np.testing.assert_array_equal(f[key],s[key])
    np.testing.assert_allclose(np.diff(s['x_m']),.0125,atol=1e-14,rtol=0)
    np.testing.assert_allclose(np.diff(s['y_m']),.0125,atol=1e-14,rtol=0)
    p=f['pavement'];stock=f['remaining_mobile_class_thickness_m']
    road=f['pavement_owned_class_thickness_m'];soil=f['soil_owned_class_thickness_m']
    np.testing.assert_array_equal(road+soil,stock)
    np.testing.assert_array_equal(stock,f['remaining_initial_mobile_class_thickness_m']+f['retained_deposit_by_class_m'])
    assert np.isfinite(stock).all() and np.min(stock)>=0
    assert np.count_nonzero(road[~p])==0 and np.count_nonzero(soil[p])==0
    ledger=receipt['class_ledger'];area=.0125**2
    initial=f['initial_mobile_class_thickness_m'].sum(axis=(0,1))*area
    remaining=f['remaining_initial_mobile_class_thickness_m'].sum(axis=(0,1))*area
    retained=f['retained_deposit_by_class_m'].sum(axis=(0,1))*area
    for actual,key in ((initial,'initial_by_class_m3'),(remaining,'remaining_initial_by_class_m3'),(retained,'retained_deposit_by_class_m3')):
        np.testing.assert_allclose(actual,ledger[key],atol=1e-15,rtol=0)
    error=initial-remaining-retained-np.asarray(ledger['export_by_class_m3'])+np.asarray(ledger['roundoff_added_by_class_m3'])
    assert np.max(abs(error))<ledger['absolute_class_tolerance_m3']==1e-12
    assert ledger['passed'] is True and receipt['coverage']['missing_xy_count']==0
    assert receipt['historical_Z_stock_modified'] is False and receipt['old_pavement_grid_reused'] is False
    assert receipt['geometry_modified_by_film'] is False and receipt['opacity_scale_modified'] is False
    result=dict(passed=True,source_sha256=SOURCE_SHA,film_sha256=FILM_SHA,
        source_and_event_grid_shape=[1281,89],actual_arrays_match_source=True,
        ownership_split_exact=True,class_ledger_rechecked_without_solver=True,
        maximum_class_balance_error_m3=float(np.max(abs(error))),
        archived_outputs_are_replay_inputs=False,full_solver_rerun=False,blender_executed=False)
    print(json.dumps(result));return result

if __name__=='__main__':run()
