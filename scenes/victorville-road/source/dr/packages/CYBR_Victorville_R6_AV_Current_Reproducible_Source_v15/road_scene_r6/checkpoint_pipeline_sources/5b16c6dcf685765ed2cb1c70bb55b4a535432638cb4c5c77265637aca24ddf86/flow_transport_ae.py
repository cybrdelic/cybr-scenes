"""AE conservative causal correction to AD/Z; NumPy only and source-only.

The preserved Z algorithm can excavate any stage-wet footprint donor using the
packet source's shear. At 50 mm spacing and a 10 mm event budget, this digs
through the donor's real downstream support while the route stays frozen. A
4 mm contact head then switches contacts off; the next event sees new pits.

AE tests current donor relief BEFORE entrainment, allowing at most a bounded
fraction of real downhill bed relief per exchange. This prevents off-source
shear from digging blind potholes. Every rejected grain stays in its original
finite inventory. Z's stage-limited deposition, inventories and ledgers remain.
No output filter, invented elevations, grain edits or material tint is applied.

The seeded material resistance now lives at fixed world-metre coordinates;
changing a crop or grid resolution no longer changes the material randomly.
This remains nonvalidated art-directed landscape evolution. Build any coherent
grading/wash foundation before transport; do not ask stronger erosion to invent
one from an already multiply weathered surface.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import time
import numpy as np
from flow_sediment_model_z import (
    FlowConfig, FlowResult, CLASS_NAMES, _validate, _axis, _neighbors,
    _flow_routes, _footprints, _footprint_face_adjacency,
    _connected_wet_contact, _repair_roundoff_inventory, _assert_event_state,
    _relax_deposits)

@dataclass(frozen=True)
class TransportOptions:
    scour_cfl: float = 0.45
    max_local_erosion_step_m: float = 0.0015


def metric_resistance_field(x_m, y_m, seed=73109):
    """Continuous, fixed-coordinate material property, not terrain geometry."""
    x, y = np.meshgrid(np.asarray(x_m), np.asarray(y_m))
    result = np.zeros_like(x, dtype=float)
    for octave, (spacing, weight) in enumerate(((0.18, .28), (.43, .46), (.91, .26))):
        u, v = x / spacing, y / spacing
        ix, iy = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
        fx, fy = u - ix, v - iy
        def value(ox, oy):
            # Integer lattice hashing is stable for negative coordinates too.
            k = ((ix + ox).astype(np.uint64) * np.uint64(0x9e3779b185ebca87)
                 ^ (iy + oy).astype(np.uint64) * np.uint64(0xc2b2ae3d27d4eb4f)
                 ^ np.uint64((int(seed) + octave * 104729) & ((1 << 64) - 1)))
            k ^= k >> np.uint64(30)
            k *= np.uint64(0xbf58476d1ce4e5b9)
            k ^= k >> np.uint64(27)
            k *= np.uint64(0x94d049bb133111eb)
            k ^= k >> np.uint64(31)
            return ((k >> np.uint64(11)).astype(float) / float(1 << 53)) * 2 - 1
        result += weight * ((value(0, 0) * (1-fx) + value(1, 0) * fx) * (1-fy)
                            + (value(0, 1) * (1-fx) + value(1, 1) * fx) * fy)
    return result


def donor_scour_room(current_z, donor_ids, neighbors, distances, options):
    """Bound pre-debit bed erosion by actual connected downhill support.

    The steepest actual shared-face contact defines a valid escape. A lower
    diagonal cell across two higher face neighbors is not permission to scour
    through their intervening dry crest. A filled spill direction alone is
    deliberately insufficient. Water routing can still distribute over D8.
    """
    js = neighbors[donor_ids]
    # Z neighbor ordering: NW, N, NE, W, E, SW, S, SE.
    face_contact = np.array([False, True, False, True, True, False, True, False])
    valid = (js >= 0) & face_contact[None, :]
    safe = np.maximum(js, 0)
    drops = current_z[donor_ids, None] - current_z[safe]
    slopes = np.where(valid, drops / distances, -np.inf)
    best = np.argmax(slopes, axis=1)
    best_drop = drops[np.arange(len(donor_ids)), best]
    draining = slopes[np.arange(len(donor_ids)), best] > 1e-12
    room = np.minimum(np.maximum(best_drop, 0.) * options.scour_cfl,
                      options.max_local_erosion_step_m)
    return np.where(draining, room, 0.), draining


def simulate_shoulder(x_m: np.ndarray, y_m: np.ndarray, z_m: np.ndarray,
                      config: FlowConfig | None = None,
                      valid_mask: np.ndarray | None = None, *,
                      initial_mobile_class_thickness_m: np.ndarray | None = None,
                      maximum_deposited_thickness_m: np.ndarray | None = None,
                      transport_options: TransportOptions | None = None) -> FlowResult:
    """Route repeat storms and return conservative, physically coupled fields.

    z_m.shape == (len(y_m),len(x_m)); class arrays append a final axis of 3.
    Exposure/burial/lag/compaction fields are bounded [0,1], dimensionless art
    controls. Exposure refers to existing grains in the initial surface; use
    retained deposit thickness/fractions for newly transported grain placement.
    Invalid cells return zero fields and receiver=-2; z may be NaN there.
    initial_mobile_class_thickness_m, when supplied, has shape (ny,nx,3),
    in metres of bulk mobile class thickness at the INITIAL z_m surface. It
    replaces the default soil inventory exactly on valid cells; it is not
    multiplied by boundary mobility. Zero means nonerodible substrate, not
    an invitation to replenish from the configured soil mixture. A remaining
    veneer still exists at the locked rim. Erosion also obeys Y's per-event
    budget and max_erosion_m * boundary_mobility initial-layer scour bound.
    z_m already includes the supplied layer; do not add its thickness again.

    maximum_deposited_thickness_m, when supplied, has shape (ny,nx) and caps
    RETAINED transported deposit thickness summed over all classes, not gross
    cumulative deposition and not net elevation. It excludes the unentrained
    initial layer. Y's global net-elevation and connected-wet-stage limits also
    apply. Excess load remains routed or exports; slope transfer obeys the same
    retained-deposit cap. Zero prevents deposition even into an eroded cell.
    Both optional arrays must be finite and nonnegative on valid cells; values
    on invalid cells are ignored. None retains each corresponding Y behavior.

    initial_mobile_class_thickness_m and remaining_initial_mobile_class_thickness_m
    in the result expose the finite initial layer separately from transported
    deposits. The remaining initial layer plus retained_deposit_by_class_m is
    the remaining mobile surface stock, not a calibrated opacity or coverage
    prediction. The art
    exposure/surface-fraction controls retain Y semantics; empty cells may use
    its fallback mixture and must not be treated as evidence of sediment mass.
    Input arrays are never modified. No scene, material or file operations occur.
    """
    started = time.perf_counter()
    options = transport_options or TransportOptions()
    if (not np.isfinite(options.scour_cfl) or not 0 < options.scour_cfl <= 1
            or not np.isfinite(options.max_local_erosion_step_m)
            or options.max_local_erosion_step_m <= 0):
        raise ValueError("AE requires positive local step and scour_cfl in (0, 1]")
    limited_erosion_requests = 0.
    no_downhill_donor_contacts = 0
    cfg = config or FlowConfig()
    _validate(cfg)
    x, dx = _axis(x_m, "x_m")
    y, dy = _axis(y_m, "y_m")
    z0 = np.asarray(z_m, np.float64)
    shape = (len(y), len(x))
    if z0.shape != shape:
        raise ValueError(f"z_m must have shape {shape}, got {z0.shape}")
    valid = np.ones(shape, bool) if valid_mask is None else np.asarray(valid_mask, bool).copy()
    if valid.shape != shape or not np.any(valid):
        raise ValueError("valid_mask must match z_m and contain active cells")
    if not np.all(np.isfinite(z0[valid])):
        raise ValueError("All active z_m samples must be finite actual terrain heights")
    n, area = z0.size, dx * dy
    active = valid.ravel()
    zbase = np.where(valid, z0, 0.).ravel().copy()
    # Hydraulic geometry uses a relative datum at picometre precision, keeping
    # arbitrary world-Z offsets from changing otherwise equal routing ties.
    zbase = np.round(zbase - zbase[np.flatnonzero(active)[0]], 12)
    texture = metric_resistance_field(x, y, cfg.seed).ravel() * cfg.heterogeneity_strength
    erodibility = np.clip(1.0 + 1.5 * texture, 0.20, 1.9)
    resistance = np.clip(1.0 - 0.65 * texture, 0.65, 1.5)
    yy, xx = np.indices(shape)
    edge_cells = np.minimum.reduce((xx, yy, shape[1] - 1 - xx, shape[0] - 1 - yy))
    band = (np.clip(edge_cells / cfg.boundary_band_cells, 0., 1.)
            if cfg.boundary_band_cells else np.ones(shape))
    if cfg.boundary_band_m is not None:
        edge_metres = np.minimum.reduce((xx * dx, yy * dy, (shape[1] - 1 - xx) * dx, (shape[0] - 1 - yy) * dy))
        band = np.clip(edge_metres / cfg.boundary_band_m, 0., 1.)
    band = (band * band * (3. - 2. * band)).ravel()
    band[~active] = 0.
    if initial_mobile_class_thickness_m is None:
        initial = np.tile(np.asarray(cfg.substrate_fractions) * cfg.max_erosion_m * area, (n, 1))
        initial *= band[:, None]
    else:
        supplied = np.asarray(initial_mobile_class_thickness_m, dtype=np.float64)
        if supplied.shape != shape + (3,):
            raise ValueError(f"initial_mobile_class_thickness_m must have shape {shape + (3,)}")
        if np.any(~np.isfinite(supplied[valid])) or np.any(supplied[valid] < 0):
            raise ValueError("Active initial mobile class thicknesses must be finite and nonnegative")
        initial = np.where(valid[..., None], supplied, 0.).reshape(n, 3).copy() * area
    deposit_cap = None
    if maximum_deposited_thickness_m is not None:
        supplied_cap = np.asarray(maximum_deposited_thickness_m, dtype=np.float64)
        if supplied_cap.shape != shape:
            raise ValueError(f"maximum_deposited_thickness_m must have shape {shape}")
        if np.any(~np.isfinite(supplied_cap[valid])) or np.any(supplied_cap[valid] < 0):
            raise ValueError("Active maximum deposited thicknesses must be finite and nonnegative")
        deposit_cap = np.where(valid, supplied_cap, 0.).ravel().copy()
    bed = initial.copy()
    deposited = np.zeros((n, 3))
    eroded = np.zeros((n, 3))
    deposition = np.zeros((n, 3))
    water_total = np.zeros(n)
    max_depth = np.zeros(n)
    max_shear = np.zeros(n)
    max_pond = np.zeros(n)
    neighbors, distances = _neighbors(shape, dx, dy, valid)
    footprint_index, footprint_weight = _footprints(shape, dx, dy, valid, cfg.exchange_diameter_m)
    footprint_adjacency, footprint_center = _footprint_face_adjacency(
        footprint_index, footprint_weight, shape[1])
    stage_blocked_contacts = 0
    unplaced_deposition_requests = 0.
    total_slope_transfer = 0.
    roundoff_ledger = {'added_by_class_m3': np.zeros(3), 'corrected_entries': 0}
    roundoff_tolerance = max(area * (cfg.max_erosion_m + cfg.max_deposition_m) * 64 * np.finfo(float).eps, 1e-25)
    upstream_area = np.zeros(shape)
    if cfg.upstream_edge is not None and cfg.upstream_width_m:
        if cfg.upstream_edge == "x_min":
            upstream_area[:, 0] = cfg.upstream_width_m * dy
        elif cfg.upstream_edge == "x_max":
            upstream_area[:, -1] = cfg.upstream_width_m * dy
        elif cfg.upstream_edge == "y_min":
            upstream_area[0] = cfg.upstream_width_m * dx
        else:
            upstream_area[-1] = cfg.upstream_width_m * dx
    upstream_area[~valid] = 0
    upstream_area = upstream_area.ravel()
    exported = np.zeros(3)
    event_receipts = []
    critical = np.asarray(cfg.critical_shear_pa)
    concentration = np.asarray(cfg.max_concentration)
    active_area = float(active.sum() * area)
    width = math.sqrt(area)
    rainfall_total = water_export_total = upstream_total = infiltration_total = 0.
    receiver = np.full(n, -1, np.int32)
    for event, rain in enumerate(cfg.rainfall_m):
        z = zbase + (bed + deposited - initial).sum(axis=1) / area
        route_weight, slope, filled, order, receiver = _flow_routes(
            z, valid, neighbors, distances, cfg.flow_partition_exponent)
        pond = np.where(active, np.maximum(filled - z, 0), 0)
        max_pond = np.maximum(max_pond, pond)
        water = np.full(n, rain * area * cfg.runoff_fraction)
        water[~active] = 0
        water += rain * cfg.upstream_runoff_fraction * upstream_area
        # Water accumulation completes before hydraulic footprint estimates.
        # This local discharge-per-width average has a physical 100 mm support.
        for i in order:
            js = neighbors[i]
            moving = route_weight[i] > 0
            if np.any(moving):
                water[js[moving]] += water[i] * route_weight[i, moving]
        hydraulic_water = np.sum(water[footprint_index] * footprint_weight, axis=1)
        event_erosion = np.zeros(n)
        mobile = np.zeros((n, 3))
        event_export = np.zeros(3)
        event_water_export = 0.
        eroded_before, deposited_before = float(eroded.sum()), float(deposition.sum())
        current_bed_height = z.copy()
        for i in order:
            w = water[i]
            if w <= 0:
                continue
            j = receiver[i]
            s = max(slope[i], cfg.minimum_transport_slope)
            # Wide-shallow Manning approximation; flooded cells are attenuated.
            h = ((hydraulic_water[i] / cfg.event_duration_s / width) * cfg.manning_n * resistance[i]
                 / math.sqrt(s)) ** 0.6
            h = min(h, 0.035)
            shear = 9810. * h * slope[i]
            pool_damping = math.exp(-min(pond[i] / 0.003, 30.))
            shear *= pool_damping
            water_total[i] += w
            max_depth[i] = max(max_depth[i], h)
            max_shear[i] = max(max_shear[i], shear)
            # Capacity saturates gently. Coarse particles stop before fine ones
            # as energy drops, producing downstream fining without region masks.
            excess = np.maximum(shear / critical - 1., 0.)
            mobility = excess / (1. + excess)
            cap = w * concentration * mobility * pool_damping
            load = mobile[i]
            reach_length = float(np.sum(route_weight[i] * distances))
            if reach_length <= 0:
                reach_length = width
            settle = (1. - np.exp(-reach_length / np.asarray(cfg.deposition_length_m))) * (cfg.deposition_relaxation / .82)
            settle = np.minimum(settle, 1.)
            want_deposit = np.maximum(load - cap, 0.) * settle
            all_ids = footprint_index[i]
            all_weights = footprint_weight[i]
            all_net = (bed[all_ids] + deposited[all_ids] - initial[all_ids]).sum(axis=1)
            current_height = zbase[all_ids] + all_net / area
            # Head is anchored to the pre-storm water calculation. It can fall
            # with a newly scoured source, but a depositing source cannot lift
            # its own water stage within the same frozen-hydraulics pass.
            source_height = current_height[footprint_center]
            stage = min(z[i], source_height) + min(h, cfg.maximum_contact_head_m)
            contact, head_room, reached = _connected_wet_contact(
                current_height, stage, all_weights, footprint_adjacency, footprint_center)
            stage_blocked_contacts += int(np.count_nonzero((all_weights > 0) & ~reached))
            supported = all_weights > 0
            ids = all_ids[supported]
            weights = contact[supported]
            net = all_net[supported]
            room = np.maximum(0., cfg.max_deposition_m * area * band[ids] - net)
            if deposit_cap is not None:
                room = np.minimum(room, np.maximum(
                    deposit_cap[ids] * area - deposited[ids].sum(axis=1), 0.))
            room = np.minimum(room, area * head_room[supported])
            add = weights[:, None] * want_deposit[None, :]
            add *= np.minimum(1., room / np.maximum(add.sum(axis=1), 1e-30))[:, None]
            if np.any((add.sum(axis=1) > 0) &
                      (current_height[supported] + add.sum(axis=1) / area > stage + 1e-12)):
                raise FloatingPointError('Stage-limited deposition exceeded available hydraulic head')
            deposited[ids] += add
            deposition[ids] += add
            load -= add.sum(axis=0)
            unplaced_deposition_requests += max(0., float(want_deposit.sum() - add.sum()))
            entrain = min(1., (1. - math.exp(-reach_length / cfg.erosion_length_m)) * (cfg.erosion_relaxation / .55))
            demand = np.maximum(cap - load, 0.) * entrain
            # Re-evaluate current wet connectivity after this deposit. A cell
            # filled to stage is no longer an erodible wetted contact here.
            updated_height = zbase[all_ids] + (bed[all_ids] + deposited[all_ids] - initial[all_ids]).sum(axis=1) / area
            contact, _, _ = _connected_wet_contact(
                updated_height, stage, all_weights, footprint_adjacency, footprint_center)
            take = contact[supported, None] * demand[None, :]
            available = np.maximum(deposited[ids] + bed[ids], 0.)
            take = np.minimum(take, available)
            # A packet's shear belongs to its wetted reach, not to arbitrarily
            # deep cells inside that reach. Reconstruct every donor's ACTUAL
            # current downhill relief before taking any of its finite stock.
            # No donor may be excavated through its open downstream bed support.
            # This is an Exner morphology CFL bound applied before debit; it
            # neither edits completed heights nor creates/fills terrain.
            current_bed_height[ids] = zbase[ids] + (bed[ids] + deposited[ids] - initial[ids]).sum(axis=1) / area
            downhill_room, draining = donor_scour_room(
                current_bed_height, ids, neighbors, distances, options)
            no_downhill_donor_contacts += int(np.count_nonzero(
                (take.sum(axis=1) > 0) & ~draining))
            proposed = take.sum(axis=1)
            take *= np.minimum(1., area * downhill_room / np.maximum(proposed, 1e-30))[:, None]
            limited_erosion_requests += float(proposed.sum() - take.sum())
            budget = (cfg.max_event_erosion_m * area * band[ids]
                      * np.minimum(erodibility[ids] * shear / 0.45, 1.0))
            budget = np.maximum(budget - event_erosion[ids], 0.)
            take *= np.minimum(1., budget / np.maximum(take.sum(axis=1), 1e-30))[:, None]
            from_deposit = np.minimum(take, deposited[ids])
            from_bed = np.minimum(np.maximum(take - from_deposit, 0.), bed[ids])
            if initial_mobile_class_thickness_m is not None:
                # Bound loss of the ORIGINAL layer independently of overlying
                # deposits: later slumping must not uncover excess deep scour.
                # The supplied class stock is never replenished from substrate.
                bed_erosion_room = np.maximum(cfg.max_erosion_m * area * band[ids]
                    - (initial[ids] - bed[ids]).sum(axis=1), 0.)
                from_bed *= np.minimum(1., bed_erosion_room
                    / np.maximum(from_bed.sum(axis=1), 1e-30))[:, None]
            take = from_deposit + from_bed
            deposited[ids] -= from_deposit
            bed[ids] -= from_bed
            current_bed_height[ids] = zbase[ids] + (bed[ids] + deposited[ids] - initial[ids]).sum(axis=1) / area
            eroded[ids] += take
            event_erosion[ids] += take.sum(axis=1)
            load += take.sum(axis=0)
            js = neighbors[i]
            moving = route_weight[i] > 0
            if np.any(moving):
                mobile[js[moving]] += route_weight[i, moving, None] * load[None, :]
            else:
                event_water_export += w
                event_export += load
            mobile[i] = 0.
        if np.any(mobile != 0.):
            raise FloatingPointError(f'event {event + 1}: sediment packet left on processed routing graph')
        _repair_roundoff_inventory(bed, roundoff_ledger, f'event {event + 1} bed', roundoff_tolerance)
        _repair_roundoff_inventory(deposited, roundoff_ledger, f'event {event + 1} deposit', roundoff_tolerance)
        _assert_event_state(f'event {event + 1} before slope transfer', initial, bed,
                            deposited, eroded, deposition, exported + event_export,
                            area, band, cfg, roundoff_ledger, deposit_cap)
        slope_transfer = _relax_deposits(zbase, initial, bed, deposited, eroded,
                                           deposition, area, band, neighbors, distances,
                                           cfg, dx, dy, roundoff_ledger, deposit_cap)
        total_slope_transfer += slope_transfer
        exported += event_export
        event_state_error = _assert_event_state(f'event {event + 1} after slope transfer',
                                                initial, bed, deposited, eroded, deposition,
                                                exported, area, band, cfg, roundoff_ledger, deposit_cap)
        rainfall = rain * active_area
        upstream = rain * cfg.upstream_runoff_fraction * float(upstream_area.sum())
        infiltrated = rainfall * (1. - cfg.runoff_fraction)
        rainfall_total += rainfall
        upstream_total += upstream
        infiltration_total += infiltrated
        event_water_error = rainfall + upstream - infiltrated - event_water_export
        if not np.isfinite(event_water_error) or abs(event_water_error) > 1e-10:
            raise FloatingPointError(f'event {event + 1}: water conservation failed: {event_water_error}')
        water_export_total += event_water_export
        net_volume = float((bed + deposited - initial).sum())
        event_receipts.append({
            "event": event + 1, "rainfall_m": float(rain),
            "slope_redistribution_m3": slope_transfer,
            "absolute_class_balance_error_m3": event_state_error,
            "roundoff_inventory_added_m3": float(roundoff_ledger['added_by_class_m3'].sum()),
            "rainfall_m3": float(rainfall), "upstream_water_m3": float(upstream),
            "infiltration_m3": float(infiltrated),
            "water_boundary_export_m3": float(event_water_export),
            "erosion_m3": float(eroded.sum()) - eroded_before,
            "deposition_m3": float(deposition.sum()) - deposited_before,
            "sediment_export_by_class_m3": event_export.tolist(),
            "cumulative_net_bed_change_m3": net_volume,
            "cumulative_sediment_balance_error_m3": net_volume + float(exported.sum()),
        })
    delta = (bed + deposited - initial).sum(axis=1) / area
    erosion_m = eroded.sum(axis=1) / area
    deposition_m = deposition.sum(axis=1) / area
    deposit_m = deposited.sum(axis=1) / area
    substrate_loss = (initial - bed).sum(axis=1) / area
    # Surface mixture uses the surviving initial layer plus only the visible
    # upper 1.8 mm-equivalent layer of transported material.
    base_mix = bed / np.maximum(bed.sum(axis=1, keepdims=True), 1e-30)
    empty = bed.sum(axis=1) <= 1e-20
    base_mix[empty] = cfg.substrate_fractions
    deposit_mix = deposited / np.maximum(deposited.sum(axis=1, keepdims=True), 1e-30)
    cover = 1. - np.exp(-deposit_m / 0.0018)
    surface = base_mix * (1. - cover[:, None]) + deposit_mix * cover[:, None]
    diameters = np.asarray(cfg.representative_diameter_m)
    # Exposure of pre-existing grains: erosion exposes, transported cover buries.
    burial = 1. - np.exp(-deposit_m[:, None] / (0.60 * diameters[None, :]))
    uncover = 1. - np.exp(-substrate_loss / 0.003)
    exposure = (0.25 + 0.75 * uncover[:, None]) * (1. - burial)
    fines_removed = (initial[:, 0] - bed[:, 0]) / np.maximum(initial[:, 0], 1e-30)
    coarse_retained = bed[:, 2] / np.maximum(initial[:, 2], 1e-30)
    lag = np.clip(fines_removed * coarse_retained * np.exp(-deposit_m / 0.004), 0, 1)
    # Log throughput makes connected feeder paths visible without claiming a
    # measured compaction law. Compaction is only an exposed-matrix art control.
    p90 = float(np.percentile(water_total[active], 90))
    flow = np.clip(np.log1p(water_total / max(p90 * 0.08, 1e-20)) / math.log(13.5), 0, 1)
    compacted = flow * uncover * (1. - cover) * (1. - 0.70 * lag)
    net_volume = float(delta[active].sum() * area)
    erosion_volume, deposition_volume = float(eroded.sum()), float(deposition.sum())
    export_volume = float(exported.sum())
    balance = erosion_volume - deposition_volume - export_volume
    water_balance = rainfall_total + upstream_total - infiltration_total - water_export_total
    receipt = {
        "model": "AE current-bed donor-supported finite-inventory sediment transport",
        "ae_scour_cfl": options.scour_cfl,
        "ae_max_local_erosion_step_m": options.max_local_erosion_step_m,
        "ae_limited_erosion_requests_m3": limited_erosion_requests,
        "ae_no_downhill_donor_contacts": no_downhill_donor_contacts,
        "ae_resistance": "World-metre-anchored hash lattice; invariant at coincident coordinates under crop/refinement",
        "ae_scour_support": "Current donor must have a lower shared-face bed; finite exchange cannot excavate below its own connected downhill support",
        "ae_limit_note": "Repeated rejected requests are not unique sediment mass; no material was debited or subsequently smoothed",
        "ae_routing_limitation": "Z MFD spill routing is retained; source-only diagnostic revision, not hydrodynamic validation",
        "maximum_contact_head_m": cfg.maximum_contact_head_m,
        "water_stage_interpretation": "Current source bed plus bounded shallow head, never above pre-storm source stage; numerical spill elevation is not permission to wet high crests",
        "contact_connectivity": "Face-connected cells below current source water stage inside the existing finite footprint; no area renormalization",
        "stage_blocked_receiver_contacts": stage_blocked_contacts,
        "unplaced_deposition_requests_m3": unplaced_deposition_requests,
        "unplaced_request_note": "Repeated unaccepted attempts, not unique sediment volume; load remains routed and is conserved",
        "head_cap_caveat": "Nonvalidated low-head contact approximation; no extra infiltration or water loss is introduced",
        "exchange_diameter_m": cfg.exchange_diameter_m,
        "hydraulic_footprint": "Cell-integrated compact disk; discharge per width averaged before bed exchange",
        "flow_routing": "Slope-weighted MFD; metric distance-to-outlet on filled flats",
        "deposition_length_m": list(cfg.deposition_length_m),
        "erosion_length_m": cfg.erosion_length_m,
        "deposit_repose_slope": cfg.deposit_repose_slope,
        "cumulative_slope_redistribution_m3": total_slope_transfer,
        "roundoff_inventory_added_m3": float(roundoff_ledger['added_by_class_m3'].sum()),
        "roundoff_inventory_added_by_class_m3": roundoff_ledger['added_by_class_m3'].tolist(),
        "roundoff_corrected_entries": roundoff_ledger['corrected_entries'],
        "invariants": "Finite nonnegative inventories, per-class absolute mass closure, and height bounds asserted before/after each storm slope transfer",
        "gross_volume_note": "Gross erosion/deposition include internal slope redistribution in equal amounts",
        "status": "NONVALIDATED ART-DIRECTED PHYSICS; not an engineering prediction",
        "seed": int(cfg.seed), "shape_yx": list(shape), "cell_size_xy_m": [dx, dy],
        "cell_area_m2": area, "active_area_m2": active_area,
        "integration": "Every sample is a cell centre with area dx*dy, including rim samples",
        "class_names": list(CLASS_NAMES),
        "representative_diameter_m": list(cfg.representative_diameter_m),
        "source": "Actual supplied triangle Z; random heterogeneity only in resistance/erodibility",
        "open_boundary": "Outer rectangle rim; invalid-mask holes closed",
        "upstream_edge": cfg.upstream_edge, "upstream_contributing_width_m": cfg.upstream_width_m,
        "upstream_source": "Water-only runoff from explicit contributing strip; no imported sediment",
        "initial_mobile_inventory_source": "Supplied exact per-cell class thicknesses" if initial_mobile_class_thickness_m is not None else "Y default soil inventory scaled by boundary mobility",
        "maximum_retained_deposit_cap_m": None if deposit_cap is None else float(deposit_cap[active].max()),
        "minimum_retained_deposit_cap_m": None if deposit_cap is None else float(deposit_cap[active].min()),
        "retained_deposit_cap_interpretation": "Optional per-cell total transported stock cap, excluding remaining initial layer; also subject to Y net-height and wet-stage bounds",
        "initial_mobile_bed_layer_by_class_m3": initial.sum(axis=0).tolist(),
        "remaining_initial_bed_layer_by_class_m3": bed.sum(axis=0).tolist(),
        "retained_transported_deposit_by_class_m3": deposited.sum(axis=0).tolist(),
        "stock_balance_by_class_m3": (initial.sum(axis=0) + roundoff_ledger['added_by_class_m3'] - bed.sum(axis=0) - deposited.sum(axis=0) - exported).tolist(),
        "minimum_remaining_initial_class_thickness_m": float(bed[active].min() / area),
        "minimum_retained_deposit_class_thickness_m": float(deposited[active].min() / area),
        "maximum_retained_deposit_cap_excess_m": None if deposit_cap is None else float(max(0., np.max(deposit_m[active] - deposit_cap[active]))),
        "initial_mobile_bed_layer_m3": float(initial.sum()),
        "remaining_initial_bed_layer_m3": float(bed.sum()),
        "retained_transported_deposit_m3": float(deposited.sum()),
        "cumulative_erosion_m3": erosion_volume,
        "cumulative_deposition_m3": deposition_volume,
        "boundary_export_m3": export_volume,
        "boundary_export_by_class_m3": exported.tolist(),
        "suspended_end_m3": 0., "net_height_volume_m3": net_volume,
        "sediment_balance_error_m3": balance,
        "net_bed_plus_export_error_m3": net_volume + export_volume,
        "relative_sediment_balance_error": abs(balance) / max(erosion_volume, 1e-30),
        "rainfall_m3": rainfall_total, "upstream_water_m3": upstream_total,
        "infiltration_m3": infiltration_total, "water_boundary_export_m3": float(water_export_total),
        "water_balance_error_m3": float(water_balance),
        "minimum_height_delta_m": float(delta[active].min()),
        "maximum_height_delta_m": float(delta[active].max()),
        "bounds_m": [-cfg.max_erosion_m, cfg.max_deposition_m],
        "boundary_band_cells": cfg.boundary_band_cells,
        "boundary_band_m": cfg.boundary_band_m,
        "boundary_treatment": "Smoothstep mobility scales local erosion/deposition bounds; rim locked, water/sediment pass through",
        "events": event_receipts, "runtime_s": time.perf_counter() - started,
    }
    def field(a: np.ndarray) -> np.ndarray:
        a = a.copy()
        a[~active] = 0
        return a.reshape(shape + a.shape[1:])
    receiver[~active] = -2
    return FlowResult(
        height_delta_m=field(delta), cumulative_water_m3=field(water_total),
        cumulative_erosion_m=field(erosion_m), cumulative_deposition_m=field(deposition_m),
        erosion_by_class_m=field(eroded / area), deposition_by_class_m=field(deposition / area),
        retained_deposit_by_class_m=field(deposited / area), deposition_fraction=field(deposit_mix),
        surface_fraction=field(surface), exposure_by_class=field(exposure), burial_by_class=field(burial),
        lag_exposure=field(lag), compacted_bare=field(compacted), flow_strength=field(flow),
        max_flow_depth_m=field(max_depth), max_shear_pa=field(max_shear), max_ponding_m=field(max_pond),
        final_receiver=receiver.reshape(shape), valid_mask=valid, boundary_mobility=field(band), receipt=receipt,
        initial_mobile_class_thickness_m=field(initial / area),
        remaining_initial_mobile_class_thickness_m=field(bed / area))


def solve_context(x_m, y_m, triangle_z_m, *, spec=None, flow_config=None,
                  transport_options=None, initial_class_fractions=None):
    """Drop-in AD ContextResult adapter; existing geometry/inventory guards kept."""
    from visible_shoulder_flow_ad import (ContextSpec, ContextResult,
        _validate_spec, inventory_mobility)
    spec = spec or ContextSpec()
    _validate_spec(spec)
    x, dx = _axis(x_m, 'x_m'); y, dy = _axis(y_m, 'y_m')
    z = np.asarray(triangle_z_m, dtype=float)
    if z.shape != (len(y), len(x)) or not np.isfinite(z).all():
        raise ValueError('Expected finite actual triangle samples')
    if z.size > spec.max_grid_samples:
        raise ValueError('Context grid exceeds explicit allocation limit')
    cfg = flow_config or spec.flow
    if cfg.max_erosion_m > .060 or cfg.max_deposition_m > .040:
        raise ValueError('Context bounds exceed 60 mm erosion / 40 mm deposition')
    mobility = inventory_mobility(x, y, spec)
    fractions=np.asarray(cfg.substrate_fractions) if initial_class_fractions is None else np.asarray(initial_class_fractions,float)
    if fractions.shape not in ((3,),z.shape+(3,)) or not np.isfinite(fractions).all() or np.any(fractions<0) or not np.allclose(fractions.sum(-1),1,rtol=0,atol=1e-10):
        raise ValueError('Initial class fractions must be finite nonnegative normalized mixtures')
    initial = mobility[..., None] * spec.loose_layer_m * fractions
    cap = mobility * spec.retained_deposit_cap_m
    flow = simulate_shoulder(x, y, z, cfg,
        initial_mobile_class_thickness_m=initial,
        maximum_deposited_thickness_m=cap,
        transport_options=transport_options)
    if np.any(flow.height_delta_m[mobility == 0] != 0):
        raise AssertionError('Protected cell changed')
    receipt = dict(model='AE current-bed supported transport on AD geometry guards',
        bounds_m=[float(x[0]), float(x[-1]), float(y[0]), float(y[-1])],
        shape_yx=list(z.shape), spacing_xy_m=[dx, dy],
        protected_bounds_m=list(spec.protected_bounds_m),
        protected_contact_x_min_m=spec.protected_contact_x_min_m,
        interpolation_grid_guard_m=max(dx,dy), mesh_projection_guard_m=spec.mesh_guard_m,
        interpolation_guard_m=max(dx,dy)+spec.mesh_guard_m,
        interface_transition_m=spec.transition_m,
        inventory_layer_m=spec.loose_layer_m,
        retained_cap_m=spec.retained_deposit_cap_m,
        initial_class_composition='Spatial authored parent-unit mixture' if initial_class_fractions is not None else 'Original constant mixture',
        initial_total_layer_unchanged=True,
        protected_cells=int((mobility == 0).sum()), protected_cells_unchanged=True,
        no_additional_height_sheets=True, no_material_or_grain_edits=True,
        source='Caller-supplied actual terrain samples; initial mobile stock already included',
        solver=flow.receipt)
    return ContextResult(x.copy(), y.copy(), z.copy(), flow, mobility, spec, receipt)
