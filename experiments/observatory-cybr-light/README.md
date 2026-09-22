# Observatory IV: preserved renderer vs CYBR LIGHT

This is a **second render path**, not a replacement for `scenes/observatory-iv`.
The original scene subtree, source archive, and delivered images remain unchanged.
The new path executes the actual `cybr-light` native main program against an exported
scene. The source is pinned by Git submodule and checked against the complete native
header-tree hash and main-program blob hash before compilation.

## Reproduce both paths

From a clone of the comparison branch, authenticated for both private repositories:

```bash
git submodule update --init engines/cybr-light
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r scenes/observatory-iv/requirements-tested.txt
python experiments/observatory-cybr-light/run.py --width 720 --height 480 \
  --spp 48 --bands 8 --threads 4
```

The runner copies the baseline into a separate work directory before building it.
It never rewrites the original scene or its render outputs. It refuses an existing
work directory; select a new one with `--work`. Outputs are in
`build/observatory-light-comparison/comparison/comparison.html`. The gallery works
offline and switches between the matched raw pair, the same reconstruction applied
to both images, and the unchanged original delivered image.

For a small complete smoke run:

```bash
python experiments/observatory-cybr-light/run.py --work build/light-smoke \
  --width 96 --height 64 --spp 2 --bands 4 --threads 2
```

`--light-checkout /path/to/cybr-light` accepts an existing checkout whose renderer
source matches the pin. The offline delivery ZIP includes the exact pinned native
engine sources, so that delivery does not require a network clone. A GitHub source
ZIP does not include submodule contents: initialize the submodule or download the
pinned CYBR LIGHT repository separately before using that ZIP.

Linux/x86-64, a C++17 compiler, OpenMP, CMake, NumPy, SciPy, Pillow, trimesh, and the
baseline's tested Python dependencies are required. Full-size builds and renders
need several GB of RAM. The runner deliberately uses CPU execution.

## What is preserved and translated

The adapter reads the baseline's rebuilt CVR2 transport mesh, not a proxy model.
All accepted triangle positions, vertex normals, UVs, and object identifiers are
transferred through a checked binary mesh format. The coordinate change `[x,z,-y]`
is a proper rotation, with no rescaling. The horizontal field of view is converted
to CYBR LIGHT's vertical field of view for the same camera and aspect ratio. The
lens aperture is 0.004 m, and the focus point is unchanged.

The baseline source has 1,511,194 triangles before its degeneracy filter. The new
adapter retains 1,510,714; the baseline's FMA-enabled filter retains 1,510,737.
That 23-face difference is numerical acceptance of nearly degenerate faces, not
intentional mesh decimation. The exporter records the input and output mesh hashes.

The original 1800 x 1200 finished image is kept separately. It is not mislabeled as
a same-budget comparison. The matched run uses two newly rendered 720 x 480 images.
The baseline takes 48 camera samples with its fixed spectral representation;
CYBR LIGHT takes 48 packets of 8 wavelengths. These are **not equal path counts,
equal compute budgets, or equivalent material models**.

## Real CYBR LIGHT changes

The shared engine additions are in `cybrdelic/cybr-light`, on
`observatory-interchange-portals`: checked binary mesh input, shared image-texture
storage, and rectangular environment-portal importance sampling with matching MIS.
The renderer's `src/main.cpp` and its material models are unchanged. The portal is
a sampling proposal; it is not extra light. Existing scenes without portals retain
their original environment-sampling path.

The exact dependency commit, parent, header tree, and main-program blob are recorded
in `dependency.json`. Upgrade that pin deliberately; do not edit copied renderer
fragments inside this scene experiment.

## Known mapping differences

The baseline's RGB spectral interpolation becomes CYBR LIGHT's native spectral
controls. Spatial roughness becomes its per-material mean. Conductors use a fit to
mean source reflectance rather than measured complex optical constants. UV-aligned
anisotropy replaces group-axis machining directions. Native normal-map handedness,
bilinear filtering, and shading models are retained rather than rewritten to mimic
the baseline. The quartz uses a fitted native Cauchy model; maximum index error
against the source expression is about 0.000410 over 360–830 nm. A distant emitting
disk approximates the source's authored directional solar cone.

Consequently this comparison exposes the present integration and engine differences;
it is **not a claim that CYBR LIGHT is automatically better**, a bit-identical port,
or a convergence/photorealism benchmark.

## Image processing and evidence

Both unfiltered comparison images use the same exposure and white balance. Optional
reconstruction uses the exact same normal/depth/variance-guided filter on both total
linear films. It does not use a learned model, upscale, replace bright outliers, or
clamp path radiance. The raw PFM and native CYBR LIGHT EXR are untouched. First-surface
center-sampled guides do not describe the image inside refractive objects and can
soften details there. The original delivered image retains its original finishing.

`test_adapter.py` checks coordinate orientation, camera-ray correspondence, PFM
orientation, the common filter, minimal full export, and degenerate-face filtering.
The shared engine's own CI tests its native and Python workflows. Scene CI validates
the adapter and original-subtree preservation without fetching a private cross-repo
submodule using an insufficient repository-scoped token. The full two-renderer
pipeline is additionally exercised in the local delivery verification.

No original renderer files, images, or source archives are deleted or replaced.
No font files are bundled. Repository and retained component license notices apply.
