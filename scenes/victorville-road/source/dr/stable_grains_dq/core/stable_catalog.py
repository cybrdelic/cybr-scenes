"""Camera-independent, bounded display catalog of unchanged physical grains.

No Blender, RNG stream, camera, retry placement, geometry scaling, or installation.
Candidate identity v1 is (uint64 seed, int32 band, int64 source_id, signed absolute
world-cell X/Y, uint64 physical ordinal). Prototype array indices are payload, not
identity. Every hash channel has a separate domain. See README.md for guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
from typing import Mapping, Sequence
import numpy as np

ALGORITHM = "world-cell-grain-catalog-v1"
_U64_MAX = (1 << 64) - 1
_I64_MAX = (1 << 63) - 1
# Keep squared-distance and extent arithmetic safely representable in float64.
_METRIC_LIMIT = 1e150
_MIN_RADIUS = 1e-150
# Fixed constants are an identity contract: changes require a new algorithm version.
_ID_DOMAIN = 0x6A09E667F3BCC909
_CHANNELS = {"x": 0xA54FF53A5F1D36F1, "y": 0x510E527FADE682D1,
             "yaw": 0x9B05688C2B3E6C1F, "lod": 0x1F83D9ABFB41BD6B,
             "thin": 0x5BE0CD19137E2179, "cap": 0xCBBB9D5DC1059ED8,
             "count": 0x629A292A367CD507}


class CatalogLimitError(ValueError):
    """A fixed build bound was exceeded; never return a silently truncated catalog."""


def _integer(value, name, low, high):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f"{name} outside [{low}, {high}]")
    return value


def _mix64(value):
    """SplitMix64 finalizer, with explicitly specified uint64 wraparound."""
    a = np.asarray(value, dtype=np.uint64)
    with np.errstate(over="ignore"):
        a = (a ^ (a >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        a = (a ^ (a >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return a ^ (a >> np.uint64(31))


def _cell_key(seed, band, source_id, ix, iy):
    state = np.uint64(_ID_DOMAIN)
    for position, value in enumerate((seed, band, source_id, ix, iy), 1):
        # Signed cells use their exact two's-complement uint64 representation.
        tagged = np.uint64(int(value) & _U64_MAX) ^ np.uint64(position * 0x9E3779B9)
        state = _mix64(state ^ _mix64(tagged))
    return state


def _uniform(key, channel):
    # Exact 53-bit [0,1) dyadics; no global random-number state.
    return (_mix64(key ^ np.uint64(_CHANNELS[channel])) >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)


@dataclass(frozen=True)
class Prototype:
    source_id: int
    prototype_id: int
    band: int
    density_per_m2: float
    radius: float

    def __post_init__(self):
        _integer(self.source_id, "source_id", 0, _I64_MAX)
        _integer(self.prototype_id, "prototype_id", 0, (1 << 31) - 1)
        _integer(self.band, "band", 0, (1 << 31) - 1)
        if not math.isfinite(self.density_per_m2) or self.density_per_m2 < 0:
            raise ValueError("density_per_m2 must be finite and nonnegative")
        if not math.isfinite(self.radius) or not _MIN_RADIUS <= self.radius <= _METRIC_LIMIT:
            raise ValueError("original enclosing radius must be within [1e-150, 1e150] metres")


@dataclass(frozen=True)
class CatalogSpec:
    seed: int
    cell_size: float
    bounds: tuple[float, float, float, float]  # xmin, xmax, ymin, ymax; half open
    thinning_by_band: Mapping[int, float]
    catalog_epoch: str
    source_pins: Mapping[str, str]
    max_virtual_candidates: int = 50_000_000
    max_catalog_candidates: int = 1_000_000
    max_cells: int = 1_000_000
    max_grid_bins: int = 4_000_000
    max_count_entries: int = 4_000_000
    chunk_size: int = 65_536

    def __post_init__(self):
        _integer(self.seed, "seed", 0, _U64_MAX)
        if not math.isfinite(self.cell_size) or not 0 < self.cell_size <= _METRIC_LIMIT:
            raise ValueError("cell_size must be positive and finite")
        if len(self.bounds) != 4 or not np.isfinite(self.bounds).all() or np.any(np.abs(self.bounds) > _METRIC_LIMIT):
            raise ValueError("bounds must be four finite numbers")
        x0, x1, y0, y1 = self.bounds
        if not x0 < x1 or not y0 < y1:
            raise ValueError("bounds must have positive area")
        if not isinstance(self.catalog_epoch, str) or not self.catalog_epoch:
            raise ValueError("an explicit catalog_epoch is required")
        if not self.source_pins or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v
                                      for k, v in self.source_pins.items()):
            raise ValueError("nonempty named source pins are required")
        for band, fraction in self.thinning_by_band.items():
            _integer(band, "thinning band", 0, (1 << 31) - 1)
            if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                raise ValueError("thinning fractions must be finite and in [0,1]")
        for name in ("max_virtual_candidates", "max_catalog_candidates", "max_cells", "max_grid_bins", "max_count_entries", "chunk_size"):
            _integer(getattr(self, name), name, 1, _I64_MAX)


@dataclass(frozen=True)
class GrainArrays:
    ids: np.ndarray                  # uint64 immutable candidate IDs
    xy: np.ndarray                   # float64 world-space XY
    prototype_id: np.ndarray         # int32 original bank index
    source_id: np.ndarray            # int64 original source identity
    yaw: np.ndarray                  # float32 radians
    priority: np.ndarray             # float64 independent LOD probability draw
    cap_priority: np.ndarray         # uint64 independent hard-cap rank
    cell_xy: np.ndarray              # int64 signed absolute world-cell coordinates
    radius: np.ndarray               # float64 original enclosing radius
    band: np.ndarray                 # int32 original population band
    physical_ordinal: np.ndarray     # uint64 full virtual-count ordinal

    def __len__(self):
        return len(self.ids)

    def take(self, selection):
        return _freeze(GrainArrays(**{f.name: getattr(self, f.name)[selection].copy() for f in fields(self)}))


def _freeze(batch):
    for f in fields(batch):
        getattr(batch, f.name).setflags(write=False)
    return batch


def _empty():
    return _freeze(GrainArrays(np.empty(0, "u8"), np.empty((0, 2), "f8"), np.empty(0, "i4"),
                              np.empty(0, "i8"), np.empty(0, "f4"), np.empty(0, "f8"),
                              np.empty(0, "u8"), np.empty((0, 2), "i8"), np.empty(0, "f8"),
                              np.empty(0, "i4"), np.empty(0, "u8")))


def concatenate_batches(batches: Sequence[GrainArrays]):
    """Concatenate independently evaluated chunks without consuming random state."""
    batches = [b for b in batches if len(b)]
    if not batches:
        return _empty()
    return _freeze(GrainArrays(**{f.name: np.concatenate([getattr(b, f.name) for b in batches])
                                 for f in fields(GrainArrays)}))


def canonicalize(batch: GrainArrays):
    """Coarse-band order then ascending candidate uint64 ID, never arrival order."""
    if len(np.unique(batch.ids)) != len(batch):
        raise ValueError("duplicate candidate ID or uint64 collision; refuse ambiguous catalog")
    return batch.take(np.lexsort((batch.ids, batch.band)))


def world_cells(spec: CatalogSpec):
    """All origin-anchored cells intersecting the fixed half-open scope."""
    x0, x1, y0, y1 = spec.bounds
    lo_x, lo_y = math.floor(x0 / spec.cell_size), math.floor(y0 / spec.cell_size)
    hi_x, hi_y = math.ceil(x1 / spec.cell_size), math.ceil(y1 / spec.cell_size)
    for value in (lo_x, lo_y, hi_x, hi_y):
        _integer(value, "absolute cell coordinate", -_I64_MAX, _I64_MAX)
    n = (hi_x - lo_x) * (hi_y - lo_y)
    if n > spec.max_cells:
        raise CatalogLimitError(f"{n} cells exceeds fixed max_cells={spec.max_cells}")
    xx = np.arange(lo_x, hi_x, dtype=np.int64)
    yy = np.arange(lo_y, hi_y, dtype=np.int64)
    return np.column_stack((np.repeat(xx, len(yy)), np.tile(yy, len(xx))))


def physical_count(seed: int, prototype: Prototype, cell_xy, cell_size: float):
    """Full cell count: floor(density*world area) plus a keyed Bernoulli remainder."""
    ix, iy = map(int, cell_xy)
    expected = float(prototype.density_per_m2) * float(cell_size) ** 2
    if not math.isfinite(expected) or expected >= _I64_MAX:
        raise CatalogLimitError("physical count is not a representable bounded integer")
    base = math.floor(expected)
    key = _cell_key(seed, prototype.band, prototype.source_id, ix, iy)
    return base + int(float(_uniform(key, "count")) < expected - base)


def candidate_block(seed: int, prototype: Prototype, cell_xy, cell_size: float,
                    start: int, stop: int) -> GrainArrays:
    """Pure random access to physical ordinals; a caller's early quota is irrelevant.

    This low-level function creates [start, stop), without thinning, packing, or
    scope clipping. Build limits are enforced by build_candidates, not this helper.
    """
    _integer(seed, "seed", 0, _U64_MAX)
    start = _integer(start, "start", 0, _I64_MAX)
    stop = _integer(stop, "stop", start, _I64_MAX)
    ix, iy = (_integer(x, "cell coordinate", -_I64_MAX, _I64_MAX) for x in cell_xy)
    if not math.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("cell_size must be positive and finite")
    ordinals = np.arange(start, stop, dtype=np.uint64)
    key = _cell_key(seed, prototype.band, prototype.source_id, ix, iy)
    ids = _mix64(key ^ _mix64(ordinals ^ np.uint64(0xD807AA98A3030242)))
    xy = np.column_stack(((ix + _uniform(ids, "x")) * cell_size,
                          (iy + _uniform(ids, "y")) * cell_size))
    if not np.isfinite(xy).all() or np.any(np.abs(xy) > _METRIC_LIMIT):
        raise ValueError("world coordinates outside the safe float64 metric range")
    n = len(ids)
    return _freeze(GrainArrays(ids, xy, np.full(n, prototype.prototype_id, "i4"),
                              np.full(n, prototype.source_id, "i8"),
                              (_uniform(ids, "yaw") * math.tau).astype("f4"),
                              _uniform(ids, "lod"), _mix64(ids ^ np.uint64(_CHANNELS["cap"])),
                              np.tile(np.array((ix, iy), "i8"), (n, 1)),
                              np.full(n, prototype.radius, "f8"), np.full(n, prototype.band, "i4"), ordinals))


def _prototypes(spec, prototypes):
    records = sorted(prototypes, key=lambda p: (p.band, p.source_id))
    if not records:
        raise ValueError("at least one prototype is required")
    if len({(p.band, p.source_id) for p in records}) != len(records):
        raise ValueError("duplicate source identity within a band")
    if len({p.prototype_id for p in records}) != len(records):
        raise ValueError("prototype indices must be unique")
    if set(spec.thinning_by_band) != {p.band for p in records}:
        raise ValueError("thinning_by_band must name exactly the prototype bands")
    return records


def build_candidates(spec: CatalogSpec, prototypes: Sequence[Prototype], *, cell_order=None):
    """Evaluate the entire bounded virtual population, then fixed catalog thinning.

    cell_order is only an evaluation-order permutation for reproducibility tests;
    no per-view quota, limit, or early stop is accepted. Counts use complete cells
    even at scope edges. Clipping happens after keyed positions are generated.
    """
    records = _prototypes(spec, prototypes)
    cells = world_cells(spec)
    entries = len(cells) * len(records)
    if entries > spec.max_count_entries:
        raise CatalogLimitError(f"{entries} count-matrix entries exceeds fixed limit {spec.max_count_entries}")
    counts = np.empty((len(cells), len(records)), dtype=np.int64)
    for c, cell in enumerate(cells):
        for p, proto in enumerate(records):
            counts[c, p] = physical_count(spec.seed, proto, cell, spec.cell_size)
    virtual_total = sum(map(int, counts.flat))
    if virtual_total > spec.max_virtual_candidates:
        raise CatalogLimitError(f"{virtual_total} virtual candidates exceeds fixed limit {spec.max_virtual_candidates}")
    if cell_order is None:
        order = np.arange(len(cells))
    else:
        order = np.asarray(cell_order)
        if order.dtype.kind not in "iu" or order.shape != (len(cells),) or not np.array_equal(np.sort(order), np.arange(len(cells))):
            raise ValueError("cell_order must permute every scope cell exactly once")
    inside_counts = np.zeros(len(records), dtype=np.int64)
    attempt_counts = np.zeros(len(records), dtype=np.int64)
    retained, total = [], 0
    x0, x1, y0, y1 = spec.bounds
    for c in order:
        for p, proto in enumerate(records):
            for start in range(0, int(counts[c, p]), spec.chunk_size):
                batch = candidate_block(spec.seed, proto, cells[c], spec.cell_size, start,
                                        min(start + spec.chunk_size, int(counts[c, p])))
                inside = ((batch.xy[:, 0] >= x0) & (batch.xy[:, 0] < x1) &
                          (batch.xy[:, 1] >= y0) & (batch.xy[:, 1] < y1))
                inside_counts[p] += np.count_nonzero(inside)
                keep = inside & (_uniform(batch.ids, "thin") < spec.thinning_by_band[proto.band])
                n = int(np.count_nonzero(keep))
                total += n
                if total > spec.max_catalog_candidates:
                    raise CatalogLimitError("fixed max_catalog_candidates exceeded; increase build bound or lower fixed thinning in a new epoch")
                attempt_counts[p] += n
                if n:
                    retained.append(batch.take(keep))
    batch = canonicalize(concatenate_batches(retained))
    stats = dict(cells=cells, physical_counts=counts, prototypes=records,
                 virtual_in_scope_by_prototype=inside_counts,
                 catalog_attempts_by_prototype=attempt_counts)
    return batch, stats


def _blockers_array(blockers):
    blockers = np.array(blockers, dtype=np.float64, copy=True)
    if blockers.size == 0:
        blockers = np.empty((0, 3), dtype=np.float64)
    if blockers.ndim != 2 or blockers.shape[1] != 3 or not np.isfinite(blockers).all() or np.any(blockers[:, 2] < _MIN_RADIUS) or np.any(np.abs(blockers) > _METRIC_LIMIT):
        raise ValueError("original blockers must be finite Nx3 [world X, world Y, original positive radius]")
    blockers[blockers == 0] = 0.  # Normalize signed zero for canonical provenance.
    # Sorting is not needed for acceptance, but makes provenance independent of input order.
    return np.ascontiguousarray(blockers[np.lexsort((blockers[:, 2], blockers[:, 1], blockers[:, 0]))])


def _packing_kernel(xy, radius, blockers, lower, grid_cell, nx, ny):
    """Typed linked grids only. This exact function also supports numba.njit."""
    original_head = np.full(nx * ny, -1, dtype=np.int64)
    catalog_head = np.full(nx * ny, -1, dtype=np.int64)
    original_next = np.full(len(blockers), -1, dtype=np.int64)
    catalog_next = np.full(len(xy), -1, dtype=np.int64)
    reasons = np.zeros(len(xy), dtype=np.uint8)
    for j in range(len(blockers)):
        gx = min(nx - 1, max(0, int(math.floor((blockers[j, 0] - lower[0]) / grid_cell))))
        gy = min(ny - 1, max(0, int(math.floor((blockers[j, 1] - lower[1]) / grid_cell))))
        cell = gy * nx + gx
        original_next[j] = original_head[cell]
        original_head[cell] = j
    for i in range(len(xy)):
        gx = min(nx - 1, max(0, int(math.floor((xy[i, 0] - lower[0]) / grid_cell))))
        gy = min(ny - 1, max(0, int(math.floor((xy[i, 1] - lower[1]) / grid_cell))))
        # Always check fixed original blockers before already accepted new grains.
        for stage in range(2):
            hit = False
            for yy in range(max(0, gy - 1), min(ny, gy + 2)):
                for xx in range(max(0, gx - 1), min(nx, gx + 2)):
                    cell = yy * nx + xx
                    j = original_head[cell] if stage == 0 else catalog_head[cell]
                    while j >= 0:
                        bx = blockers[j, 0] if stage == 0 else xy[j, 0]
                        by = blockers[j, 1] if stage == 0 else xy[j, 1]
                        br = blockers[j, 2] if stage == 0 else radius[j]
                        dx, dy = xy[i, 0] - bx, xy[i, 1] - by
                        if dx * dx + dy * dy < (radius[i] + br) ** 2:
                            hit = True
                            break
                        j = original_next[j] if stage == 0 else catalog_next[j]
                    if hit:
                        break
                if hit:
                    break
            if hit:
                reasons[i] = stage + 1
                break
        if reasons[i] == 0:
            cell = gy * nx + gx
            catalog_next[i] = catalog_head[cell]
            catalog_head[cell] = i
    return reasons


_NUMBA_KERNEL = None


def pack_candidates(batch: GrainArrays, original_blockers=(), *, max_grid_bins=4_000_000, backend="numpy"):
    """Resolve every catalog candidate before any view selection. No relocation.

    Returns canonical batch, rejection codes (0 accepted, 1 original blocker,
    2 earlier canonical catalog grain), and grid diagnostics. Tangency is allowed.
    A larger bin size reduces memory if needed without changing exact acceptance.
    """
    _integer(max_grid_bins, "max_grid_bins", 1, _I64_MAX)
    if backend not in ("numpy", "numba"):
        raise ValueError("backend must be numpy or numba")
    if batch.xy.shape != (len(batch), 2) or batch.radius.shape != (len(batch),):
        raise ValueError("candidate XY and radius must be aligned arrays")
    if not np.isfinite(batch.xy).all() or np.any(np.abs(batch.xy) > _METRIC_LIMIT) or not np.isfinite(batch.radius).all() or np.any((batch.radius < _MIN_RADIUS) | (batch.radius > _METRIC_LIMIT)):
        raise ValueError("candidate geometry outside the safe float64 metric range")
    batch = canonicalize(batch)
    blockers = _blockers_array(original_blockers)
    if not len(batch):
        return batch, np.empty(0, "u1"), dict(backend=backend, grid_bins=0, relevant_original_blockers=0)
    # Discard only blockers whose enclosing disk cannot intersect any candidate disk.
    max_r = float(batch.radius.max())
    low, high = batch.xy.min(0), batch.xy.max(0)
    delta = np.maximum(np.maximum(low - blockers[:, :2], blockers[:, :2] - high), 0)
    blockers = blockers[np.sum(delta * delta, axis=1) < (blockers[:, 2] + max_r) ** 2]
    largest = max(max_r, float(blockers[:, 2].max()) if len(blockers) else 0.)
    grid_cell = 2 * largest
    lower = np.minimum(low, blockers[:, :2].min(0)) if len(blockers) else low
    upper = np.maximum(high, blockers[:, :2].max(0)) if len(blockers) else high
    span = upper - lower
    while True:
        nx, ny = (int(math.floor(float(v) / grid_cell)) + 1 for v in span)
        if nx * ny <= max_grid_bins:
            break
        grid_cell *= 2
    kernel = _packing_kernel
    if backend == "numba":
        global _NUMBA_KERNEL
        if _NUMBA_KERNEL is None:
            try:
                from numba import njit
            except ImportError as error:
                raise ImportError("Numba backend requested but unavailable; use numpy or the existing optional environment") from error
            # No fastmath: exact acceptance must agree with the NumPy/Python path.
            _NUMBA_KERNEL = njit(cache=False, fastmath=False)(_packing_kernel)
        kernel = _NUMBA_KERNEL
    reasons = kernel(batch.xy, batch.radius, blockers, lower, grid_cell, nx, ny)
    reasons.setflags(write=False)
    return batch, reasons, dict(backend=backend, grid_bins=nx * ny, grid_shape=[nx, ny],
                               grid_cell_size=grid_cell, relevant_original_blockers=len(blockers))


@dataclass(frozen=True)
class Catalog:
    grains: GrainArrays
    rejected_ids: np.ndarray
    rejection_reason: np.ndarray
    provenance: dict
    report: dict


def build_catalog(spec: CatalogSpec, prototypes: Sequence[Prototype], original_blockers=(), *,
                  cell_order=None, backend="numpy") -> Catalog:
    candidates, stats = build_candidates(spec, prototypes, cell_order=cell_order)
    blockers = _blockers_array(original_blockers)
    candidates, reason, grid = pack_candidates(candidates, blockers, max_grid_bins=spec.max_grid_bins, backend=backend)
    grains = candidates.take(reason == 0)
    rejected_ids = candidates.ids[reason != 0].copy()
    rejection_reason = reason[reason != 0].copy()
    rejected_ids.setflags(write=False)
    rejection_reason.setflags(write=False)
    area = (spec.bounds[1] - spec.bounds[0]) * (spec.bounds[3] - spec.bounds[2])
    rows = []
    for i, p in enumerate(stats["prototypes"]):
        accepted = int(np.count_nonzero((grains.band == p.band) & (grains.source_id == p.source_id)))
        attempted = int(stats["catalog_attempts_by_prototype"][i])
        rows.append(dict(source_id=int(p.source_id), prototype_id=int(p.prototype_id), band=int(p.band),
                         target_physical_density_per_m2=float(p.density_per_m2),
                         expected_physical_count_in_scope=float(p.density_per_m2 * area),
                         full_cell_virtual_count=sum(map(int, stats["physical_counts"][:, i])),
                         virtual_count_in_scope=int(stats["virtual_in_scope_by_prototype"][i]),
                         fixed_catalog_thinning=float(spec.thinning_by_band[p.band]),
                         catalog_attempt_count=attempted, packed_catalog_count=accepted,
                         packing_shortfall=attempted - accepted,
                         achieved_display_catalog_density_per_m2=accepted / area))
    report = dict(meaning="Bounded display catalog, not a claim of complete physical packing or rendered coverage",
                  scope_area_m2=area, world_cell_count=len(stats["cells"]),
                  full_cell_virtual_count=sum(map(int, stats["physical_counts"].flat)),
                  virtual_count_in_scope=int(stats["virtual_in_scope_by_prototype"].sum()),
                  catalog_attempt_count=len(candidates), packed_catalog_count=len(grains),
                  original_blocker_rejections=int(np.count_nonzero(reason == 1)),
                  catalog_packing_rejections=int(np.count_nonzero(reason == 2)),
                  target_physical_density_per_m2=sum(float(p.density_per_m2) for p in stats["prototypes"]),
                  achieved_display_catalog_density_per_m2=len(grains) / area,
                  prototypes=rows, packing=grid)
    provenance = dict(algorithm=ALGORITHM, catalog_epoch=spec.catalog_epoch,
                      source_pins=dict(sorted(spec.source_pins.items())), seed=int(spec.seed),
                      world_origin=[0., 0.], cell_size=float(spec.cell_size), bounds=list(map(float, spec.bounds)),
                      thinning_by_band={str(k): float(v) for k, v in sorted(spec.thinning_by_band.items())},
                      prototypes=[dict(source_id=int(p.source_id), prototype_id=int(p.prototype_id), band=int(p.band),
                                       density_per_m2=float(p.density_per_m2), radius=float(p.radius)) for p in stats["prototypes"]],
                      original_blocker_count=len(blockers),
                      original_blockers_sha256=hashlib.sha256(blockers.astype("<f8").tobytes()).hexdigest(),
                      canonical_order="ascending numeric band, ascending uint64 candidate ID",
                      id_tuple="seed, band, source_id, absolute cell_x, absolute cell_y, physical ordinal",
                      no_geometry_scaling=True)
    provenance["catalog_fingerprint_sha256"] = hashlib.sha256(json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return Catalog(grains, rejected_ids, rejection_reason, provenance, report)


def select_view_indices(grains: GrainArrays, visibility, lod_probability=1., *, max_instances=None):
    """Pure visibility + per-ID LOD threshold + deterministic priority hard cap.

    Uncapped increasing probabilities produce nested selections. A changed hard
    cap or visibility may change membership, never a shared ID's payload. Output
    retains catalog order. This function cannot refill rejected candidate IDs.
    """
    visible = np.asarray(visibility)
    if visible.dtype.kind != "b" or visible.shape != (len(grains),):
        raise ValueError("visibility must be a boolean vector aligned to the packed catalog")
    probability = np.asarray(lod_probability, dtype=np.float64)
    if probability.shape not in ((), (len(grains),)) or not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError("lod_probability must be scalar or aligned finite probabilities in [0,1]")
    chosen = np.flatnonzero(visible & (grains.priority < probability))
    if max_instances is not None:
        max_instances = _integer(max_instances, "max_instances", 0, _I64_MAX)
        if len(chosen) > max_instances:
            rank = np.lexsort((grains.ids[chosen], grains.cap_priority[chosen]))
            chosen = np.sort(chosen[rank[:max_instances]])
    chosen.setflags(write=False)
    return chosen


def select_view(grains: GrainArrays, visibility, lod_probability=1., *, max_instances=None):
    """Return unchanged grain payload for select_view_indices; selection never repacks."""
    return grains.take(select_view_indices(grains, visibility, lod_probability, max_instances=max_instances))


def lod_fraction(diameter_px, factor=1.):
    """Original .25–1 equivalent-pixel smoothstep; no geometry-size changes."""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("factor must be positive and finite")
    diameter_px = np.asarray(diameter_px, dtype=np.float64)
    if not np.isfinite(diameter_px).all() or np.any(diameter_px < 0):
        raise ValueError("diameter_px must be finite and nonnegative")
    t = np.clip((diameter_px / factor - .25) / .75, 0., 1.)
    return t * t * (3 - 2 * t)
