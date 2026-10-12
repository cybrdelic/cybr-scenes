# CA metric pavement coverage extension

This corrects a representation limit in the retained road scene. The original dense asphalt recipe was physically instantiated only from y=0 to 2 metres. The first authored maintenance patch spans y=3.36 to 5.40 m. Its distant portion therefore had shader normals but lacked the same real aggregate relief.

CA extends the unchanged 0.25 m native tile bank through y=6 m, with the original 4 mm height scale. The old y=2 far fade becomes an interior seam; the far fade moves to y=6. Original mountain objects, AZ/BW ground response and BY road wear remain unchanged. This is neither a new mineral recipe nor a calibrated asphalt-aging model.

## Contact and field preservation

- Cuts the actual retained Blender loop triangles, preserving all exterior source coordinates, POINT attributes and both source face-material assignments.
- Removes exactly 11 square metres of base beneath the additional native interior. It does not leave a second sheet below the aggregate.
- Uses a three-sided conforming collar. The first topology test exposed 156 unmatched side-join segments at y=2; the corrected construction splits the collar to the exact inherited edge sequence. The corrected actual-source test has zero unmatched non-native boundary edges and zero overused edges.
- Shares nine original geometry templates among 264 instances. Full affine parent inverses retain the road grade/crossfall. Runtime validation checks all 493 adjacent pairs at 513 boundary samples per pair.
- Extends the packed RGBA32F scene-field lookup at the same 2 mm lattice. All 1,041 original rows are copied exactly; new rows use barycentrics on actual road triangles. Channels remain macro tint, edge inset, deposit depth and original paint reference height. The white stripe and deposits use the same displaced surface.
- Source `.blend` is never overwritten. No new full-scene cache is saved.

## Evidence and reproduction

`export_source_fixture.py` extracts the exact retained AV road and source lookup without rendering. `metric_extension_math_ca.py` produces the numerical extension payload. `metric_pavement_extension_ca.py` installs it in memory after exact source-array and payload checks. The capture job invokes that adapter before camera culling and preview LOD.

The first fixture export refused an unexpected EDGE attribute. The corrected exporter handles its actual all-false sharp-edge array and the two face-material assignments. Original failed receipts are retained.

This checkpoint has been tested against the retained AV cache. A fresh complete AV source rebuild followed by this extension is not yet verified. The exact cached payload is a replaceable acceleration input, but its hash is required by the current capture job.

The comparison crop uses 4,000 × 2,668 camera projection and an actual 1,200 × 390 crop, 32 Cycles CPU samples, documented stride-two (~0.977 mm) native geometry preview and 1,024 px texture mips. Fine shoulder particles retain their earlier finite allocation; this does not claim native-4K material fidelity. Final guided cleanup is valid only if the retained guide contract and resource receipt pass.
