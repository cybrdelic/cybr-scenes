# Compact foreground grain consistency extension

This checkpoint extends the previously inspected DQ macro into a fixed 23.664 m² foreground support domain: X −7.00 to −3.52 m, Y 4.70 to 11.50 m. The full road scene is larger. This is not a claim that all distant terrain has explicit particle coverage.

## What is fixed before a camera exists

- The original physical geometry, 64-chip/grit mapping, 64-sand bank and metric sizes.
- Stable IDs from seed, prototype/source ID, absolute world cell and physical ordinal.
- XY and yaw. XY is converted to the same float32 storage convention before terrain contact.
- Coarse-to-fine packing with a strict enclosing-disk overlap predicate. The radius-tier implementation changes only broad-phase indexing. Small cases and the entire retained macro have bitwise-equal collision decisions.
- The exact retained macro's roles, positions and spent volume remain unchanged. Its bodies block additional placement.
- Outside-world deposited/static roles use complete stock cells and independent keyed draws. Their finite volume and exposed-area proxies spend only the residual after the frozen macro debit.

Only then may camera footprint, frustum and a stable-rank rendering budget select a subset. Contact is a pure evaluation from the fixed source triangle field, ID, prototype, yaw and frozen role. Changing the view cannot reallocate stock or move a surviving body.

## Artifacts and execution order

1. Preserve ACTUAL_CATALOG.npz and its original source/metadata; do not regenerate over the delivered version.
2. Run check_radius_tiers.py under the existing CPU/RSS guard. It validates the exact broad-phase replacement.
3. Run build_full_compact_tiered.py once. It refuses an already-completed output. FULL_ROAD_PACKING_STATUS.npz records two bits per virtual candidate. Incomplete progress snapshots are not valid role inputs.
4. Run prepare_full_ledger.py. It replays the original macro allocation exactly, debits that ledger, and independently counts every additional supported candidate.
5. Run roles/build_world_roles.py. Disjoint complete stock-cell bands freeze the outside roles and their selected ledgers. It never takes a camera.
6. Run export_view_projections.py with Blender to read the frozen camera and produce exact projection parameters.
7. Run prepare_world_view.py --view normal_2000 or --view macro_1800. This is a numerical-only, bounded selection/contact phase, separate from Blender's rendering memory.
8. Run prepare_world_render.py for the same view, then the existing qualified current_cache_source/cache_driver.py with after_da_hook.py as the geometry_soil_normals_db late hook. Each heavy phase acquires/releases the shared landscape lock independently.

The prepared cache/input tree from the retained DM/DH source is required. The archive is an additive source checkpoint, not a self-contained fresh-checkout road build. Exact file pins and Library dependencies accompany the delivery manifest. A fresh full-chain rebuild has not been established by the compact numerical tests.

## Physical and visual limits

These are nonvalidated display-stock proxies. Nearest-origin stock cells, enclosing disks, planar exposure targets, historical overburden and the camera footprint rule do not constitute a resolved physical sediment simulation. Static grains and deposited representatives remain distinct. The old macro's small stochastic area overshoot is recorded; new residual area is a hard cap.

The grain geometry is not enlarged for distant visibility. Subpixel material maps provide an averaged response; exact optical no-double-counting between maps and visible geometry is not established. Culling follows the inherited origin-based contract, so a grain crossing the frame edge may be omitted if its origin is outside. A rendering budget may change subset membership, but common IDs must retain identical pose and role.

The first whole-world collision implementation reached its 900-second guard; no completed result was asserted. The tiered implementation completed the same intended domain in 279 seconds at about 1,479 MiB. Numerical consistency is not, by itself, evidence of a visible scene-quality improvement. Actual matched renders must be inspected separately.
