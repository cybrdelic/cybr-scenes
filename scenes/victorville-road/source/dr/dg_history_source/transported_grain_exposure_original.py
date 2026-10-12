"""Budgeted exposure of an EXISTING supplemental grain candidate population.

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


def allocate_transported_grains(
    *, xy_m: np.ndarray, flow_class: np.ndarray, solid_volume_m3: np.ndarray,
    diameter_m: np.ndarray, footprint_area_m2: np.ndarray,
    local_z_bounds_m: np.ndarray, final_surface_m: np.ndarray,
    x_m: np.ndarray, y_m: np.ndarray,
    retained_deposit_by_class_m: np.ndarray, net_deposit_m: np.ndarray,
    local_net_deposit_m: np.ndarray | None = None,
    config: ExposureConfig | None = None,
) -> ExposureResult:
    """Select supplemental grains; no inputs or scene state are mutated.

    Candidate arrays have N entries; XY and local Z bounds are (N,2). Classes
    must be solver IDs 1=grit or 2=chips, never bank indices. Volume is the actual
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
    Reproducibility assumes the same candidate array order and configuration.
    """
    cfg = config or ExposureConfig()
    _validate_config(cfg)
    x, dx = _axis(x_m, 'x_m')
    y, dy = _axis(y_m, 'y_m')
    xy = np.asarray(xy_m, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
        raise ValueError('xy_m must be finite with shape (N,2)')
    n = len(xy)
    classes = _array(flow_class, (n,), 'flow_class')
    if np.any((classes != 1) & (classes != 2)):
        raise ValueError('flow_class must use solver class 1=grit or 2=chips')
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

    inside = ((xy[:, 0] >= x[0]) & (xy[:, 0] <= x[-1])
              & (xy[:, 1] >= y[0]) & (xy[:, 1] <= y[-1]))
    ix = np.floor(np.clip((xy[:, 0] - x[0]) / dx + .5, 0, len(x) - 1)).astype(np.int64)
    iy = np.floor(np.clip((xy[:, 1] - y[0]) / dy + .5, 0, len(y) - 1)).astype(np.int64)
    cell_yx = np.column_stack((iy, ix))
    cell_yx[~inside] = -1
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
    rng = np.random.default_rng(cfg.seed)
    jitter = rng.uniform(*cfg.protrusion_jitter_range, size=n)
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
    race = -np.log(np.maximum(rng.random(n), np.finfo(float).tiny))
    priority = np.full(n, np.inf)
    priority[candidates] = np.log(race[candidates]) - np.log(candidate_weight[candidates])
    order = candidates[np.lexsort((priority[candidates], group[candidates]))]
    fractional_draw = rng.random(n)
    selected = np.zeros(n, dtype=bool)
    selected_volume = np.zeros_like(budget)
    selected_area = np.zeros_like(budget)
    selected_count = np.zeros(budget.shape, dtype=np.int64)
    volume_rejected = fractional_roundups = fractional_rounddowns = 0
    roundoff_deselections = 0
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
        selected[chosen] = True
        selected_volume.ravel()[g] = used
        selected_area.ravel()[g] = math.fsum(float(exposed_proxy[i]) for i in chosen)
        selected_count.ravel()[g] = len(chosen)
    extra[~selected] = 0
    remaining = budget - selected_volume
    if np.any(remaining < 0) or not np.isfinite(remaining).all():
        raise AssertionError('Invalid representation-volume inventory')
    overshoot = np.maximum(selected_area - target, 0)
    shortfall = np.maximum(target - selected_area, 0)
    available_volume = np.bincount(group[candidates], weights=volume[candidates],
                                   minlength=budget.size).reshape(budget.shape)
    available_area = np.bincount(group[candidates], weights=exposed_proxy[candidates],
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
            'Matrix class has no supplied geometric candidates and remains unrepresented in this allocation.',
            'Representation selection adds no new solver mass and makes no exact no-double-counting claim against the existing source bake or retained source geometry.',
            ('Surviving deposited stock may be represented in net-eroded cells; this is an explicit top-surface proxy without resolved stratigraphy.' if surviving else 'Net-erosional origins are deliberately excluded even if the solver retains some transported material there.'),
            'Only selected supplemental origins may move vertically; retained originals, XY, metric prototype geometry, material, yaw and scale must stay unchanged.',
        ],
    )
    return ExposureResult(selected, extra, cell_yx, local_deposit, local_net,
                          local_top, budget, selected_volume, remaining,
                          target, selected_area, selected_count, receipt)
