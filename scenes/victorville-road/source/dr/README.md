# Procedural Victorville road: DR source checkpoint

This is the original authored regional road scene used for the DR Cycles CPU
preview. It is a work in progress, not a surveyed reconstruction or an accepted
photoreal final. The road alignment and original AV mountain objects are retained.
The CN warm soil palette and CO22 side-daylight are the displayed candidates.
No reference photograph is used as a texture, heightfield or scan.

## What is included

- Original R5D mineral-grain and dense asphalt recipe dependencies, unchanged.
- The exact approved microbed input and physical-height source data.
- Scene grading, pavement/contact construction, shrub layout and source fields.
- Selected two-body DH shape correction and DM static fine-cap coupling.
- DR deterministic world identities and the exact 220,000-body normal-view subset.
- Source guards, semantic geometry admission, finite-stock records and builders.

No generated Blender scene or large generated texture bake is checked in.
DS and DT appearance experiments are excluded from the selected scene. Later
unsaved I work was lost and is not represented here. Older source modules retained
as dependencies do not become alternative selected defaults.

## Reproduce on Linux

Test environment: Blender 4.3.2, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0,
Pillow 12.3.0; jemalloc 5.3.0 at /lib/x86_64-linux-gnu/libjemalloc.so.2.
Use two CPU threads and the retained 4480 MiB aggregate process-tree guard.
The shell wrappers use CPUs 0 and 1; adapt affinity to two permitted CPUs if
needed. Keep at least 1 GiB free in addition to the multi-GB generated assets.
Set CYBR_HEAVY_LOCK to a shared writable lock when other scene jobs run.

From this directory:

    python3 restore_inputs.py
    mkdir -p logs
    python3 packages/CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15/verify_pinned_inputs.py
    bash restore_av.sh initial
    bash restore_av.sh continued
    bash restore_av.sh av
    bash rebuild_ca_cb_oct12.sh ca
    bash rebuild_ca_cb_oct12.sh cb
    python3 prepare_current_dr.py

The first command reconstructs the unchanged 18,480,390-byte DR world catalogue
from three bounded byte parts, verifies its original SHA-256, and refuses to
overwrite conflicting existing bytes. The reconstructed binary is a local build
input and is intentionally excluded from the publication manifest.

Each build wrapper releases its lock at the stage boundary. The AV phase includes
one original 1000-pixel raw proof because the captured source does not expose a
qualified cache-only stop. Its admitted optional assembled cache is then reused.
For the final scene, run clean_render_landform_candidate.sh in
`dr_recovered_whole/runtime/pipeline` with `dr_recovered_whole/job.json`, under
the same shared lock and resource guard. A typical guarded invocation is:

    R="$PWD"
    export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
    export LD_PRELOAD=/lib/x86_64-linux-gnu/libjemalloc.so.2
    export MALLOC_CONF=narenas:2,dirty_decay_ms:0,muzzy_decay_ms:0,abort_conf:true
    flock -x "${CYBR_HEAVY_LOCK:-$R/cybr-heavy.lock}" taskset -c 0,1 python3 helpers/run_bounded_stage.py logs/dr.log logs/dr_guard.json 900 bash dr_recovered_whole/runtime/pipeline/clean_render_landform_candidate.sh dr_recovered_whole/job.json

Output is UNFILTERED_PANEL.png at 2000 x 1334, 32 raw Cycles samples, using the
qualified 1024-pixel context texture tier. This is not a claim that every material
map is native 4096 at every distance. Real grains keep metric size; selection is
projection-bounded within the declared foreground domain. The rest of the road
uses its distance representation.

## Verification and remaining limits

See VALIDATION.json for the current tested scope. All source/input hashes and
relative symlinks are listed by PUBLIC_MANIFEST.json. The preparation accepts
an optional --artifacts-root to reuse an already semantically admitted AV cache
and exactly regenerated CA/CB payloads. That qualification is distinct from
rebuilding the entire public folder a second time from zero.

The surface-stock models use documented authored assumptions. They are not
validated hydraulic, wind or rigid-body simulations. Some coarse shapes and
large-scale soil organization remain visually weak. No validation count alone
establishes visual quality.

This source introduces no new standalone CYBR MATERIAL recipe and does not
replace a material-catalogue default. Original procedural material source bytes
are preserved as dependencies. Use the destination repository's existing
licensing and notices; this package does not invent new third-party rights.
