# CZ current-view sand and grit checkpoint

Original procedural Victorville-inspired road, not a surveyed site or scan. Work-in-progress: fine grains are now explicit and visible in the close view; dark angular contrast remains too strong. The 1000px wide difference is modest. Original AV mountains, CQ terrain/vegetation, CN warm reflectance and CO 22° daylight are retained.

## What changed
The old original fine instancer contributes zero points in this whole-road frustum; its later supplement contributes only 135. The sand class was never explicit in that scene bank. CZ re-evaluates the exact approved R5D source RNG, retains 64 source sand specimens, and replaces the camera-specific chip/grit supplement with a current-view allocation. Actual sand horizontal diameters are 0.159–0.641 mm, median 0.263 mm. The source nominal class is 0.16–0.64 mm. No particle enlargement, image grading, photographic texture or image generation.

Close proof: 900 × 675, 48 raw Cycles CPU samples. Added 441 chips, 10,772 grit and 55,620 sand; original supplement had 5 frustum-visible points. Whole proof: 1000 × 667, 32 raw samples; added 41,421 chip/grit and 69,523 sand. These are LOD allocations, not complete physical density or sediment-transport conservation claims. Both use 1024 context maps plus native 1101 AZ fine slope/color. Camera/preview culling can affect indirect transport.

The sand bank follows the original source's broad-ground datum. The original microbed was geometric in R5D but remains normal-only here. Restoring source-relative bed burial is the next correction; no such correction is claimed in this checkpoint. The detached-looking central dark patch also exists in the baseline. The nearby central coarse body has 223/368 vertices below current terrain (5.57 mm deepest); its highest exposed vertex is 5.33 mm. This excludes a wholly floating body but does not identify the patch's caster. Sand contact has a conservative slope-bound embedded witness; see evidence.

## Dependency and staging
This is an additive module, not a standalone whole-scene package. It requires the frozen public CQ source v2 (PUBLIC_SOURCE_MANIFEST SHA256 58cb6c55c74e4fb153c525260f670dc0761806ae3ff32442e6a547a60ed4f1f4) and a prepared CQ capture with pipeline 067ceffd2795b5c059b8341dd179bdd11ddb53cfbaf669298c50ff4d97999168. Follow that package's AV replay and prepare_capture.py first. Its full fresh public-wrapper rebuild remains unverified; the underlying AV-to-CQ cloud recovery was actually reconstructed/rendered. This add-on does not remove that limitation.

Stage after preparing CQ:

    python prepare_addon.py --cq PREPARED_CQ --out NEW_CZ --mode wide
    python prepare_addon.py --cq PREPARED_CQ --out NEW_CLOSE --mode close
    python prepare_addon.py --cq PREPARED_CQ --out NEW_CONTROL --mode close_baseline

Then run the generated runtime/pipeline/clean_render_landform_candidate.sh with its job.json using Blender 4.3.2, two CPU threads and the 4480 MiB aggregate guard, serialized with other heavy work. The prepared job retains all exact parent input paths. Do not mistake staging verification for a second full rebuild.

## Rebuild the tiny sand bank
The included inputs are original procedural source and normalized fracture solids, not photographs. With NumPy 2.3.5:

    python extract_source_sand.py inputs/build_diagnostic.py inputs/fracture_solids.json NEW_sand_bank.json

The original packing stream reproduces counts 297/8859/64577 and conservative mask 0.35925725. The supplied sand_bank.json is pinned SHA256 8ad5c6795e064aa15bfc111d0693397c653ed8835fc153977bc27a2157c1b7cc. Independent source regeneration was checked; no byte comparison to a recovered original R5D .blend is claimed. Source bank vertices are not modified or scaled by the scene adapter. Remaining grains use inherited normal/color fields, not equivalent cast shadows or parallax.

Regional qualitative references remain USDA Bryman/Cajon soil descriptions and the already documented Victorville daylight reference observation in CQ. The palette is authored, not calibrated Munsell-to-RGB.
