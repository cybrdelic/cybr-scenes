VICTORVILLE CA: CONTINUOUS METRIC ASPHALT THROUGH THE VISIBLE REPAIR
Current-source add-on v1. Original AV mountains, approved material recipes and physical grain sizes are retained.

REQUIRED FULL SOURCE
Keep the previously delivered CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15.zip:
13,559,633 bytes; SHA-256 daae4846d4ef9506b01c40bfa9b1ecfd369fbd17f457d0a63c68f168a79aaa04.
Library private-archive-reference-omitted, version15.
This add-on includes the complete previously delivered BY extension, its exact original microbed cache and builder, plus the new CA geometry/field regenerator. No separate BY or AZ archive is required. It is not a replacement for AV v15.

WHAT CHANGED
The source road physically instantiated its original dense .25m asphalt tiles only through y=2m. The first authored repair spans y=3.36–5.40m. CA extends the same shared native geometry bank through y=6m, retaining the original .004m height scale. It moves the old far fade, removes 11 square metres of underlying base, and stitches three conforming collar sides. Markings and deposited fines share the displaced surface. Both existing base-face material assignments and all original POINT fields are retained. The source field lookup keeps all 1,041 prior pixel rows exactly and adds actual-triangle barycentric fields on the same 2mm lattice.

The result uses264 tile objects and9 shared native mesh templates. All493 neighboring tile boundaries were evaluated at513 samples; maximum coordinate mismatch was1.47e-8m. The actual mesh contact test found zero unmatched non-native boundary edges and zero overused edges. The first failed contact test is described in the construction notes; no layered replacement sheet was accepted.

TESTED, WITH LIMITS
- Actual matched1200x390 crop from4000x2668 projection:32 CPU Cycles samples, qualified native-guide OIDN,140.6seconds,4268.7MiB peak.
- Actual1000x667 whole-road frame:24 raw CPU Cycles samples,92.8seconds,4090.9MiB peak. Full-frame guide filtering remains unqualified, so the context is explicitly raw.
- Fresh extraction from the retained AV file reproduced the complete46,410,403-byte CA acceleration payload exactly, including SHA-256 d1c7a52a2ca1845aa377eca3679135159e3c71762658a39488db0aa1cb472fd3.18.3seconds,665MiB peak. The payload need not be shipped; the included generator recreates it.
- The strict packaged Z semantic admission passed, then the combined BY+CA apply-only wrapper actually ran on retained AV:28.1seconds,3004.8MiB kernel high-water mark. It did not save or render a new scene.
- Fresh generation of AV itself from the full source, and pixel-identical capture from the convenience wrapper, remain UNVERIFIED. This is an exact retained-input application/replay checkpoint, not a claim of complete from-zero validation.

The crop uses documented stride2 native-grid preview (~.977mm spacing) and1024px texture mips. Whole-road uses stride4. The approved native inputs remain unchanged. Fine shoulder particle allocation is still bounded to the original AV views. The narrow outer pavement strip, farther road detail, shoulder uniformity and overall scene realism remain unfinished.

A Blender4.3.2 read-only check found is_dirty=true immediately after opening the retained file. The old convenience wrapper consequently refused before applying anything. The new wrapper explicitly reloads the requested file itself immediately before all existing file/build/admission/material/geometry guards. It does not accept arbitrary edited sessions by suppressing the dirty flag. Original wrapper and failed proof are retained.

REPRODUCE THE PAYLOAD
Requirements: Python3 with NumPy, Blender4.3.x (captured4.3.2). First follow the unchanged AV v15 README and strict semantic admission to create an unedited assembled AV scene, its .blend.json receipt, and source_admission.json/source_admission_resources.json.

From this extracted add-on directory:
  python verify_ca_extension.py --base-archive /path/to/full_AV_v15.zip
  python road_scene_r6/src/regenerate_metric_pavement_ca.py --av-scene /path/to/ASSEMBLED_SCENE_AV.blend --output-dir /path/to/fresh_CA_data

Allow about90MB of new data. The command reads only the relevant actual road and tile inputs, checks pinned semantic arrays, and regenerates the exact payload. It refuses a mismatch. It does not overwrite the input or render. The --verify-payload-without-writing switch tests the compressed payload in memory while retaining the extracted fixture.

APPLY CURRENT SOURCE
Use a fresh Blender process; this command explicitly loads the requested AV file and keeps the result in that process. It does not save or render automatically:
  blender -t 2 --python-exit-code 1 --python apply_current_ca_blender.py -- --av-scene /path/to/ASSEMBLED_SCENE_AV.blend --base-archive /path/to/full_AV_v15.zip --z-admission /path/to/source_admission.json --payload /path/to/fresh_CA_data/extension_payload.npz --output-dir /path/to/fresh_CA_application

A fresh output directory is required. The source file, material bank, finite particle allocation and preceding semantic admission must pass. Save only to a new chosen derivative path. Discard the process on any failed check; do not weaken guards. In background mode (-b), this is a validation/application test and exits without saving.

The captured render recipes and exact active pipeline snapshots are included as evidence. Their absolute paths belong to the original cloud run, not portable one-click launch commands. The convenience application is tested separately before preview LOD. Nested original BY preflight flags describe that earlier package's qualification; the current successful resource/application evidence is under evidence/current_wrapper.

PROVENANCE
All source is procedural, with regional references used only for observation. No scans, photographic textures or generated images enter the construction. The asphalt repair/wear field is authored rather than calibrated aging physics. Original mountains were restored at the user's request. The point of this revision is faithful geometric coverage of the existing material, not larger grains or invented detail.

This ZIP uses standard Deflate compression. Python extraction is also supported:
  python -m zipfile -e CYBR_Victorville_CA_Current_Source_Extension_v1.zip ca_source
