"""Build only finite outside-world role bits, before any camera/view selection.

Pure NumPy band core with dependency-injected Reader/Support for tiny tests.
The CLI uses exact current source-triangle support and immutable packed inputs.
No full XYZ catalog, Blender, solver rerun, or frozen-macro changes are produced.
This is NONVALIDATED display-stock accounting, not new transport physics.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

try:
    from .transported_grain_exposure_dq import (
        ExposureConfig, KEYED_ROLE_VERSION, _axis, allocate_transported_grains)
except ImportError:
    from transported_grain_exposure_dq import (
        ExposureConfig, KEYED_ROLE_VERSION, _axis, allocate_transported_grains)

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent
STORAGE_SCHEMA = 'dq-full-virtual-serial-role1-v1'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _serials(serial, virtual_count):
    serial = np.asarray(serial)
    if serial.ndim != 1 or serial.dtype != np.dtype(np.uint32):
        raise ValueError('serial must be a one-dimensional uint32 array')
    if len(serial) and int(serial.max()) >= virtual_count:
        raise ValueError('serial exceeds the original full virtual serial map')
    return serial


def serial_bits_at(bits, serial):
    """Read uint32 full-virtual serial roles, least-significant bit first."""
    serial = np.asarray(serial, dtype=np.uint32)
    return ((bits[serial // np.uint32(8)] >> (serial % np.uint32(8))) & 1).astype(bool)


def set_serial_bits(bits, serial):
    """Set all serials correctly even when many indices share one byte.

    Fancy-indexed |= loses repeated byte-index updates. The ufunc.at reduction
    is intentional and tested, including repeated serials and byte boundaries.
    """
    serial = np.asarray(serial, dtype=np.uint32)
    masks = (np.uint32(1) << (serial % np.uint32(8))).astype(np.uint8)
    np.bitwise_or.at(bits, serial // np.uint32(8), masks)


def nearest_stock_cells(xy, x, y, dx, dy):
    """Exactly the allocator's inclusive support and nearest-origin convention."""
    inside = ((xy[:, 0] >= x[0]) & (xy[:, 0] <= x[-1])
              & (xy[:, 1] >= y[0]) & (xy[:, 1] <= y[-1]))
    ix = np.floor(np.clip((xy[:, 0] - x[0]) / dx + .5, 0, len(x) - 1)).astype(np.int64)
    iy = np.floor(np.clip((xy[:, 1] - y[0]) / dy + .5, 0, len(y) - 1)).astype(np.int64)
    return inside, iy, ix


def _grid_array(budget, key, shape, nonnegative=True):
    value = np.asarray(budget[key], dtype=float)
    if value.shape != shape or not np.isfinite(value).all():
        raise ValueError(f'{key} must be finite with shape {shape}')
    if nonnegative and np.any(value < 0):
        raise ValueError(f'{key} must be nonnegative')
    return value


@dataclass
class WorldRoles:
    role1: np.ndarray
    selected_volume: np.ndarray
    selected_area: np.ndarray
    selected_count: np.ndarray
    processed_counts: np.ndarray
    processed_rows: np.ndarray
    receipt: dict


