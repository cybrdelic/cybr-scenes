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
the CYBR MATERIAL checkout at commit `85af551411994757395d6a490d8ae649cb25412e` containing the pinned files. Use a fresh output path:

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
