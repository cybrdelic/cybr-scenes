# Spectral quartz growth

## Fractured ice extension

The September 14 extension adds an actual Mitsuba spectral volume path trace of
fractured ice, trapped air bubbles, a cloudy internal fracture and a thin puddle
on dark slate. See [README_ICE.md](README_ICE.md) for the exact render command,
optical-data sources, validation and numerical limits. The original quartz
renderer, assets and outputs remain below.

A reproducible, entirely procedural 3D quartz specimen and an illustrative
crystal-growth timelapse. The principal crystals use wavelength-dependent
ray directions, Fresnel reflection/refraction, total internal reflection and
path-length-dependent spectral absorption. There are no generated photographs,
billboard crystals or image-to-video assets.

## Revised still

`specimen.py` rebuilds the scene with ten asymmetrically arranged principal
crystals, alternating terminal-face offsets, a fractured mineral matrix,
fine secondary quartz, restrained growth striae, enclosed air fissures,
a neutral studio lighting environment and a thin-lens camera. Every visible object is rendered
geometry. The layout and aspect ratios are artistic remappings of the retained
moving-facet history; the solute field is not rerun for that remapped layout.
The legacy animation and its scene remain available in `animate.py`.

Reproduce the revised still with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4 python -c 'import specimen; specimen.dr.set_thread_count(4); specimen.main()' --width 1100 --height 1280 --bands 16 --spp 16 --reference-spp 256 --mode cv --mist 0 --name quartz_revision_final
python package_revision.py --name quartz_revision_final
```

This traces 768 camera paths per pixel: 256 independent reference spatial/path
samples plus 16 wavelength bands with two paired 16-sample renders per band.
The paired correction uses common samples; it is not another 512 independent
spatial samples. Every reference path carries four sampled wavelengths; the
correction traces each wavelength with its own refracted direction.

The revised still does not use the previous whole-image Gaussian prefilter or
nonlocal-means smoothing. OIDN denoises the reference radiance. A cross-bilateral
filter denoises only the signed dispersion correction, guided by that reference
(radius 3 pixels, spatial sigma 1.25 pixels, guide sigma 0.055). This is a biased
display reconstruction; the unfiltered reference, signed correction and their
sum are retained as separate EXRs for inspection. The
`--mode spectral` option performs direct wavelength quadrature. The
`--mode cv` option uses a nondispersive spectral reference plus paired,
common-random-number traces of the wavelength-dependent refraction correction.
The latter is a control-variate estimator, not an RGB approximation to dispersion:
both members of every correction pair are actual path traces. The reference
traces four spectral samples on each shared nondispersive path, with separate
wavelength-dependent absorption in every lane. Finite quadrature error and Monte
Carlo noise remain. Air fissures use the reciprocal quartz-to-air index ratio.

The original rendering and finishing settings below describe the earlier still
and the retained animation. The revised still's exact command and settings are
recorded in `output/quartz_spectral_hero.json`; it uses `specimen.py` instead of
`render.py`. `assets/revised_crystals.obj` exports its ten principal crystals.
The older `assets/final_crystals.obj` exports the original 18-crystal arrangement.

## Outputs

- `output/quartz_spectral_hero.png`: finished, denoised specimen render.
- `output/quartz_spectral_hero_raw.exr`: unfiltered linear RGB radiance after
  integration of the spectral bands. The EXR is not a 32-channel spectral cube.
- `output/quartz_spectral_growth.mp4`: independently rendered growth states.
- `output/*.json`: render settings and timings.
- `assets/growth.npz`: moving-facet history and final solute concentration grid.
- `assets/final_crystals.obj`: geometry-only export of the 18 principal crystals.
- `assets/growth_diagnostics.json` and `assets/validation.json`: numerical checks.

## Reproduce the original animation and scene

Use Python 3.12 on Linux with an LLVM-capable CPU. No GPU is required.

```bash
python -m pip install -r requirements.txt
python growth.py
python validate.py
python render.py --width 1600 --height 1200 --bands 32 --band-spp 16 --name quartz_spectral_hero
python animate.py --frames 36 --fps 12 --width 640 --height 480 --bands 16 --band-spp 4
```

The scripts use eight CPU threads by default. Set `dr.set_thread_count()` in
`spectral.py` to suit the machine. The renderer is CPU intensive. The animation
can resume with `--start N`; each completed frame is checkpointed separately.
Use square power-of-two samples per band (4, 16, 64, 256) with the low-discrepancy
sampler. Rendering with 64 samples per band improves spatial convergence.

`--bands` sets the number of wavelength quadrature nodes, rather than three RGB
light simulations. Every band traces its own rays through the current geometry.
The renderer also contains a continuous hero-wavelength Monte Carlo camera mode
for experimentation; the delivered images use the quadrature mode.

## Optical model

`spectral.py` implements an isotropic dielectric using Ghosh's room-temperature
ordinary-ray refractive-index equation for alpha quartz. Wavelengths are measured
in nanometers, and converted to micrometers in the equation. At 400, 550, and
700 nm, the indices are approximately 1.557731, 1.545948, and 1.540614.

The production integrator uses midpoint quadrature over 360–830 nm, with one
refracted path per wavelength and spatial sample. Identical random-number
sequences across wavelength bands reduce gratuitous chromatic variance on
neutral, nondispersive surfaces. This is finite-band spectral integration, with
quadrature error; it is not an infinitely resolved spectrum. Mitsuba converts
each contribution through its CIE color-matching functions to linear RGB.
The neutral-unit-environment check measured about 0.4% maximum channel error
with 32 bands and about 2.45% with the 16-band animation setting.

The principal crystal geometry is closed and outward-facing. The custom
dielectric uses exact unpolarized Fresnel probabilities and the radiance-mode
index-squared transport correction. Quartz birefringence, polarization and wave
optics are not included. This ordinary-ray approximation cannot reproduce double
refraction. The violet and smoky absorption profiles are artistic choices,
not measured spectra from particular specimens. Beer attenuation is evaluated
on interior segments ending at crystal interfaces; it does not fully account
for host attenuation before a ray terminates on an embedded opaque inclusion.

In the original scene, the tiny pale surface grains use a nondispersive rough
dielectric/plastic appearance proxy; their detailed internal transport is not resolved. The original 18 principal prisms use the spectral quartz shader. The revised
scene uses ten principal spectral crystals and nondispersive rough-dielectric
secondary grains. The specimen matrix, flecks,
microrelief and lighting environment are generated from code. Surface striae are
bump-mapped relief; major facets and inclusions are actual triangle geometry.

## Growth model

The 18 principal seeds start with small faceted nuclei. Their shapes are
intersections of six prism planes, six terminal planes and a base plane.
Direction-dependent attachment coefficients advance the faces in response to
local supersaturation. A six-neighbor, conservative finite-volume reservoir
diffuses solute around the static mineral-matrix mask. Facet-centered sinks
deplete the reservoir. Faces have different velocities, so this is not uniform
scaling of a completed crystal mesh.

The parameters are nondimensional and illustrative. Nuclei are prescribed;
nucleation chemistry is not simulated. The moving crystal interiors are not
represented as cut cells in the diffusion grid. Swept-facet volumes approximate
solute uptake, and bounded sinks can differ from geometrical growth volume.
The reported solute balance therefore validates reservoir transport and sink
bookkeeping, not complete solid-plus-fluid thermodynamic conservation. The
model excludes geochemical speciation, lattice defects, elastic stress, heat
release and geological timescale calibration. Small surface grains use a
procedural growth schedule rather than the reservoir solver.

## Legacy rendering and finishing

The earlier still used 32 wavelength bands and 16 spatial/path samples per band: 512
traced paths per pixel, with correlation between bands. This should not be
interpreted as 512 independent spatial samples. Path depth is capped at 24;
Russian roulette begins at depth 9. The timelapse uses 16 bands and 4 samples
per band, with the exact settings recorded alongside the video.

Finished images use a small spatial prefilter, Intel Open Image Denoise,
nonlocal chroma/luma noise reduction and a fixed filmic luminance curve.
Denoising and filtering are biased display operations and can soften very
small inclusions. Unfiltered radiance is kept separately. The animation uses
fixed lighting, exposure, camera and random seed to improve temporal stability;
each displayed growth frame is path traced. No frame interpolation or temporal
image warping is used. Low-sample animation can retain small lighting variations.

## References

- G. Ghosh, *Dispersion-equation coefficients for the refractive index and
  birefringence of calcite and quartz crystals*, Optical Communications 163,
  95–102 (1999), [DOI](https://doi.org/10.1016/S0030-4018(99)00091-7).
- [Ordinary-ray quartz equation and coefficients](https://refractiveindex.info/?shelf=main&book=SiO2&page=Ghosh-o),
  RefractiveIndex.INFO, Ghosh-o dataset.
- [Mitsuba participating media](https://mitsuba.readthedocs.io/en/stable/src/generated/plugins_media.html) (optional `--mist` experiment).
- [Mitsuba 3 custom plugin interface](https://mitsuba.readthedocs.io/en/stable/src/others/custom_plugin.html).

The tests check estimator normalization, index dispersion, normal-incidence
refraction, total internal reflection, closed outward meshes, monotone facet
growth and absence of overlaps between principal crystals above the matrix.
They establish implementation properties, not experimental validation of
natural quartz growth.
