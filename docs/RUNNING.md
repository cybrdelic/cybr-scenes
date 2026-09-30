# Working with CYBR Scenes

Run the root `cybr_scenes.py` entry point from the checkout, or invoke it by absolute path from another directory. It supports all seven scenes with the same install and command surface. The older entry point inside `environments/` remains available for baseline comparison, explicit preparation and the local gallery server.

## Settings

```bash
python cybr_scenes.py render observatory-iv --quality preview --width 960 --spp 48 --threads 4
python cybr_scenes.py render fernwater --quality preview --width 640 --spp 24 --water-spp 48
python cybr_scenes.py render observatory-iv --quality production --output outputs/final
```

| Quality | Observatory | Six environment presets |
| --- | --- | --- |
| `smoke` | 64 × 48, 4 spp, depth 6 | 64 pixels wide, 4/4 surface/water spp |
| `preview` | 640 × 426, 24 spp, depth 8 | 640 pixels wide, 24/48 spp |
| `production` | 1800 × 1200, 96 spp, depth 12, adaptive spectral-band output | 1280 pixels wide, per-scene sample budgets in `environments/scenes.json` |

These are iteration budgets, not image-quality guarantees. `--width`, `--height`, `--spp`, `--water-spp`, `--threads`, `--timeout` and `--output` override applicable defaults. `--depth` is Observatory-only; environment path depths are part of their authored presets. All frames are traced at the requested dimensions, with no upscaling. `--force` repeats the rendering even if a matching result exists.

`render all` attempts every scene sequentially and returns failure if any scene fails. Start with a single scene; full geometry preparation is substantial. Increasing samples increases render cost. `doctor <scene>` checks prerequisites before geometry creation, including Observatory's EXR encoder.

## Outputs and reuse

Default new output is `outputs/<scene>/hero/hero.png`. Native radiance, metadata, guides and verification reports sit beside it. `receipt.json` is a completed-run record, written only after output checks pass. A failed replacement removes the old success receipt; it cannot look like a completed new run.

The environment path compares source/build inputs, geometry, camera, atlas, renderer executable, finishing sources and requested settings before reusing a result. Matching cached outputs are checked again against their recorded native/PNG/spectral hashes. A partial or invalid run is rebuilt. Bundled gallery PNGs are not treated as new run caches.

Observatory uses separate fingerprints for source/executable and geometry/material inputs. It checks generated asset hashes before reuse, and records settings and output hashes for the completed render. Changing finishing or verification code also invalidates the output cache. Fresh geometry and material previews are created under `scenes/observatory-iv/build/scene/`; historical manifests, material previews and verification files remain untouched.

Fresh stage logs and process state are in `scenes/observatory-iv/build/logs/` or `environments/build/logs/`. The environment batch report is `environments/build/logs/render-batch.json`. These and `outputs/` are ignored by Git.

## Platforms and dependencies

Linux/WSL2 is supported. The process controller uses `/proc`, POSIX process groups and `flock`; native Windows and macOS are not currently supported by that controller. Drowned Geode uses AVX2. Observatory uses AVX2/FMA. Build binaries on the machine that will run them; some backends use `-march=native`.

Use Python 3.11–3.13 in a virtual environment and install the root `requirements.txt`. Its pinned OpenCV 4.13 build supports EXR. Installing an unbounded newer OpenCV version can lose that codec. If `doctor` reports EXR unavailable, reinstall the root requirements in a clean venv rather than skipping raw output checks.

The root workflow does not require FFmpeg, a GPU, Blender or a remote rendering service. Full geometry can take several GB of RAM and disk. Fernwater builds the complete procedural forest; the workflow does not replace it with a small primitive stand-in to pass a check.

## Advanced / legacy paths

`cd environments && python cybr_scenes.py serve` serves the retained six-scene gallery. `compile`, `prepare` and `render --baseline` remain available through that backend CLI. New backend renders also default to the repository's `outputs/`; use `--output` to select another destination.

Observatory's direct `build_scene.py`, `render.sh`, native binary and `finish.py` remain available. `render.sh` is the original delivered-camera reproduction path and assumes prepared assets. The root command performs preparation automatically. `verify.py --scene-dir <dir> --stem <stem> --out <report>` supports custom generated geometry and separate reports. Without `--out`, new reports go under `build/verification/`.

Original PNGs, evidence and the compact source archive are retained. The large original EXR/spectral films and prepared transport archives are not bundled; rendering creates new ones. [Original import manifest](observatory-iv-import.json), [environment provenance](../environments/provenance).
