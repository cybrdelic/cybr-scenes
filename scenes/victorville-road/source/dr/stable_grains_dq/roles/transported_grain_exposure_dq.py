"""Camera-independent, finite display-stock allocation for supplemental grains.

DQ extension of transported_grain_exposure_dg.py, whose source remains untouched.
Without the new keyword arguments this preserves the legacy calculations,
random draws, result schema, and receipts exactly. Optional ID-keyed mode uses
independent hash channels instead of an array-length/order-dependent RNG stream.
Allocate COMPLETE nearest-stock-cell populations before any camera selection.
The whole fixed catalog may be processed in disjoint complete-stock-cell bands.

This is display-stock accounting, NOT new validated transport physics.

Budgeted exposure of an EXISTING supplemental grain candidate population.

NumPy only, SI units. This is a NONVALIDATED, ART-DIRECTED representation
selector, not another sediment solver. It never moves XY, scales a body, changes
material, or touches the retained original particle object. The caller applies:

    selected = result.transported
    new_origin_z[selected] = (final_surface_m[selected]
                              - result.extra_embedment_m[selected])

The approved prototype's local Z coordinates already encode its original
embedment and must remain unchanged. Unselected origins retain their previous Z.
The final surface must be sampled from the actual final terrain triangles.

Budgets use retained deposited BULK thickness times cell area times an explicit
0.62 solid fraction. Only actual closed-mesh solid volume spends that budget.
These are representation budgets, not new physical mass in the flow solver.
Nearest candidate-origin cell accounting does not resolve particle transport or
body/cell intersections. Neither area proxies nor the existing source bake are
an exact, disjoint, no-double-counting representation of the sediment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np

CLASS_NAMES = ('matrix', 'grit', 'chips')


@dataclass(frozen=True)
class ExposureConfig:
    """Explicit art controls; fixed across a candidate, not fitted per cell."""
    seed: int = 73181
    availability_mode: str = "net_positive_only"
    solid_fraction: float = 0.62
    active_layer_m: float = 0.0018
    # Summed footprint proxies, not true disjoint ground coverage.
    maximum_planar_area_proxy_fraction: float = 0.36
    # Coarser settling is represented by less material remaining at the top.
    top_availability_by_class: tuple[float, float, float] = (1.0, 0.80, 0.35)
    representative_diameter_m: tuple[float, float, float] = (0.00022, 0.00108, 0.00330)
    within_class_settling_exponent: float = 0.8
    exposure_depth_diameters: float = 0.60
    protrusion_jitter_range: tuple[float, float] = (0.55, 0.95)


@dataclass
class ExposureResult:
    transported: np.ndarray
    extra_embedment_m: np.ndarray
    candidate_cell_yx: np.ndarray
    local_retained_deposit_m: np.ndarray
    local_net_deposit_m: np.ndarray
    local_top_active_layer_fraction: np.ndarray
    solid_budget_by_cell_class_m3: np.ndarray
    selected_solid_volume_by_cell_class_m3: np.ndarray
    remaining_representation_volume_by_cell_class_m3: np.ndarray
    target_planar_area_proxy_by_cell_class_m2: np.ndarray
    exposed_planar_area_proxy_by_cell_class_m2: np.ndarray
    selected_count_by_cell_class: np.ndarray
    receipt: dict[str, Any]


def _axis(values: np.ndarray, name: str) -> tuple[np.ndarray, float]:
    a = np.asarray(values, dtype=float)
    if a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all():
        raise ValueError(f'{name} must contain at least two finite cell centres')
    d = np.diff(a)
    if np.any(d <= 0) or not np.allclose(d, d[0], rtol=1e-6, atol=1e-12):
        raise ValueError(f'{name} must be uniformly increasing')
    return a, float(f'{d[0]:.12g}')


def _array(values: np.ndarray, shape: tuple[int, ...], name: str,
           *, positive: bool = False, nonnegative: bool = False) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if a.shape != shape or not np.isfinite(a).all():
        raise ValueError(f'{name} must be finite with shape {shape}')
    if positive and np.any(a <= 0):
        raise ValueError(f'{name} must be strictly positive')
    if nonnegative and np.any(a < 0):
        raise ValueError(f'{name} cannot contain negative inventory')
    return a


def _validate_config(cfg: ExposureConfig) -> None:
    if cfg.availability_mode not in ('net_positive_only','surviving_deposit_stock'):
        raise ValueError('Unsupported deposited-surface availability mode')
    if not isinstance(cfg.seed, (int, np.integer)) or cfg.seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    for name in ('solid_fraction', 'maximum_planar_area_proxy_fraction'):
        v = getattr(cfg, name)
        if not np.isfinite(v) or not 0 < v <= 1:
            raise ValueError(f'{name} must lie in (0,1]')
    for name in ('active_layer_m', 'exposure_depth_diameters'):
        if not np.isfinite(getattr(cfg, name)) or getattr(cfg, name) <= 0:
            raise ValueError(f'{name} must be positive')
    if not np.isfinite(cfg.within_class_settling_exponent) or cfg.within_class_settling_exponent < 0:
        raise ValueError('within_class_settling_exponent must be nonnegative')
    weights = _array(cfg.top_availability_by_class, (3,), 'top_availability_by_class', positive=True)
    if np.any(weights > 1):
        raise ValueError('top_availability_by_class must lie in (0,1]')
    _array(cfg.representative_diameter_m, (3,), 'representative_diameter_m', positive=True)
    lo, hi = _array(cfg.protrusion_jitter_range, (2,), 'protrusion_jitter_range', positive=True)
    if not lo <= hi <= 1:
        raise ValueError('protrusion_jitter_range must be ordered in (0,1]')


def _bilinear(field: np.ndarray, xy: np.ndarray, x: np.ndarray, y: np.ndarray,
              dx: float, dy: float, inside: np.ndarray) -> np.ndarray:
    """Zero outside the sampled rectangle; never extrapolate to other ground."""
    fx = np.clip((xy[:, 0] - x[0]) / dx, 0, len(x) - 1)
    fy = np.clip((xy[:, 1] - y[0]) / dy, 0, len(y) - 1)
    ix = np.minimum(fx.astype(np.int64), len(x) - 2)
    iy = np.minimum(fy.astype(np.int64), len(y) - 2)
    tx, ty = fx - ix, fy - iy
    if field.ndim == 3:
        tx, ty = tx[:, None], ty[:, None]
    a = ((field[iy, ix] * (1 - tx) + field[iy, ix + 1] * tx) * (1 - ty)
         + (field[iy + 1, ix] * (1 - tx) + field[iy + 1, ix + 1] * tx) * ty)
    a[~inside] = 0
    return a


def _top_fraction(deposit: np.ndarray, availability: np.ndarray) -> np.ndarray:
    # No vertical stratigraphy is available: this is explicitly a top-layer proxy.
    weighted = deposit * availability
    total = weighted.sum(axis=-1, keepdims=True)
    return np.divide(weighted, total, out=np.zeros_like(weighted), where=total > 0)


def retained_top_proxy(retained_by_class_m, active_depth_m=.0018, availability_by_class=(1.,.80,.35)):
    """Explicit bounded top-layer proxy, never inferred vertical stratigraphy.
    Each proxy class <= its surviving inventory; total <= active_depth_m.
    Full-body representation volume budgets must still use retained inventory.
    """
    d=np.asarray(retained_by_class_m,float);w=np.asarray(availability_by_class,float)
    if d.ndim<1 or d.shape[-1]!=3 or not np.isfinite(d).all() or np.any(d<0):raise ValueError('Nonnegative finite retained classes required')
    if w.shape!=(3,) or not np.isfinite(w).all() or np.any(w<0) or np.any(w>1):raise ValueError('Availability fractions must be in [0,1]')
    if not np.isfinite(active_depth_m) or active_depth_m<=0:raise ValueError('Positive finite active depth required')
    q=d*w;total=q.sum(-1,keepdims=True);scale=np.minimum(1,np.divide(active_depth_m,total,out=np.ones_like(total),where=total>0));q=q*scale;total=q.sum(-1,keepdims=True)
    fractions=np.divide(q,total,out=np.zeros_like(q),where=total>0)
    return q,total[...,0],fractions


# These constants and float conversion are part of the DQ role identity contract.
# Changing any of them requires a new role-allocation version.
KEYED_ROLE_VERSION = 'dq-stock-role-v1'
_U64_MASK = (1 << 64) - 1
_KEY_DOMAINS = {'jitter': 0x3C6EF372FE94F82B,
                'race': 0xA54FF53A5F1D36F1,
                'fraction': 0x510E527FADE682D1}


def _mix64(value):
    """SplitMix64 finalizer, explicit modulo-2**64 arithmetic; no RNG state."""
    value = np.asarray(value, dtype=np.uint64)
    with np.errstate(over='ignore'):
        value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


def _keyed_uniform(candidate_ids, seed, channel):
    """Independent deterministic channel per uint64 ID, with exact [0,1) draws."""
    # Fold every seed limb so the legacy API's arbitrary nonnegative int seeds
    # remain usable without silently dropping their high bits.
    remaining_seed = int(seed)
    seed_key = np.uint64(0x6A09E667F3BCC909)
    while True:
        seed_key = _mix64(seed_key ^ np.uint64(remaining_seed & _U64_MASK))
        remaining_seed >>= 64
        if not remaining_seed:
            break
    bits = _mix64(np.asarray(candidate_ids, dtype=np.uint64)
                  ^ seed_key ^ np.uint64(_KEY_DOMAINS[channel]))
    return (bits >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)


def keyed_uniform(candidate_ids, seed, channel):
    """Public stateless [0,1) draw for 'jitter', 'race', or 'fraction'.

    Reuse exactly these draws when displaying a previously allocated population.
    IDs must have uint64 dtype. This evaluator accepts a subset or repeated IDs;
    allocation itself requires unique IDs and complete stock-cell populations.
    Channel constants belong to KEYED_ROLE_VERSION and must not be retuned.
    """
    ids = np.asarray(candidate_ids)
    if ids.ndim != 1 or ids.dtype != np.dtype(np.uint64):
        raise ValueError('candidate_ids must be a one-dimensional uint64 array')
    if not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if channel not in _KEY_DOMAINS:
        raise ValueError("channel must be 'jitter', 'race', or 'fraction'")
    return _keyed_uniform(ids, seed, channel)


def keyed_extra_embedment_m(*, candidate_ids, local_effective_deposit_m,
                            diameter_m, local_z_bounds_m, transported=None,
                            config=None):
    """Reevaluate embedding of frozen roles without allocating display stock.

    local_effective_deposit_m MUST be the original field-derived effective depth
    used at allocation, never a residual budget. In surviving_deposit_stock
    mode it is retained_top_proxy(local_retained_classes, ...)[1], zeroed where
    unsupported. In net_positive_only mode it is min(local_retained_total,
    max(local_net, 0)), also zeroed where unsupported. The full-field bilinear
    samples/config and metric geometry must be identical to those at allocation.
    This function makes no eligibility or role decision. Supply the frozen
    transported boolean mask to obtain exactly the allocator's masked output.
    A display/camera subset is allowed here because no inventory is allocated.
    """
    cfg = config or ExposureConfig()
    _validate_config(cfg)
    u = keyed_uniform(candidate_ids, cfg.seed, 'jitter')
    n = len(u)
    effective = _array(local_effective_deposit_m, (n,),
                       'local_effective_deposit_m', nonnegative=True)
    diameter = _array(diameter_m, (n,), 'diameter_m', positive=True)
    bounds = _array(local_z_bounds_m, (n, 2), 'local_z_bounds_m')
    if np.any(bounds[:, 1] <= bounds[:, 0]):
        raise ValueError('local_z_bounds_m must have strictly increasing min/max')
    lo, hi = cfg.protrusion_jitter_range
    jitter = lo + (hi - lo) * u
    exposure = -np.expm1(-effective / (cfg.exposure_depth_diameters * diameter))
    extra = np.maximum(bounds[:, 1], 0) * (1 - exposure * jitter)
    if transported is not None:
        selected = np.asarray(transported)
        if selected.shape != (n,) or selected.dtype != np.dtype(bool):
            raise ValueError('transported must be a boolean array with shape (N,)')
        extra[~selected] = 0
    return extra


def _candidate_ids(values, n):
    ids = np.asarray(values)
    if ids.shape != (n,) or ids.dtype != np.dtype(np.uint64):
        raise ValueError('candidate_ids must have shape (N,) and dtype uint64')
    if len(np.unique(ids)) != n:
        raise ValueError('candidate_ids must be unique; ambiguous duplicate identity')
    return ids


def _check_complete_stock_cells(expected, iy, ix, inside, shape):
    """Compare against an independently frozen full-world catalog manifest.

    A call may omit entire cells, never part of an included cell. Counts must
    include ALL candidates (all classes and even unsupported candidates), not
    just eligible or camera-visible ones. The caller must obtain this manifest
    before view selection; rebuilding it from a camera subset invalidates the
    contract. This check cannot prove an externally supplied manifest's origin.
    """
    if expected is None:
        raise ValueError('DQ allocation requires complete_stock_cell_counts from '
                         'the fixed full-world catalog, before camera selection')
    expected = np.asarray(expected)
    if (expected.shape != shape or expected.dtype.kind not in 'iu'
            or np.any(expected < 0)):
        raise ValueError(f'complete_stock_cell_counts must be nonnegative integer '
                         f'counts with shape {shape}')
    actual = np.bincount((iy[inside] * shape[1] + ix[inside]),
                         minlength=shape[0] * shape[1]).reshape(shape)
    touched = actual > 0
    if np.any(actual[touched] != expected[touched]):
        raise ValueError('Incomplete nearest-stock-cell population: allocate '
                         'all candidates in each included cell before camera selection')
    return int(np.count_nonzero(touched))


def allocate_transported_grains(
    *, xy_m: np.ndarray, flow_class: np.ndarray, solid_volume_m3: np.ndarray,
    diameter_m: np.ndarray, footprint_area_m2: np.ndarray,
    local_z_bounds_m: np.ndarray, final_surface_m: np.ndarray,
    x_m: np.ndarray, y_m: np.ndarray,
    retained_deposit_by_class_m: np.ndarray, net_deposit_m: np.ndarray,
    local_net_deposit_m: np.ndarray | None = None,
    config: ExposureConfig | None = None,
    candidate_ids: np.ndarray | None = None,
    remaining_solid_budget_by_cell_class_m3: np.ndarray | None = None,
    remaining_planar_area_target_by_cell_class_m2: np.ndarray | None = None,
    complete_stock_cell_counts: np.ndarray | None = None,
) -> ExposureResult:
    """Select supplemental grains; no inputs or scene state are mutated.

    Candidate arrays have N entries; XY and local Z bounds are (N,2). Classes
    must be solver IDs 0=fine sand,1=grit,2=chips, never bank indices. Volume is the actual
    closed-mesh volume, footprint the actual XY convex-hull area, and Z bounds
    include the original baked embedment. Grid arrays are (ny,nx,3) retained bulk
    thickness and (ny,nx) net bed-height change. Axes are uniform cell centres.

    local_net_deposit_m optionally overrides bilinear net height at each origin
    with exact final-minus-source triangle heights. NaN final surface / local net
    heights mean unsupported candidates, which are retained but never promoted.
    Retained inventory, metric geometry, and all other inputs must be finite.

    Whole-body solid volume is strictly capped per nearest origin cell/class.
    The soft area target uses a finite 1.8 mm active-layer activation and a
    settling-weighted top mixture. A weighted seeded random ordering favors
    locally deposited material and smaller grains within a class. A fractional
    final grain is stochastically rounded, allowing at most one footprint proxy
    of area-target overshoot in a cell/class, NEVER a solid-volume overshoot.
    Legacy reproducibility assumes the same array order and configuration.

    DQ keyword arguments:
      candidate_ids: unique persistent uint64 identity, never array indices.
        Independent ID/seed keyed jitter, race and fractional draws plus ID tie
        breaks make each complete cell permutation/band independent.
      remaining_solid_budget_by_cell_class_m3: optional nonnegative (ny,nx,3)
        residual display volume after debiting a frozen macro population.
      remaining_planar_area_target_by_cell_class_m2: optional nonnegative
        (ny,nx,3) residual area. This supplied residual is a HARD area cap;
        oversized footprints are skipped rather than fractionally rounded up.
        Without it the existing soft target/one-footprint overshoot is retained.
      complete_stock_cell_counts: independently frozen (ny,nx) integer counts
        of ALL full-world candidates, required when any DQ option is used.
        Entire cells can be omitted for batching, but included cells must be
        complete. Do not create the manifest from camera-visible candidates.

    Residuals cap the original display limits, never replace retained deposit
    fields in activation, top-mixture, exposure or weighting equations. All grid
    fields and axes must retain the full fixed-world extent in every batch;
    cropping interpolation fields to a band changes the physical input problem.
    Calls are stateless. They must not split a stock cell, feed a band's residual
    back to another part of that same cell, or reallocate after camera selection.
    Sum per-cell *selected* ledgers across disjoint bands; original/residual
    budget and target arrays describe the full grid and must NOT be summed.
    """
    cfg = config or ExposureConfig()
    _validate_config(cfg)
    x, dx = _axis(x_m, 'x_m')
    y, dy = _axis(y_m, 'y_m')
    xy = np.asarray(xy_m, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
        raise ValueError('xy_m must be finite with shape (N,2)')
    n = len(xy)
    persistent_ids = None if candidate_ids is None else _candidate_ids(candidate_ids, n)
    dq_mode = (candidate_ids is not None
               or remaining_solid_budget_by_cell_class_m3 is not None
               or remaining_planar_area_target_by_cell_class_m2 is not None
               or complete_stock_cell_counts is not None)
    classes = _array(flow_class, (n,), 'flow_class')
    if np.any((classes != 0) & (classes != 1) & (classes != 2)):
        raise ValueError('flow_class must use 0=fine sand,1=grit,2=chips')
    classes = classes.astype(np.int64)
    volume = _array(solid_volume_m3, (n,), 'solid_volume_m3', positive=True)
    diameter = _array(diameter_m, (n,), 'diameter_m', positive=True)
    footprint = _array(footprint_area_m2, (n,), 'footprint_area_m2', positive=True)
    bounds = _array(local_z_bounds_m, (n, 2), 'local_z_bounds_m')
    if np.any(bounds[:, 1] <= bounds[:, 0]):
        raise ValueError('local_z_bounds_m must have strictly increasing min/max')
    surface = np.asarray(final_surface_m, dtype=float)
    if surface.shape != (n,) or np.isinf(surface).any():
        raise ValueError('final_surface_m must have shape (N,) without infinities')
    shape = (len(y), len(x))
    deposit = _array(retained_deposit_by_class_m, shape + (3,),
                     'retained_deposit_by_class_m', nonnegative=True)
    net = _array(net_deposit_m, shape, 'net_deposit_m')
    area = dx * dy
    budget = deposit * area * cfg.solid_fraction
    original_budget = budget
    if remaining_solid_budget_by_cell_class_m3 is not None:
        residual = _array(remaining_solid_budget_by_cell_class_m3, shape + (3,),
                          'remaining_solid_budget_by_cell_class_m3', nonnegative=True)
        budget = np.minimum(budget, residual)
    availability = np.asarray(cfg.top_availability_by_class)
    top = _top_fraction(deposit, availability)
    total_deposit = deposit.sum(axis=-1)
    # Smoothly saturating active-layer thickness, with no arbitrary deposit mask.
    # Surviving transported inventory remains available after net scour.
    # This optional top-surface proxy does not assert vertical stratigraphy.
    surviving = cfg.availability_mode == "surviving_deposit_stock"
    if surviving:
        _,effective,top=retained_top_proxy(deposit,cfg.active_layer_m,cfg.top_availability_by_class)
    else:effective=np.minimum(total_deposit, np.maximum(net, 0))
    activation = -np.expm1(-effective / cfg.active_layer_m)
    target = area * cfg.maximum_planar_area_proxy_fraction * activation[..., None] * top
    original_target = target
    strict_area = remaining_planar_area_target_by_cell_class_m2 is not None
    if strict_area:
        residual_area = _array(remaining_planar_area_target_by_cell_class_m2,
                              shape + (3,),
                              'remaining_planar_area_target_by_cell_class_m2',
                              nonnegative=True)
        target = np.minimum(target, residual_area)

    inside = ((xy[:, 0] >= x[0]) & (xy[:, 0] <= x[-1])
              & (xy[:, 1] >= y[0]) & (xy[:, 1] <= y[-1]))
    ix = np.floor(np.clip((xy[:, 0] - x[0]) / dx + .5, 0, len(x) - 1)).astype(np.int64)
    iy = np.floor(np.clip((xy[:, 1] - y[0]) / dy + .5, 0, len(y) - 1)).astype(np.int64)
    cell_yx = np.column_stack((iy, ix))
    cell_yx[~inside] = -1
    complete_cells = (_check_complete_stock_cells(complete_stock_cell_counts,
                      iy, ix, inside, shape) if dq_mode else None)
    group = (iy * len(x) + ix) * 3 + classes
    local_deposit_class = _bilinear(deposit, xy, x, y, dx, dy, inside)
    local_deposit = local_deposit_class.sum(axis=1)
    local_top = _top_fraction(local_deposit_class, availability)
    if local_net_deposit_m is None:
        local_net = _bilinear(net, xy, x, y, dx, dy, inside)
    else:
        local_net = np.asarray(local_net_deposit_m, dtype=float)
        if local_net.shape != (n,) or np.isinf(local_net).any():
            raise ValueError('local_net_deposit_m must have shape (N,) without infinities')
        local_net = local_net.copy()
    supported = np.isfinite(surface) & np.isfinite(local_net)
    if surviving:
        _,local_effective,local_top=retained_top_proxy(local_deposit_class,cfg.active_layer_m,cfg.top_availability_by_class)
        local_effective=np.where(supported,local_effective,0)
    else:local_effective=np.minimum(local_deposit, np.maximum(np.where(supported, local_net, 0), 0))
    local_activation = -np.expm1(-local_effective / cfg.active_layer_m)
    if persistent_ids is None:
        rng = np.random.default_rng(cfg.seed)
        jitter = rng.uniform(*cfg.protrusion_jitter_range, size=n)
    else:
        lo, hi = cfg.protrusion_jitter_range
        jitter = lo + (hi - lo) * _keyed_uniform(persistent_ids, cfg.seed, 'jitter')
    exposure = -np.expm1(-local_effective / (cfg.exposure_depth_diameters * diameter))
    # Additional embedding is downward only; original prototype coordinates stay.
    extra = np.maximum(bounds[:, 1], 0) * (1 - exposure * jitter)
    exposed_height = np.maximum(bounds[:, 1] - extra, 0)
    exposed_proxy = footprint * np.clip(exposed_height / (bounds[:, 1] - bounds[:, 0]), 0, 1)
    candidate_weight = (local_activation * local_top[np.arange(n), classes]
                        / (1 + (diameter / np.asarray(cfg.representative_diameter_m)[classes])
                           ** cfg.within_class_settling_exponent))
    height_gate = np.ones(n,dtype=bool) if surviving else local_net > 0
    eligible = (inside & supported & height_gate & (local_deposit > 0)
                & (local_deposit_class[np.arange(n), classes] > 0)
                & (budget.ravel()[group] > 0) & (target.ravel()[group] > 0)
                & (bounds[:, 0] <= 0) & (bounds[:, 1] > 0)
                & (exposed_proxy > 0) & (candidate_weight > 0))
    candidates = np.flatnonzero(eligible)
    # Log-domain exponential race avoids overflow for trace deposition weights.
    race_draw = rng.random(n) if persistent_ids is None else _keyed_uniform(persistent_ids, cfg.seed, 'race')
    race = -np.log(np.maximum(race_draw, np.finfo(float).tiny))
    priority = np.full(n, np.inf)
    priority[candidates] = np.log(race[candidates]) - np.log(candidate_weight[candidates])
    if persistent_ids is None:
        order = candidates[np.lexsort((priority[candidates], group[candidates]))]
        fractional_draw = rng.random(n)
    else:
        order = candidates[np.lexsort((persistent_ids[candidates], priority[candidates],
                                       group[candidates]))]
        fractional_draw = _keyed_uniform(persistent_ids, cfg.seed, 'fraction')
    selected = np.zeros(n, dtype=bool)
    selected_volume = np.zeros_like(budget)
    selected_area = np.zeros_like(budget)
    selected_count = np.zeros(budget.shape, dtype=np.int64)
    volume_rejected = fractional_roundups = fractional_rounddowns = 0
    roundoff_deselections = 0
    area_rejected = area_roundoff_deselections = 0
    flat_budget, flat_target = budget.ravel(), target.ravel()
    starts = np.r_[0, np.flatnonzero(np.diff(group[order])) + 1, len(order)]
    for begin, end in zip(starts[:-1], starts[1:]):
        ids = order[begin:end]
        if not len(ids):
            continue
        g = group[ids[0]]
        remaining_volume = float(flat_budget[g])
        remaining_area = float(flat_target[g])
        chosen = []
        for i in ids:
            if remaining_area <= 0:
                break
            if volume[i] > remaining_volume:
                volume_rejected += 1
                continue
            if exposed_proxy[i] > remaining_area:
                if strict_area:
                    area_rejected += 1
                    continue
                if fractional_draw[i] < remaining_area / exposed_proxy[i]:
                    chosen.append(int(i))
                    fractional_roundups += 1
                else:
                    fractional_rounddowns += 1
                break
            chosen.append(int(i))
            remaining_volume -= float(volume[i])
            remaining_area -= float(exposed_proxy[i])
        # fsum removes ordering-dependent accumulation error from the ledger.
        # Strictly refuse even a floating-point-ulp budget overshoot.
        used = math.fsum(float(volume[i]) for i in chosen)
        while used > flat_budget[g]:
            chosen.pop()
            roundoff_deselections += 1
            used = math.fsum(float(volume[i]) for i in chosen)
        if strict_area:
            used_area = math.fsum(float(exposed_proxy[i]) for i in chosen)
            while used_area > flat_target[g]:
                chosen.pop()
                area_roundoff_deselections += 1
                used_area = math.fsum(float(exposed_proxy[i]) for i in chosen)
            used = math.fsum(float(volume[i]) for i in chosen)
        selected[chosen] = True
        selected_volume.ravel()[g] = used
        selected_area.ravel()[g] = math.fsum(float(exposed_proxy[i]) for i in chosen)
        selected_count.ravel()[g] = len(chosen)
    extra[~selected] = 0
    remaining = budget - selected_volume
    if np.any(remaining < 0) or not np.isfinite(remaining).all():
        raise AssertionError('Invalid representation-volume inventory')
    if strict_area and np.any(selected_area > target):
        raise AssertionError('Invalid residual planar-area inventory')
    overshoot = np.maximum(selected_area - target, 0)
    shortfall = np.maximum(target - selected_area, 0)
    diagnostic_order = order if persistent_ids is not None else candidates
    available_volume = np.bincount(group[diagnostic_order], weights=volume[diagnostic_order],
                                   minlength=budget.size).reshape(budget.shape)
    available_area = np.bincount(group[diagnostic_order], weights=exposed_proxy[diagnostic_order],
                                 minlength=budget.size).reshape(budget.shape)
    actual = np.flatnonzero(selected)
    audit = dict(
        availability_mode=cfg.availability_mode,
        net_sign_is_availability_gate=not surviving,
        promoted_count=int(len(actual)),
        promoted_outside_grid=int(np.count_nonzero(selected & ~inside)),
        promoted_unsupported_surface=int(np.count_nonzero(selected & ~supported)),
        promoted_without_positive_net_deposit=int(np.count_nonzero(selected & ~(local_net > 0))),
        promoted_without_retained_own_class=int(np.count_nonzero(
            selected & ~(local_deposit_class[np.arange(n), classes] > 0))),
        negative_remaining_inventory_entries=int(np.count_nonzero(remaining < 0)),
        solid_budget_exceedance_m3=float(np.maximum(selected_volume - budget, 0).max(initial=0)),
        minimum_promoted_net_deposit_m=float(local_net[actual].min()) if len(actual) else None,
        minimum_promoted_retained_deposit_m=float(local_deposit[actual].min()) if len(actual) else None,
        minimum_promoted_top_above_final_surface_m=float(exposed_height[actual].min()) if len(actual) else None,
        triangle_contact_audit='Required in the scene adapter; origin proxies cannot prove triangle contact',
    )
    receipt = dict(
        model='Retained-deposit budgeted supplemental transported-grain exposure',
        status='NONVALIDATED ART-DIRECTED representation selector; not a sediment solver',
        config=asdict(cfg), class_names=list(CLASS_NAMES), grid_shape_yx=list(shape),
        cell_size_xy_m=[dx, dy], cell_area_m2=area,
        candidate_count=n, eligible_candidate_count=int(eligible.sum()),
        selected_count=int(selected.sum()), selected_count_by_class=selected_count.sum(axis=(0, 1)).tolist(),
        candidate_count_by_class=np.bincount(classes, minlength=3).tolist(),
        retained_deposited_bulk_volume_by_class_m3=(deposit.sum(axis=(0, 1)) * area).tolist(),
        solid_budget_by_class_m3=budget.sum(axis=(0, 1)).tolist(),
        selected_solid_volume_by_class_m3=selected_volume.sum(axis=(0, 1)).tolist(),
        remaining_representation_volume_by_class_m3=remaining.sum(axis=(0, 1)).tolist(),
        target_planar_area_proxy_by_class_m2=target.sum(axis=(0, 1)).tolist(),
        exposed_planar_area_proxy_by_class_m2=selected_area.sum(axis=(0, 1)).tolist(),
        area_target_shortfall_sum_by_class_m2=shortfall.sum(axis=(0, 1)).tolist(),
        area_target_overshoot_sum_by_class_m2=overshoot.sum(axis=(0, 1)).tolist(),
        eligible_candidate_solid_volume_by_class_m3=available_volume.sum(axis=(0, 1)).tolist(),
        eligible_candidate_exposed_area_proxy_by_class_m2=available_area.sum(axis=(0, 1)).tolist(),
        target_cells_with_insufficient_candidate_area=int(np.count_nonzero((target > 0) & (available_area < target))),
        volume_rejected_attempts=volume_rejected,
        fractional_area_roundups=fractional_roundups,
        fractional_area_rounddowns=fractional_rounddowns,
        strict_budget_roundoff_deselections=roundoff_deselections,
        extra_embedment_min_max_m=[float(extra[actual].min()), float(extra[actual].max())] if len(actual) else [0., 0.],
        audit=audit,
        limits=[
            '0.62 solid fraction is an explicit fixed, nonvalidated art-directed porosity assumption.',
            'Candidate-origin nearest-cell bookkeeping approximates whole-body volume; individual mass transport and body/cell intersections are unresolved.',
            'The solver has no vertical stratigraphy: top active-layer fractions are retained-class mixtures weighted by explicit selective-settling factors.',
            'Convex-hull footprint times exposed vertical-height fraction is only an area proxy, not a measured visible silhouette or disjoint true coverage.',
            'Area targets permit stochastic rounding by at most one candidate area per cell/class; solid-volume budgets permit no overshoot.',
            'Existing finite candidates, packing, camera LOD and per-cell whole-body quantization may leave substantial target area and deposited volume unrepresented.',
            'Fine sand geometry represents only its supplied portion of matrix class; finer unresolved material remains a surface response.',
            'Representation selection adds no new solver mass and makes no exact no-double-counting claim against the existing source bake or retained source geometry.',
            ('Surviving deposited stock may be represented in net-eroded cells; this is an explicit top-surface proxy without resolved stratigraphy.' if surviving else 'Net-erosional origins are deliberately excluded even if the solver retains some transported material there.'),
            'Only selected supplemental origins may move vertically; retained originals, XY, metric prototype geometry, material, yaw and scale must stay unchanged.',
        ],
    )
    if dq_mode:
        receipt['display_stock_accounting'] = dict(
            keyed_role_version=KEYED_ROLE_VERSION if persistent_ids is not None else None,
            randomness='independent ID-keyed channels' if persistent_ids is not None else 'legacy array RNG stream',
            complete_stock_cells_in_call=complete_cells,
            complete_stock_cell_manifest_checked=True,
            requires_camera_selection_after_allocation=True,
            full_fixed_grid_fields_required=True,
            original_solid_budget_by_class_m3=original_budget.sum(axis=(0, 1)).tolist(),
            original_planar_area_target_by_class_m2=original_target.sum(axis=(0, 1)).tolist(),
            residual_volume_cap_supplied=remaining_solid_budget_by_cell_class_m3 is not None,
            residual_area_cap_supplied=strict_area,
            planar_area_policy='hard residual cap' if strict_area else 'legacy soft target',
            area_rejected_attempts=area_rejected,
            strict_area_roundoff_deselections=area_roundoff_deselections,
            warning='NONVALIDATED display-stock accounting, not new transport physics',
        )
        if strict_area:
            receipt['limits'][4] = ('Supplied residual planar-area targets are hard caps; '
                'whole candidate footprints that do not fit are skipped. '
                'Solid-volume budgets permit no overshoot.')
    return ExposureResult(selected, extra, cell_yx, local_deposit, local_net,
                          local_top, budget, selected_volume, remaining,
                          target, selected_area, selected_count, receipt)
