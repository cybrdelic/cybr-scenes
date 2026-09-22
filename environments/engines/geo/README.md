# CYBR Fernwater R6

A new, geometry-built riparian woodland rendered by the recovered CYBR GEO native
spectral pipeline. The forest scene has been rebuilt; this is not an image edit.

## Run

Use Python 3.10 or later and a C++17 compiler with OpenMP (`g++` was tested on
Linux). Install the Python dependencies and run from this extracted directory:

```sh
python -m pip install -r requirements.txt
python run.py check
python run.py test
python test_r6_integration.py
python run.py all --scene forest --quality production --threads 4
```

The production preset uses 1920 x 1280 pixels, 192 camera samples for ordinary
surfaces, 384 for water, and 64 guide samples per pixel. It is an offline CPU job.
The `preview` preset retains high sampling at 640 x 426. For a quick layout test:

```sh
python run.py build --scene forest
python cybr-geo/examples/three_scenes/render_scenes.py --root output --scene forest --width 640 --height 426 --spp 32 --water-spp 64 --stem layout --threads 4
```

A completed scene can be rendered again without regeneration:

```sh
python run.py render --scene forest --quality production --threads 4
python run.py verify --scene forest --quality production --threads 4
```

The program reconstructs its native executable when the renderer, any native
header, compiler settings, CPU features, or executable identity changes. Different
library/compiler versions can alter geometry ordering or floating-point results.
The delivered receipts identify the exact tested inputs and outputs.

## What changed

`cybr-geo/examples/three_scenes/fernwater_r6.py` constructs an asymmetric meandering
stream, deposited gravel, actual bank relief, attached roots, irregular greywacke
stones, discontinuous geometric moss, broadleaf canopies, a dense background tree
tier, divided ferns, slope-aligned litter, twigs, and an open-ended hollow log.
Near leaves have folded, serrated or lobed silhouettes. Distant leaves use simpler
opaque polygon silhouettes, not image cards or an opaque crown shell.

The builder still uses CYBR GEO `Part` and `Assembly` objects and their save/load
path. Independent foliage groups are chunked during export to reduce temporary
concatenation memory without removing their geometry. The saved assembly is the
source of the native triangle stream.

`native/fernwater_materials_r6.h` uses per-component material frames. Veins and
midribs are expressed in each leaf's longitudinal/transverse coordinates; bark
fissures and lenticles follow each woody component's axis. This replaces the
world-coordinate diagonal texture patterns. The original photographic grayscale
grain and granular-relief inputs remain active where appropriate. Their source
and license are in `examples/desert_hot_springs/assets/ATTRIBUTION.txt`.

The native transport adds upper-hemisphere sky next-event sampling for forest
surfaces. Sky samples and BSDF-sampled sky escape are combined with the power
heuristic; water and volume events reset that local MIS state. The existing sun,
water and thin-leaf transport remain. `--no-sky-nee` disables the new technique for
investigation, rather than silently selecting a different renderer.

The R5 multisampled guides and non-neural variance-aware noise reconstruction are
retained. The raw PFM/EXR and fixed-band radiance are saved separately. No raw-noise
reinjection, sharpening, photographic backplate, generated-image texture, or
image-generation model is used. Denoising is biased and may soften subpixel detail.

## Local surface-coordinate files

Each built forest directory contains:

- `assembly/scene.json` and `assembly/meshes.npz`: CYBR GEO geometry in millimetres.
- `assembly/surface_coordinates.npz`: local frames and their triangle ranges.
- `scene.meshbin`: the original twenty-float triangle layout, in metres.
- `surface_frames.bin`: `FRM6`, a little-endian uint32 count, then sixteen float32
  values per frame: origin, longitudinal axis, transverse axis, normal, length,
  width/radius, kind, and seed. Index zero is the unframed default.

The existing native group slot carries a material-frame index. It does not change
the primitive-intersection code. The loader rejects corrupt/nonfinite frame
records and invalid indices rather than silently accepting mismatched tables.
Keep the frame file beside its matching mesh. Older scene formats with no table
use the unframed fallback; the rebuilt forest requires its generated table.

## Verification

`test_project.py` runs the inherited optical, traversal, material-input, wave,
namespace, guide, and denoising tests plus R6 material-coordinate and independent
sky/BSDF MIS quadrature tests. `test_r6_integration.py` builds and renders a small
new native fixture twice, checks deterministic radiance, tests local-coordinate
serialization, and exercises corrupt-sidecar rejection. These are not duplicate
full-forest rebuilds.

`verify_outputs.py` checks the rendered image, sample-count map, mesh fingerprint,
raw values, and independent reintegration of all sixteen saved spectral bands.
Tests do not certify photographic realism, geophysical accuracy, or botanical
accuracy. The final visual review is separate from these numerical checks.

## Limits

The vegetation, geology, material spectra, atmospheric density, and ripple field
are authored mathematical models, not measured reconstructions or growth/erosion
simulations. Transport uses sixteen fixed wavelength bins over 380–780 nm, not
continuous wavelength sampling. Water has spectral absorption but a constant
refractive index; dispersion is absent. Water caustics retain the approximate
one-root interface connections. The sky uses a single-scattering lookup model.
The finite path depth and those approximations preclude a claim of an unbiased
all-path reference solution.

The legacy canyon/coast recipes remain for compatibility; this R6 upgrade and its
final visual review concern Fernwater. Nothing is automatically pushed to GitHub.

The complete source and local detail assets are included. Large generated geometry
and image buffers are regenerated by the commands above and need not be present
in the source archive. See the supplied release verification for outputs actually
completed; a production preset alone is not evidence that a render finished.
