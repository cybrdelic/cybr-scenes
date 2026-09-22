# CYBR SCENES — R2

Six recovered, upgraded 3D environments, one CPU build/render/verification entrypoint.

- **Sandstone Passage:** sandstone canyon and rockfall.
- **Basalt Tide:** columnar basalt shoreline and offshore stacks.
- **Fernwater:** full woodland, fern and leaf-litter geometry, winding stream.
- **Desert Hot Springs:** desert terrain, mineral pools, rocks and scrub.
- **Obsidian Reach:** volcanic gorge with authored hot interior and detached crust.
- **Drowned Geode:** flooded fracture-cell cavern, quartz and collapsed skylight.

These are real native renderer runs against triangle geometry. Reference screenshots
are catalog/comparison assets only. They are not fed into the scene builders or the
renderers. There is no image-generation model, neural denoiser, painted backdrop,
image-to-video service, or Blender dependency in this workflow.

## Run

Linux or WSL with an AVX2-capable x86-64 CPU, g++ and OpenMP is the tested target.
The four recovered native implementations are preserved as distinct backends;
this is a unified project/asset workflow, **not** a claim that their transport models
have been rewritten into a single identical integrator.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python cybr_scenes.py doctor
python tools/prepare_detail.py
python cybr_scenes.py compile
python cybr_scenes.py prepare all
python cybr_scenes.py render all --quality preview --force
python cybr_scenes.py render sandstone-passage --quality production --force
python cybr_scenes.py verify
python cybr_scenes.py serve
```

Open `gallery.html` via the local server for the six-scene comparison catalog.
The source delivery excludes multi-gigabyte generated triangle streams; `prepare`
rebuilds them from the included original procedural source and source assets,
then writes upgraded meshes separately. It does not overwrite the recovered mesh.

The delivery contains finished PNGs. Use `--force` to actually re-render over
them, or choose `--output renders/my-run` to keep a separate run. Without
`--force`, existing results are verified, not silently rendered again. If only
the display PNGs are installed, also extract Raw Proof for verification.

The production defaults are 1280 pixels wide, with per-scene sample budgets in
`scenes.json`. `--width`, `--height`, `--spp`, `--water-spp`, `--threads` and `--output`
provide explicit control. A render at 960 pixels is genuinely rendered at 960;
the finish stage does **not** upscale. Every delivered render has its actual
resolution, sample count, execution command and source/mesh hashes in its receipt.

A high-density forest build can use several GB of RAM. Run the six scenes
sequentially; raising sample budgets increases rendering time substantially.
Use the `preview` setting for a first installation check. Building the original
full forest is a minutes-long operation, not an instant primitive stand-in.

## What changed

The complete source patches are in `provenance/renderer-upgrade.diff` and the
pre-edit source versions are in `provenance/native-before/`.

### Shared surface system

`shared/surface_detail.hpp` adds photographed mineral detail sampled on the 3D
surface: independent rotated/translated tile instances, smooth overlap,
triplanar projection, footprint-selected mip levels, and linear reflectance
ratios. Roughness uses height-slope second moments to turn unresolved normal
variation into broader highlights rather than subpixel sparkles. The atlas is
created from existing recovered CC0 albedo, height and roughness maps; it is not
created from the reference scene images.

`tools/enhance_geometry.py` changes actual triangle positions using bounded,
continuous world-space deformations and transforms normals using the exact
inverse-transpose Jacobian. Each result records the changed vertex count,
maximum displacement, minimum Jacobian determinant and before/after mesh hashes.
Water triangles are preserved, including the optical enclosures. UVs, material
IDs, object IDs and primitive ordering remain intact. These are modest resolved
surface changes, not a replacement of the established environment composition.

### Per-scene changes

**Sandstone:** resolved weathering relief; footprint-filtered fine bedding;
stochastic mineral color/height/roughness; explicit sky next-event sampling with
matching multiple-importance weights in shaded parts of the canyon.

**Basalt:** resolved weathering on rock and column surfaces; new mineral
microstructure; waterline deposits; sky next-event sampling on the coast.

**Fernwater:** curled dead-leaf geometry in each leaf's local coordinate frame;
more decomposed, damp litter rather than uniformly orange leaves; living-leaf
mottling in local coordinates; new mineral detail on stream rocks. The full
recovered tree, root, shoot, fern, litter and stream geometry is retained.

**Hot springs:** resolved rock weathering; stochastic photographed rock and
sinter detail; deposition/pore variation linked to the pool-edge region;
explicit sky sampling with complementary BSDF escape MIS weights.

**Obsidian:** continuous deformation on cold crust and its attached warm edges;
full-sphere HDR environment importance sampling, with exact cell solid-angle
PDFs and complementary BSDF MIS; lower thermal-map emission multiplier. This
remains an authored lava scene, **not** a newly computed fluid simulation.

**Geode:** resolved rock relief; vertical seepage/deposition variation on the
limestone; roughness coupled to wet deposit masks; clear quartz tips and rougher,
etched attachment regions using identical roughness in the sampler, BSDF and PDF.

## Evidence and limitations

`renders/<scene>/hero/` contains the PNG, the unfiltered PNG, raw PFM radiance,
native metadata, subprocess logs, finish logs, execution command, hashes,
verification result and provenance receipt. In the downloadable delivery, raw native films are in the separate Raw Proof archive; extract it into this project to inspect the delivered films without re-rendering. The Source archive includes source inputs, the display images, receipts and gallery, but omits generated geometry and large raw film arrays. Additional guides/spectral films
are emitted by the corresponding native backend.

The GEO/hot PNG finish demodulates primary-opaque radiance by the actual albedo AOV, filters estimated irradiance, and remodulates it. Primary water is excluded using the native sample-budget map. This preserves material variation instead of averaging the reflectance into the lighting. It is not a diffuse/specular AOV decomposition.

Fernwater adds a material-gated, two-sided live-leaf display filter. It uses soft
absolute normal alignment and relative depth instead of treating neighboring
leaves with opposing normals as unrelated opaque surfaces. This reduces the
isolated dark foliage speckles at the recorded sample budget. Sky, water, bark
and ground pixels are not modified by the leaf-specific pass. Tests check
constant-radiance preservation, isolated-zero recovery, and material exclusion.
It remains a biased spatial estimate; unresolved canopy and water detail are
not fully converged.

The PNG finish is non-neural, normal/depth/albedo/variance-guided filtering of
computed linear radiance followed by a documented display transform. It is a
biased display estimator, not additional path samples. Raw PFM files remain
unchanged. A cleaner display does not prove that all lighting paths are converged.

The GEO/hot/geode models use fixed 16-band spectral quadrature and authored
RGB-derived material spectra rather than measured mineral spectra. Water
connections and atmospheric models retain the limitations documented by their
recovered implementations. Obsidian uses spectrally integrated thermal emission
with an RGB native transport bridge. This release does not establish measured
physical accuracy, cinematic convergence, or a particular commercial-engine
quality level.

The native canyon's exact old screenshot revision was not conclusively recovered.
All comparisons distinguish supplied reference images from newly executed R2
renders. The mobile canyon screenshot is a presentation of the same environment,
not a seventh native scene. Mobile-viewer performance is not validated by a CPU
still render.

## Tests

```bash
bash tools/test_r2.sh
python -m unittest discover -s tests -v
python cybr_scenes.py verify
```

Tests cover analytic deformation gradients, inverse-transpose normal transport,
non-inversion, litter endpoints, binary headers, lock safety, nonnegative spectral energy despite out-of-gamut display RGB, denoiser remodulation identity, finite and normalized surface
normals, mip slope moments, texture-tile continuity, and HDR-sampler PDF agreement
and normalization. Native self-tests also run during compilation.

For a controlled old-code comparison, reconstruct the preserved source versions
and render the same recovered geometry/camera:

```bash
python tools/compile_originals.py
python cybr_scenes.py render sandstone-passage --baseline --width 640 --spp 64
```

The old code is reconstructed in `build/original-engines`; it does not replace R2.
A baseline compile must never silently compile the upgraded source as the old code.

## Licensing

The combined project and new source use GPL-2.0-only. Existing files retain their
own notices. Recovered photographic inputs retain their original CC0 or other
notices in `engines/obsidian/LICENSES/ASSET_NOTICES.txt` and
`engines/geode/THIRD_PARTY_NOTICES.md`. See `provenance/material-atlas.json` for
exact atlas input files and hashes. No font files are redistributed.

### Memory-bound assembly build

The hot-springs builder now spools completed Parts as read-only memory-mapped
float64/int64 arrays, preserving their numerical precision and geometric formulas.
Its saved CYBR GEO archive is hash-checked and reconstructed one Part at a time
when writing native triangles. This removes the old requirement to hold the whole
assembly plus a second loaded copy in memory. No decimation is used. The source
change is recorded in `provenance/builder-upgrade.diff`.

### Why some linear RGB values are negative

The spectral renderers transform positive wavelength samples to XYZ and then a
limited display-RGB gamut. Small negative linear RGB components are legitimate
out-of-gamut coordinates, not negative transported energy. The verifier checks
finite display RGB and nonnegative finite transported wavelength bands. The raw
film is never clipped to manufacture a passing test. A regression test covers
this distinction.

### Historical comparison and browser files

Reference images are supplied earlier images, not same-sample R2 baselines. The
exact earlier native canyon still revision remains unresolved. The older mobile
canyon code is preserved under `legacy/`; it has not been relit with the new CPU
transport, and still-render completion is not evidence of a new interactive GPU
version. The gallery is an inspection interface, not a 3D engine.

### Display reproducibility test

`python tools/verify_finishing.py` reruns the exact per-scene native-film finish
and checks that every PNG is byte-identical while every source PFM hash stays
unchanged. This is stronger than inspecting an image filename, but is not a
second independent full transport run. Its report is
`evidence/finish-reproduction.json`. Packaging requires this test to pass.

Near-degenerate triangles are rejected by the recovered native loaders. Mesh
stream counts and actual traced-triangle counts are both retained rather than
assuming they are always identical. Rebuild results may differ in low bits
across compilers/CPU instruction sets; native commands and compiler fingerprints
are recorded for the executed runs.

### Optional gallery browser audit

The executed browser audit injects the exact standalone HTML bytes into Chromium
with Playwright `set_content`; this runtime blocks direct local-file and loopback
navigation. Image switching, decoding, enlargement and layout were exercised,
not the local-URL serving path.

Install the optional dependencies in `requirements-audit.txt` and a system
Chromium, then run `python tools/verify_gallery.py`. This exercises all six scene
image-mode switches, image decoding, enlargement controls, desktop/mobile layouts
and the self-contained offline HTML. It does not validate an interactive 3D
renderer. The ordinary geometry/transport workflow does not need a browser.
