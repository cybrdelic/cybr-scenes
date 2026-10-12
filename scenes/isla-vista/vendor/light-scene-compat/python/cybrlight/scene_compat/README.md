# Indexed offline scene compatibility

This deliberately isolated module preserves the exact native runtime used by the recovered Isla Vista scene. It is not an alternate import for the current public cybrlight Scene API.

`from cybrlight.scene_compat import Scene, Meshlets, render`

The wrapper compiles only the included C++17/OpenMP dependency closure into a source-hashed temporary cache. It does not fetch code or replace the current native engine. NumPy, Pillow and Numba are required for the existing display finishing; raw radiance and all guides remain unchanged.

This snapshot adds CLM1 indexed meshlets, shared float32 vertices with double-precision intersections, exact ray reuse, finite-sun importance sampling, metric height derivatives, tangent handedness, textured first-hit guides and temperature-textured emission to a historical LIGHT base. It lacks several newer public LIGHT features. Keep scene compatibility explicit until these additions have separately been ported and tested against current transport.

GPL-2.0-only, with the retained original MIT notice in native/LICENSES. DEPENDENCY_MANIFEST.json records the executed native source hash and every packaged byte hash. Large scene geometry, images, browser assets and unrelated engines are excluded.

The latest 320-pixel gate verifies geometry/material admission and finite transport only. Its scene appearance was rejected; that does not invalidate the runtime compatibility proof or qualify the scene as photorealistic.
