# Victorville DU5: opt-in soil improvement

This original procedural candidate is a useful material improvement over DR,
not photoreal completion. It preserves the AV mountain objects, CN chromatic
endpoints and CO22 daylight. The shrub trunk and large clast still need work.
The accepted DR source and output remain unchanged in the adjacent `dr` folder.

## Ownership

CYBR MATERIAL owns `source/granular_matrix.py` and its one authoritative JSON
profile. This folder only binds that material to the scene's depositional and
compaction fields. The scene also owns finite-stock redistribution, root collars
and shared basal wood geometry. `MATERIAL_DEPENDENCY.json` pins the exact owner
files; there is no copied hard-coded aggregate recipe here.

## Prepare and render

First prepare the adjacent DR source using its README. Point the following at
the CYBR MATERIAL checkout containing the pinned files. Use a fresh output path:

    python3 prepare_du5.py --material-root /path/to/cybr-material --output-root /path/to/du5-output --view normal

`--dr-root` can select another already prepared/admitted DR tree. `--view crop`
uses the exact 1300 × 680 foreground border of the native 2000 × 1334 camera.
`--view wide` changes only lens to 24 mm and remains subject to separate visual
review. It does not reroll the material or existing grain identities.

Use the DR guarded render invocation with the new output's `job.json` and
`runtime/pipeline/clean_render_landform_candidate.sh`. Retain the same shared
lock, CPUs 0 and 1, 4480 MiB sampled process-tree cap, 900-second stage bound,
jemalloc environment and at least 1 GiB free disk reserve. Preparation does
not render and does not modify the accepted DR files.

## Known limits

- Finite retained cap bulk is conserved; foundation cut/fill is area-weighted
  and zero net in float64, with float32 residual reported separately.
- The original 220,000 fine-grain identities, XY positions and metric meshes
  remain. Heights and static exposure change with the authored substrate.
- The matrix is optical shading relief, not newly created mineral inventory.
- Footprint filtering and roughness compensation are approximate, not a
  calibrated BRDF or a complete grain-packing/transport simulation.
- Basal wood flare is original authored form. It is not surveyed botany and
  does not enter sediment inventory accounting.
- Normal-context and wide-context quality are distinct from the useful crop
  improvement. Use recorded evidence; do not infer visual acceptance from tests.
- The experimental serialized DR cache failed its RGB control and is excluded.
  Always use the complete original DR assembly.

## Native integer pixel borders

For an exact camera crop, prefer job key `render_border_pixels` with four
integer edges `[xmin, xmax, ymin, ymax]` in the full projection's bottom-left
coordinate system. Upper edges are exclusive. For example, `[800, 1300, 0, 394]`
at 2000 × 1334 must produce 500 × 394 native pixels. Camera geometry, projection,
material scale and sample density are unchanged; no resizing is performed.

The version 2 helper derives float32 normalized RNA values from these integer
bounds, reads them back, and requires both float32 and double multiplication to
resolve to the same integer edges. A normalized Python value can otherwise round
just below an edge when stored by Blender, silently losing one row. Legacy
`render_border` jobs remain supported only when their ratios align to integer
edges; supplying both forms with conflicting bounds fails before rendering.

The preparer replaces only the exact source-hash-admitted version 1 AST handler.
Unknown or ambiguous renderer layouts fail. The helper is included in the
runtime source snapshot. With neither border key, the normal render path does
not invoke the helper. The tiny actual Cycles regression is
`tests/render_victorville_pixel_border_fixture.py`; recorded results are in
`PIXEL_BORDER_VALIDATION.json`. These checks qualify crop coordinates, not scene
realism.
