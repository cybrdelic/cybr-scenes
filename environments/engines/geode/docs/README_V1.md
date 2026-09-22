# CYBR — Drowned Geode

A new, metre-scale flooded mineral cavern, constructed and **actually rendered** from components in the two supplied projects. This is a triangle scene with native CPU light transport—not an image-generation result, a painted backdrop, or a generated-image-to-3D conversion.

![Drowned Geode](output/Drowned_Geode.png)

## Delivered scene

An irregular collapsed roof admits warm sunlight into a cool flooded chamber. A continuous displaced stone vault surrounds a submerged mineral floor, photographed rock scans, fallen rubble, quartz seams, small druse, and hanging roots. Water has a closed displaced boundary and participating-medium transport; haze occupies a bounded three-dimensional region. All geometry is authored in metres.

The main render is **1600 × 1000, 64 camera samples per pixel, up to 18 path vertices, 16 spectral bands**, executed on five CPU threads. The scene contains **2,069,866 triangles**. Render metadata records the actual elapsed execution time, seed, BVH size, sample diagnostics and spectral means. The alternate-camera clay render is 900 × 600 at 20 samples per pixel, without water or haze, to make the underlying geometry easier to inspect.

## What was reused, and what changed

The uploaded CYBR GEO native `spectral_geometry.h` supplies the SAH BVH, triangle intersections, rays and random generator. Its `spectral_desert.cpp` supplies the starting spectral transport, GGX surface sampling, heterogeneous-medium tracking, and numerical water/sun connection. These originals are preserved in `src/` beside the extension.

From the quartz source, `growth.py` supplies the half-space crystal facet construction. The ordinary-ray quartz refractive-index equation from `spectral.py` was ported into the native transport. Crystal placement, sizes and orientations in this scene are authored; the diffusion/growth time integration is **not** run here.

The original scanned boulder geometry and photographed material maps are reused. The cave, roof opening, water boundary, pool bed, quartz layout, rubble placement and roots are new. There is no reused desert backdrop, mountain mesh, ice scene or sky panorama.

Native-renderer additions include:

- A CVR2 mesh adapter preserving per-corner UVs, vertex colours and texture IDs; bilinear/trilinear mipmaps and triplanar wall texturing.
- Two non-emissive sky-sampling portals, with visibility checked against actual geometry and multiple-importance weighting.
- Wavelength-dependent path splitting at macro quartz interfaces. All sixteen wavelengths follow their own refraction direction, using correlated random numbers to reduce colour variance. The small druse uses the index at 550 nm as an achromatic optimization.
- Scattering events within the water volume, with continuation for subsequent scattering, and the inherited wavelength-dependent absorption.
- New bounded cavern-haze density and a geometry-aware, variance-guided **non-neural** finishing pass.

The executed renderer is this **native CYBR GEO C++ extension**. The supplied photographic examples also contain a Mitsuba adapter, but Mitsuba was not installed in the execution environment and could not be installed there. No Mitsuba render is claimed for this delivery.

## Reproduce

Requirements: a 64-bit Linux environment, a C++17 compiler with OpenMP, Python 3.11 or newer, and the packages in `requirements.txt`. The tested environment was Python 3.13.5. Keep at least 2 GB of working space for intermediate assets and output. The delivered source package includes the necessary original photographic assets; no download or access to a repository is required after the dependencies are installed.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Rebuild approximately 300 MB of native geometry plus filtered texture assets.
python build_scene.py

# Assemble the complete C++ extension from the preserved original and additions.
python src/assemble_renderer.py
g++ -O3 -std=c++17 -fopenmp -fno-math-errno src/cavern.cpp -o cavern

# Render the main image, the separate-camera clay check, finish, and verify.
bash render_final.sh
```

`-march=native` was additionally used for the delivered local executable. It is optional; omit it for a more portable build. `render_final.sh` does not rebuild assets or compile the renderer, so perform the preceding steps first. To render a faster preview:

```bash
./cavern assets/built/scene.meshbin output/preview \
  --view hero --w 720 --h 450 --spp 24 --depth 16 \
  --threads 5 --seed 20260920 --exposure 1.15 --no-bands
