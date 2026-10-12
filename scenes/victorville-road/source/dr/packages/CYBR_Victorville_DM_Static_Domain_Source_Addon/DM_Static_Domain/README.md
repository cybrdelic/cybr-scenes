# DM static fine-cap continuity candidate

This add-on changes the original static fine-cap allocation in the existing Victorville road scene. It keeps the same 0.19181345 m3 cap total, every mixed reserve and every event array. The continuous original AP grading/receiving field owns its distribution, instead of the rectangular boundary of an old mobile-sediment simulation.

The fully covered static layer is 10.2661156 mm. About 0.030489 m3 of fines is reassigned geographically. This is an authored initial-condition revision, not inferred transport, measured stratigraphy or an exact Victorville reconstruction. It does not add terrain, scatter, grain scaling or a new geological inventory. Original mountains, warm CN palette, CO22 candidate daylight and DH body sources are retained.

See OWNERSHIP_DECISION.md, STATIC_FINE_LAYER.json and SEAM_SOURCE_CHECK.json for assumptions and accounting. The older CE erosion/matrix response remains unchanged in this isolated test and can still carry a smaller domain-dependent artifact.

## Required baseline

The exact delivered DL source add-on:
- CYBR_Victorville_DL_Static_Fines_Source_Addon.zip
- Library ID: private-archive-reference-omitted, version 0
- SHA-256: af565079e68dfd611cff96e6842e8e615fa669deab67b45a7726b27b229de82a

Use its instructions to prepare a DL scene from its DH dependency chain. The resulting directory must contain job.json and runtime/, and reference the exact DL field SHA c989d4ea7799f69b872504460055cb18529bc12d3128ee0774b8085a90bb492f.

## Reproduce

1. Optional numerical replay: python regenerate_layer.py --dl-layer /path/to/DL/STATIC_FINE_LAYER.npz --out /new/numerical-check
2. Prepare a scene derivative: python prepare_scene.py --baseline /path/to/prepared-DL --out /new/prepared-DM
3. Use the rendering command printed by that entrypoint, with the same existing 2-thread CPU and 4480 MiB process-tree guard. The source pipeline never writes a new full .blend.

The exact evaluated field is included to pin the inspected result. All fifteen numerical arrays reproduced exactly in the local replay. Fresh derivative preparation from the retained DL baseline was tested. A new clean extraction/rebuild of the full public dependency chain is still unverified.

## Preview and provenance

Actual images are procedural Blender Cycles CPU outputs. No photos/scans/imagegen were used as textures. Regional references remain qualitative palette/geology observations in the retained baseline provenance. The source is original authored scene work; it does not claim measured site reconstruction or validated erosion physics.

One cache-based native-window attempt stopped at the existing process-tree RSS guard before rendering. Its failure receipt is retained. The full-source path is used for the current actual whole-view proof; this cache failure is not hidden as a successful capture.
