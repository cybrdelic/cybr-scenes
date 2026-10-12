# DQ finite display-stock roles

`transported_grain_exposure_dq.py` is a standalone NumPy-only extension of the
unchanged `low_ground_dp_native/runtime/src/transported_grain_exposure_dg.py`.
It does **display-stock accounting, not new validated transport physics**.
No Blender, terrain modification, solver rerun, RNG global state, geometry
scaling, or source-ledger edits are involved. Defaults and physical/role proxy
equations are retained; no new-options calls exactly match the DG allocator,
including every returned array and the entire receipt.

## Allocation API

Existing `ExposureConfig`, `ExposureResult`, `retained_top_proxy`, and
`allocate_transported_grains` interfaces are preserved. New optional keywords:

- `candidate_ids`: `(N,)`, **uint64**, unique persistent catalog IDs. With IDs,
  independent SplitMix64-derived `jitter`, `race`, and `fraction` channels replace
  the order/length-dependent generator. Sort is by nearest stock cell/class,
  weighted race, then unsigned ID. Changing constants requires a new
  `KEYED_ROLE_VERSION` (currently `dq-stock-role-v1`). Every nonnegative integer
  seed limb contributes; values above 64 bits are not silently truncated.
- `remaining_solid_budget_by_cell_class_m3`: `(ny,nx,3)`, finite nonnegative.
  Effective budget is `minimum(original physical display budget, supplied
  residual)`. Whole-body volume never overshoots it, including by one ULP.
- `remaining_planar_area_target_by_cell_class_m2`: `(ny,nx,3)`, finite
  nonnegative. Effective target is `minimum(original target, supplied residual)`.
  **Supplying this field makes it a hard area cap**. A footprint that does not
  fit is skipped; later smaller candidates can fit. No fractional roundup is
  permitted. Without this option the original soft target/stochastic final
  grain rule remains, allowing at most one footprint of overshoot per cell/class.
- `complete_stock_cell_counts`: `(ny,nx)`, nonnegative integer full-catalog
  candidate count manifest. Required whenever any new option is used. Every
  included cell must contain exactly the count recorded for that cell; all
  classes and unsupported candidates count. Whole omitted cells are allowed
  for batches. Outside-grid candidates never spend stock and are not counted.

Residual arrays do **not** replace sediment thickness in activation, top-mixture,
settling weights, or exposure. Those calculations use the unchanged original
retained deposit and net-deposit fields. Inputs are never mutated.

All returned budget/target arrays refer to the **full grid**. With supplied
residuals they are the effective residual caps, while the receipt records the
original full-grid totals too. Remaining volume is effective budget minus newly
selected volume. Remaining planar area can be computed as
`maximum(target_planar_area_proxy_by_cell_class_m2 -
exposed_planar_area_proxy_by_cell_class_m2, 0)`.

## Frozen macro + new population contract

1. Keep the existing macro IDs, roles, heights, poses, and already-spent ledger
   unchanged. Do not rerun keyed allocation over legacy macro roles: the new
   hash draws intentionally differ from the old order-dependent RNG stream.
2. Compute residual volume as `max(original budget - macro spent volume, 0)`
   and residual area as `max(original target - macro spent exposed area, 0)`.
   A previous soft-area overshoot means zero residual; it cannot be undone by
   the new allocator. Any already-overdrawn frozen ledger must be reported by
   the caller; this helper does not rewrite it or assert it was valid.
3. Exclude those frozen macro IDs from the new candidate population. Freeze
   full-world counts for that **new population** before any camera/LOD selection.
   Pin that manifest and catalog identity with the existing inputs. Duplicate
   IDs are checked within each call; global uniqueness and macro exclusion
   remain caller responsibilities across separate calls.
4. Process the new whole-world catalog in **disjoint complete stock-cell Y
   bands across the full X support**. Keep full fixed axes and full original
   deposit/net fields in every call, to preserve bilinear neighbors and index
   identity. Never split one stock cell among calls and never batch by class.
   The count manifest checks all classes together.
5. Sum only the **selected** per-cell ledgers across disjoint bands, then debit
   the fixed residual ledger once. Do not sum full-grid budget or remaining
   arrays returned by each batch; untouched cells are represented in every one.
6. Freeze newly selected roles and their embedding/positions. Camera selection
   is an indexing operation afterward, never an allocation input.

The count manifest is a caller-supplied **completeness guard, not an authenticity
proof**. It rejects partial included cells relative to the manifest. It cannot
detect a fabricated manifest generated from visible points, replacement of IDs
with equal counts, omission of whole bands from an ostensibly complete build,
or duplication of a cell in separate calls. The world build must validate band
coverage, no repeat cell processing, identity, and that the manifest predates
view selection. Changes to competitors **within the same cell** may legitimately
change a role; keyed randomness cannot make finite-stock competition disappear.

## Read-only display evaluation

`keyed_uniform(candidate_ids, seed, channel)` is public and accepts `'jitter'`,
`'race'`, or `'fraction'`. It may evaluate a camera subset or repeated IDs because
it makes no stock allocation. Draws are exact 53-bit `[0,1)` dyadics.

`keyed_extra_embedment_m(candidate_ids=..., local_effective_deposit_m=...,
 diameter_m=..., local_z_bounds_m=..., transported=frozen_role_mask,
 config=same_config)` reproduces the keyed allocator's extra embedding without
rerunning allocation. The frozen-role mask is optional; omitting it returns the
unmasked mathematical embedding, not an eligibility decision.

The effective local depth must come from the **same original field samples**:

