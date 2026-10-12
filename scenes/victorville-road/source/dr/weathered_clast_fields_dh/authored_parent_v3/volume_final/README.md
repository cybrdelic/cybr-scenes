# DH3: pinned two-body continuous-fracture replacement

## Status

The final isolated clay and exact-current-CN fixtures are useful enough for one actual terrain/context gate. The old CG brick and AS socket are gone. Rounded clean margins and restrained relief remain visible limitations. This is not a claim of photorealism or calibrated Victorville morphology.

Both final shapes, exact material transfer, and standalone regeneration are verified. A subsequent separate exact-DG close-crop gate checked actual terrain heights at up to512 stratified/low footprint vertices for all18 changed bodies: none unsupported and no settling needed. The receipt is copied in scene_evidence/. It also verifies unchanged CG XY/IDs/yaws. This is a sampled contact sanity gate, not full triangle-collision or rigid-body-equilibrium proof. Old CI exposure remains baseline-only. No further shape or material variants are queued by this fixture task.

## Final integration pins

- Manifest: `CANDIDATE_MANIFEST.json`
- Manifest SHA256: `6ba7b8aa87ecaa9cd0758e1b850c3839a2dde3c0d37e793f9ff66b916f36a563`
- Late adapter: `apply_weathered_fields.py`
- Adapter SHA256: `dcf7965b8a8702c7dafacb663b428afee878e4d8815c3f5b3cc80ca9756d32f7`
- API: `apply(scene, {"revision": 1, "manifest": "/absolute/path/CANDIDATE_MANIFEST.json", "manifest_sha256": "6ba7b8aa87ecaa9cd0758e1b850c3839a2dde3c0d37e793f9ff66b916f36a563"}, output_dir)`

Apply only after the old CI convex exposure/support accounting. The old CI estimate remains baseline-only. The adapter source-checks both parents, retains material slots, reads current live mineral/roughness fields, preserves CG point instances/IDs/yaws, and computes actual multiplicity/determinant-weighted representation accounts. It does not edit a transport ledger. Any terrain-contact settling must be separately measured and recorded.

The adapter was tested in a tiny Blender scene with nonconstant live color and roughness fields, including shared AS users, a scaled hidden AS user and multiple CG point instances. These synthetic counts are contract checks, not road totals.

## Geometry and authorship

Each specimen has 40,962 vertices and 81,920 real triangles. The new primary body is a lopsided low-frequency continuous body with four unequal nonorthogonal fracture planes and narrow metric transitions. It uses the old metric envelope and material identity, but never blends the old silhouette or sockets into its shape. There is no per-ray old-face inward cap. Local space outside the old solid is permitted and separately accounted.

Differential relief uses variable-size compact-support mineral-susceptibility domains. Complete support neighborhoods are checked, so truncated neighbor switches cannot cause seams. Only the sparse weak-domain population drives interface loss; there is no cobbled all-boundary network. These fields are geometric only. They do not alter or replace the current material graph.

Final CG146:
- Dimensions: 46.240 x 42.088 x 9.395 mm, inside original 52.378 x 46.510 x 11.123 mm envelope
- Closed volume: 9.168720626798847e-6 m3, versus parent 9.169637588708543e-6 m3
- Exact net representation reserve: +9.169619096958872e-10 m3 per body
- Uniform linear contraction after the original v3 clay: 0.9892703420246957 about the old envelope center; no object-transform change
- Effective grain-domain spacing after contraction: 1.68176 mm
- Normal relief: median 0.05718 mm, maximum 0.33419 mm
- Remaining horizontal-fixture burial: 1.74460 mm; projected volume-centroid support margin 14.3151 mm

Final AS039:
- Dimensions: 142.899 x 77.548 x 68.587 mm, inside original 155.547 x 85.823 x 74.085 mm envelope
- Closed volume: 3.676419220152930e-4 m3, versus parent 5.623880865819677e-4 m3
- Exact net representation reserve: +1.9474616456667467e-4 m3 per body
- No final contraction; bytes are identical to the accepted v3 clay geometry
- Grain-domain spacing: 2.8 mm
- Normal relief: median 0.12256 mm, maximum 0.69851 mm
- Remaining horizontal-fixture burial: 21.2618 mm; projected support margin 34.9055 mm

