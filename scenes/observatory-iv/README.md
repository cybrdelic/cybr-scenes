# CYBR — Quiet Observatory IV

A real, offline-rendered 3D scene. The project uses a native C++ spectral path tracer and the retained CYBR GEO triangle-intersection/BVH kernel. It does not use image generation, image editing models, neural textures, neural denoising, rendered-image upscaling, photography as a scene background, or painted fixes to the finished frame.

## Open the result

`renders/Observatory_IV.png` is the finished native-resolution image. `renders/Observatory_IV_unfiltered.png` applies the same display transform to the raw render without reconstruction. `renders/Observatory_IV_raw.exr` is untouched scene-linear RGB radiance, before reconstruction and the display transform. The optional raw-data download also contains the sixteen-band framebuffer and component outputs.

`scene/observatory_v4_inspection.glb` is a portable geometry inspection file. Its vertex-color materials are intentionally simpler than the native renderer's texture, anisotropic reflection, and dielectric shaders. The GLB is not a second renderer or an equivalent beauty render.

## Render the delivered scene

The compiled native renderer requires an AVX2-capable x86-64 CPU, a C++17 compiler with OpenMP, and CMake 3.16 or newer. GCC/Linux was executed for this delivery. Other toolchains are not claimed as tested. Rendering is CPU-only. Approximately 3 GB of available RAM is recommended for the production settings; more is useful for reconstruction and rebuilding.

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure

./build/observatory \
  --mesh scene/observatory.cvr2 \
  --out renders/reproduction \
  --width 1800 --height 1200 \
  --spp 96 --adaptive --depth 12 \
  --aperture .004 --threads 5 --bands

python -m pip install -r requirements.txt
./build/observatory --mesh scene/observatory.cvr2 --out renders/reproduction \
  --width 1800 --height 1200 --threads 5 --guides-only
python finish.py renders/reproduction
```

The output directory must exist. `--threads` changes CPU concurrency. `--adaptive` is **fixed geometry/material-based sample allocation**, not statistical stopping: the requested count is a base budget, not the count at every pixel. The JSON sidecar reports the actual minimum, mean, maximum, histogram, and camera-sample total. The `.samples` array contains the count at each pixel.

Available cameras: `hero`, `instrument`, and `workbench`. For a quick check, omit `--adaptive` and use `--width 480 --height 320 --spp 16`.

## Validate a delivery or reproduction

```bash
python verify.py --geometry-only
python verify.py --stem renders/reproduction
```

The first command checks the ready-to-render assets and native numerical tests. The second checks a newly rendered and finished output, including the lossless raw EXR conversion. Full checks on `renders/Observatory_IV` require the raw-data archive to be extracted alongside the ready-to-render project. The compact source archive requires `python build_scene.py` before rendering or geometry checks.

## Substantive changes

The prior interior GLB is retained as the source geometry asset. Materials and transport were reauthored rather than applying a color grade to an earlier render.

* The open front of the room is replaced with an actual wall and off-camera window. Two geometry-tested apertures guide environmental lighting. They are sampling distributions, not emissive cards.
* The new microfacet implementation uses anisotropic GGX visible-normal sampling, compatible evaluation/PDFs, and separate dielectric/metal behavior. Machining direction comes from each part's geometric axis; it does not jump when a mesh's planar texture projection changes.
* The spectral renderer transports sixteen wavelength bins. At a quartz interface it splits into wavelength-specific paths with shared random numbers, rather than assigning unrelated wavelength noise to individual pixels.
* Sun-like directional lighting, window importance sampling, and sampled material directions use multiple-importance weights. There is **no path-radiance clamp**.
* Camera-visible haze uses forced first-collision sampling with analytic transmittance and stochastic higher-order continuation. The latter has unbiased Russian roulette. Haze is a bounded homogeneous participating medium, not a simulated dust or atmospheric flow field.
* A separate geometry-only guide pass follows the dominant 550-nm refracted path through quartz, so reconstruction sees the internal instrument rather than only the globe surface. It is an approximation for mixed reflection/transmission and never changes raw radiance.
* Direct illumination, indirect illumination, and participating-medium radiance are saved separately and reconstructed separately. The finish is non-neural, guided by geometry, material, albedo and sample variance. It does not replace isolated bright pixels or mix back a noisy percentage of the original.
* New geometry includes a layered, curved open folio, chart paper, a slack linen runner, a gathered curtain, an optical rail with two closed lenses and focusing hardware, engraved-style horizon divisions, and a continuous terrain floor beyond the window.

## Assets and units

The scene uses metres and Z-up coordinates internally. The GLB root rotates it to Y-up for inspection. `scene/manifest.json` lists the retained/new parts, counts, bounds, materials, and hashes. `scene/observatory.groups` holds each part's machining axis and anisotropy.

Eleven mipmapped material maps contain linear albedo, surface normal and roughness. The wood, plaster, stone, brass, cloth and leather maps are deterministic mathematical textures authored by `build_scene.py`; they are not photographs or learned textures. The printed charts are programmatically drawn diagrams attached to real paper meshes. Rasterized text is baked into those maps. No font binaries are distributed.

To rebuild authoring assets and meshes:

```bash
python build_scene.py
```

The delivered texture binaries already contain the exact rasterized diagrams and do not need local fonts to render. Rebuilding the diagrams from scratch uses a locally installed DejaVu/Liberation serif font or a fallback; that can change typography on another system. Use the delivered scene and maps for exact asset reproduction.

## Important boundaries

This is an authored visual scene, not a physically validated historical observatory or a mechanical CAD design. Cloth folds and the landscape are constructed geometry, not cloth dynamics or DEM measurements. Apertures are open; the glazing bars do not imply modeled window glass.

The soft directional emitter has an authored angular diameter of about 4.9 degrees. It is **not the real Sun's angular diameter** or a calibrated atmosphere simulation. Environmental spectra and most reflectances are authored smooth functions, not measured material data. The CIE observer approximation and fixed 25 nm quadrature have finite accuracy. Quartz uses an ordinary-ray dispersive index; birefringence, polarization, diffraction and fluorescence are not modeled.

The raw result contains Monte Carlo sampling error. Reconstruction reduces that noise but also changes some small highlights and fine illumination detail; it is not a proof of convergence. `verification/` records numerical checks and executed renders, not a claim of photographic equivalence. Changing the scene, light distribution, camera and shaders means the old and new beauty renders are not a controlled noise benchmark.

## Project layout

`src/` — complete native renderer, spectral model, sampler, mesh acceleration and texture loader.

`build_scene.py` — full geometry/material authoring recipe.

`finish.py` — component-separated non-neural reconstruction and raw EXR export.

`verify.py` — archive/geometry/material/output checks.

`assets/` — retained geometry input and generated material previews.

`scene/` — ready-to-render mesh, machining attributes, maps and inspection GLB.

`renders/` — executed outputs and their per-render metadata.

## Licensing and provenance

The retained CYBR GEO native intersection/BVH/sampler source is distributed under its existing GPL-2.0-only terms. The native scene extension and authoring/finishing code are distributed under GPL-2.0-only. The retained input geometry comes from the preceding delivered CYBR Observatory rebuild. No external renderer binary, font file, or image-generation output is bundled. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