python finish.py output/preview --exposure 1.15 --iterations 4
```

For a higher-sample image, change `--spp` to 256 or 512 in the full render command. Runtime increases with samples, pixel count, path depth and the fraction of paths interacting with quartz. Available camera views are `hero`, `detail`, and `reverse`. Diagnostic options include `--clay`, `--no-water`, `--no-steam`, `--no-split`, `--no-bands`, `--aperture`, and `--water-absorption`. `--no-split` is an achromatic-quartz comparison, not a switch from spectral to RGB rendering.

## Raw data and viewing images

- `output/Drowned_Geode.png`: the finished viewing image.
- `output/Drowned_Geode_unfiltered.png`: the same exposure and display curve, without spatial filtering.
- `output/Drowned_Geode_raw.exr`: untouched float32 scene-linear RGB converted directly from the native framebuffer. No denoising, radiance clamping, or tone mapping is applied to this file.
- `output/Drowned_Geode_guides.npz`: actual camera-ray normals, albedo, depth, material ID and Monte Carlo variance used for finishing.
- `output/Drowned_Geode.spectral`: untouched float32 radiance for all sixteen bands, when included in the full raw package. A fresh render produces it unless `--no-bands` is specified.
- `output/Drowned_Geode_Clay.png`: separately rendered alternate-camera geometry view, not a recoloured beauty image.
- `output/verification.json`: numerical and geometry checks, not a photorealism score.
- `output/source_provenance.json`: input archive hashes, source reuse and environment details.

Finishing first applies viewing-only, variance-gated compression of isolated bright sample outliers, then four iterations of a variance/normal/depth/albedo-guided A-trous filter, followed by the fitted ACES display curve and the sRGB transfer function. There is no neural denoiser, inpainting, texture synthesis, image generation, or manual pixel painting. The outlier compression is a biased viewing regularizer: it prevents individual underconverged paths from spreading into bright blotches, but can suppress genuine unresolved glints. The renderer, spectral buffer, unfiltered display and raw EXR are not altered. Its parameters and affected-pixel count are recorded in the JSON; use `--disable-outlier-control` with `finish.py` to omit it. The unfiltered display image and raw EXR make its effect inspectable. `finish.py` can use either the native PFM/guides files or the delivered EXR/NPZ equivalents.

The renderer's native PPM uses a different, older shoulder curve and is a diagnostic output only; the delivered PNGs are produced by `finish.py`. Linear RGB has an associated `film_white_rgb` normalization in the JSON metadata. Use that normalization and the recorded exposure to reproduce the supplied display image.

### Binary formats

`CVR2`: four ASCII bytes, one little-endian uint32 triangle count, then 36 little-endian float32 values per triangle: positions 9, vertex normals 9, material ID 1, legacy scalar 1, UVs 6, vertex RGB 9, texture ID 1. IDs are encoded as float values. Rebuilt textures use the adapter's documented native header and channel layout.

`.spectral`: four little-endian uint32 values (magic `0x36315053`, width, height, 16), followed by row-major float32 `[height, width, 16]`, top row first. Band centres are `392.5 + 25*k` nm for `k=0…15`. These are spectral radiance estimates, not a false-colour image.

Native `.guides`: width and height as little-endian uint32, then float32 `[height, width, 9]`: normal XYZ, albedo RGB, depth, variance, material ID. PFM is RGB float32, bottom-up rows, negative scale for little-endian values. The EXR and NPZ equivalents avoid custom readers for normal inspection and finishing.

## Validation and limits

The geometry and texture assets were also rebuilt from the **included portable inputs**, in a separate directory. All mesh and converted-texture hashes matched byte for byte; see `output/portable_rebuild_verification.json`. `python audit_outputs.py` additionally checks raw/guide finiteness, lossless EXR preservation of the native framebuffer when PFM is available, and independent reconstruction of RGB from the sixteen spectral channels.

`python verify.py` checks finite mesh data, water edge manifoldness and signed volume, Fresnel normal-incidence behaviour, Beer–Lambert composition, a Snell-law check, sampled haze-density bounds, visible quartz dispersion ordering, and agreement between the water surface gradient and the builder. It also reads completed render metadata and requires zero recorded non-finite path samples.

This is an experimental specialized renderer, **not a claim of reference-integrator equivalence or a physically exhaustive simulation**. The haze field, cave erosion, wave displacement, quartz placement, sun/sky spectrum and water absorption parameters are authored. The surface is not driven by CFD; no erosion, crystal-growth evolution or thermal solver was run. Water IOR is achromatic. RGB photographs are approximately spectrally upsampled. Quartz uses one ordinary-ray index: no birefringence, polarization or measured inclusion statistics. The native water/sun connector is specialized, not a general specular-manifold solution. The medium handling is not a general arbitrary-overlap dielectric stack.

Sixty-four samples per pixel is not a convergence guarantee, especially for spectral caustics and multi-interface paths. Remaining noise and denoising softness can be inspected in the unfiltered PNG and raw EXR. The scene is not a survey of a real cavern; the structural tests do not certify geological plausibility or photorealism.

## Asset attribution and licensing

The project preserves CYBR GEO's supplied GPL-2.0-only license in `LICENSE`; upstream source files remain available. The source ZIPs supplied the following photographic assets as CC0 assets from Poly Haven:

- Boulder 01 — Rico Cilliers.
- Namaqualand Boulder 02 — Greg Zaal and Rico Cilliers.
- Namaqualand Boulder 03 — Dario Barresi and Jenelle van Heerden.
- Brown Mud Rocks 01 — Rob Tuytel.
- Rock Boulder Dry — photography by Dimitrios Savva; processing by Rico Cilliers (attribution preserved in `assets/ORIGINAL_V2_README.md`).

`assets/ORIGINAL_ASSET_README.md` and the copied asset manifests preserve the original attribution context and source URLs. The original sky panorama, terrain tiles, and ice image assets are not used here. The quartz files preserve their supplied source; the quartz ZIP did not include a standalone license file, so this package does not assert a new license grant over those upstream files.
