# CYBR GEO — Desert hot springs V11

This is an executed scene/renderer revision, not a generated-image edit. The supplied CYBR GEO `Assembly` and `Part` APIs construct and serialize the meshes. The supplied native triangle-intersection and SAH BVH code traces them. The renderer transports sixteen wavelength bins jointly and saves the spectral radiance before its RGB display transform.

The landscape is fictional and authored. It is not a survey of Desert Hot Springs, a reconstruction from photographs, a measured-material scene, or a geothermal simulation. The visual assessment is separate from the numerical tests.

## Reproduce the wide image

Tested here on Linux with Python, a C++17-capable g++ compiler and OpenMP. Install the pinned dependencies, then run from the package root:

```sh
python -m pip install -r cybr-geo/examples/desert_hot_springs/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=5 python cybr-geo/examples/desert_hot_springs/render.py \
  --out output --stem final --width 1920 --height 1280 \
  --spp 128 --water-spp 320 --depth 12 --no-glb --no-clouds \
  --indirect-clamp 0 --sun=-0.80,0.40,0.28 \
  --exposure 1.90 --white-balance 5750 --opaque-filter-strength .50
```

The recipe rebuilds the geometric scene when the recorded input fingerprints do not match. It compiles the actual native source, performs an optical smoke test, renders the frame, and writes both unfiltered and filtered outputs. Full geometry is generated from the recipe rather than included as a multi-gigabyte attachment. Building and rendering require several gigabytes of memory and are substantial CPU tasks. No GPU implementation or Windows-native execution is claimed.

Use `--view detail --stem shoreline --width 1200 --height 800 --spp 128 --water-spp 256` for the independent shoreline camera; preserve the other options above. Omitting `--no-glb` exports an additional full-scene GLB and requires more memory and disk space.

## Actual changes

- Replaced the broad terrain profile with an irregular ridge-and-spur network, hydraulic-particle erosion and drainage-correlated incision. The final terrain is not broadly smoothed back into low-detail hills.
- Replaced the previous hero-rock construction with highly tessellated joint-plane solids. Compact spall depressions are centered on the actual shell rather than mostly missing it from interior coordinates. Recomputed vertex normals follow the deformed geometry.
- Separated the foreground's coarse topography, thin accretion margins, granular geometry, small-scale normal detail and material variation. The existing gravel photograph supplies weak albedo detail and an explicitly authored granular support field, not measured displacement.
- Corrected the near-shore plant-rejection threshold; added actual curved stems and attached small leaves. Plant forms remain procedural, not scanned or botanically validated.
- Added an Oren–Nayar rough-diffuse term to the existing dielectric/GGX material model, with a sampled energy check. This is an approximate surface model rather than a measured BSDF.
- Refined the numerical quadrature of the reduced spectral sky. Near-observer samples now resolve the shallow aerosol layer instead of using a small number of uniformly spaced samples along the entire atmospheric ray.
- Represented the prescribed steam in a trilinear 3-D field and computed its tracking majorant from every grid vertex. Tests record both its approximation error against the authored analytic field and sampled transmittance against numerical integration. This is not CFD.
- Replaced archive-sized hash buffers in CYBR GEO scene I/O with streaming hashes. Released temporary geometry buffers before serialization. The source includes an exact round-trip, hash-equivalence, array-ownership and tamper-detection test.

## Files and evidence

The delivery has a wide native render, an independent shoreline render, a comparison using the previous frame's sun/exposure/white-balance/sample settings, source code, raw RGB/spectral buffers, and fresh named tests. The comparison setting does **not** restore V10's atmosphere implementation or materials; it is not a geometry-only ablation. The primary wide image has higher native resolution and a different exposure than V10.

Each native render writes:

- `.pfm`: unfiltered scene-linear RGB integrated from the transported bands;
- `.spectral`: width/height/band header followed by the sixteen-band radiance;
- `.guides` and `.samples`: geometric filtering guides and actual per-pixel sample budgets;
- `.json` and `_run_receipt.json`: actual completed settings, executed commands, compiler/binary/source fingerprints;
- `_raw.png`: the unfiltered accumulation after the declared display transform;
- `.png`: geometry-guided, non-neural radiance filtering followed by that same display transform.

No content is synthesized during finishing. The display transform is a global exposure, blackbody white balance, toe and highlight compression followed by sRGB encoding. No extra grain, generative upscaling, photographic backplate or compositing is used. Filtered PNGs should not be mistaken for unfiltered reference integrator output.

Export an unfiltered float32 EXR with:

```sh
OPENCV_IO_ENABLE_OPENEXR=1 python cybr-geo/examples/desert_hot_springs/export_exr.py \
  output/final.pfm output/final_linear.exr
```

Fresh delivery checks use `verify_v11.py`, not the older historical `verify.py` command. The latter retains helpers used by the renderer's display integration; its older main program is not the V11 delivery validator.

## Important limits

The transport uses sixteen fixed midpoint wavelength bins, not continuous-wavelength integration or measured spectra. Water has spectral absorption but a constant refractive index: dispersion is not modeled. Reflected/transmitted solar caustics use one-root macro-interface connections rather than a complete, unbiased all-root rough-interface solution. The sky is a reduced single-scattering atmosphere. Steam and ripples are prescribed fields, not coupled thermal/fluid dynamics.

Contribution clamping is disabled in the delivered runs. This does not remove the estimator/model approximations above or make the denoised image unbiased. Watertight optical water enclosures are not a certification of all scene geometry, plant biology, mineral formation, or visual realism.

All changes are local to this delivered snapshot. Nothing was pushed to GitHub; the upstream product/studio render defaults were not changed.

## License and asset origin

The supplied CYBR GEO source carries its GPL-2.0-only license; the included LICENSE is retained. The grayscale gravel crop and its derivative were already in the supplied source. Their inherited CC0 attribution and the V11 reconstructed-relief provenance are in `examples/desert_hot_springs/assets/`. No new scan, DEM, HDRI or paid asset was acquired for this delivery.

## Run the new checks

```sh
python cybr-geo/examples/desert_hot_springs/run_checks_v11.py --out output/tests
python cybr-geo/examples/desert_hot_springs/verify_v11.py --out output --views final
```

The first command compiles and executes the newly added material and steam-grid tests, exercises actual scene I/O, and records sky-quadrature convergence. The second independently reintegrates the saved spectral buffers, checks the completed render's sample budget and source receipt, and checks the two optical water enclosures. Add other completed view stems to `--views`; do not list a view that has not been rendered. Historical tests remain in the supplied source for context, but only the named freshly executed checks are claimed in the V11 report.
