# CYBR — Drowned Geode V2

A new execution of the flooded-cavern scene with revised geometry and a substantially revised native CPU renderer. The original camera and 1600 × 1000 framing are retained. No image-generation model, generated background, inpainting or generative denoiser is used.

![Drowned Geode V2](output/Drowned_Geode_V2.png)

## What changed

### Light transport and noise

The first camera-visible water interface now evaluates **both Fresnel reflection and transmission**, with their correct weights, instead of choosing one contribution by roulette. These terms are not painted or composited from unrelated views. The same scene is traced along each direction.

The underwater renderer now directly samples the sky through the **actual water triangle interface**, checking Snell refraction, total internal reflection, Fresnel transmission, wavelength-dependent absorption, scattering extinction, and geometry visibility. Multiple-importance weights reconcile this estimator with BSDF/phase sampling. Previously, the underwater sky contribution depended mainly on indirect paths happening to escape through the surface.

The new authored haze medium is bounded and homogeneous. Its beam transmittance is analytic. Camera samples evaluate both the surface-survival term and a forced first-scattering term, with full multiple-scattering continuation thereafter. This replaces the old heterogeneous authored density; it is a real change to the scene's medium, not a claim that the two density fields are identical. No fluid simulation was run.

The sampler uses per-pixel digital shifts over a 1024-dimensional, linearly scrambled Sobol net. The renderer allocates samples **deterministically from primary material/depth**: fewer samples for the visible sky and distant opaque walls, more for camera-visible quartz. The allocation does not stop sampling based on noisy values already accumulated. The nominal command-line setting is not a uniform sample count; actual minimum, mean, maximum and histogram are recorded in render metadata and the per-pixel sample-count array.

The same SAH geometry hierarchy is converted to a **BVH4 with SIMD bounding-box tests and AVX2 triangle packets**. This does not simplify geometry. A dedicated opaque-hit mask skips water during visibility tests without repeatedly tracing to its nearest surface. Compilation disables floating-point contraction to keep scalar and SIMD intersection arithmetic consistent. Each render compares 5,000 rays against the scalar reference traversal before starting.

### Geometry and materials

The vault has finer tessellation, actual bedding relief and revised fracture shape. The unsupported thin bridge and conspicuous isolated block-like wall inserts were removed. A real outer shell closes the exposed rock thickness around the roof aperture.

Quartz nuclei are now ray-anchored to the surfaces of the photographed rock meshes. Larger points and smaller druse use separate spacing/size ranges; inclusions are less conspicuous. The half-space crystal builder and ordinary-ray quartz index equation are retained from the supplied quartz project.

The water has longer, lower-frequency ripples, while the bed material separates pale silt from explicit pebble geometry. Surface texture footprints accumulate travelled distance through specular paths instead of restarting at each interface. Rock shading adds bedding-correlated mineral coloration and less mirror-like wet roughness.

### Finishing

The renderer writes **primary-water reflection, first atmospheric scattering, and total radiance separately**. The base term is their scene-linear remainder; it includes water transmission and opaque-surface lighting. Each component is denoised with appropriate geometry guides, then recombined in linear light.

Water reflection is no longer divided by and reconstructed from the *submerged floor's albedo*. This was an important weakness of the previous finishing pass. The new reflection guides follow reflected scene geometry; base guides follow transmitted geometry; haze uses primary depth. High-frequency shading-normal textures are not used as hard geometric boundaries in the filter.

Filtering is non-neural and necessarily trades some detail for lower Monte Carlo noise. Optional variance-gated compression of isolated bright outliers is applied **only to the viewing pipeline**. Its affected-pixel count is recorded. It can suppress genuine unresolved highlights; this is explicitly a biased display regularization, not an unbiased caustic solver. Use `--no-outlier-control` to disable it. All raw RGB, spectral and component buffers are untouched.

## Reproduce

Tested on Linux x86-64 with AVX2, five CPU threads, Python 3.13 and a C++17/OpenMP compiler. The included photographed source assets and bundled Sobol directions eliminate runtime downloads. Keep approximately 2 GB free for working geometry, converted textures and render buffers.

```bash
python -m pip install -r requirements.txt
bash build.sh
bash render_final.sh
```

`build.sh` rebuilds the geometry and compiles the direct V2 source. The preserved V1 generator in `src/assemble_renderer_v1.py` is historical reference, not the V2 build path.

A faster scene preview:

