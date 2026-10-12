# DG historical support / grain role diagnostic

This source is a candidate representation repair. The original metric particle geometry, pigment, roughness, count, XY and yaw remain intact. No input mass ledger is edited. The source begins with current-view DE allocation after original sand datum DA; DG replaces DF's narrower burial step rather than applying both.

Static grains use the already-established CI horizon: current terrain minus max(max(prior AH net cover,0)+later CE net change,0). Existing per-class retained-deposit inventories supply a bounded surface-representative pool. Later class erosion is charged against prior retained material first, a conservative visibility assumption; retained CE deposits are then available too. This does not reconstruct stratigraphy or particle trajectories.

The retained source allocator is included byte-identically. Its derivative permits the supplied original sand bank as class0 and changes the matching documentation; volume caps, random seed, top-depth proxy and selection equations are unchanged. Every prototype must be closed for the exact solid-volume budget. The original AI lowest-vertex20um embedding cap is checked against actual final terrain. Body/cell intersections, full collision and complete subpixel populations remain approximations.

Prepare in an existing DE/DB pipeline, without the optional cache:

    python dg_history_source/prepare_full.py --baseline /path/to/de_native --runtime /path/to/db_native/runtime --out /path/to/new_dg

For the diagnostic camera add: --close-centre -4.9 5.5

Run new_dg/runtime/pipeline/clean_render_landform_candidate.sh with new_dg/job.json under the original2CPU/4480MiB process-tree guard. The source-only staging check validates the declared pins and entrypoint; a new end-to-end public checkout regeneration is not thereby claimed.

The cache-based comparison uses the same adapter on a semantically and actual-pixel qualified common checkpoint. It renders500x400 native pixels from a900x675 projection at32raw Cycles samples. Nothing is resized. Numerical/preparation tests are not visual acceptance; inspect the actual paired render receipt before promoting the candidate.

To prepare the exact close diagnostic projection and native border, add `--native-close-proof` instead of `--close-centre`. It sets the tested900x675 projection,500x400 crop, centre(-4.9,5.5)m, and matching camera culling. The full-pipeline staging command and paths were checked against the actual cache diagnostic controls; a second full-pipeline close render was not performed. Use a separate baseline job without DG for a causal before/after proof.