def build_roles(reader, support, budget, *, rows_per_band=4,
                max_batch_candidates=2_000_000, config=None, progress=None):
    """Process each stock cell once with all its additional accepted candidates.

    reader.band(ylo,yhi) returns unviewed accepted outside-world candidates with
    serial/id/xy/prototype (yaw may also be present). Its immutable full virtual
    map determines role-bit positions. support.local_fields samples actual source
    triangles, and support.arr supplies unchanged metric prototype metadata.
    budget is WORLD_ROLE_BUDGET.npz content: the independent complete_counts
    manifest and original full-grid fields plus already-debited macro residuals.

    All nearest stock rows, including empty rows, must be completed exactly once.
    Query padding only ensures boundary candidates are available: exact nearest
    stock-cell iy is the sole ownership rule. Outside-grid points stay static.
    """
    if not isinstance(rows_per_band, int) or not 1 <= rows_per_band <= 32:
        raise ValueError('rows_per_band must be an integer in [1,32]')
    if not isinstance(max_batch_candidates, int) or max_batch_candidates < 1:
        raise ValueError('max_batch_candidates must be a positive integer')
    cfg = config or ExposureConfig(availability_mode='surviving_deposit_stock')
    x, dx = _axis(budget['x'], 'x')
    y, dy = _axis(budget['y'], 'y')
    # _axis derives the same 12-significant-digit spacing as the existing
    # allocator; the pinned .05m grid therefore matches prepare_full_ledger.
    if not np.array_equal(support.x, x) or not np.array_equal(support.y, y):
        raise ValueError('Support axes differ from the immutable budget axes')
    shape = (len(y), len(x))
    cells3 = shape + (3,)
    available = _grid_array(budget, 'available', cells3)
    net = _grid_array(budget, 'cover_grid', shape, nonnegative=False)
    original_volume = _grid_array(budget, 'original_budget', cells3)
    original_area = _grid_array(budget, 'original_target', cells3)
    macro_volume = _grid_array(budget, 'macro_spent_volume', cells3)
    macro_area = _grid_array(budget, 'macro_spent_area', cells3)
    remaining_volume = _grid_array(budget, 'remaining_volume', cells3)
    remaining_area = _grid_array(budget, 'remaining_area', cells3)
    if np.any(macro_volume > original_volume):
        raise ValueError('Frozen macro volume already exceeds original display budget')
    if not np.array_equal(remaining_volume, np.maximum(original_volume - macro_volume, 0)):
        raise ValueError('remaining_volume does not equal the fixed macro debit')
    if not np.array_equal(remaining_area, np.maximum(original_area - macro_area, 0)):
        raise ValueError('remaining_area does not equal the fixed macro area debit')
    expected = np.asarray(budget['complete_counts'])
    if (expected.shape != shape or expected.dtype.kind not in 'iu'
            or np.any(expected < 0)):
        raise ValueError('complete_counts must be a full-grid nonnegative integer manifest')
    virtual_count = int(reader.map.virtual_count)
    if not 0 <= virtual_count <= np.iinfo(np.uint32).max:
        raise ValueError('Full virtual count must fit uint32 serial indexing')
    if int(expected.sum()) > virtual_count:
        raise ValueError('Manifest contains more candidates than the full virtual map')
    role1 = np.zeros((virtual_count + 7) // 8, dtype=np.uint8)
    seen_serials = np.zeros_like(role1)
    selected_volume = np.zeros(cells3)
    selected_area = np.zeros(cells3)
    selected_count = np.zeros(cells3, dtype=np.int64)
    processed_counts = np.zeros(shape, dtype=np.int64)
    processed_rows = np.zeros(len(y), dtype=bool)
    metadata = {key: np.asarray(support.arr(key)) for key in (
        'flow_class', 'volume', 'diameter', 'footprint', 'minimum', 'maximum', 'offset')}
    nproto = len(metadata['volume'])
    if any(value.shape != (nproto,) for value in metadata.values()):
        raise ValueError('Prototype metadata must have one scalar per original prototype')
    bounds = np.c_[metadata['minimum'], metadata['maximum']]
    # Cover storage quantization and float evaluation at row boundaries. This
    # changes retrieval only; allocation uses exact nearest-cell ownership.
    scale = np.float32(max(1., float(np.max(np.abs(y)))))
    query_padding = max(4 * abs(float(np.spacing(scale))), dy * 1e-9)
    bands = []
    started = time.monotonic()
    for first in range(0, len(y), rows_per_band):
        stop = min(first + rows_per_band, len(y))
        if processed_rows[first:stop].any():
            raise AssertionError('A stock row would be processed more than once')
        expected_band_count = int(expected[first:stop].sum())
        if expected_band_count > max_batch_candidates:
            raise ValueError(f'Band [{first},{stop}) manifest has {expected_band_count} '
                             f'candidates, exceeding bounded limit {max_batch_candidates}; '
                             'reduce rows_per_band before decoding')
        lo = max(float(y[0]), float(y[0] + (first - .5) * dy)) - query_padding
        hi = min(float(y[-1]), float(y[0] + (stop - .5) * dy)) + query_padding
        batch = reader.band(lo, hi)
        serial = _serials(batch['serial'], virtual_count)
        raw_count = len(serial)
        if raw_count > max_batch_candidates:
            raise ValueError(f'Band [{first},{stop}) returned {raw_count} candidates, '
                             f'exceeding bounded limit {max_batch_candidates}; reduce rows_per_band')
        xy = np.asarray(batch['xy'], dtype=float)
        ids = np.asarray(batch['id'])
        pi = np.asarray(batch['prototype'])
        if xy.shape != (raw_count, 2) or not np.isfinite(xy).all():
            raise ValueError('Reader XY must be finite with shape (N,2)')
        if ids.shape != (raw_count,) or ids.dtype != np.dtype(np.uint64):
            raise ValueError('Reader ID must be uint64 with shape (N,)')
        if (pi.shape != (raw_count,) or pi.dtype.kind not in 'iu'
                or np.any(pi < 0) or np.any(pi >= nproto)):
            raise ValueError('Reader prototype must index the unchanged source bank')
        inside, iy, ix = nearest_stock_cells(xy, x, y, dx, dy)
        owner = inside & (iy >= first) & (iy < stop)
        serial, xy, ids, pi = serial[owner], xy[owner], ids[owner], pi[owner]
        iy, ix = iy[owner], ix[owner]
        del batch, inside, owner
        if len(np.unique(serial)) != len(serial) or serial_bits_at(seen_serials, serial).any():
            raise ValueError('Duplicate full virtual serial in the fixed-world allocation')
        counts = np.bincount(iy * len(x) + ix, minlength=shape[0] * shape[1]).reshape(shape)
        # Unlike the allocator's included-cell guard, this checks every cell in
        # the owned band, including cells accidentally omitted by the reader.
        if not np.array_equal(counts[first:stop], expected[first:stop]):
            raise ValueError(f'Missing/extra complete-cell candidates in stock rows [{first},{stop})')
        if counts[:first].any() or counts[stop:].any():
            raise AssertionError('Exact nearest-cell ownership escaped the current band')
        if len(serial):
            height, cover, _ = support.local_fields(xy)
            height, cover = np.asarray(height, float), np.asarray(cover, float)
            if height.shape != (len(serial),) or cover.shape != (len(serial),):
                raise ValueError('Exact source support fields must match candidate count')
            offset = metadata['offset'][pi]
            # Exactly the existing legacy builder's storage/reference equation.
            before = (height.astype('f4').astype(float) - offset).astype('f4')
            final_surface = before.astype(float) + offset
            ans = allocate_transported_grains(
                xy_m=xy, flow_class=metadata['flow_class'][pi],
                solid_volume_m3=metadata['volume'][pi], diameter_m=metadata['diameter'][pi],
                footprint_area_m2=metadata['footprint'][pi], local_z_bounds_m=bounds[pi],
                final_surface_m=final_surface, x_m=x, y_m=y,
                retained_deposit_by_class_m=available, net_deposit_m=net,
                local_net_deposit_m=cover, config=cfg, candidate_ids=ids,
                remaining_solid_budget_by_cell_class_m3=remaining_volume,
                remaining_planar_area_target_by_cell_class_m2=remaining_area,
                complete_stock_cell_counts=expected)
            # Disjoint owned cells mean addition must never combine allocations
            # from a previous band; full-grid budget/remaining arrays are ignored.
            occupied = (ans.selected_count_by_cell_class > 0).any(axis=2)
            if occupied[:first].any() or occupied[stop:].any():
                raise AssertionError('Allocator selected a cell outside its owned rows')
            selected_volume += ans.selected_solid_volume_by_cell_class_m3
            selected_area += ans.exposed_planar_area_proxy_by_cell_class_m2
            selected_count += ans.selected_count_by_cell_class
            set_serial_bits(role1, serial[ans.transported])
            band_selected = int(ans.transported.sum())
            del ans, height, cover, offset, before, final_surface
        else:
            band_selected = 0
        set_serial_bits(seen_serials, serial)
        processed_counts[first:stop] = counts[first:stop]
        processed_rows[first:stop] = True
        report = dict(first_stock_row=first, stop_stock_row=stop,
                      retrieved_candidates=raw_count, owned_candidates=len(serial),
                      selected_count=band_selected, elapsed_seconds=time.monotonic() - started)
        bands.append(report)
        if progress:
            progress(report)
    if not processed_rows.all() or not np.array_equal(processed_counts, expected):
        raise AssertionError('Missing stock rows or candidates in completed fixed-world allocation')
    if np.any(selected_volume > remaining_volume) or np.any(selected_area > remaining_area):
        raise AssertionError('Additional selected display stock exceeds the frozen residual caps')
    if np.any(selected_volume < 0) or np.any(selected_area < 0):
        raise AssertionError('Negative display stock allocation')
    unused_volume = remaining_volume - selected_volume
    unused_area = remaining_area - selected_area
    bit_counts = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(axis=1).astype(np.int64)
    popcount = int(np.dot(np.bincount(role1, minlength=256), bit_counts))
    if popcount != int(selected_count.sum()):
        raise AssertionError('Role bitset and selected cell ledger disagree')
    if np.any(role1 & ~seen_serials):
        raise AssertionError('Role bits outside processed supported-grid candidates')
    receipt = dict(
        schema=STORAGE_SCHEMA, keyed_role_version=KEYED_ROLE_VERSION,
        status='Fixed full-world outside roles allocated before view selection',
        roles_ready=True,
        validation='NONVALIDATED display-stock accounting, not new transport physics',
        config=asdict(cfg), virtual_count=virtual_count, role_bit_order='little within each byte',
        role_index='original uint32 full virtual serial; not accepted-candidate rank',
        role_bytes=int(role1.nbytes), role_sha256=hashlib.sha256(role1.tobytes()).hexdigest(),
        grid_shape_yx=list(shape), stock_spacing_xy_m=[dx, dy], rows_per_band=rows_per_band,
        max_batch_candidates=max_batch_candidates,
        maximum_retrieved_batch_candidates=max((b['retrieved_candidates'] for b in bands), default=0),
        inside_grid_candidates_processed=int(processed_counts.sum()), selected_count=popcount,
        all_stock_rows_processed_once=bool(processed_rows.all()),
        complete_count_manifest_matched=True, exact_source_triangle_support=True,
        final_surface_equation='float64(float32(float64(float32(height)) - offset)) + offset',
        physical_placement_and_contact_deferred=True,
        new_volume_by_class_m3=selected_volume.sum((0, 1)).tolist(),
        new_area_by_class_m2=selected_area.sum((0, 1)).tolist(),
        residual_volume_cap_by_class_m3=remaining_volume.sum((0, 1)).tolist(),
        residual_area_cap_by_class_m2=remaining_area.sum((0, 1)).tolist(),
        unused_volume_by_class_m3=unused_volume.sum((0, 1)).tolist(),
        unused_area_by_class_m2=unused_area.sum((0, 1)).tolist(),
        maximum_volume_cap_exceedance_m3=float(np.maximum(selected_volume - remaining_volume, 0).max(initial=0)),
        maximum_area_cap_exceedance_m2=float(np.maximum(selected_area - remaining_area, 0).max(initial=0)),
        frozen_macro_area_overshoot_by_class_m2=np.maximum(macro_area - original_area, 0).sum((0, 1)).tolist(),
        outside_grid_role_policy='always static (zero role bit)',
        bands=bands, elapsed_seconds=time.monotonic() - started,
        limits=[
            'Count manifest is an independent caller-supplied completeness guard, not authenticity proof.',
            'Original macro roles, poses, and spent ledger are immutable and excluded from new candidates.',
            'No full XYZ population is written; exact contact and placement are deferred to read-only view evaluation.',
            'Nearest-origin cells, top mixtures, and projected area remain art-directed display proxies.',
        ])
    return WorldRoles(role1, selected_volume, selected_area, selected_count,
                      processed_counts, processed_rows, receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows-per-band', type=int, default=4)
    parser.add_argument('--max-batch-candidates', type=int, default=2_000_000)
    parser.add_argument('--overwrite', action='store_true', help='replace only this builder\'s existing WORLD_ROLES outputs')
    args = parser.parse_args(argv)
    output_npz, output_json = HERE / 'WORLD_ROLES.npz', HERE / 'WORLD_ROLES.json'
    if not args.overwrite and (output_npz.exists() or output_json.exists()):
        parser.error('WORLD_ROLES output exists; use --overwrite explicitly to replace it')
    inputs = {name: WORLD / name for name in (
        'WORLD_ROLE_BUDGET.npz', 'WORLD_ROLE_BUDGET.json',
        'FULL_ROAD_PACKING_STATUS.npz', 'FULL_ROAD_PACKING_STATUS.json',
        'ACTUAL_CATALOG.npz', 'ACTUAL_CATALOG.json', 'FIXED_DISPLAY_BUDGET.npz',
        'COMPACT_ACTUAL_STATUS.npz')}
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        parser.error('Required immutable input is not ready: ' + ', '.join(missing))
    pins = {name: sha(path) for name, path in inputs.items()}
    sys.path.insert(0, str(WORLD))
    # Imports must not create bytecode beside immutable input modules.
    sys.dont_write_bytecode = True
    from stream_compact import Reader
    from support_context import Support
    reader, support = Reader(), Support(build_budget=False)
    budget_report = json.loads(inputs['WORLD_ROLE_BUDGET.json'].read_text())
    if not (budget_report.get('macro_roles_bitwise_equal') is True
            and budget_report.get('macro_volume_ledger_bitwise_equal') is True):
        raise ValueError('Budget preparation did not verify frozen macro replay')
    macro_report = json.loads(inputs['ACTUAL_CATALOG.json'].read_text())
    if macro_report['catalog_sha256'] != pins['ACTUAL_CATALOG.npz']:
        raise ValueError('Frozen macro catalog/report hash mismatch')
    if support.pins != budget_report['field_pins']:
        raise ValueError('Original field hashes changed since macro debit preparation')
    if (reader.report['frozen_macro_catalog_sha256'] != pins['ACTUAL_CATALOG.npz']
            or reader.report['spec']['source_pins']['frozen_macro_catalog'] != pins['ACTUAL_CATALOG.npz']
            or reader.report['spec']['source_pins']['frozen_macro_status'] != pins['COMPACT_ACTUAL_STATUS.npz']):
        raise ValueError('Full-world packing does not match the unchanged frozen macro inputs')
    if reader.report['status_file_sha256'] != pins['FULL_ROAD_PACKING_STATUS.npz']:
        raise ValueError('Full-world packing status file hash mismatch')
    with np.load(inputs['WORLD_ROLE_BUDGET.npz'], allow_pickle=False) as archive:
        budget = {name: archive[name] for name in archive.files}
    result = build_roles(reader, support, budget, rows_per_band=args.rows_per_band,
                         max_batch_candidates=args.max_batch_candidates,
                         progress=lambda r: print('ROLE_BAND', json.dumps(r), flush=True))
    if result.receipt['inside_grid_candidates_processed'] != budget_report['inside_budget_grid_candidates']:
        raise ValueError('Processed world count differs from independent macro-debit report')
    accepted = int(reader.report['report']['packed_catalog_count'])
    if accepted != budget_report['additional_world_candidates']:
        raise ValueError('Packing and budget manifest disagree on additional accepted count')
    if {name: sha(path) for name, path in inputs.items()} != pins:
        raise ValueError('An immutable input changed during allocation; output not published')
    result.receipt.update(input_sha256=pins, field_pins=support.pins,
                          additional_accepted_candidates=accepted,
                          outside_grid_remain_static=accepted - result.receipt['inside_grid_candidates_processed'],
                          input_inventory_changed=False,
                          frozen_macro_inputs_unchanged=True,
                          source_sha256={name: sha(HERE / name) for name in (
                              'build_world_roles.py', 'transported_grain_exposure_dq.py')})
    temporary = HERE / '.WORLD_ROLES.npz.partial'
    with temporary.open('wb') as stream:
        np.savez_compressed(stream, role1=result.role1, selected_volume=result.selected_volume,
                            selected_area=result.selected_area, selected_count=result.selected_count,
                            processed_counts=result.processed_counts, processed_rows=result.processed_rows,
                            virtual_count=np.array(result.receipt['virtual_count'], dtype=np.uint64))
    result.receipt['output_npz_sha256'] = sha(temporary)
    result.receipt['output_npz_bytes'] = temporary.stat().st_size
    temporary.replace(output_npz)
    report_tmp = HERE / '.WORLD_ROLES.json.partial'
    report_tmp.write_text(json.dumps(result.receipt, indent=2) + '\n')
    report_tmp.replace(output_json)
    print('WORLD_ROLES_DONE', json.dumps({k: v for k, v in result.receipt.items() if k != 'bands'}), flush=True)


if __name__ == '__main__':
    main()
