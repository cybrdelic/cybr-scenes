VICTORVILLE AV: CURRENT REPRODUCIBLE SOURCE CHECKPOINT v15

STATUS
Current-only combined-scene source and actual capture evidence. Fresh full
clean-directory end-to-end regeneration remains explicitly UNVERIFIED.
This is an unfinished progress candidate. Neither whole-scene nor final material
quality is accepted. Packaging performs CPU1 source/hash/layout checks and tiny
fixtures only. It does not launch Blender, assemble a scene, solve the full
terrain event, render, create another cache, or upload.
Earlier source archives, including the complete AQ v14 baseline, remain unchanged.

CONTENTS AND AUTHORITATIVE INPUTS
The inherited original-asphalt and R5D/Y/Z build chain, source/configuration,
strict semantic admission, exact 3,913,561-byte approved R5D microbed and exact
2,093,642-byte Z stock ledger remain pinned. SOURCE_LOCK.json checks all files;
PINNED_INPUTS.json and the inherited guards retain the original ground contracts.
The exact captured source bank under road_scene_r6/checkpoint_pipeline_sources/
is authoritative for AV. Older public source modules are deliberately retained
where the inherited builders/tests depend on their exact bytes. The AV runtime
stages its captured bank into separate pipeline, src, and vegetation siblings,
so no mutable local-module substitution is required. The closure receipt lists
exact input hashes, imports, generated dependencies and runtime requirements.

AV combines AR fractured actual-road topology and exposed-rim continuity, AT
worked shoulder foundation, the revised fractured-candidate metric coarse bodies,
and AU source-scale finite grain allocation for two explicitly qualified views.
That coarse-body candidate remains unapproved. All supporting original test
sources are included. A single historical morphology test pins a pre-AV assembly
file and is explicitly excluded from current fixture results; its source remains.
The current bank replaces previous capture snapshots; old giant guides, images
and serialized scenes are not included. Necessary inherited small sources and
build/test dependencies are retained. Historical AQ arrays are replaced by exact
AV-generated arrays, which are evidence ONLY, never regenerated-scene inputs.
Canonical evidence changes only absolute path strings/keys; original-local and
packaged hashes plus path-normalization receipts are retained.

REGENERATION
Use Python 3 with standard lzma support for ZIP_LZMA JSON entries:
  python -m zipfile -e CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15.zip current_av
  cd current_av

Requirements: Blender 4.3.2 with Python/NumPy, host Python 3 with NumPy/SciPy/Pillow,
Linux bash and ps, and official OIDN 2.5.1 oidnDenoise at OIDN_BIN. Blender defaults
to the blender executable; BLENDER_BIN is accepted by inherited builders where
supported. Unset MATERIAL_PATH_MAP_FILE. Review the preserved build scripts for
stage-level resource caps. Source tests do not establish full-build resources.

  bash test_source_current_av.sh
  bash regenerate.sh build-only
  export OIDN_BIN=/absolute/path/to/oidnDenoise
  bash regenerate.sh render-only

Or perform the two build/render steps in sequence with:
  bash regenerate.sh preview

Check exact source inputs without Blender:
  python road_scene_r6/src/render_checkpoint_av.py --check-sources

Explicit new repeat directory, using strict semantic admission of rebuilt Z:
  python road_scene_r6/src/render_checkpoint_av.py --role av_outward --tag av_repeat

The inherited Z build validates its rebuilt Y semantically. The AV replay then
uses the unchanged strict Z admission and records the actual rebuilt .blend hash.
A historical serialized .blend hash is NEVER required as input. Both pavement
contact and AR fractured-boundary consumers relocate/pin the regenerated native
GeometryHeight.npy; the historical exact Z stock ledger stays a separate pinned
input. Source/ledger corruption and unapproved path mapping must still fail.

OPTIONAL CACHE
The default exact-job replay writes one distinct optional output named
ASSEMBLED_SCENE_AV.blend inside its NEW capture directory. Its allowed directory
is relocated along with its output path; the recorded captured source digest and
all geometry guards remain unchanged. Cache source bytes are not bundled and no
cache is needed to regenerate AV. Copy-save rejects an existing target/receipt,
requires the preserved free-space reserve, and never overwrites rebuilt Z.

To render directly from rebuilt Z without writing an assembled output cache:
  python road_scene_r6/src/render_checkpoint_av.py --tag av_no_cache --without-cache

This option disables only the output step. The exact source bank stays intact;
the expected executed manifest explicitly omits assembled_scene_cache_av.py,
so its manifest digest differs and both historical/actual digests are recorded.
It never substitutes an unpinned helper or relaxes a source/geometry guard.

If a verified assembled cache already exists, the optional prepare_cached_view_av.py
helper accepts --cache PATH --output FRESH_DIRECTORY --view outward|road. It checks
cache bytes/provenance and prepares a job for the two already allocated cameras.
It does not render. For a cache produced by the default replay above, an explicit
bounded additional road-camera command is:
  R=road_scene_r6/captures/av_outward_rebuilt/av_outward
  python road_scene_r6/src/prepare_cached_view_av.py --cache "$R/ASSEMBLED_SCENE_AV.blend" --output "$R/road_view" --view road
  python "$R/runtime/pipeline/bounded_clean_run.py" "$R/road_view/job.json" "$R/road_view/run.log" "$R/road_view/resource_receipt.json" 4480
Check that resource_receipt.json passes before using any output. This second-view
recipe is provided as an optional regeneration command, not a claim that its
fresh extracted execution has been verified. Do not treat this accelerator as
the clean rebuild.
The cache's pre-LOD preservation does not provide unrestricted view coverage.

QUALIFIED CAMERAS AND LIMITS
Both views are 1000 x 667, 26 mm. The current outward capture is from
(-5.12, 2.0, 0.4) towards (-3.6, 8.5, 0.1). The allocation's additional road view
is from (-3.97, -0.8, 0.35) towards (-0.5, 7.0, -0.03). Finite source-scale grain
allocation is qualified only for those poses/resolutions. Other cameras, crops,
resolutions, or native/4K views need separate coverage/resource/visual review.
Current Cycles proof is a 24-sample guided preview. It uses 1024-pixel asphalt
mips, stride-2 asphalt geometry, camera and terrain culls and guided OIDN denoise.
These reductions are explicit; they do not establish native-detail equivalence.

The foundation and prior substrate are authored approximations. Transport is a
finite-inventory, art-directed low-head numerical model, not validated site
reconstruction or hydraulics. Metric body dimensions and topology audits do not
prove full particle collision/packing, mineral realism, optics or botanical
identity. Grain allocation preserves source identities/scales but remains a
view-bounded representation selector. AQ current-surface film resamples/solves
on replay; historical output arrays are audited without solving. Cross-version
byte identity of freshly solved NPZ files has not been established.
The current evidence receipts define precisely which geometry, stock balance,
source identity, preview resources and guides passed. No fresh complete build,
final appearance, arbitrary-camera completeness or native/4K performance claim
is made by this package.
