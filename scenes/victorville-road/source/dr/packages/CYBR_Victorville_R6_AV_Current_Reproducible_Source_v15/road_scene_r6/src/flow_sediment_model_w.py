"""Small conservative shoulder-flow model, NumPy + Python standard library only.

NONVALIDATED, ART-DIRECTED PHYSICS. This is a bounded landscape-weathering
model, not a hydraulic/engineering prediction. Feed uniformly sampled ACTUAL
terrain-triangle heights, in metres; no analytic replacement terrain is used.
A priority-flood surface determines connected multiple-flow drainage. Each storm
routes water and three mobile bulk-volume sediment bins in acyclic sweeps.
W uses a finite physical bed-exchange footprint and metre-based equilibration
lengths. Sediment-only slope relaxation is accounted during every storm, never
applied as an unaccounted smoothing filter to the finished height field. Local
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
    exchange_diameter_m: float = 0.10
    flow_partition_exponent: float = 1.35
    erosion_length_m: float = 0.075
    deposition_length_m: tuple[float, float, float] = (0.14, 0.085, 0.045)
    deposit_repose_slope: float = 0.30
    slope_relaxation_rate: float = 0.18
    heterogeneity_strength: float = 1.0
    boundary_band_cells: float = 4.0
    boundary_band_m: float | None = 0.10
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
    # Suppress coordinate-origin subtraction noise, not physical resolution.
    return a, float(f"{d[0]:.12g}")


def _validate(config: FlowConfig) -> None:
    for name in ("event_duration_s", "max_erosion_m", "max_deposition_m",
                 "max_event_erosion_m", "manning_n", "minimum_transport_slope",
                 "exchange_diameter_m", "flow_partition_exponent", "erosion_length_m",
                 "deposit_repose_slope", "slope_relaxation_rate"):
        v = getattr(config, name)
        if not np.isfinite(v) or v <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("runoff_fraction", "upstream_runoff_fraction",
                 "deposition_relaxation", "erosion_relaxation"):
        v = getattr(config, name)
        if not np.isfinite(v) or not 0 <= v <= 1:
            raise ValueError(f"{name} must lie in [0,1]")
    if not np.isfinite(config.heterogeneity_strength) or not 0 <= config.heterogeneity_strength <= 1:
        raise ValueError("heterogeneity_strength must be in [0,1]")
    if config.boundary_band_m is not None and (not np.isfinite(config.boundary_band_m) or config.boundary_band_m <= 0):
        raise ValueError("boundary_band_m must be None or finite and positive")
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
                 "critical_shear_pa", "max_concentration", "deposition_length_m"):
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


def _flow_routes(z, valid, neighbors, distances, exponent):
    """MFD with metric flat-drain distances; no index-directed flood-tree streaks."""
    _, exit_slope, filled, _ = _drainage(z, valid, neighbors, distances)
    n = len(z)
    safe = np.maximum(neighbors, 0)
    good = neighbors >= 0
    drop = filled[:, None] - filled[safe]
    drop[~good] = 0.
    lower = good & (drop > 1e-12)
    rim = np.zeros(valid.shape, bool)
    rim[[0, -1]] = True
    rim[:, [0, -1]] = True
    seeds = np.flatnonzero((lower.any(axis=1) | rim.ravel()) & valid.ravel())
    flat_distance = np.full(n, np.inf)
    flat_distance[seeds] = 0.
    heap = [(0., int(i)) for i in seeds]
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d != flat_distance[i]:
            continue
        for k, j in enumerate(neighbors[i]):
            if j < 0 or abs(filled[j] - filled[i]) > 1e-12:
                continue
            candidate = d + distances[k]
            if candidate < flat_distance[j] - 1e-12:
                flat_distance[j] = candidate
                heapq.heappush(heap, (candidate, int(j)))
    if np.any(~np.isfinite(flat_distance[valid.ravel()])):
        raise ValueError('Spill-flat component has no draining perimeter')
    gradient = np.maximum(drop / distances, 0.)
    flat_drop = flat_distance[:, None] - flat_distance[safe]
    on_flat = good & (np.abs(drop) <= 1e-12) & (flat_drop > 1e-12)
    flat_gradient = np.where(on_flat, np.maximum(flat_drop / distances, 0.), 0.)
    # True downhill exits take priority over routes remaining on a level pool.
    effective = np.where(lower.any(axis=1)[:, None], gradient, flat_gradient)
    effective[~good] = 0.
    weights = effective ** exponent
    weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-30)
    slope = np.sum(weights * gradient, axis=1)
    exits = weights.sum(axis=1) == 0
    slope[exits] = exit_slope[exits]
    active = np.flatnonzero(valid.ravel())
    # Strict descending (filled level, metric distance-to-drain) is acyclic.
    order = active[np.lexsort((flat_distance[active], filled[active]))[::-1]]
    dominant = np.full(n, -1, np.int32)
    moving = np.flatnonzero(~exits & valid.ravel())
    dominant[moving] = neighbors[moving, np.argmax(weights[moving], axis=1)]
    return weights, slope, filled, order, dominant


def _footprints(shape, dx, dy, valid, diameter):
    """Cell-integrated compact disk; physical width independent of grid spacing.

    A 5x5 subcell quadrature gives area fractions at the disk rim. Every local
    interaction uses this finite reach/contact area, before mass exchange.
    This is not filtering or a later height/deposition-mask convolution.
    """
    ny, nx = shape
    yy, xx = np.indices(shape)
    radius = diameter / 2
    offsets, kernel = [], []
    samples = (np.arange(5) + .5) / 5 - .5
    qy, qx = np.meshgrid(samples * dy, samples * dx, indexing='ij')
    for oy in range(-int(math.ceil(radius / dy)), int(math.ceil(radius / dy)) + 1):
        for ox in range(-int(math.ceil(radius / dx)), int(math.ceil(radius / dx)) + 1):
            overlap = np.mean((ox * dx + qx) ** 2 + (oy * dy + qy) ** 2 <= radius ** 2 * (1. + 1e-12))
            if overlap > 0:
                offsets.append((oy, ox))
                kernel.append(float(overlap))
    indices = np.zeros((ny * nx, len(offsets)), np.int32)
    weights = np.zeros(indices.shape)
    for k, ((oy, ox), w) in enumerate(zip(offsets, kernel)):
        y, x = yy + oy, xx + ox
        inside = (y >= 0) & (y < ny) & (x >= 0) & (x < nx)
        src = np.flatnonzero(inside.ravel())
        target = (y[inside] * nx + x[inside]).ravel()
        allowed = valid.ravel()[src] & valid.ravel()[target]
        src, target = src[allowed], target[allowed]
        indices[src, k] = target
        weights[src, k] = w
    weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-30)
    return indices, weights


def _repair_roundoff_inventory(array, ledger, label, tolerance):
    """Repair only sub-tolerance subtraction roundoff; reject real deficits."""
    if not np.all(np.isfinite(array)):
        raise FloatingPointError(f"{label}: nonfinite inventory")
    minimum = float(array.min())
    if minimum < -tolerance:
        raise FloatingPointError(f"{label}: negative inventory {minimum:.9g} m3 exceeds roundoff tolerance {tolerance:.3g}")
    negative = array < 0
    if np.any(negative):
        correction = np.where(negative, -array, 0.)
        ledger['added_by_class_m3'] += correction.sum(axis=0)
        ledger['corrected_entries'] += int(negative.sum())
        array[negative] = 0.


def _assert_event_state(stage, initial, bed, deposited, eroded, deposition,
                        exported, area, band, cfg, ledger):
    """Absolute, class-wise invariants; never hide blow-ups in relative error."""
    for name, a in (('bed', bed), ('deposit', deposited), ('erosion', eroded),
                    ('deposition', deposition), ('export', exported)):
        if not np.all(np.isfinite(a)) or np.any(a < 0):
            raise FloatingPointError(f"{stage}: {name} must be finite and nonnegative")
    tolerance = max(1e-12, float(initial.sum()) * 1e-10)
    correction = ledger['added_by_class_m3']
    if float(correction.sum()) > tolerance * .01:
        raise FloatingPointError(f"{stage}: accumulated roundoff repair exceeded its tiny correction budget")
    net = bed + deposited - initial
    gross_error = eroded.sum(axis=0) - deposition.sum(axis=0) - exported
    stock_error = net.sum(axis=0) + exported - correction
    if max(float(np.max(abs(gross_error))), float(np.max(abs(stock_error)))) > tolerance:
        raise FloatingPointError(f"{stage}: absolute class conservation failed; gross={gross_error}, stock={stock_error}")
    height = net.sum(axis=1) / area
    if (np.any(height < -cfg.max_erosion_m * band - 1e-12)
            or np.any(height > cfg.max_deposition_m * band + 1e-12)):
        raise FloatingPointError(f"{stage}: bounded height invariant failed")
    return float(max(np.max(abs(gross_error)), np.max(abs(stock_error))))


def _relax_deposits(zbase, initial, bed, deposited, erosion, deposition,
                    area, band, neighbors, distances, cfg, dx, dy, roundoff_ledger=None):
    """Pairwise finite-volume slumping of mobile deposits, by class.

    No original terrain is blurred. Donor inventory, receiver elevation bound,
    and locked-rim mobility limit every transfer. The next storm sees this bed.
    """
    if roundoff_ledger is None:
        roundoff_ledger = {'added_by_class_m3': np.zeros(3), 'corrected_entries': 0}
    tolerance = max(area * (cfg.max_erosion_m + cfg.max_deposition_m) * 64 * np.finfo(float).eps, 1e-25)
    _repair_roundoff_inventory(deposited, roundoff_ledger, 'relaxation entry', tolerance)
    source, target, distance = [], [], []
    n = len(zbase)
    for k, (oy, ox) in enumerate(_OFFSETS):
        if oy < 0 or (oy == 0 and ox < 0):
            continue
        j = neighbors[:, k]
        i = np.flatnonzero(j >= 0)
        source.extend(i.tolist())
        target.extend(j[i].tolist())
        distance.extend([distances[k]] * len(i))
    a, b, d = np.asarray(source), np.asarray(target), np.asarray(distance)
    total_moved = 0.
    iterations = max(2, int(math.ceil(cfg.exchange_diameter_m / min(dx, dy))) * 2)
    for _ in range(iterations):
        net = (bed + deposited - initial).sum(axis=1)
        height = zbase + net / area
        diff = height[a] - height[b]
        src = np.where(diff >= 0, a, b)
        dst = np.where(diff >= 0, b, a)
        amount = np.maximum(np.abs(diff) - cfg.deposit_repose_slope * d, 0.)
        amount *= area * cfg.slope_relaxation_rate * np.minimum(band[src], band[dst])
        active = amount > 1e-18
        if not np.any(active):
            break
        src, dst, amount = src[active], dst[active], amount[active]
        inventory = deposited.sum(axis=1)
        outgoing = np.bincount(src, weights=amount, minlength=n)
        amount *= np.clip(inventory[src] / np.maximum(outgoing[src], 1e-30), 0., 1.)
        incoming = np.bincount(dst, weights=amount, minlength=n)
        room = np.maximum(cfg.max_deposition_m * area * band - net, 0.)
        amount *= np.clip(room[dst] / np.maximum(incoming[dst], 1e-30), 0., 1.)
        fractions = np.divide(deposited[src], inventory[src, None],
                              out=np.zeros((len(src), 3)), where=inventory[src, None] > 0)
        moved = amount[:, None] * fractions
        # Bound each outgoing CLASS independently. Reserving a few ULPs at an
        # exhausted donor avoids subtracting many rounded edges past zero.
        outgoing_class = np.column_stack([np.bincount(src, weights=moved[:, k], minlength=n)
                                          for k in range(3)])
        donor_limit = np.clip(np.divide(deposited, outgoing_class,
                                       out=np.ones_like(deposited), where=outgoing_class > 0), 0., 1.)
        donor_limit *= 1. - 32. * np.finfo(float).eps
        moved *= donor_limit[src]
        outgoing_class = np.column_stack([np.bincount(src, weights=moved[:, k], minlength=n)
                                          for k in range(3)])
        incoming_class = np.column_stack([np.bincount(dst, weights=moved[:, k], minlength=n)
                                          for k in range(3)])
        # Aggregate first, then subtract once per donor/class. This is the
        # finite-volume transfer ledger, rather than repeated in-place debits.
        deposited[:] = (deposited - outgoing_class) + incoming_class
        erosion += outgoing_class
        deposition += incoming_class
        _repair_roundoff_inventory(deposited, roundoff_ledger,
                                    f'slope iteration {_ + 1}', tolerance)
        total_moved += float(moved.sum())
    return total_moved


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
    # Hydraulic geometry uses a relative datum at picometre precision, keeping
    # arbitrary world-Z offsets from changing otherwise equal routing ties.
    zbase = np.round(zbase - zbase[np.flatnonzero(active)[0]], 12)
    rng = np.random.default_rng(cfg.seed)
    texture = _heterogeneity(shape, dx, dy, rng).ravel() * cfg.heterogeneity_strength
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
    footprint_index, footprint_weight = _footprints(shape, dx, dy, valid, cfg.exchange_diameter_m)
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
            ids = footprint_index[i]
            weights = footprint_weight[i]
            supported = weights > 0
            ids, weights = ids[supported], weights[supported]
            # Exchange is distributed over the physical contact reach *before*
            # any bed change. Individual target inventory/bounds are conserved.
            net = (bed[ids] + deposited[ids] - initial[ids]).sum(axis=1)
            room = np.maximum(0., cfg.max_deposition_m * area * band[ids] - net)
            add = weights[:, None] * want_deposit[None, :]
            add *= np.minimum(1., room / np.maximum(add.sum(axis=1), 1e-30))[:, None]
            deposited[ids] += add
            deposition[ids] += add
            load -= add.sum(axis=0)
            entrain = min(1., (1. - math.exp(-reach_length / cfg.erosion_length_m)) * (cfg.erosion_relaxation / .55))
            demand = np.maximum(cap - load, 0.) * entrain
            take = weights[:, None] * demand[None, :]
            available = np.maximum(deposited[ids] + bed[ids], 0.)
            take = np.minimum(take, available)
            budget = (cfg.max_event_erosion_m * area * band[ids]
                      * np.minimum(erodibility[ids] * shear / 0.45, 1.0))
            budget = np.maximum(budget - event_erosion[ids], 0.)
            take *= np.minimum(1., budget / np.maximum(take.sum(axis=1), 1e-30))[:, None]
            from_deposit = np.minimum(take, deposited[ids])
            from_bed = np.minimum(np.maximum(take - from_deposit, 0.), bed[ids])
            take = from_deposit + from_bed
            deposited[ids] -= from_deposit
            bed[ids] -= from_bed
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
        _repair_roundoff_inventory(bed, roundoff_ledger, f'event {event + 1} bed', roundoff_tolerance)
        _repair_roundoff_inventory(deposited, roundoff_ledger, f'event {event + 1} deposit', roundoff_tolerance)
        _assert_event_state(f'event {event + 1} before slope transfer', initial, bed,
                            deposited, eroded, deposition, exported + event_export,
                            area, band, cfg, roundoff_ledger)
        slope_transfer = _relax_deposits(zbase, initial, bed, deposited, eroded,
                                           deposition, area, band, neighbors, distances,
                                           cfg, dx, dy, roundoff_ledger)
        total_slope_transfer += slope_transfer
        exported += event_export
        event_state_error = _assert_event_state(f'event {event + 1} after slope transfer',
                                                initial, bed, deposited, eroded, deposition,
                                                exported, area, band, cfg, roundoff_ledger)
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
        "model": "W finite-footprint multiple-flow bulk sediment transport",
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
        final_receiver=receiver.reshape(shape), valid_mask=valid, boundary_mobility=field(band), receipt=receipt)
