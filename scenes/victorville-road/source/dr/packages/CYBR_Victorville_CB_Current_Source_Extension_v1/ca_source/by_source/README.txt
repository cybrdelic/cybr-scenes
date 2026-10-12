VICTORVILLE CURRENT ROAD: ORIGINAL MOUNTAINS + AZ/BW FINES + BY WEAR
Source extension v1. This is a dependent add-on, not the full road source.

REQUIRED RETAINED FULL SOURCE
CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15.zip
13,559,633 bytes
SHA-256 daae4846d4ef9506b01c40bfa9b1ecfd369fbd17f457d0a63c68f168a79aaa04
Library private-archive-reference-omitted, version15.
Keep that delivered archive. This extension needs no private serialized scene
input and no separately delivered AZ archive. The pinned original microbed,
original R5D source builder and all current material helpers are included here.
The experimental BV mountain replacement is deliberately absent: the latest
user direction restored original AV mountain shapes and objects.

STATUS
BY was actually applied to the retained assembled AV scene and rendered with
AZ/BW and direction-corrected daylight, using actual CPU Cycles at1000x667,
24 raw samples. Raw pixels are unfiltered and unretouched. The guarded process
finished at4032.37MiB peak in88.30seconds. That is a historical capture result,
not an estimate for a full from-zero rebuild. Exact jobs, source snapshots and
resource/material receipts are included. Numerical field tests and actual
material-only Blender fixture tests also passed.

Fresh AV regeneration and this new portable wrapper's combined execution have
NOT been exercised end to end. Wrapper checks are syntax/closure/package checks
only. The underlying AZ/BW/BY code was used in the actual captured frame. Keep
this distinction when reporting reproducibility. The retained v15 source has
its own strict Y/Z semantic admission path; do not bypass that path or replace
an old serialized scene hash with an arbitrary newly generated file.

CURRENT MECHANISM
- Original mountain geometry is retained unchanged.
- AZ restores native1101x1101/.18m original fine-grain color and metric slopes.
- BW replaces one unsupported coarse RGB multiplier with a source-derived fine
  closure selected by existing historical fine-area attributes. This is an
  authored area mixture, not a calibrated sediment optical model.
- BY adds unequal metric flush-repair footprints, broadly wandering wheel
  corridors, original-source binder aging, aggregate-only polish and coherent
  paint retention/loss. Dust stays above these changes in the existing graph.
  Repairs and old paint share the actual surface; no new overlaid mesh can
  intersect the road. Repair bodies retain the existing aggregate geometry and
  receive a fresh-binder response. Excavation and compaction are not simulated.
  Crown-contact paint coverage derives from original metric asphalt heights.
- Sky azimuth is aligned with the existing Sun without changing either energy,
  exposure or material colors. The sky's direct sun disc stays disabled.
- Approved source maps, original material datablocks, metric grain sizes,
  terrain, road contact and finite particle allocation remain intact.

The authored road maintenance parameters are not measurements of Victorville
or a validated deterioration model. Qualitative mechanism definitions were
checked against FHWA-HRT-13-092, chapter1:
https://www.fhwa.dot.gov/publications/research/infrastructure/pavements/ltpp/13092/001.cfm
Regional NPS road/landscape references were viewed for observation only. No
reference pixels, scans, photo textures or generated images enter the material.

PREFLIGHT
Extract this ZIP with Python if a native ZIP tool lacks ZIP_LZMA support:
  python -m zipfile -e CYBR_Victorville_BY_Current_Source_Extension_v1.zip by_source
Then from the extracted extension directory:
  python verify_extension.py --base-archive /path/to/full_AV_v15.zip
This validates the exact prerequisite, files, captured source closure and CRC.
It does not perform scene regeneration or a render.

REBUILD / APPLY
1. Follow the unchanged AV v15 README and its semantic admission commands.
   Retain ASSEMBLED_SCENE_AV.blend, its .blend.json receipt and the associated
   source_admission.json plus source_admission_resources.json.
2. Open the freshly generated, unedited AV scene in Blender4.3.2. Require NumPy.
   The apply wrapper checks its current digest against its own build receipt,
   its source-bank identity, original finite grain allocation, strict preceding
   semantic admission and the exact material graph. It does not require the
   historical cloud cache's .blend hash.
3. With this extension root on sys.path in Blender:
   from apply_extension_blender import run
   result=run(base_archive='/path/to/full_AV_v15.zip',
              z_admission='/path/to/run/source_admission.json',
              output_dir='/path/to/fresh_current_receipts',
              variant='candidate',with_aw=False)
   'baseline' applies identical AZ/BW/daylight without BY wear. Reopen the
   pristine AV scene before either operation. A fresh output directory is
   mandatory. Failure can leave partial in-memory edits; discard that session.
4. The result remains in the session for inspection. The wrapper never saves
   or renders automatically. Save only to a new user-chosen derivative path.

Equivalent apply-only command, omitting -b to keep Blender interactive:
  blender /path/to/ASSEMBLED_SCENE_AV.blend --python-exit-code 1 --python apply_extension_blender.py -- --base-archive /path/to/full_AV_v15.zip --z-admission /path/to/run/source_admission.json --output-dir /path/to/new_receipts --variant candidate
No optional AW terrain or mountain redesign is used.

CAPTURE LIMITS
Historical jobs are evidence and contain original absolute paths. The captured
render helpers are preserved exactly, with their active-path dependency closure;
raw jobs are not portable launch commands. In-memory preview reductions used
1024px asphalt maps, stride4 road context geometry and conservative culling.
No native detail equivalence, arbitrary-camera grain coverage or higher-density
particle allocation is claimed. The two valid allocation cameras are retained
1000x667 AV views. Raw24samples can show noise. Native source maps remain4K.
Full-quality/source regeneration, all indirect culling equivalence and fresh
wrapper+render replay remain unverified. Do not weaken guards to force a pass.
