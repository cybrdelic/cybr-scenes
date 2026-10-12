# DL static original-fine support candidate

This is an additive candidate for the retained DH Victorville road. The same-view close is visually checked. The full-road counterpart is recorded separately when complete. This is an authored static vertical partition of existing fines, not a new transport simulation or measured Victorville stratigraphy. Original mountains, CO22 candidate light, CN regional palette, physical grain sizes and particle XY/IDs remain unchanged.

## Required preceding road source

Use the independently delivered CYBR_Victorville_Ground_Current_Source_v8.zip, Library private-archive-reference-omitted version6, SHA25630c6dd020f03eeafed738787b863a7c1374b4370f2878cbc292db77e884db57c. Follow its declared CQ/DG/DH preparation chain to a prepared DH scene job directory. This addon is not a standalone road. Fresh combined public-checkout regeneration remains unverified.

## Pinned current layer and source

STATIC_FINE_LAYER.npz is the exact evaluated candidate input. CURRENT_EVALUATED_FIELDS.npz contains the actual immutable-prefix evaluated soil fields and exact post-CE coordinates used to derive it. Both are retained rather than relying on a later exporter or unspecified memory state. The source audit distinguishes known lost fine-bank coupling from this new static-layer interpretation.

To regenerate the layer from the preceding job's pinned CE/AH data and included field export:

    python -B regenerate_layer.py --baseline /path/to/prepared_dh --out /path/to/new_layer

Use NumPy/SciPy matching the preceding source checkpoint; cap BLAS/OpenMP at two threads. Serialized NPZ timestamps are not data identity. Compare every decoded array against the included STATIC_FINE_LAYER.npz before using a regenerated alternative.

To stage the current pinned layer into that existing DH job:

    python -B prepare_scene.py --baseline /path/to/prepared_dh --out /path/to/new_dl

Then run new_dl/runtime/pipeline/clean_render_landform_candidate.sh with new_dl/job.json under the retained two-CPU,4480MiB aggregate process-tree guard. Serialize heavy jobs on the common cloud lock. The preparation wrapper does not render or overwrite the baseline. No new full-scene cache is needed.

## Physical/representation limits

Original versus old/new deposited classes are reconciled on the same CE vertex basis, with reported float32 roundoff.0.19181345m3 of original fines is partitioned to an effective cap and the complementary mixed reserve is recorded. Total material and terrain elevation are unchanged. Effective cap depth is0-12.307mm. Pre-existing clasts descend relative to this horizon, while stock-budgeted deposit representatives and original fine-sand geometry keep their roles. Existing intrinsic embedding remains an authored approximation.

The same bounded original fine-area field joins the finite fine-material response. CC/CE's single surface-authority ordering remains, so an independent historical overcoat is not restored. Fractional optical area and mean-column support are illustrative closures, not a resolved packed-mixture solution. Downward-only rigid translation cannot create a new floating contact relative to unchanged terrain; full body collisions/settling are not solved.

No scans, photo textures or image-generated assets are included. DK/DI stone studies remain separate unselected experiments; this candidate uses retained DH bodies and materials.
