# Render CYBR Scenes

Use the root `cybr_scenes.py` entry point. It prepares real geometry, compiles the bundled CYBR LIGHT engine, packs indexed meshlets, renders linear films, finishes the PNG and writes the success receipt in one invocation.

```bash
python cybr_scenes.py render observatory-iv --quality preview
python cybr_scenes.py render fernwater --width 960 --spp 128 --bands 12 --threads 4
python cybr_scenes.py render observatory-iv --quality production --output outputs/final
```

| Quality | Width | Spectral packets per pixel | Wavelengths per packet |
| --- | --- | --- | --- |
| `smoke` | 64 | 4 | 4 |
| `preview` | 800 | 64 | 8 |
| `production` | 1800 | 192 | 12 |

Height follows the scene's aspect ratio. `--width`, `--height`, `--spp`, `--bands`, `--threads`, `--depth`, `--timeout` and `--output` override settings. Samples count wavelength packets, not RGB paths. These budgets do not guarantee convergence. Dimensions are traced directly; no upscaling occurs. CYBR LIGHT uses one packet budget for the complete scene, so use `--spp` instead of `--water-spp`.

`render all --quality smoke` attempts all seven scenes sequentially and returns failure if any scene fails. `--force` repeats a matching run. Full geometry preparation can be substantial, especially the forest; meshlets reduce native vertex storage but do not eliminate the builder's memory or disk requirements.

## Outputs and reuse

Open `outputs/<scene>/hero/hero.png`. `_unfiltered.png`, `.pfm`, `.exr`, diagnostic PFM passes, `.cys`, `scene.clm` and `.json` sit beside it. Raw linear films are retained unchanged. The PNG uses three non-neural camera-footprint/geometry/object/variance guided filtering passes followed by an ACES display transform.

CLM1 meshlets hold at most 64 full-attribute vertices and 124 triangles. Normals, UVs and tint participate in deduplication; material/component IDs remain per triangle. Native triangle references share float32 vertex blocks through the CPU SAH BVH. Intersection math remains double precision. Exact ray-cache keys reuse visibility across wavelengths without quantization. There is no GPU mesh-shader backend.

A completed `receipt.json` records settings, geometry/material inputs, engine source, adapter/finishing source and output hashes. It is written last. Sampling/resolution changes reuse the independently checked meshlet pack; geometry, converter and material changes rebuild it. Changed inputs/settings invalidate render reuse, and changed output bytes prevent cache acceptance. A failed replacement removes the prior success receipt. Engine compile failures retain a log in `CYBR_LIGHT_CACHE`; stage logs are in `build/logs/`. Fresh meshes and outputs are ignored by Git.

## Platforms

Linux/WSL2, Python 3.11–3.13 and g++/OpenMP are supported. Install root `requirements.txt`. The process controller uses `/proc`, process groups and `flock`. CYBR LIGHT writes its own float32 EXR; its native path needs no OpenCV EXR codec, CMake, AVX2/FMA, FFmpeg, GPU or network renderer download.

## Materials and historical reproduction

The adapter preserves geometry, vertex normals, UVs, vertex tint and component IDs. CVR2 surface maps become linear texture inputs and normal-map BSDFs. Lava's retained temperature field drives wavelength-dependent Planck emission. Authored RGB values are spectral controls, not measured reflectance. CYBR LIGHT uses its general glass/BSDF/volume models; scene-specific water manifolds, atmosphere estimators and layered material models do not transfer exactly.

Use `--renderer authored` for the original scene-specific transport and its historical sample budgets. Observatory then requires CMake and AVX2/FMA; Drowned Geode requires AVX2. `--water-spp` and the original EXR codec checks belong to that path. The older environment CLI remains available for baseline comparisons and gallery serving:

```bash
python cybr_scenes.py render observatory-iv --renderer authored --quality preview
cd environments
python cybr_scenes.py serve
```

The retained gallery images keep their original provenance. Newly published CYBR LIGHT renders have their own reproduction records. [Pinned engine and patches](../rendering/cybr_light/UPSTREAM.json) · [Original import record](observatory-iv-import.json).
