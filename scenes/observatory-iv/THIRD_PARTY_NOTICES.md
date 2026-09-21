# Provenance and dependencies

The input `assets/observatory_interior_source.glb` is the exact mounted `observatory_interior_y_up.glb` supplied with the prior CYBR Observatory rebuild. Its SHA-256 is recorded in `scene/manifest.json`.

`spectral_geometry.h`, `wide_bvh.h`, `sobol_directions.h`, and the original texture-loader layout derive from the supplied CYBR Drowned Geode V2 source archive, which itself identifies the retained CYBR GEO geometry kernel. Their source notices are preserved. The new spectral material/light-transport kernel is in `src/observatory.cpp`; the ordinary quartz refractive-index formula is retained from that supplied optical code.

Build-time Python libraries: NumPy, SciPy, Pillow, trimesh, and OpenCV. Native build tools: GCC, OpenMP, CMake. These dependencies are not bundled as binaries. Their individual licenses remain separate from this project.

Only rendered glyph pixels in diagram textures and the retained glyph geometry are present. No font files are included. No material image or render produced by an image-generation model is included.
