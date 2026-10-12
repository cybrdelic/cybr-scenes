# Mojave-inspired procedural scrub

`desert_scrub.py` targets Blender 4.3+, with no assets or Python dependencies beyond Blender. `create_variants(collection, seed=260910)` returns a dictionary of hidden source objects. Place visible instances using `bpy.data.objects.new(name, prototype.data)` and link them into the scene. This shares the mesh rather than copying it. Heights are physical metres; roots lie on local Z=0.

## Return keys

- `shrubs`: all 12 shrubs, 0.22–1.08 m tall
- `olive_open_scrub`: five small-leaf, open multi-stem forms
- `silver_low_scrub`: four low, spreading, grey-olive forms
- `dry_open_scrub`: three drought-thinned/bare-twig forms
- `grass`: five straw-coloured bunchgrass/stubble forms, 0.14–0.47 m tall
- `all`: all 17 prototypes

Call `variant_summary(bank)` for dimensions, triangle counts, and geometry counts. Per-object custom properties record family, generation seed, and nominal size.

Every shrub has tapered branching geometry, narrow secondary/terminal twigs, individually modelled folded leaves, crown gaps, and bare dead wood. There are no spheres, opaque polygon-cluster foliage masses, billboards, alpha cards, photo textures, or scans. These are intentionally representative desert scene assets, not exact botanical reconstructions.

## Placement guidance

Use irregular patches with large bare interspaces. Rotate each instance around Z and vary scale moderately (roughly 0.8–1.2 overall, 0.85–1.15 height). Repeated very large scale changes make the leaf size implausible. Mix young/low shrubs with a few taller olive shrubs, and put thin grasses in local pockets. Avoid a regular plantation, a continuous roadside hedge, or an even alternating sequence of prototypes.

Source objects hide only themselves. New linked-mesh instances are visible. Keep sources in a separate collection; never hide the collection holding visible instances. This module leaves scene materials, lights, terrain, camera and render settings untouched and does not start rendering.

## Test

`validate_variants.py` runs a no-render Blender check and writes `validation_report.json` beside the source. It checks all mesh topology, finite coordinates, zero-based roots, height bounds, material indices, reasonable triangle budgets, visibility of new shared-mesh instances, deterministic builds, and absence of imported image assets.
