"""Experimental exact compact storage/packing for stable_catalog, not a new sampler.

Frozen stable_catalog.py supplies identity/hash/count semantics and is unchanged.
Only tiny fixtures have been qualified. No Blender or downstream Z/role allocation.
"""
from __future__ import annotations
from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
import resource
import time
import numpy as np
try:
    from . import stable_catalog as ref
except ImportError:
    import stable_catalog as ref

STORAGE_SCHEMA = "stable-grain-band-serial-status2-v1"
RECORD_DTYPE = np.dtype([("id", "<u8"), ("serial", "<u4")], align=False)
MiB = 1 << 20


@dataclass(frozen=True)
class CompactLimits:
    max_rss_bytes: int = 4480 * MiB
    safety_headroom_bytes: int = 256 * MiB
    max_original_blockers: int = 1_000_000
    max_reconstruction_candidates: int = 10_000
    max_chunk_size: int = 262_144

    def __post_init__(self):
        for f in fields(self):
            ref._integer(getattr(self, f.name), f.name, 1, (1 << 63) - 1)


def rss_bytes():
    """Linux current RSS, with peak-RSS fallback; never an OS hard limit."""
    try:
        with open("/proc/self/statm") as stream:
            return int(stream.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return peak_rss_bytes()


def peak_rss_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _array_sha256(array, dtype):
    """Hash canonical bytes without a full-array conversion or bytes duplicate."""
    h = hashlib.sha256()
    for start in range(0, len(array), 65536):
        block = np.ascontiguousarray(array[start:start + 65536], dtype=dtype)
        h.update(memoryview(block).cast("B"))
    return h.hexdigest()


def _readonly(array):
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class SerialMap:
    cells: np.ndarray
    prototypes: tuple
    group_cell: np.ndarray
    group_prototype: np.ndarray
    group_key: np.ndarray
    prefix: np.ndarray
    band_ranges: tuple             # (band, serial_start, serial_stop)
    full_count_by_prototype: np.ndarray

    @property
    def virtual_count(self):
        return int(self.prefix[-1])

    @property
    def nbytes(self):
        return sum(getattr(self, f.name).nbytes for f in fields(self)
                   if isinstance(getattr(self, f.name), np.ndarray))


def build_serial_map(spec, prototypes, limits=CompactLimits()):
    records = tuple(ref._prototypes(spec, prototypes))
    if len(records) > 65536:
        raise ref.CatalogLimitError("compact prototype slots must fit uint16")
    x0, x1, y0, y1 = spec.bounds
    lo_x, lo_y = math.floor(x0 / spec.cell_size), math.floor(y0 / spec.cell_size)
    hi_x, hi_y = math.ceil(x1 / spec.cell_size), math.ceil(y1 / spec.cell_size)
    for coordinate in (lo_x, lo_y, hi_x, hi_y):
        ref._integer(coordinate, "absolute cell coordinate", -ref._I64_MAX, ref._I64_MAX)
    cell_count = (hi_x - lo_x) * (hi_y - lo_y)
    if cell_count > spec.max_cells:
        raise ref.CatalogLimitError("compact world cells exceed max_cells before allocation")
    groups = cell_count * len(records)
    if groups > spec.max_count_entries:
        raise ref.CatalogLimitError("compact prefix-map count exceeds max_count_entries")
    if cell_count > np.iinfo(np.int32).max:
        raise ref.CatalogLimitError("compact cell indices must fit int32")
    if spec.chunk_size > limits.max_chunk_size:
        raise ref.CatalogLimitError("chunk_size exceeds explicit compact chunk bound")
    estimated_map = cell_count * 48 + (groups + 1) * 24 + len(records) * 256
    if rss_bytes() + limits.safety_headroom_bytes + estimated_map > limits.max_rss_bytes:
        raise ref.CatalogLimitError("compact prefix-map allocation exceeds RSS admission bound")
    cells = ref.world_cells(spec)
    gp = np.empty(groups, dtype=np.uint16)
    gc = np.empty(groups, dtype=np.int32)
    keys = np.empty(groups, dtype=np.uint64)
    prefix = np.empty(groups + 1, dtype=np.uint64)
    prefix[0] = 0
    totals = np.zeros(len(records), dtype=np.int64)
    ranges, g, total = [], 0, 0
    for band in sorted({p.band for p in records}):
        first = total
        pp = [i for i, p in enumerate(records) if p.band == band]
        for c, cell in enumerate(cells):
            for p in pp:
                proto = records[p]
                count = ref.physical_count(spec.seed, proto, cell, spec.cell_size)
                total += count
                if total > spec.max_virtual_candidates or total > np.iinfo(np.uint32).max:
                    raise ref.CatalogLimitError("virtual count exceeds fixed work bound or uint32 serial capacity")
                gp[g], gc[g] = p, c
                keys[g] = ref._cell_key(spec.seed, proto.band, proto.source_id, int(cell[0]), int(cell[1]))
                prefix[g + 1] = total
                totals[p] += count
                g += 1
        ranges.append((int(band), first, total))
    return SerialMap(_readonly(cells), records, _readonly(gc), _readonly(gp),
                     _readonly(keys), _readonly(prefix), tuple(ranges), _readonly(totals))


def allocation_plan(spec, serial_map, blocker_count, limits=CompactLimits()):
    capacity = min(serial_map.virtual_count, spec.max_catalog_candidates)
    if capacity > np.iinfo(np.int32).max:
        raise ref.CatalogLimitError("accepted linked indices exceed int32 capacity")
    width = 1 if len(serial_map.prototypes) <= 256 else 2
    allocations = dict(records=capacity * RECORD_DTYPE.itemsize,
                       accepted_xy_prototype_next=capacity * (16 + width + 4),
                       status2=(serial_map.virtual_count + 3) // 4,
                       head_grids=spec.max_grid_bins * 8,
                       blocker_arrays_and_copies=blocker_count * 100,
                       chunk_scratch=spec.chunk_size * 256,
                       inplace_sort_reserve=16 * MiB)
    # The map is already resident in this baseline; avoid counting it twice.
    baseline = rss_bytes()
    estimate = baseline + limits.safety_headroom_bytes + sum(allocations.values())
    if estimate > limits.max_rss_bytes:
        raise ref.CatalogLimitError(f"compact allocation admission estimate {estimate} exceeds RSS bound {limits.max_rss_bytes}")
    return dict(baseline_rss_bytes=baseline, estimated_peak_rss_bytes=estimate,
                rss_bound_bytes=limits.max_rss_bytes, safety_headroom_bytes=limits.safety_headroom_bytes,
                allocations=allocations, virtual_count=serial_map.virtual_count,
                record_capacity=capacity, accepted_slot_capacity=capacity,
                accepted_prototype_bytes=width, serial_map_bytes=serial_map.nbytes,
                meaning="Conservative allocation admission estimate, not an OS-enforced RSS limit")


def _decode(serial_map, serial, cell_size, known_ids=None):
    serial = np.asarray(serial, dtype=np.uint32)
    group = np.searchsorted(serial_map.prefix, serial, side="right") - 1
    ordinal = serial.astype(np.uint64) - serial_map.prefix[group]
    slots = serial_map.group_prototype[group]
    cell = serial_map.cells[serial_map.group_cell[group]]
    ids = (ref._mix64(serial_map.group_key[group] ^ ref._mix64(ordinal ^ np.uint64(0xD807AA98A3030242)))
           if known_ids is None else np.asarray(known_ids, dtype=np.uint64))
    xy = np.column_stack(((cell[:, 0] + ref._uniform(ids, "x")) * cell_size,
                          (cell[:, 1] + ref._uniform(ids, "y")) * cell_size))
    return ids, xy, slots, cell, ordinal


def _eligible_records(spec, serial_map, capacity, group_order):
    records = np.empty(capacity, dtype=RECORD_DTYPE)
    inside_counts = np.zeros(len(serial_map.prototypes), dtype=np.int64)
    attempt_counts = np.zeros_like(inside_counts)
    low, high, largest, n = np.full(2, np.inf), np.full(2, -np.inf), 0., 0
    groups = len(serial_map.group_cell)
    if group_order is None:
        order = range(groups)
    else:
        order = np.asarray(group_order)
        if order.dtype.kind not in "iu" or order.shape != (groups,) or not np.array_equal(np.sort(order), np.arange(groups)):
            raise ValueError("group_order must permute every canonical serial group exactly once")
    x0, x1, y0, y1 = spec.bounds
    for g in order:
        p = int(serial_map.group_prototype[g])
        proto = serial_map.prototypes[p]
        first, last = int(serial_map.prefix[g]), int(serial_map.prefix[g + 1])
        for start in range(first, last, spec.chunk_size):
            serial = np.arange(start, min(start + spec.chunk_size, last), dtype=np.uint32)
            ids, xy, _, _, _ = _decode(serial_map, serial, spec.cell_size)
            if not np.isfinite(xy).all() or np.any(np.abs(xy) > ref._METRIC_LIMIT):
                raise ValueError("compact world coordinates outside safe float64 range")
            inside = (xy[:, 0] >= x0) & (xy[:, 0] < x1) & (xy[:, 1] >= y0) & (xy[:, 1] < y1)
            inside_counts[p] += np.count_nonzero(inside)
            keep = inside & (ref._uniform(ids, "thin") < spec.thinning_by_band[proto.band])
            k = int(np.count_nonzero(keep))
            if n + k > capacity:
                raise ref.CatalogLimitError("compact eligible records exceed fixed max_catalog_candidates")
            if k:
                records["id"][n:n+k], records["serial"][n:n+k] = ids[keep], serial[keep]
                low = np.minimum(low, xy[keep].min(0))
                high = np.maximum(high, xy[keep].max(0))
                largest = max(largest, float(proto.radius))
                attempt_counts[p] += k
                n += k
    # This view owns the full admitted capacity, without allocating a second copy.
    return records[:n], inside_counts, attempt_counts, low, high, largest


def validate_sorted_ids(records, chunk_size):
    """Check all eligible bands globally, using only a chunk-sized boolean temporary."""
    for start in range(1, len(records), chunk_size):
        stop = min(start + chunk_size, len(records))
        if np.any(records["id"][start:stop] == records["id"][start-1:stop-1]):
            raise ValueError("duplicate candidate ID or uint64 collision; refuse ambiguous catalog")


def _original_links(blockers, lower, grid_cell, nx, ny, heads, links):
    for j in range(len(blockers)):
        gx = min(nx - 1, max(0, int(math.floor((blockers[j, 0] - lower[0]) / grid_cell))))
        gy = min(ny - 1, max(0, int(math.floor((blockers[j, 1] - lower[1]) / grid_cell))))
        cell = gy * nx + gx
        links[j] = heads[cell]
        heads[cell] = j


def _pack_chunk(xy, slots, serials, radii, blockers, lower, grid_cell, nx, ny,
                original_head, original_next, accepted_head, accepted_next,
                accepted_xy, accepted_prototype, accepted_count, status, counts):
    for i in range(len(xy)):
        radius = radii[slots[i]]
        gx = min(nx - 1, max(0, int(math.floor((xy[i, 0] - lower[0]) / grid_cell))))
        gy = min(ny - 1, max(0, int(math.floor((xy[i, 1] - lower[1]) / grid_cell))))
        code = 1
        for stage in range(2):
            hit = False
            for yy in range(max(0, gy - 1), min(ny, gy + 2)):
                for xx in range(max(0, gx - 1), min(nx, gx + 2)):
                    cell = yy * nx + xx
                    j = original_head[cell] if stage == 0 else accepted_head[cell]
                    while j >= 0:
                        bx = blockers[j, 0] if stage == 0 else accepted_xy[j, 0]
                        by = blockers[j, 1] if stage == 0 else accepted_xy[j, 1]
                        br = blockers[j, 2] if stage == 0 else radii[accepted_prototype[j]]
                        dx, dy = xy[i, 0] - bx, xy[i, 1] - by
                        if dx * dx + dy * dy < (radius + br) ** 2:
                            hit = True
                            break
                        j = original_next[j] if stage == 0 else accepted_next[j]
                    if hit:
                        break
                if hit:
                    break
            if hit:
                code = stage + 2
                break
        if code == 1:
            cell = gy * nx + gx
            accepted_xy[accepted_count, 0] = xy[i, 0]
            accepted_xy[accepted_count, 1] = xy[i, 1]
            accepted_prototype[accepted_count] = slots[i]
            accepted_next[accepted_count] = accepted_head[cell]
            accepted_head[cell] = accepted_count
            accepted_count += 1
        serial = int(serials[i])
        status[serial >> 2] |= np.uint8(code << ((serial & 3) * 2))
        counts[slots[i], code - 1] += 1
    return accepted_count


_JIT = None


def _kernels(backend):
    if backend == "numpy":
        return _original_links, _pack_chunk
    if backend != "numba":
        raise ValueError("backend must be numpy or numba")
    global _JIT
    if _JIT is None:
        from numba import njit
        _JIT = (njit(cache=False, fastmath=False)(_original_links),
                njit(cache=False, fastmath=False)(_pack_chunk))
    return _JIT


def _pack_records(spec, serial_map, records, original_blockers, low, high, max_r, backend):
    status = np.zeros((serial_map.virtual_count + 3) // 4, dtype=np.uint8)
    counts = np.zeros((len(serial_map.prototypes), 3), dtype=np.int64)
    if not len(records):
        return status, counts, dict(backend=backend, grid_bins=0, relevant_original_blockers=0)
    delta = np.maximum(np.maximum(low - original_blockers[:, :2], original_blockers[:, :2] - high), 0)
    blockers = original_blockers[np.sum(delta * delta, axis=1) < (original_blockers[:, 2] + max_r) ** 2]
    largest = max(max_r, float(blockers[:, 2].max()) if len(blockers) else 0.)
    grid_cell = 2 * largest
    lower = np.minimum(low, blockers[:, :2].min(0)) if len(blockers) else low
    upper = np.maximum(high, blockers[:, :2].max(0)) if len(blockers) else high
    span = upper - lower
    while True:
        nx, ny = (int(math.floor(float(v) / grid_cell)) + 1 for v in span)
        if nx * ny <= spec.max_grid_bins:
            break
        grid_cell *= 2
    original_head = np.full(nx * ny, -1, dtype=np.int32)
    accepted_head = np.full(nx * ny, -1, dtype=np.int32)
    original_next = np.empty(len(blockers), dtype=np.int32)
    accepted_next = np.empty(len(records), dtype=np.int32)
    accepted_xy = np.empty((len(records), 2), dtype=np.float64)
    accepted_prototype = np.empty(len(records), dtype=np.uint8 if len(serial_map.prototypes) <= 256 else np.uint16)
    radii = np.array([p.radius for p in serial_map.prototypes], dtype=np.float64)
    initialize, pack = _kernels(backend)
    initialize(blockers, lower, grid_cell, nx, ny, original_head, original_next)
    accepted_count = 0
    # Serial intervals identify bands without an extra per-record band array.
    for _, first, last in serial_map.band_ranges:
        for start in range(0, len(records), spec.chunk_size):
            block = records[start:start + spec.chunk_size]
            member = (block["serial"] >= first) & (block["serial"] < last)
            if not np.any(member):
                continue
            serial, ids = block["serial"][member], block["id"][member]
            _, xy, slots, _, _ = _decode(serial_map, serial, spec.cell_size, known_ids=ids)
            accepted_count = pack(xy, slots, serial, radii, blockers, lower, grid_cell, nx, ny,
                                  original_head, original_next, accepted_head, accepted_next,
                                  accepted_xy, accepted_prototype, accepted_count, status, counts)
    if accepted_count != int(counts[:, 0].sum()):
        raise AssertionError("compact accepted counter mismatch")
    return status, counts, dict(backend=backend, grid_bins=nx * ny, grid_shape=[nx, ny],
                               grid_cell_size=grid_cell, relevant_original_blockers=len(blockers))


@dataclass(frozen=True)
class CompactCatalog:
    spec: ref.CatalogSpec
    serial_map: SerialMap
    status2: np.ndarray
    provenance: dict
    report: dict
    storage: dict
    limits: CompactLimits

    def status_at(self, serials):
        serials = np.asarray(serials)
        if serials.dtype.kind not in "iu" or np.any(serials < 0) or np.any(serials >= self.serial_map.virtual_count):
            raise ValueError("serials must reference this compact catalog's virtual population")
        serials = serials.astype(np.uint64)
        return (self.status2[(serials >> np.uint64(2)).astype(np.intp)] >> ((serials & np.uint64(3)) * np.uint64(2)).astype(np.uint8)) & np.uint8(3)


def _metadata(spec, serial_map, blockers, inside, attempts, counts, grid):
    area = (spec.bounds[1] - spec.bounds[0]) * (spec.bounds[3] - spec.bounds[2])
    rows = []
    for i, p in enumerate(serial_map.prototypes):
        accepted = int(counts[i, 0])
        rows.append(dict(source_id=int(p.source_id), prototype_id=int(p.prototype_id), band=int(p.band),
                         target_physical_density_per_m2=float(p.density_per_m2),
                         expected_physical_count_in_scope=float(p.density_per_m2 * area),
                         full_cell_virtual_count=int(serial_map.full_count_by_prototype[i]),
                         virtual_count_in_scope=int(inside[i]), fixed_catalog_thinning=float(spec.thinning_by_band[p.band]),
                         catalog_attempt_count=int(attempts[i]), packed_catalog_count=accepted,
                         packing_shortfall=int(attempts[i]) - accepted,
                         achieved_display_catalog_density_per_m2=accepted / area))
    report = dict(meaning="Bounded display catalog, not a claim of complete physical packing or rendered coverage",
                  scope_area_m2=area, world_cell_count=len(serial_map.cells), full_cell_virtual_count=serial_map.virtual_count,
                  virtual_count_in_scope=int(inside.sum()), catalog_attempt_count=int(attempts.sum()),
                  packed_catalog_count=int(counts[:, 0].sum()), original_blocker_rejections=int(counts[:, 1].sum()),
                  catalog_packing_rejections=int(counts[:, 2].sum()),
                  target_physical_density_per_m2=sum(float(p.density_per_m2) for p in serial_map.prototypes),
                  achieved_display_catalog_density_per_m2=int(counts[:, 0].sum()) / area, prototypes=rows, packing=grid)
    provenance = dict(algorithm=ref.ALGORITHM, catalog_epoch=spec.catalog_epoch,
                      source_pins=dict(sorted(spec.source_pins.items())), seed=int(spec.seed),
                      world_origin=[0., 0.], cell_size=float(spec.cell_size), bounds=list(map(float, spec.bounds)),
                      thinning_by_band={str(k): float(v) for k, v in sorted(spec.thinning_by_band.items())},
                      prototypes=[dict(source_id=int(p.source_id), prototype_id=int(p.prototype_id), band=int(p.band),
                                       density_per_m2=float(p.density_per_m2), radius=float(p.radius)) for p in serial_map.prototypes],
                      original_blocker_count=len(blockers),
                      original_blockers_sha256=_array_sha256(blockers, "<f8"),
                      canonical_order="ascending numeric band, ascending uint64 candidate ID",
                      id_tuple="seed, band, source_id, absolute cell_x, absolute cell_y, physical ordinal",
                      no_geometry_scaling=True)
    provenance["catalog_fingerprint_sha256"] = hashlib.sha256(json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return provenance, report


def build_compact_catalog(spec, prototypes, original_blockers=(), *, backend="numpy",
                          group_order=None, limits=CompactLimits()):
    started = time.monotonic()
    if backend not in ("numpy", "numba"):
        raise ValueError("backend must be numpy or numba")
    if len(original_blockers) > limits.max_original_blockers or len(original_blockers) > np.iinfo(np.int32).max:
        raise ref.CatalogLimitError("original blocker input exceeds explicit compact bound")
    serial_map = build_serial_map(spec, prototypes, limits)
    plan = allocation_plan(spec, serial_map, len(original_blockers), limits)
    blockers = ref._blockers_array(original_blockers)
    records, inside, attempts, low, high, max_r = _eligible_records(spec, serial_map, plan["record_capacity"], group_order)
    generated = time.monotonic()
    records.sort(order=["id", "serial"], kind="quicksort")
    validate_sorted_ids(records, spec.chunk_size)
    sorted_at = time.monotonic()
    status, counts, grid = _pack_records(spec, serial_map, records, blockers, low, high, max_r, backend)
    packed_at = time.monotonic()
    provenance, report = _metadata(spec, serial_map, blockers, inside, attempts, counts, grid)
    storage = dict(schema=STORAGE_SCHEMA, serial_order="numeric band, lexicographic absolute cell, source ID, physical ordinal",
                   status_encoding={"0": "outside scope or fixed thinning", "1": "accepted", "2": "original blocker", "3": "catalog blocker"},
                   status_bit_order="two low bits first, four virtual serials per byte",
                   prefix_sha256=_array_sha256(serial_map.prefix, "<u8"),
                   status_sha256=_array_sha256(status, "u1"),
                   persistent_array_bytes=serial_map.nbytes + status.nbytes,
                   memory_plan=plan, measured_process_peak_rss_bytes=peak_rss_bytes(),
                   seconds=dict(generation_and_mapping=generated - started, sort_and_duplicate_check=sorted_at - generated,
                                packing=packed_at - sorted_at, total=time.monotonic() - started),
                   downstream_Z_roles_burial_included=False)
    if storage["measured_process_peak_rss_bytes"] > limits.max_rss_bytes:
        raise ref.CatalogLimitError("observed process peak RSS exceeded compact limit; result rejected")
    return CompactCatalog(spec, serial_map, _readonly(status), provenance, report, storage, limits)


@dataclass(frozen=True)
class Reconstruction:
    grains: ref.GrainArrays
    serials: np.ndarray
    rejection_reason: np.ndarray       # 0 accepted, 1 original blocker, 2 catalog blocker


def reconstruct(compact, *, statuses=(1,), max_candidates=None):
    """Size-guarded canonical reconstruction; never silently materialize a full domain.

    statuses may select accepted (1), original rejection (2), catalog rejection (3).
    Reconstructing millions requires a separate explicitly bounded streaming client.
    """
    statuses = tuple(statuses)
    if not statuses or not set(statuses).issubset({1, 2, 3}):
        raise ValueError("reconstruction statuses must be a nonempty subset of 1,2,3")
    limit = compact.limits.max_reconstruction_candidates if max_candidates is None else ref._integer(max_candidates, "max_candidates", 0, compact.limits.max_reconstruction_candidates)
    count = sum(compact.report[k] for code, k in [(1, "packed_catalog_count"), (2, "original_blocker_rejections"), (3, "catalog_packing_rejections")] if code in statuses)
    if count > limit:
        raise ref.CatalogLimitError("reconstruction exceeds explicit materialization limit; use a separately bounded streaming client")
    estimate = rss_bytes() + compact.limits.safety_headroom_bytes + count * 256 + compact.spec.chunk_size * 64
    if estimate > compact.limits.max_rss_bytes:
        raise ref.CatalogLimitError("reconstruction allocation estimate exceeds RSS admission bound")
    serials = np.empty(count, dtype=np.uint32)
    codes = np.empty(count, dtype=np.uint8)
    n = 0
    for start in range(0, compact.serial_map.virtual_count, compact.spec.chunk_size):
        block = np.arange(start, min(start + compact.spec.chunk_size, compact.serial_map.virtual_count), dtype=np.uint32)
        status = compact.status_at(block)
        selected = np.isin(status, statuses)
        k = int(selected.sum())
        serials[n:n+k], codes[n:n+k] = block[selected], status[selected]
        n += k
    if n != count:
        raise ValueError("compact status bits disagree with stored reporting counts")
    ids, xy, slots, cells, ordinal = _decode(compact.serial_map, serials, compact.spec.cell_size)
    pp = compact.serial_map.prototypes
    batch = ref.GrainArrays(ids, xy, np.array([p.prototype_id for p in pp], "i4")[slots],
                            np.array([p.source_id for p in pp], "i8")[slots],
                            (ref._uniform(ids, "yaw") * math.tau).astype("f4"),
                            ref._uniform(ids, "lod"), ref._mix64(ids ^ np.uint64(ref._CHANNELS["cap"])), cells,
                            np.array([p.radius for p in pp], "f8")[slots],
                            np.array([p.band for p in pp], "i4")[slots], ordinal)
    order = np.lexsort((batch.ids, batch.band))
    return Reconstruction(batch.take(order), _readonly(serials[order]), _readonly(codes[order] - np.uint8(1)))
