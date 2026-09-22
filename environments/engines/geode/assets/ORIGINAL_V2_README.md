# CYBR GEO — Desert Hot Springs V2

A rebuilt 3D desert spring scene with individually weathered rock meshes,
mineral crust plates, displaced pool beds, submerged gravel, dry grasses,
measured background mountain terrain, and wavelength-dependent water
absorption. This delivery uses **Mitsuba 3.9.1 spectral path tracing through a
CYBR GEO scene adapter**. It does not use the earlier experimental native
CYBR GEO renderer, and it does not change upstream rendering defaults.

The image creation process uses no image-generation model, neural texture
generator, image inpainting, background photograph, or neural upscaler.

## Reproduce

Use Python 3.12 on Linux with at least 12 GB of available RAM. The exact package
versions used are in `requirements-tested.txt`. All paths below are relative to
the `cybr-geo` directory inside the source archive.

```bash
python3 -m pip install -r examples/desert_hot_springs_v2/requirements-tested.txt
python3 examples/desert_hot_springs_v2/build.py --out ../rebuild --texture-size 3072 --save-assembly
python3 examples/desert_hot_springs_v2/refine.py --scene ../rebuild
python3 examples/desert_hot_springs_v2/terrain_dem.py --scene ../rebuild
python3 examples/desert_hot_springs_v2/verify.py --scene ../rebuild --sync-assembly
python3 examples/desert_hot_springs_v2/render.py --scene ../rebuild --view wide --width 1536 --height 1024 --spp 256 --batch 16 --threads 6 --out ../rebuild/wide
python3 examples/desert_hot_springs_v2/render.py --scene ../rebuild --view detail --width 1536 --height 1024 --spp 192 --batch 16 --threads 6 --out ../rebuild/detail
python3 examples/desert_hot_springs_v2/finish.py ../rebuild/wide.png ../rebuild/wide_finished.png --strength 4
python3 examples/desert_hot_springs_v2/finish.py ../rebuild/detail.png ../rebuild/detail_finished.png --strength 4
```

For a quick preview, use `--width 768 --height 512 --spp 32 --batch 4`.
`--resume` continues a render from its existing checkpoint. Resume only when
the scene, camera, resolution, seed, and transport settings are unchanged.
The output checkpoint stores a floating-point radiance sum and accumulated
sample count. Final linear EXRs remain unfiltered; PNG output uses a global
exposure and fitted ACES display curve followed by sRGB encoding.
Independent views may render concurrently. An output-specific file lock
prevents concurrent writes; completed results with matching settings are reused.
Choose a new output stem to explicitly render a second realization.

## Source structure

- `build.py`: deterministic geometry, procedural mineral fields, CYBR GEO
  `Part` and `Assembly` construction, metre conversion, PLY export, and water
  closure checks.
- `refine.py`: photographed stone-material projection, low-frequency physical
  vertex displacement and residual bump mapping, and ridge datum correction.
- `terrain_dem.py`: measured USGS/Mapzen elevation tiles converted into a
  positioned mountain mesh, distant ground closure, and atmospheric haze.
- `render.py`: sun/sky lighting, the spectral path tracer, participating steam,
  dielectric water, lens camera, accumulation checkpoints, and render receipts.
- `finish.py`: isolated bright-outlier rejection and conservative OpenCV
  nonlocal-means noise reduction. The report records every replaced outlier.
  These are numerical filters and contain no neural network.
- `verify.py`: mesh and water-volume validation and synchronization of the
  optional CYBR GEO assembly after the material displacement pass.
- `assets/`: original CC0 rock material maps and the attributed terrain tiles.

The generated PLY files carry vertex normals and UVs; these attributes accompany
the CYBR GEO assembly because its original core serializer does not store UVs.
The scene configuration uses portable paths relative to the generated scene.

## Verification and numerical limits

The builder checks finite coordinates and normals, valid face indices, positive
water volume, watertight water boundaries, and consistent winding. Rendered
batches are rejected if radiance contains a nonfinite value. Each completed
view writes its settings, elapsed time, and scene hash into a JSON receipt.

The spring is authored environmental geometry, not a surveyed location or a
validated geothermal/fluid simulation. The distant mountain geometry uses
measured elevation data, rotated and repositioned to frame the spring; its
near edge is blended into the authored ground. This is not an exact geographic
reconstruction. Steam is a prescribed heterogeneous
density field. Ripples are deterministic displaced wave components. The water
IOR is achromatic; its absorption varies with wavelength. Reflectance textures
originate as RGB values and are spectrally upsampled, rather than measured
mineral spectra. Fine refractive sunlight caustics converge slowly because the
integrator does not include a manifold caustic solver. Sun/sky illumination uses
the analytic Hosek–Wilkie emitter rather than a simulated planetary atmosphere.
The output is a new rendering study; no GitHub repository was modified.

## Terrain credit

Mapzen; United States terrain data courtesy of the U.S. Geological Survey.
[Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) was accessed on
2026-09-14. [Attribution and public-domain source information](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
Three Terrarium tiles at zoom 11, x=360, y=818 through 820 supply the mountain
heightfield. `terrain_provenance.json` records hashes and spatial adjustments.
Terrain colors are authored materials illuminated in the 3D scene; the PNG
source tiles encode numeric elevations, not photographic scenery.

## Photographic material credit

**Rock Boulder Dry** — photography by Dimitrios Savva, processing by Rico
Cilliers. [Original material](https://polyhaven.com/a/rock_boulder_dry),
[CC0 license](https://polyhaven.com/license). The diffuse, displacement, and
roughness maps are applied to 3D surfaces; none serves as a scene backplate.
The asset provenance report records the exact source-image SHA-256 hashes.
The diffuse map was retrieved from a public mirror of the same named material;
the displacement and roughness maps came from the original download service.

Renderer reference: [Mitsuba](https://mitsuba.readthedocs.io/en/stable/).
The recovered CYBR GEO source retains its original license. The CC0 material
maps retain their separate public-domain dedication.
