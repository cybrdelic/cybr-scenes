VICTORVILLE CB: ONE CONTINUOUS METRIC PAVEMENT EDGE
Current source extension v1. Original AV mountains and approved procedural materials retained.

REQUIRED FULL SOURCE
This add-on includes the complete previous CA extension, including BY, AZ/BW and the exact approved R5D microbed input. No separate CA/BY download is needed.
Keep the full AV v15 archive: CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15.zip, 13,559,633 bytes, SHA256 daae4846d4ef9506b01c40bfa9b1ecfd369fbd17f457d0a63c68f168a79aaa04. Library private-archive-reference-omitted version15. This remains an add-on, not a replacement for AV.

VISIBLE CHANGE
CA restored native asphalt through the first repair but retained a 7 cm smooth gap and 12.5 cm broad tile-edge fade. CB replaces the top once, from the exact existing physical broken rim to the native tile boundary at x=-3 m, over y=0..6 m. It removes the first native column's left fade. No second sheet is added. The actual rim XYZ, edge support and soil remain unchanged. The same original .25 m phase and .004 m height scale drive the new surface.

The candidate strip has 556,144 vertices and 1,089,792 triangles. Its pitch is approximately0.977 mm through y0..2 m,1.953 mm through2..6 m, with a0.977 mm native joining edge. This is a bounded adaptive preview representation. Full step1 strip construction has not been qualified. Inner native tiles must use the included stride2 LOD to match every joining edge sample. Do not arbitrarily substitute stride4 or skip this LOD after application.

ACTUAL PROOF
- Exact road/soil triangle-overlap checks found zero penetrating overlap polygons. This tests the continuous supporting meshes, not every discrete grain body.
- Unified topology found no unpaired non-native contact edges or overused edges. A pre-existing7.45 nm float32 vertical rim step is retained rather than silently welded.
- Actual Blender native-to-strip transformed seam error:9.82e-9 m.
- Full metric normal map is combined with the captured broad surface datum once. The existing displaced-edge material is reused; its BY wear is bound explicitly after the material pass.
- Matched1200x390 native crop from4000x2668 camera projection,32 CPU Cycles samples, qualified native-guide OIDN.141.86seconds,4313.56MiB sampled peak under4480MiB guard.
- Portable payload regeneration reproduced all24,936,054 bytes exactly, SHA256 aef0aee3894aa18f3353faffc4f3f824e99f953779cbd8933dce5578daaee5ee.15.66seconds,595MiB maximum recorded peak.
- The included combined wrapper ran on the retained admitted AV scene, including exact current supporting-mesh guards and the required stride2 boundary.33.25seconds,3005.61MiB recorded peak. No new scene was saved or rendered by that application proof.
- Fresh creation of AV from zero remains unverified. Pixel-identical rendering from the convenience wrapper is also unverified; the exact actual capture pipeline and settings are retained separately.

REPRODUCE
Requirements: Blender4.3.x (captured4.3.2), Python3 with NumPy. Use the full AV v15 instructions and ca_source/README.txt to obtain the admitted AV scene, matching semantic source_admission.json, and CA regeneration data. The CA command must write actual_road_fixture.npz and extension_payload.npz.

From this extracted directory:
  python verify_cb_extension.py --base-archive /path/to/full_AV_v15.zip
  python road_scene_r6/src/regenerate_continuous_edge_cb.py --ca-data /path/to/CA_data --height inputs/GeometryHeight.npy --output-dir /path/to/new_CB_data

The second command refuses mismatched exact input pins and reproduces edge_payload_step2.npz. Allow25MB new output. --verify-without-writing compares the exact compressed payload in memory instead.

To load and apply to a fresh admitted source in Blender, without saving or rendering automatically:
  blender -t 2 --python-exit-code 1 --python apply_current_cb_blender.py -- --base-archive /path/to/full_AV_v15.zip --av-scene /path/to/ASSEMBLED_SCENE_AV.blend --z-admission /path/to/source_admission.json --ca-payload /path/to/CA_data/extension_payload.npz --cb-payload /path/to/new_CB_data/edge_payload_step2.npz --output-dir /path/to/new_CB_application

Use a new output directory. The wrapper explicitly opens the selected source and runs prior admission/material/geometry guards. Save only to a new derivative chosen by the user. Background mode exits without saving. The actual render snapshots contain captured absolute cloud paths; they are evidence, not an unedited portable one-click render command.

The source adapter adds a full supporting-ground SHA check beyond the captured rendering adapter; the combined application proof exercises it. That stronger guard does not change geometry. The approved source recipes, scales, images and original mountains remain retained. Overall road and shoulder realism is unfinished; the pale uniform shoulder is being diagnosed separately.

All material/geometry source is procedural. Regional references were observations only. No scans, photo textures or generated imagery are used. Standard ZIP Deflate compression; Python extraction is supported with python -m zipfile -e.
