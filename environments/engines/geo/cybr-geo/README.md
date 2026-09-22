# CYBR GEO — V9 desert hot springs source snapshot

This directory is the actual geometry and native renderer used by the V9 delivery. See the parent `README.md` for complete reproducible commands, data formats, source changes, dependencies, limitations and provenance. See `CRITIQUE.md` for the visual assessment and `evidence/` for execution evidence.

The native entry point is `examples/desert_hot_springs/render.py`. It builds a real CYBR GEO Assembly, reloads it, exports triangles, compiles `native/spectral_desert.cpp`, and renders. The product/studio renderer defaults are not replaced.

The code is derived from the user-supplied V8 archive, not retrieved from or committed to GitHub during this revision. The saved source is the authority; older version-numbered utility files remain only where imported or used for regression comparisons. They are not a claim that earlier render outputs are part of this delivery.

The included GPL-2.0-only license and CC0 gravel attribution are preserved. No generated image, photographic backdrop or new photogrammetry asset is used.
