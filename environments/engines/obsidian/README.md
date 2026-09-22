# Obsidian Reach IV

An offline volcanic-reach still, constructed from real meshes and rendered by a
custom native CPU integration of the CYBR projects. No image-generation model,
image upscaler, or generative post-processing is involved.

## Reproduce the delivered frame

```sh
python -m pip install -r requirements.txt
python run.py
```

The default command rebuilds the geometry, compiles the C++ renderer, executes
regression checks, traces the native 2560 × 1120 frame, denoises reflected light,
and exports an unfiltered float32 EXR. The delivered pixel sample-budget map is
included. Four CPU rendering threads are used by the native executable.

A compiler with C++17 and OpenMP support is required. This delivery was executed
on Linux. The source inputs are included; no network connection, GitHub account,
GPU, Blender, or external rendering service is needed to reproduce the frame.

```sh
# Build the geometry and run tests without the long render.
python run.py --prepare-only

# New preview: uniform, independent native rendering, not image resampling.
python run.py --width 1200 --height 528 --spp 32 --uniform --output render/preview

# Regenerate a pilot-guided sample allocation for a new framing.
python run.py --camera 1 --new-budget --output render/alternate

# Uniform sampling at the same delivered resolution.
python run.py --uniform --spp 192 --output render/uniform_reference
```

## Actual scene construction

The river is not the old continuous glowing sheet. It consists of a continuous
hot interior beneath 1,008 independently meshed cooling-crust bodies. Each body
has its own folded upper surface, tilt, thickness, and free-edge wall geometry.
Light passes through actual gaps; the crust can cast shadows on the molten
interior and on neighbouring bodies. An irregular fracture partition is
nonlinearly warped before the bodies are constructed.

The banks use scanned, texture-coordinate-preserving rock fragments, embedded
outcrops, a continuous displaced foundation, and a relocated elevation-derived
horizon. Close fragments receive higher mesh density. The source scene contains
6,210,833 triangles in 9,583 named parts. Metres are used for authoring and native
rendering; CYBR GEO stores its named-part assembly in millimetres/Z-up.

## Project contributions

- **CYBR GEO:** vendored Part/Assembly representation, coordinate conversion,
  named-part management, and structural validation.
- **CYBR ELEMENTS:** vendored temperature-dependent Planck emission and
  material-coordinate/Jacobian helpers.
- **CYBR LIGHT:** native ray/triangle and analytic-shape intersections, camera,
  sampling, SAH acceleration, spectral observer/thermal source integration.
  The native transport driver and scene-specific materials are custom code.

This is not an unchanged execution of the stock CYBR LIGHT renderer. Thermal
emission is preintegrated to RGB; subsequent surface light transport is RGB.

## Rendering and finishing

The surface integrator uses a diffuse/GGX mixture, visible-normal specular
sampling, emitter importance sampling, shadow rays, multiple importance
sampling, and finite-depth secondary paths. The thermal emitter map averages
radiance, not temperature, when making mip levels. Textures are filtered using
an approximate ray footprint. Rock relief gradients are precomputed and
filtered alongside the texture instead of repeatedly differencing the image
at every material evaluation.

Acceleration changes retain the CYBR geometry core: inverse ray directions are
reused, BVH entry distances avoid repeated node testing, and triangle-only
shadow tests skip shading data construction. The accelerated closest-hit and
shadow results were compared against brute-force intersections for 12,000 rays,
including axis-parallel rays and moving primitives.

A separate 20-sample pilot determined the final per-pixel budget. Final radiance
was then traced at 2560 × 1120 with an independent randomization, using 16–192
samples per pixel: 172,873,328 primary camera paths, averaging about 60.29 per
pixel. The film is not upscaled. The renderer's `spp` field is the maximum budget,
not the number used for every pixel; consult the sampling record for actual work.

The display PNG uses non-neural, variance/normal/depth/albedo-guided filtering
of reflected light. Directly visible emission is retained separately. The
finishing script applies a filmic display fit, restrained linear-light bloom,
and a slight lens falloff. The EXR is the unfiltered native linear film; it is
not the denoised PNG written into an EXR container.

## Scope

The shape, temperature, and atmospheric fields are authored for a static image.
This is not a conservation-law lava solver, a calibrated crust-fracture model,
or a reconstruction of a particular eruption. The atmosphere uses deterministic
Beer–Lambert ray integration with approximate source illumination, not a
multiple-scattering gas simulation. The observer is an analytic approximation.
Numerical/structural tests do not establish photographic realism or an objective
ranking against commercial game graphics.

## Files

`authoring.py` supplies geometry/material authoring utilities. `build_scene.py`
constructs the complete scene and regenerates its binary meshes and texture
caches. `src/render.cpp` is the native rendering driver. `include/cybr/` contains
the modified core. `finish_v4.py` and `finish_v2.py` implement display/filtering.
`allocate_samples.py` builds pixel-budget maps. `tests/` includes structural,
optical, sampling, acceleration and EXR checks. `reference/` contains the exact
sampling budget and final records. `verification/` holds executed test logs.

The large regenerable `assets/scene.bin`, scan/thermal texture caches, compiled
executables, and working auxiliary films are not required source assets and are
excluded from the source archive.

## Input assets and references

The two photogrammetric rock assets and the overcast HDR panorama were supplied
in the preceding project archive. Their retained provenance is in
`assets/download_manifest.json`, `assets/scan_provenance.json`, and
`LICENSES/ASSET_NOTICES.txt`. The historical download manifest also mentions an
unused third rock; only `boulder_01` and `namaqualand_boulder_03` are used here.
All included asset files have their own entries in the archive checksum manifest.

Morphological references used while rebuilding the scene:

- US National Park Service, *Lava Flow Forms*:
  https://home.nps.gov/articles/000/lava-flow-forms.htm
- US Geological Survey, *Kīlauea Volcano — Drone Over Lava Channel*, July 2, 2018:
  https://www.usgs.gov/media/images/kilauea-volcano-drone-over-lava-channel

These reference photographs are not composited into the rendered foreground.
The photographic HDR panorama provides the environment backdrop/illumination.

## Licensing

The retained GPLv2 license and original component notices are included. Input
asset attribution and CC0 notices are retained in `LICENSES/` and the asset
provenance records. No font files are included.
