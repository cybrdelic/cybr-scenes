"""Small conservative shoulder-flow model, NumPy + Python standard library only.

NONVALIDATED, ART-DIRECTED PHYSICS. This is a bounded landscape-weathering
model, not a hydraulic/engineering prediction. Feed uniformly sampled ACTUAL
terrain-triangle heights, in metres; no analytic replacement terrain is used.
A priority-flood surface determines connected D8 drainage. Each storm routes
water and three mobile bulk-volume sediment bins in one acyclic sweep. Local
capacity responds to discharge, slope, hydraulic resistance and grain size.
Changing bed levels alter the next storm's drainage. No painted island masks,
Gaussian deposition blanket, color, or intrinsic material changes are made.

Axes represent cell centres, increasing east/north; all 2-D arrays are (y,x).
Integration uses dx*dy per sample (including boundary samples). Supply a grid
covering the region to deform. A conservative smoothstep boundary band locks
the perimeter while permitting water and suspended sediment through it.
The default road-runoff source is an EXPLICIT 1.8 m contributing strip at x_max;
it brings water, not external sediment. Disable/change this for other sites.

    result = simulate_shoulder(x_m, y_m, triangle_z_m)
    deformed_z = triangle_z_m + result.height_delta_m
    # Bilinearly sample fields to drive geometry/exposure, never material tint.
    print(result.receipt)

All displaced volumes are bulk bed volumes at one constant implied porosity.
Every entrained volume either deposits, exits the boundary, or remains in the
reported mobile store. Water rainfall is split into immediate infiltration and
runoff; runoff fully drains along the spill surface during each whole event.
Thus actual pond timing and infiltration during transit are not simulated.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import time
from typing import Any

import numpy as np

CLASS_NAMES = ("matrix_lt_0p69mm", "grit_0p69_to_1p66mm", "chips_1p66_to_5p9mm")


@dataclass(frozen=True)
class FlowConfig:
    """All dimensions SI; coefficients deliberately art-directed and bounded."""
    seed: int = 73109
    boundary_band_cells: float = 4.0
    rainfall_m: tuple[float, ...] = (0.012, 0.026, 0.017, 0.035, 0.019)
    event_duration_s: float = 900.0
    runoff_fraction: float = 0.48
    upstream_edge: str | None = "x_max"
    upstream_width_m: float = 1.8
    upstream_runoff_fraction: float = 0.88
    max_erosion_m: float = 0.018
    max_deposition_m: float = 0.024
    max_event_erosion_m: float = 0.0045
    substrate_fractions: tuple[float, float, float] = (0.68, 0.24, 0.08)
    representative_diameter_m: tuple[float, float, float] = (0.00022, 0.00108, 0.00330)
    # Art-directed critical stresses; not calibrated Shields thresholds.
    critical_shear_pa: tuple[float, float, float] = (0.045, 0.19, 0.70)
    max_concentration: tuple[float, float, float] = (0.055, 0.019, 0.006)
    manning_n: float = 0.050
    deposition_relaxation: float = 0.82
    erosion_relaxation: float = 0.55
    minimum_transport_slope: float = 0.00012


@dataclass
class FlowResult:
    height_delta_m: np.ndarray
    cumulative_water_m3: np.ndarray
    cumulative_erosion_m: np.ndarray
    cumulative_deposition_m: np.ndarray
    erosion_by_class_m: np.ndarray
    deposition_by_class_m: np.ndarray
    retained_deposit_by_class_m: np.ndarray
    deposition_fraction: np.ndarray
    surface_fraction: np.ndarray
    exposure_by_class: np.ndarray
    burial_by_class: np.ndarray
    lag_exposure: np.ndarray
    compacted_bare: np.ndarray
    flow_strength: np.ndarray
    max_flow_depth_m: np.ndarray
    max_shear_pa: np.ndarray
    max_ponding_m: np.ndarray
    final_receiver: np.ndarray  # Last storm routing, computed before that storm deformed the bed.
    valid_mask: np.ndarray
    boundary_mobility: np.ndarray
    receipt: dict[str, Any]

    @property
    def final_deposit_m(self) -> np.ndarray:
        return self.retained_deposit_by_class_m.sum(axis=-1)


_OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
            (0, 1), (1, -1), (1, 0), (1, 1))


def _axis(values: np.ndarray, name: str) -> tuple[np.ndarray, float]:
    a = np.asarray(values, dtype=np.float64)
    if a.ndim != 1 or len(a) < 3 or not np.all(np.isfinite(a)):
        raise ValueError(f"{name} must contain at least three finite cell centres")
    d = np.diff(a)
    if np.any(d <= 0) or not np.allclose(d, d[0], rtol=1e-6, atol=1e-10):
        raise ValueError(f"{name} must be increasing and uniformly sampled")
    return a, float(d[0])


def _validate(config: FlowConfig) -> None:
    for name in ("event_duration_s", "max_erosion_m", "max_deposition_m",
                 "max_event_erosion_m", "manning_n", "minimum_transport_slope"):
        v = getattr(config, name)
        if not np.isfinite(v) or v <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("runoff_fraction", "upstream_runoff_fraction",
                 "deposition_relaxation", "erosion_relaxation"):
        v = getattr(config, name)
        if not np.isfinite(v) or not 0 <= v <= 1:
            raise ValueError(f"{name} must lie in [0,1]")
    if not np.isfinite(config.boundary_band_cells) or config.boundary_band_cells < 0:
        raise ValueError("boundary_band_cells must be finite and nonnegative")
    if not np.isfinite(config.upstream_width_m) or config.upstream_width_m < 0:
        raise ValueError("upstream_width_m must be finite and nonnegative")
    if config.upstream_edge not in (None, "x_min", "x_max", "y_min", "y_max"):
        raise ValueError("upstream_edge must be x_min, x_max, y_min, y_max or None")
    rain = np.asarray(config.rainfall_m, float)
    if rain.ndim != 1 or not len(rain) or np.any(~np.isfinite(rain)) or np.any(rain < 0):
        raise ValueError("rainfall_m must be a nonempty sequence of nonnegative depths")
    for name in ("substrate_fractions", "representative_diameter_m",
                 "critical_shear_pa", "max_concentration"):
        a = np.asarray(getattr(config, name), float)
        if a.shape != (3,) or np.any(~np.isfinite(a)) or np.any(a <= 0):
            raise ValueError(f"{name} must contain three finite positive values")
    if not np.isclose(sum(config.substrate_fractions), 1.0, rtol=0, atol=1e-9):
        raise ValueError("substrate_fractions must sum to 1")


def _heterogeneity(shape: tuple[int, int], dx: float, dy: float,
                   rng: np.random.Generator) -> np.ndarray:
    """Stationary multiscale material variability; no feature centres or masks.

    Linear interpolation of seeded random material measurements changes
    erodibility/resistance, not elevation or direct deposit placement.
    """
    ny, nx = shape
    field = np.zeros(shape)
    for spacing, weight in ((0.075, 0.28), (0.23, 0.46), (0.61, 0.26)):
        sx, sy = max(1., spacing / dx), max(1., spacing / dy)
        gx = np.arange(int(math.ceil((nx - 1) / sx)) + 2) * sx
        gy = np.arange(int(math.ceil((ny - 1) / sy)) + 2) * sy
        coarse = rng.uniform(-1., 1., (len(gy), len(gx)))
        rows = np.array([np.interp(np.arange(nx), gx, row) for row in coarse])
        interp = np.array([np.interp(np.arange(ny), gy, rows[:, c])
                           for c in range(nx)]).T
        field += weight * interp
    return field


def _neighbors(shape: tuple[int, int], dx: float, dy: float,
               valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ny, nx = shape
    yy, xx = np.indices(shape)
    nbr = np.full((ny * nx, 8), -1, dtype=np.int32)
    distance = np.empty(8, float)
    for k, (oy, ox) in enumerate(_OFFSETS):
        y, x = yy + oy, xx + ox
        inside = (y >= 0) & (y < ny) & (x >= 0) & (x < nx)
        indices = np.flatnonzero(inside.ravel())
        targets = (y[inside] * nx + x[inside]).ravel()
        allowed = valid.ravel()[indices] & valid.ravel()[targets]
        nbr[indices[allowed], k] = targets[allowed]
        distance[k] = math.hypot(ox * dx, oy * dy)
    return nbr, distance


def _drainage(z: np.ndarray, valid: np.ndarray, neighbors: np.ndarray,
              distance: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Priority flood + steepest D8; invalid holes are CLOSED, outer rim OPEN.

    An acyclic spill route exists for every supported cell. Isolated active
    components not connected to the outer rim are rejected, never leaked.
    """
    shape = valid.shape
    n = z.size
    seen = np.zeros(n, bool)
    filled = np.full(n, np.nan)
    parent = np.full(n, -1, np.int32)
    rim = np.zeros(shape, bool)
    rim[0] = rim[-1] = True
    rim[:, 0] = rim[:, -1] = True
    seeds = np.flatnonzero((rim & valid).ravel())
    queue: list[tuple[float, int]] = []
    for i in seeds:
        seen[i] = True
        filled[i] = z[i]
        heapq.heappush(queue, (float(z[i]), int(i)))
    order = []
    while queue:
        level, i = heapq.heappop(queue)
        order.append(i)
        for j in neighbors[i]:
            if j < 0 or seen[j]:
                continue
            seen[j] = True
            filled[j] = max(z[j], level)
            parent[j] = i
            heapq.heappush(queue, (float(filled[j]), int(j)))
    if not np.array_equal(seen, valid.ravel()):
        raise ValueError("Every valid terrain component must reach the grid's open outer rim")
    order = np.asarray(order, np.int32)
    rank = np.full(n, -1, np.int32)
    rank[order] = np.arange(len(order))
    receiver = parent.copy()
    slope = np.zeros(n)
    # Resolve gradient from spill-surface elevation, falling back to flood-tree
    # parent only across exactly flat filled pools. This preserves acyclicity.
    for k in range(8):
        j = neighbors[:, k]
        good = (j >= 0)
        i = np.flatnonzero(good)
        target = j[good]
        good2 = rank[target] < rank[i]
        i, target = i[good2], target[good2]
        gradient = (filled[i] - filled[target]) / distance[k]
        improve = gradient > slope[i] + 1e-14
        receiver[i[improve]] = target[improve]
        slope[i[improve]] = gradient[improve]
    # At exits, extrapolate the actual downhill surface over the boundary.
    # This avoids forcing all suspended sediment to deposit at zero-slope rim.
    exits = order[receiver[order] < 0]
    for i in exits:
        js = neighbors[i]
        ok = js >= 0
        if np.any(ok):
            slope[i] = max(0., float(np.max((z[js[ok]] - z[i]) / distance[ok])))
    return receiver, slope, filled, order[::-1]