```bash
./cavern_v2 assets/built/scene.meshbin output/preview \
  --w 640 --h 400 --spp 32 --depth 20 --threads 5 \
  --seed 20260922 --exposure 1.13 --no-bands
python finish_v2.py output/preview
```

The delivered hero uses:

```bash
./cavern_v2 assets/built/scene.meshbin output/Drowned_Geode_V2 \
  --w 1600 --h 1000 --spp 64 --adaptive --depth 20 --threads 5 \
  --seed 20260923 --exposure 1.13
python finish_v2.py output/Drowned_Geode_V2
python verify_v2.py
```

Omit `--adaptive` for a uniform sample count. Increasing the sample count continues to improve difficult light paths; this delivery is not represented as noise-free or mathematically converged.

## Outputs

- `output/Drowned_Geode_V2.png`: denoised, tone-mapped viewing image.
- `output/Drowned_Geode_V2_unfiltered.png`: raw radiance with the same display curve, no spatial filtering.
- `output/Drowned_Geode_V2_raw.exr`: untouched scene-linear RGB.
- `output/Drowned_Geode_V2.spectral`: sixteen untouched spectral radiance bands.
- `output/*_reflection_raw.exr`, `*_volume_raw.exr`, `*_base_raw.exr`: untouched linear component outputs.
- `output/*_denoised.exr`: linear output after viewing-only regularization and filtering, explicitly not raw.
- `output/*_guides.npz`: actual base, reflection and primary geometry guides.
- `output/*_sample_counts.npy`: exact camera-sample allocation per pixel.
- `output/*.json`: settings, timing, sample distribution and finishing details.
- `verification/validation.json`: geometry, optics, traversal and output checks.
- `verification/sampling.json`: Sobol one-dimensional stratification tests.

Native `.pfm` and `.guides` outputs are rebuilt by the renderer. The full delivery archive preserves the equivalent lossless EXR/NPZ data; `finish_v2.py` reads either representation without another render. The smaller source archive contains source, original assets, documentation and the viewing render, not the full framebuffer data. All raw image formats are distinct from the denoised PNG.

### Comparison sheets

`python create_comparisons.py` produces a same-camera overview and native-pixel crop sheets from the included previous finished image. The sheets compare two finished images with changed geometry, materials, haze and transport. They are not an equal-scene statistical noise benchmark.

### Structural/numerical checks

The audit checks finite mesh data, watertight outward-oriented water and quartz components, the agreement of water displacement and analytic normals, Fresnel/Snell/Beer–Lambert checks, finite radiance and lossless raw-EXR preservation. Small solid volumes are computed in float64 around a local origin: float32 volumes about the distant world origin suffer cancellation at the druse scale.

A separate rebuild directory is used to compare the scene, material files and crystal-anchor records byte for byte. These are reproducibility checks, not visual quality scores or proof of geological accuracy.

## Limits and provenance

The sixteen spectral bands are a fixed 25 nm quadrature from 380–780 nm. Large quartz points split into wavelength-dependent paths; small druse uses the 550 nm index as an achromatic optimization. Water's index is achromatic, with wavelength-dependent absorption. RGB photographs are approximately spectrally upsampled. Quartz is represented with its ordinary-ray index only: no polarization, birefringence, atomistic growth or measured inclusion distribution is claimed.

The sun/sky, haze density, cave shape, material variation, water displacement and mineral placement are authored. The water/sun connector is specialized; this is not a general specular-manifold path tracer or a general arbitrary-overlap medium-stack implementation. Finite path depth and view filtering remain approximations. The cavity and material detail still have procedural/CG qualities, especially at close inspection.

The original CPU renderer, scanned boulders and photographed material maps come from the supplied CYBR Desert Hot Springs V3 source. The crystal facet construction and index equation come from the supplied Spectral Quartz source. No new photographs or generated assets were downloaded. The original scene's camera is preserved for comparison.

See `docs/README_V1.md`, the preserved upstream source and `assets/ORIGINAL_ASSET_README.md` / `assets/ORIGINAL_V2_README.md` for original provenance. The source's supplied GPL-2.0-only license is preserved. The supplied Poly Haven photographic assets were identified as CC0 in their manifests; author attribution remains in the original asset readmes. The quartz archive did not supply a standalone license; no new license grant over it is asserted here.

Sampling reference: *Physically Based Rendering*, fourth edition, Sampling and Reconstruction — https://pbr-book.org/4ed/Sampling_and_Reconstruction . Bundled Sobol directions were generated through SciPy's Sobol implementation; see `src/make_sampler.py` and `THIRD_PARTY_NOTICES.md`.
