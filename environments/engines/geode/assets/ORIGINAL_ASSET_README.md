# Desert hot springs — revision 3

These images are renders of a real triangle scene. No image-generation model,
neural texture synthesis, inpainting, or neural image finishing is used.

The foreground spring and mineral deposits are authored geometry. Three CC0
photogrammetry rock models supply rock shapes and surface photographs; smaller
stones use cleaned, simplified versions of those meshes. A photographed sky
panorama supplies environment illumination and reflections. The mountains are
3D elevation data, not a photographic landscape background.

## Changes from revision 2

- Replaced procedural layered boulders and flat-shaded gravel with scanned rock
  geometry, smooth normals, photographed albedo, and normal/roughness maps.
- Removed the separate planar mineral flakes. The bank is one continuous
  displaced sheet with irregular deposits and photographed granular detail.
- Corrected the ground atlas and glTF V coordinates for Mitsuba's top-origin
  bitmap convention, so deposits and wetness follow the actual pool beds.
- Made the beds shallower with a graded shelf and actual submerged stones.
- Changed volumetric transport to `volpathmis`, which samples spectral medium
  extinction more efficiently, and used multijitter sampling.
- Used softer photographed daylight, revised camera positions, and filtered
  distant geometric detail to avoid aliasing into large triangular ridges.

## Reproduce

From the `cybr-geo` directory, in a Python 3.12 environment:

```bash
python -m pip install -r examples/desert_hot_springs_v3/requirements-tested.txt
python examples/desert_hot_springs_v3/rebuild.py --out ../v3_scene --save-assembly
python examples/desert_hot_springs_v3/complete_scene.py --scene ../v3_scene
python examples/desert_hot_springs_v3/verify.py --scene ../v3_scene --sync-assembly
python examples/desert_hot_springs_v3/render.py --scene ../v3_scene --view wide --width 1536 --height 1024 --spp 256 --batch 4 --threads 4 --out ../v3_scene/photo_wide
python examples/desert_hot_springs_v3/render.py --scene ../v3_scene --view detail --width 1536 --height 1024 --spp 256 --batch 4 --threads 4 --out ../v3_scene/photo_detail
python examples/desert_hot_springs_v3/package_delivery.py --scene ../v3_scene --out ../delivery_v3
```

The material assets are included. `fetch_assets.py` can retrieve their original
files again if necessary. Its manifest records source URLs, sizes and SHA-256.
The V2 example supplies shared geometry helpers and the measured terrain data;
it must remain beside this example.

The build produces metre-native PLY transport meshes and a millimetre-native
CYBR GEO `Assembly`. PLY files preserve UVs and vertex colours; the core assembly
serializer stores geometry, normals and material identifiers. The renderer is
the included Mitsuba adapter, not a change to CYBR GEO's native renderer.

The archive contains all source/material assets, unfiltered linear EXRs,
unfiltered display PNGs, finished PNGs, render settings and verification reports.
The large scene meshes and assembly are reproduced by the commands above.

## Sources and limitations

CC0 assets from Poly Haven:

- [Boulder 01](https://polyhaven.com/a/boulder_01), Rico Cilliers.
- [Namaqualand Boulder 02](https://polyhaven.com/a/namaqualand_boulder_02),
  Greg Zaal and Rico Cilliers.
- [Namaqualand Boulder 03](https://polyhaven.com/a/namaqualand_boulder_03),
  Dario Barresi and Jenelle van Heerden.
- [Brown Mud Rocks 01](https://polyhaven.com/a/brown_mud_rocks_01), Rob Tuytel.
- [Overcast Soil Pure Sky](https://polyhaven.com/a/overcast_soil_puresky),
  Sergej Majboroda and Jarod Guest.
- [Poly Haven license](https://polyhaven.com/license).

Terrain: Mapzen/Tilezen terrain tiles, with United States data courtesy of the
U.S. Geological Survey. See the included provenance report and
[terrain attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
The mountains are rotated and repositioned behind an authored spring; this is
not an exact survey of a real hot spring.

Water has closed, outward-wound boundaries, IOR 1.333, and wavelength-dependent
absorption. Its IOR is achromatic. The authored absorption curve is an
approximation, not a measured sample of this spring. RGB reflectances and the
RGB panorama are spectrally upsampled. Steam density is an authored 3D field,
not a fluid simulation. There is no specular-manifold caustic solver. See
[Mitsuba's integrator documentation](https://mitsuba.readthedocs.io/en/stable/src/generated/plugins_integrators.html)
for the transport method.

Finishing uses a global exposure/display curve and conventional OpenCV noise
reduction blended at 55% with the raw display image. Bright grains are not
replaced with median pixels. The untouched EXRs and PNGs remain available for
inspection.