def simulate_shoulder(x_m: np.ndarray, y_m: np.ndarray, z_m: np.ndarray,
                      config: FlowConfig | None = None,
                      valid_mask: np.ndarray | None = None) -> FlowResult:
    """Route repeat storms and return conservative, physically coupled fields.

    z_m.shape == (len(y_m),len(x_m)); class arrays append a final axis of 3.
    Exposure/burial/lag/compaction fields are bounded [0,1], dimensionless art
    controls. Exposure refers to existing grains in the initial surface; use
    retained deposit thickness/fractions for newly transported grain placement.
    Invalid cells return zero fields and receiver=-2; z may be NaN there.
    Input arrays are never modified. No scene, material or file operations occur.
    """
    started = time.perf_counter()
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
    rng = np.random.default_rng(cfg.seed)
    texture = _heterogeneity(shape, dx, dy, rng).ravel()
    erodibility = np.clip(1.0 + 1.5 * texture, 0.20, 1.9)
    resistance = np.clip(1.0 - 0.65 * texture, 0.65, 1.5)
    yy, xx = np.indices(shape)
    edge_cells = np.minimum.reduce((xx, yy, shape[1] - 1 - xx, shape[0] - 1 - yy))
    band = (np.clip(edge_cells / cfg.boundary_band_cells, 0., 1.)
            if cfg.boundary_band_cells else np.ones(shape))
    band = (band * band * (3. - 2. * band)).ravel()
    band[~active] = 0.
    initial = np.tile(np.asarray(cfg.substrate_fractions) * cfg.max_erosion_m * area, (n, 1))
    initial *= band[:, None]
    bed = initial.copy()
    deposited = np.zeros((n, 3))
    eroded = np.zeros((n, 3))
    deposition = np.zeros((n, 3))
    water_total = np.zeros(n)
    max_depth = np.zeros(n)
    max_shear = np.zeros(n)
    max_pond = np.zeros(n)
    neighbors, distances = _neighbors(shape, dx, dy, valid)
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
        receiver, slope, filled, order = _drainage(z, valid, neighbors, distances)
        pond = np.where(active, np.maximum(filled - z, 0), 0)
        max_pond = np.maximum(max_pond, pond)
        water = np.full(n, rain * area * cfg.runoff_fraction)
        water[~active] = 0
        water += rain * cfg.upstream_runoff_fraction * upstream_area
        mobile = np.zeros((n, 3))
        event_export = np.zeros(3)
        event_water_export = 0.
        eroded_before, deposited_before = float(eroded.sum()), float(deposition.sum())
        for i in order:
            w = water[i]
            if w <= 0:
                continue
            j = receiver[i]
            s = max(slope[i], cfg.minimum_transport_slope)
            # Wide-shallow Manning approximation; flooded cells are attenuated.
            h = ((w / cfg.event_duration_s / width) * cfg.manning_n * resistance[i]
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
            want_deposit = np.maximum(load - cap, 0.) * cfg.deposition_relaxation
            net = float((bed[i] + deposited[i] - initial[i]).sum())
            room = max(0., cfg.max_deposition_m * area * band[i] - net)
            requested = float(want_deposit.sum())
            if requested > room:
                want_deposit *= room / requested
            deposited[i] += want_deposit
            deposition[i] += want_deposit
            load -= want_deposit
            # Only entrain undersaturated classes. A finite event budget and a
            # finite initial bed layer bound cuts, even with extreme rain.
            demand = np.maximum(cap - load, 0.) * cfg.erosion_relaxation
            budget = (cfg.max_event_erosion_m * area * band[i]
                      * min(erodibility[i] * shear / 0.45, 1.0))
            demand *= min(1., budget / max(float(demand.sum()), 1e-30))
            available = deposited[i] + bed[i]
            take = np.minimum(demand, available)
            from_deposit = np.minimum(take, deposited[i])
            deposited[i] -= from_deposit
            bed[i] -= take - from_deposit
            eroded[i] += take
            load += take
            if j >= 0:
                water[j] += w
                mobile[j] += load
            else:
                event_water_export += w
                event_export += load
            mobile[i] = 0.
        exported += event_export
        rainfall = rain * active_area
        upstream = rain * cfg.upstream_runoff_fraction * float(upstream_area.sum())
        infiltrated = rainfall * (1. - cfg.runoff_fraction)
        rainfall_total += rainfall
        upstream_total += upstream
        infiltration_total += infiltrated
        water_export_total += event_water_export
        net_volume = float((bed + deposited - initial).sum())
        event_receipts.append({
            "event": event + 1, "rainfall_m": float(rain),
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
        "model": "bounded multi-event priority-flood D8 bulk sediment transport",
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
        final_receiver=receiver.reshape(shape), valid_mask=valid, boundary_mobility=field(band), receipt=receipt)