Both final float32 meshes are closed, oriented, genus-zero, have nonzero triangle areas and positive true volume, and lie inside the original axis-aligned metric envelope. The support cross-section hull is used only for the horizontal support diagnostic, never to replace a clast surface. No settling was performed here. In particular, the CG burial margin does not establish contact on a sloping road shoulder.

## Added and removed represented solid

True volumes of the old and final closed triangle meshes are computed directly. Local overlap is measured from the actual old triangles and actual final polyhedron at 40,962 and 163,842 common directions. Fine candidate samples are lifted onto its existing planar mesh edges, so the second sample density does not silently create a different candidate surface.

Level7 estimates per body:
- CG: added 2.241210933685615e-6 m3; removed 2.242127895595311e-6 m3
- AS: added 1.1092672215689181e-5 m3; removed 2.0583883678236385e-4 m3

The observed intersection-volume change between the two sample densities is 6.1904e-10 m3 CG and 1.1971e-8 m3 AS. This is an observed sampling change, not a rigorous error bound or an exact Boolean intersection. Added-minus-removed matches the exact closed-volume change algebraically. No multiple source intersections were detected in the level7 sampled directions. No fresh mesh-convergence sweep is claimed.

These local additions are an authored representation redistribution, not physical mineral growth. Body lobes, fracture planes, smoothing width, domain distributions and relief depths are unvalidated modeling choices. No weathering time, process rate, sediment transport or physical erosion-event conservation is claimed.

## Appearance proof

`mineral_fixture/` contains:
- `CG_146_before.png`, `CG_146_after.png`: exact-current-CN comparison
- `AS_039_before.png`, `AS_039_after.png`: exact-current-CN comparison
- `CG_146_before_clay.png`, `CG_146_final_clay.png`: original versus exact final calibrated geometry in neutral clay
- `AS_039_before_clay.png`, `AS_039_final_clay.png`: original versus exact final AS geometry in neutral clay

All images are 512x384, raw32 samples, two CPU threads, no denoising, matching source-relative camera/yaw/burial/light. The original source uses flat normals; the final genuinely dense surface uses smooth vertex normals. Clay uses no noise, bump or texture.

The material companion executes the existing `material()` recipe and exact `color_variant(old, 'coarse mineral')` CN graph. The original 680/m variation and 3100/m microbump are unchanged. Parent attributes were regenerated and their parent-coordinate bytes checked before transfer. The old failed candidate's vertex colors were never assigned to a differently shaped parent. New susceptibility is NOT connected to shader color or roughness. No photograph, scan or generated image is used as texture.

Current live scene pigments and roughness are transferred by saved convex nearest-parent weights, including newly occupied locations. That is an explicit authored transfer from surface samples, not a claim to know the old body's internal mineral field. Packed parent colors are reproduction evidence; the adapter must continue reading current live fields instead of overriding them.

## Portable reproduction

`portable/inputs/` contains the exact two parent meshes and original point colors/roughness. `SOURCE_PINS.json` pins them. `regenerate_two_specimens.py` uses only these local files and NumPy/SciPy, without the previous audit-folder layout, a road scene, a source bank or a terrain cache.

The replay regenerated every saved array byte-for-byte, including vertices, faces, source arrays, weights and susceptibility fields. See `portable/REGENERATION_VERIFIED.json` and `RUNTIME_VERSIONS.json`. The checked runtime is recorded; other library versions should verify the arrays before being treated as exact replicas.

To run in this cloud workspace, use `portable/regenerate_bounded.sh`. For another workspace, set `DH_HEAVY_LOCK` to its shared heavy-job lock and `DH_OUTPUT_DIR` to a fresh output directory. The bundled process-tree guard is an unchanged copy of the existing helper and enforces a 4480 MiB aggregate cap. The live scene still supplies its existing DG/CQ shader/runtime and adapter API. No road rebuild is needed to verify this source package.

## Resource checks

- Final calibration, exact parent-attribute preparation, four CN images, one final-byte CG clay image, and adapter test: 46.95 seconds, 293.17 MiB peak
- Standalone exact-array regeneration: 10.37 seconds, 340.02 MiB peak

Both stages used the common heavy-job lock, existing guard and at most two CPU threads. All stages are terminal, and this task has no heavy work queued.
