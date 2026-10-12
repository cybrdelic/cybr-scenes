# DE: allocate grains against the actual native whole-view footprint

The preceding DB whole image is2000x1334 but retained its1000x667 allocation footprint for the controlled broad-normal comparison. DE changes only those two CZ allocation dimensions to2000x1334. The camera,32raw Cycles samples, daylight, material endpoints and maps, body dimensions, source class density, packing rules, and maximum135000chip/grit plus85000sand counts stay unchanged. The actual retained point selection and layout may change with the new footprint.

The context texture tier remains1024; the original native1101fine-only endpoint is unchanged. A2000pixel image does not turn context textures into native4096 maps. This is an actual-output allocation correction, not complete source population, perfect physical transport, or exact far-field appearance equivalence.

Prepare only:

    python de_source/prepare.py --baseline /path/to/db_wide_native --out /path/to/new_de_native

Run the unchanged baseline runtime/pipeline/clean_render_landform_candidate.sh with the new job.json under the established two-thread CPU and4480MiB process-tree guard. The actual receipt records retained counts and any changed budget threshold. DD is deliberately absent from this whole-view control, so its partial near-proxy experiment is not silently promoted. DC is also absent to preserve a clean attribution to the allocation footprint.

Fresh full public-parent regeneration remains unverified. This module requires the prepared DB/CZ stage from the current source chain.