- `surviving_deposit_stock`: the effective-depth output of `retained_top_proxy`
  on bilinearly sampled original retained classes, using the same active depth
  and top availability, then zero where surface/local-net is unsupported.
- `net_positive_only`: `minimum(local_retained_total,
  maximum(where(supported, local_net, 0), 0))`.

It must never be reconstructed from residual stock. This evaluator is for
**new keyed roles**, not for recomputing the frozen legacy macro population.
No cross-platform libm/NumPy bitwise guarantee is claimed for transcendental
role/embedding calculations; use the same pinned runtime for exact bytes.

## Validation

Run from this directory:

    python -m unittest -v test_transported_grain_exposure_dq.py

All fixtures contain at most 1,800 points. Tests cover exact DG compatibility in
both modes, large seeds and empty inputs; permutation including receipt equality;
complete Y-band allocation; unrelated cells; hard residual caps; original field
semantics; no input mutation; incomplete-cell/camera rejection; render-subset
embedding parity; RNG-stream prohibition; ID ties/high unsigned IDs; pinned hash
channel vectors; invalid inputs; and untouched original source hashes.

The original sources are pinned read-only:

- `transported_grain_exposure_dg.py` SHA-256:
  `0019380b537bf35309c25939b8fc1285e2a09036cea6a81e8024822bc788a587`
- `history_budget_dg.py` SHA-256:
  `18c5bc3b096c190ad889606508474e1ed24d3dc1823c9e0d46768a08e0410a98`

Nearest-origin bookkeeping, class mixtures, porosity, and planar footprints
remain nonvalidated display proxies. Whole-body/cell intersections, actual
transport trajectories, known vertical stratigraphy, disjoint optical coverage,
and exact no-double-counting against baked source response are not established.

## Bounded full-world role-bit builder

`build_world_roles.py` is import-safe and does not load real data until its CLI
is explicitly run. It consumes the finished `WORLD_ROLE_BUDGET.npz/json` and
`FULL_ROAD_PACKING_STATUS.npz/json` prepared by the upstream world build. Missing
inputs fail immediately; the builder never waits for or starts packing.

    python roles/build_world_roles.py

Run this from `stable_grains_dq`, under the parent build's existing lock. Defaults
are four stock rows (0.2 m on this grid) and a 2,000,000 candidate per-query limit.
`--rows-per-band` and `--max-batch-candidates` set explicit bounds; no automatic
camera/LOD clipping or silently truncated batches are permitted. The manifest
admission check runs before decoding each band, and the returned query size is
checked too. The supplied Reader internally decodes overlapping packing cells;
its transient scratch still depends on that Reader's implementation.

The core `build_roles(reader, support, budget, ...)`:

- Queries complete Y bands across the full X support, with conservative boundary
  padding, then filters by the allocator's **exact nearest-cell iy** ownership.
  Spacing comes from the same `_axis` routine as the allocator, so the prepared
  `.05 m` count convention stays unchanged. Inclusive outer grid endpoints are
  included; outside-grid bodies receive zero role bits.
- Verifies every owned cell's count, including cells accidentally missing from
  a query, against independent `complete_counts`. Marks every stock row once
  and rejects repeated virtual serials, including across separate bands.
- Uses `Support.local_fields` for exact original triangle height and cover.
  Its final-surface support input exactly preserves the legacy expression:
  `(height.astype('f4').astype(float) - offset).astype('f4').astype(float)
  + offset`. Unsupported source samples remain unsupported; no flat surface
  substitutes for real support. `Support.arr` supplies original metric metadata.
- Passes original full-grid deposits/net fields and fixed residual caps into the
  keyed allocator; aggregates selected ledgers only. Completed-band scratch is
  released before allocating the next band's roles.
- Stores one role bit at each original uint32 **full virtual serial**, never at
  an accepted-candidate rank. Byte packing is least-significant-bit first and
  uses `np.bitwise_or.at`, so multiple selected indices per byte are preserved.

Outputs are only `roles/WORLD_ROLES.npz` and `roles/WORLD_ROLES.json`:

- NPZ arrays: `role1` (uint8 packed bits), `selected_volume`, `selected_area`,
  `selected_count`, `processed_counts`, `processed_rows`, `virtual_count`.
- JSON success gate: `roles_ready: true`, `schema: "dq-full-virtual-serial-role1-v1"`,
  plus verified `output_npz_sha256`. Other receipt fields include the
  storage/version/bit-order contract, original input and frozen-macro
  hashes, field hashes, count/coverage checks, residual-cap accounting, already
  existing frozen-macro area overshoot, source hashes, and band progress.
- Physical XYZ placement/contact is intentionally deferred to read-only view
  evaluation. No full XYZ catalog is written. Frozen `ACTUAL_CATALOG` and all
  upstream inputs remain immutable; CLI checks input hashes again before output.
- Existing output requires `--overwrite`. Data is written through temporary
  files; the JSON receipt is published last. Consumers must require both files
  and verify the receipt's `output_npz_sha256` before using the role bits.

The builder keeps role and seen-serial bitsets, bounded band candidates, and
small full-grid ledgers. Counts/manifests and pinned input hashes are still
caller-provided provenance, not a new physical validation claim.

Additional tiny tests (220 candidates) compare whole allocation with 1/2/4/8-row
builds, including exact stock-row boundaries, outside-grid candidates, unsupported
source samples, immutable ledgers, missing complete cells, duplicate serials,
batch limits, stale macro debits, and multiple selected indices within one byte:

    python -m unittest -v test_build_world_roles.py test_transported_grain_exposure_dq.py

No real full-world build was executed as part of these tests.
