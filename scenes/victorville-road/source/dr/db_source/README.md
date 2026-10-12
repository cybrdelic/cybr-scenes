# DB actual-terrain shading-normal repair

The matched DA receiver check found the central dark patch on the continuous soil mesh, with no solar-ray blocker. Its actual triangle solar cosine was 0.376, but one stored corner normal was tilted about 46 degrees with cosine -0.119. Nearby corners repeated the unsupported tilt. The composite and AZ source maps did not contain a corresponding dark centimeter-scale feature.

DB resets broad normals on the two continuous soil meshes to Blender's automatic geometry normals, retaining the existing smooth/sharp topology. At the same receiver the three corrected corner cosines are 0.377–0.380. It does not alter any coordinates, topology, smoothing flags, grain body, material graph, texture, light, camera or original mountain. Metric R5D/AZ grain normal/bump fields remain in their shaders. Separate rock faces are not globally smoothed.

Left soil: 47,412 of 5,805,491 corners changed by more than 5 degrees; 22,590 by more than 20 degrees. Broad normals now follow current actual geometry. Old below-grid analytic broad-normal detail is not retained, so this is explicitly a scene-shading repair, not proof that far tessellation resolves every original field.

Requires the bundled CZ/DA modules and prepared public CQ source v2 described in their READMEs. For the matched close:

    python cz/prepare_addon.py --cq PREPARED_CQ --out CZ_CLOSE --mode close
    python da/prepare.py --cz CZ_CLOSE --out DA_CLOSE
    python db/prepare.py --da DA_CLOSE --out DB_CLOSE

For the whole view, stage CZ with --mode wide, DA with --width 2000 --height 1334, then DB. Use spaces between each option and its value. Run the prepared clean_render_landform_candidate.sh with job.json, two CPU threads and the fixed 4480 MiB aggregate guard. The matched DB whole view was rendered at 2000 x 1334 with 32 raw samples, taking 435.93 seconds and 3741.40 MiB guarded peak. The package includes its exact image hash, source-pipeline pin and render evidence. Its native 900 x 550 crop preserves every original 16-bit pixel without resizing or grading.

The portable DB stager reproduces the actual close pipeline manifest 4dbfd82ce5edc244532559a7bd58da0609664f1899deb3301973c31f58dbcaee. Full public-wrapper replay remains separately unverified; the original AV-to-CQ recovery and subsequent captures were actually executed.

This work remains a representative authored Victorville-inspired scene. Fine sand is 0.159–0.641mm, never enlarged to make it visible at distance. Coarse fragment shape and the broad smooth worked margin remain visual limitations.
