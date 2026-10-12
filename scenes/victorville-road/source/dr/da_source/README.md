# DA source-relative sand burial

This additive work-in-progress preserves the CQ road, original AV mountains, CN authored warm regional reflectance, CO 22-degree daylight, and exact CZ fine-grain dimensions/material. It changes only Z of newly restored sand bodies to account for their original R5D microbed reference height.

## Actual result and limitations
The 900 x 675, 48-sample raw Cycles CPU close view retains 55,620 sand instances and identical XY, specimen index, yaw, geometry and material. Measured offsets range 26.64–101.34 micrometres. The local-plane test classifies 25,254 bodies below that plane after adjustment. This is pointwise source-bed support, not full-footprint intersection against the original varying microbed. Dark angular contrast remains strong and the change is modest. The persistent centimetre-scale dark patch exists in the baseline; its cause is separately audited and is not presumed to be floating sand.

The old 64 chip/grit specimens use a different float32-centroid extraction datum; their offsets are unqualified and are NOT applied. New sand uses the fully traced original particle origin. Geometry counts, XY and particle volume are unchanged; no mass-conserving transport claim is made.

The 2000 x 1334 whole view uses the same 1000px physical geometry allocation as the prior CZ wide, so increased output sampling is isolated from changing its allocation. 1024 context maps plus native 1101 AZ fine-bed fields remain unchanged. Subpixel grains have no individually resolvable silhouette at distance. Full source population and exact far-field transport are not represented by this finite LOD.

## Required parent and preparation
This is an additive checkpoint requiring the public CQ source v2 (manifest SHA256 58cb6c55c74e4fb153c525260f670dc0761806ae3ff32442e6a547a60ed4f1f4) and a prepared CQ capture. The bundled CZ source handles its own exact parent pipeline validation. See CZ documentation for the inherited AV reconstruction and public-wrapper replay limitation.

    python cz/prepare_addon.py --cq PREPARED_CQ --out NEW_CZ_CLOSE --mode close
    python da/prepare.py --cz NEW_CZ_CLOSE --out NEW_DA_CLOSE
    python cz/prepare_addon.py --cq PREPARED_CQ --out NEW_CZ_WIDE --mode wide
    python da/prepare.py --cz NEW_CZ_WIDE --out NEW_DA_WIDE --width 2000 --height 1334 --shadow-probe

Run each generated runtime/pipeline/clean_render_landform_candidate.sh with its job.json under the provided parent resource guard, Blender 4.3.2 and two CPU threads, serialized against other heavy jobs. Staging was verified to reproduce the exact native-image pipeline manifest. A separate fresh end-to-end public-wrapper scene rebuild is not claimed.

## Rebuild measurements
Pinned original microbed data is included; it is procedural data, not a photo. Original builder and normalized fracture inputs are in cz/inputs. NumPy 2.3.5 was used.

    python da/extract_source_datums.py cz/inputs/build_diagnostic.py cz/inputs/fracture_solids.json NEW_witnesses.json
    python da/build_source_datums.py NEW_witnesses.json da/inputs/microbed.npz cz/inputs/build_diagnostic.py NEW_datums.json

The bank dimensions and original per-particle colors/roughness remain in the bundled CZ source. Existing shader, camera and terrain source dependencies remain pinned in CQ; they are not duplicated here.

Original procedural Victorville-inspired scene, not a surveyed site reconstruction. No scans, photo textures or image generation. Qualitative local soil palette bounds remain USDA Bryman and Cajon descriptions; authored RGB is not a calibrated Munsell conversion:
https://soilseries.sc.egov.usda.gov/OSD_Docs/B/BRYMAN.html
https://soilseries.sc.egov.usda.gov/OSD_Docs/C/CAJON.html
