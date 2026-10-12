"""CQ: repair CF's proposal domain without adding historical gravel stock.

The original selected stock and its proposal/packing/exclusion domain agree.
CE's existing owner labels conserve each labelled group's exact body inventory.
Owner zero includes CE's unassigned/background region; these are static authored
groups, not measured catchments or transport by the latest small storm.
"""
from pathlib import Path
import gc
import hashlib
import json
import time

import numpy as np

from coupled_shoulder_ce import history, region
from approved_density_lod import PackingIndex

NAME = 'AP graded margin / exact metric lag instances'
BOUNDS = (-6.4, -3.50, -.65, 8.0)
SEED = 2610101856
PROPOSAL_COUNT = 200000
Y_BANDS = ((-.65, .3), (.3, 1.), (1., 3.), (3., 5.3), (5.3, 6.5), (6.5, 8.))
X_BANDS = ((-6.4, -5.65), (-5.65, -3.52), (-3.52, -3.50))


def digest(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def eligible_domain(xy):
    q = np.asarray(xy)
    xmin, xmax, ymin, ymax = BOUNDS
    return ((q[:, 0] > xmin) & (q[:, 0] < xmax) &
            (q[:, 1] > ymin) & (q[:, 1] < ymax))


def footprint_reaches_domain(xy, radius, candidate_radius):
    """Conservative disk/AABB overlap; includes obstacles across every edge."""
    xmin, xmax, ymin, ymax = BOUNDS
    r = float(radius) + float(candidate_radius)
    return (xy[0] + r > xmin and xy[0] - r < xmax and
            xy[1] + r > ymin and xy[1] - r < ymax)


def band_counts(xy):
    q = np.asarray(xy)
    return {
        'x': [{'bounds_m': [a, b], 'count': int(((q[:, 0] >= a) & (q[:, 0] < b)).sum())}
              for a, b in X_BANDS],
        'y': [{'bounds_m': [a, b], 'count': int(((q[:, 1] >= a) & (q[:, 1] < b)).sum())}
              for a, b in Y_BANDS],
    }


def proposals(count=PROPOSAL_COUNT):
    """Same CF score and seed; only its finite physical support is repaired."""
    xmin, xmax, ymin, ymax = BOUNDS
    rng = np.random.default_rng(SEED)
    # Evaluate the coordinates that will actually be stored in the point mesh.
    raw = np.c_[rng.uniform(xmin, xmax, count), rng.uniform(ymin, ymax, count)].astype('f4')
    valid = eligible_domain(raw)
    _, core, receive, owner = history(raw)
    score = (.04 + .96 * core ** 1.25) * (1 - .93 * receive) * region(raw)
    keep = valid & (rng.random(len(raw)) < score)
    accepted = raw[keep]
    groups = owner[keep]
    order = rng.permutation(len(accepted))
    accepted, groups = accepted[order], groups[order]
    report = {
        'seed': SEED, 'raw_count': len(raw), 'accepted_count': len(accepted),
        'domain_bounds_m': list(BOUNDS),
        'raw_coordinate_minmax_m': [raw.min(0).tolist(), raw.max(0).tolist()],
        'raw_band_counts': band_counts(raw), 'accepted_band_counts': band_counts(accepted),
        'accepted_group_counts': {str(g): int((groups == g).sum()) for g in (0, 1)},
        'accepted_group_large_shape_pool_counts': {
            str(g): int(((groups == g) & (accepted[:, 1] >= 3.)).sum()) for g in (0, 1)},
        'accepted_coordinates_and_groups_sha256': digest(accepted, groups),
        'score_changed': False,
    }
    assert len(accepted) and np.all(eligible_domain(accepted))
    return accepted, groups, report


def allocate(before, prototype, radius, diameter, proposal, proposal_group, exclusions,
             spacing_obstacles=()):
    """Every selected original ID must fit its existing CE-labelled group."""
    eligible = eligible_domain(before[:, :2])
    ids = np.flatnonzero(eligible)
    source_group = history(before[ids, :2])[3]
    by_id = dict(zip(ids.tolist(), source_group.tolist()))
    largest = max([float(np.max(radius))] + [float(r) for _, r in spacing_obstacles])
    packing = PackingIndex(largest)
    for xy, r in spacing_obstacles:
        packing.add(xy, r)
    obstacle_count = 0
    for i in np.flatnonzero(~eligible):
        if footprint_reaches_domain(before[i, :2], radius[prototype[i]], largest):
            packing.add(before[i, :2], radius[prototype[i]])
            obstacle_count += 1
    pools = {(g, large): proposal[(proposal_group == g) &
                                  ((proposal[:, 1] >= 3.) if large else True)]
             for g in (0, 1) for large in (False, True)}
    cursors = {key: 0 for key in pools}
    selected_ids, selected_xy = [], []
    order = ids[np.argsort(-radius[prototype[ids]], kind='stable')]
    for i in order:
        rr = float(radius[prototype[i]])
        key = (by_id[int(i)], bool(diameter[prototype[i]] > .013))
        pool = pools[key]
        while cursors[key] < len(pool):
            v = pool[cursors[key]]
            cursors[key] += 1
            blocked = any(float(np.sum((v - c) ** 2)) < (rr + r) ** 2 for c, r in exclusions)
            if not blocked and packing.clear(v, rr):
                packing.add(v, rr)
                selected_ids.append(i)
                selected_xy.append(v)
                break
        else:
            raise AssertionError(('CQ exact group inventory cannot fit; no partial scene mutation',
                                  int(i), key, len(selected_ids), len(ids), len(pool)))
    ix = np.asarray(selected_ids, dtype=np.int64)
    xy = np.asarray(selected_xy, dtype='f4')
    assert np.array_equal(np.sort(ix), ids)
    assert np.all(eligible_domain(xy))
    final_group = history(xy)[3]
    assert np.array_equal(final_group, np.asarray([by_id[int(i)] for i in ix]))
    assert np.all(xy[diameter[prototype[ix]] > .013, 1] >= 3.)
    return ix, xy, {
        'unchanged_body_spacing_obstacles': obstacle_count,
        'fixed_other_bank_spacing_obstacles': len(spacing_obstacles),
        'group_labels_before_in_selected_id_order': np.asarray([by_id[int(i)] for i in ix]),
        'group_labels_after_in_selected_id_order': final_group,
        'pool_consumption': {str(key): value for key, value in cursors.items()},
    }


def apply_after_ci(scene, cfg, out):
    """Run AFTER the unchanged baseline CF/CG/CH/CI, before mesh culling.

    Uses the saved original CF inventory, not the already-relocated CF domain.
    Leaves all baseline receipts and baseline CG positions/identities intact.
    """
    import bpy
    from context_mesh_refine_ab import _read, SourceSampler

    start = time.monotonic()
    assert cfg['revision'] == 1
    ob = scene.objects[NAME]
    assert np.array_equal(np.asarray(ob.matrix_world), np.eye(4)) and len(ob.modifiers) == 1
    current_cf = _read(ob.data.vertices, 'co', 3)
    pr = _read(ob.data.attributes['prototype'].data, 'value', 1, np.int32)
    yaw = _read(ob.data.attributes['yaw'].data, 'vector', 3)
    baseline_path = Path(out) / 'CF_EXACT_POINT_CHANGE.npz'
    baseline_receipt = Path(out) / 'EXISTING_GRAVEL_POCKETS_CF.json'
    baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    baseline_receipt_sha = hashlib.sha256(baseline_receipt.read_bytes()).hexdigest()
    with np.load(baseline_path, allow_pickle=False) as saved:
        before = saved['before'].copy()
        assert np.array_equal(current_cf, saved['after']), 'CQ requires exact baseline CF after-state'
        assert np.array_equal(pr, saved['prototype']) and np.array_equal(yaw, saved['yaw'])
    assert len(before) == 5939
    body_ids = np.arange(len(before), dtype=np.int64)
    identity = digest(body_ids, pr, yaw)
    bank = sorted(bpy.data.collections['AP exact coarse lag bank'].objects, key=lambda q: q.name)
    assert len(bank) == 64 and [o.name for o in bank] == [f'AP exact lag {i:03d}' for i in range(64)]
    dims, mins, maxs, rad, vol, hashes = [], [], [], [], [], []
    for o in bank:
        co = _read(o.data.vertices, 'co', 3)
        o.data.calc_loop_triangles()
        tri = _read(o.data.loop_triangles, 'vertices', 3, np.int32)
        v = co[tri].astype(float)
        vol.append(abs(float(np.sum(v[:, 0] * np.cross(v[:, 1], v[:, 2])) / 6)))
        rad.append(np.linalg.norm(co[:, :2], axis=1).max())
        mins.append(co[:, 2].min()); maxs.append(co[:, 2].max())
        dims.append(np.linalg.norm(np.ptp(co[:, :2], axis=0)))
        hashes.append(digest(co, tri))
    rad, vol, mins, maxs, dims = map(np.asarray, (rad, vol, mins, maxs, dims))
    assert dims.max() < .032 and dims.min() > .006
    proposal, groups, proposal_report = proposals()
    exclusions = []
    for o in scene.objects:
        if o.hide_render or not o.name.startswith('AS sparse outer fragment /'):
            continue
        loc = np.asarray(o.matrix_world.translation, float)
        w = np.array(o.bound_box) @ np.asarray(o.matrix_world)[:3, :3].T + loc
        r = float(np.linalg.norm(w[:, :2] - loc[:2], axis=1).max())
        if footprint_reaches_domain(loc[:2], r, rad.max()):
            exclusions.append((loc[:2], r))
    # Freeze the already-built larger class. Its actual weathered geometry sets
    # footprint radii; a packing hash avoids an O(proposals * CG bodies) scan.
    cg = scene.objects['CG finite 18–60 mm historical gravel pockets']
    cg_before = _read(cg.data.vertices, 'co', 3)
    cg_pr = _read(cg.data.attributes['prototype'].data, 'value', 1, np.int32)
    cg_yaw = _read(cg.data.attributes['yaw'].data, 'vector', 3)
    assert np.array_equal(np.asarray(cg.matrix_world), np.eye(4))
    assert np.max(abs(cg_yaw[:, :2])) == 0
    cg_identity = digest(cg_before, cg_pr, cg_yaw)
    ci_report = json.loads((Path(out) / 'FIXED_GRAVEL_SUPPORT_CI.json').read_text())
    assert digest(cg_before[:, :2], cg_pr, cg_yaw) == ci_report['exact_identity_xy_yaw_sha256']
    cg_bank = sorted(bpy.data.collections['CG finite historical gravel prototype bank'].objects,
                     key=lambda q: q.name)
    assert [o.name for o in cg_bank] == [f'CG finite gravel {i:03d}' for i in range(192)]
    cg_radius = np.asarray([np.linalg.norm(_read(o.data.vertices, 'co', 3)[:, :2], axis=1).max()
                            for o in cg_bank])
    spacing_obstacles = [(q[:2], float(cg_radius[k])) for q, k in zip(cg_before, cg_pr)
                         if footprint_reaches_domain(q[:2], cg_radius[k], rad.max())]
    ix, xy, allocation = allocate(before, pr, rad, dims, proposal, groups, exclusions,
                                 spacing_obstacles=spacing_obstacles)
    assert hashlib.sha256(Path(cfg['terrain_payload']).read_bytes()).hexdigest() == cfg['terrain_sha256']
    p = np.load(cfg['terrain_payload'], allow_pickle=False)
    co = p['source_coordinates'].astype(float); co[:, 2] += p['delta']
    tri = p['tri']
    sampler = SourceSampler(co, tri, np.arange(len(tri)), max_triangles=500000, max_bin_entries=4000000)
    z, dep = np.empty(len(xy)), np.empty(len(xy))
    for first in range(0, len(xy), 2048):
        sl = slice(first, first + 2048)
        z[sl] = sampler.height(xy[sl])
        dep[sl] = sampler.sample(p['deposited'][:, 0], xy[sl])
    coat = -np.expm1(-dep / .00035)
    embed = (maxs - mins)[pr[ix]] * (.23 + .52 * coat)
    after = before.copy(); after[ix, :2] = xy; after[ix, 2] = z - mins[pr[ix]] - embed
    assert np.isfinite(after).all()
    unchanged = ~eligible_domain(before[:, :2])
    assert np.array_equal(after[unchanged], before[unchanged])
    before_groups = allocation.pop('group_labels_before_in_selected_id_order')
    after_groups = allocation.pop('group_labels_after_in_selected_id_order')
    group_report = []
    for g in (0, 1):
        left, right = ix[before_groups == g], ix[after_groups == g]
        assert np.array_equal(np.sort(left), np.sort(right))
        group_report.append({
            'group': g, 'before_count': len(left), 'after_count': len(right),
            'before_solid_m3': float(vol[pr[left]].sum()),
            'after_solid_m3': float(vol[pr[right]].sum()),
            'before_body_ids_sha256': digest(np.sort(left)),
            'after_body_ids_sha256': digest(np.sort(right)),
            'before_bands': band_counts(before[left, :2]),
            'after_bands': band_counts(after[right, :2]),
        })
    ob.data.vertices.foreach_set('co', after.ravel()); ob.data.update()
    assert np.array_equal(_read(ob.data.attributes['prototype'].data, 'value', 1, np.int32), pr)
    assert np.array_equal(_read(ob.data.attributes['yaw'].data, 'vector', 3), yaw)
    assert digest(body_ids, pr, yaw) == identity
    assert digest(_read(cg.data.vertices, 'co', 3),
                  _read(cg.data.attributes['prototype'].data, 'value', 1, np.int32),
                  _read(cg.data.attributes['yaw'].data, 'vector', 3)) == cg_identity
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_sha
    assert hashlib.sha256(baseline_receipt.read_bytes()).hexdigest() == baseline_receipt_sha
    report = dict(
        revision='CQ physical-domain correction of CF',
        kind='Finite authored historical gravel; original selected domain and connected-group body inventories preserved',
        existing_points=len(before), selected_existing_points=len(ix), moved_existing_points=len(ix),
        unchanged_prototype_histogram=np.bincount(pr, minlength=64).tolist(),
        prototype_geometry_hashes=hashes,
        prototype_diameter_range_m=[float(dims.min()), float(dims.max())],
        exact_total_body_solid_volume_m3=float(vol[pr].sum()), moved_body_solid_volume_m3=float(vol[pr[ix]].sum()),
        new_particles=0, deleted_particles=0, prototype_shapes_materials_sizes_yaws_changed=False,
        terrain_changed_by_this_adapter=False, shaders_changed=False, cg_objects_changed_by_this_adapter=False,
        application_stage='After unchanged CF/CG/CH/CI and before terrain camera culling',
        baseline_cf_after_sha256=digest(current_cf),
        baseline_cf_array_file_sha256=baseline_sha, baseline_cf_receipt_sha256=baseline_receipt_sha,
        frozen_cg_point_prototype_yaw_sha256=cg_identity,
        before_and_after_body_id_prototype_yaw_sha256=[identity, identity],
        old_and_new_positions_sha256=[digest(before), digest(after)],
        unchanged_outside_selected_domain_sha256=digest(before[unchanged]),
        pocket_bounds_m=list(BOUNDS), original_selection_domain_m=list(BOUNDS),
        before_selected_bands=band_counts(before[ix, :2]), after_selected_bands=band_counts(after[ix, :2]),
        baseline_cf_selected_bands=band_counts(current_cf[ix, :2]),
        connected_group_inventory=group_report, proposals=proposal_report, packing=allocation,
        minimum_embed_fraction=.23, maximum_embed_fraction=.75,
        source_near_shape_guard='Original AP rule retained: diameters above 13 mm remain at y >= 3 m.',
        largest_fragment_exclusions=len(exclusions),
        group_policy='Exact existing CE history owner labels; label 0 includes default background, not a proven hydraulic catchment.',
        history='Original finite historical body inventory reconstructed within its original physical support; no event transport, new stock, per-cell conservation claim, tint change, or target camera density.',
        contact_limit='Enclosing disks exclude this point bank, fixed post-CI CG bank, and AS large fragments. Existing CE height/deposition sampler and embedding formula unchanged; no rigid-body settling or full-scene collision solve.',
        full_exact_allocation_required=True, elapsed_seconds=time.monotonic() - start)
    np.savez_compressed(Path(out) / 'CQ_EXACT_POINT_CHANGE.npz', before=before,
                        baseline_cf_after=current_cf, after=after,
                        prototype=pr, yaw=yaw, selected_body_ids=ix,
                        group_before=before_groups, group_after=after_groups)
    (Path(out) / 'EXISTING_GRAVEL_DOMAIN_CQ.json').write_text(json.dumps(report, indent=2) + '\n')
    p.close(); del sampler, co, tri, before, after
    gc.collect(); print('CQ_GRAVEL_DOMAIN_CORRECTION', json.dumps(report), flush=True)
    return report


def apply(scene, cfg, out):
    """Explicit compatibility entry: this is never a pre-CG CF replacement."""
    return apply_after_ci(scene, cfg, out)
