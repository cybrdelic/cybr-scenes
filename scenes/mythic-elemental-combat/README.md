# CYBR Mythic Elemental Combat

A rigged humanoid combat proof that joins **CYBR SCENES**, **CYBR LIGHT**, and **CYBR ELEMENTS** in one world-space pipeline.

The target is weighty mythic action combat: committed axe arcs, strong anticipation, root-driven impact, follow-through, and element-specific attacks. The five authored moves are original; no God of War animation, model, texture, audio, or game asset is copied or retargeted.

## Sequence

| Frames | Move | CYBR ELEMENTS payload |
| --- | --- | --- |
| 16–66 | Frost Cleave | ice shard mesh |
| 75–128 | Flame Slam | advected fire/smoke density + emissive hot core |
| 138–198 | Storm Spin | branching lightning + advected air wake |
| 208–258 | Earth Breaker | ballistic fracture ring |
| 270–330 | Tidal Recall | swept liquid ribbon + droplets |

## Architecture

1. `fetch_avatar.py` downloads Khronos/Cesium's CC-BY-4.0 CesiumMan rig and records a SHA-256 provenance receipt.
2. `animate_avatar.py` imports the GLB in Blender, authors the combat animation, bone-parents a procedural axe, and evaluates the **real skinned mesh** every frame.
3. Each frame is exported as explicit avatar/weapon OBJ geometry because CYBR LIGHT's current native motion path supports translating primitives, not skeletal deformation.
4. `cybr-elements/work/avatar-combat/render_avatar_elements.py` consumes the same axe/hand trajectory and generates dense fields, reconstructed meshes, rigid fragments, and electrical channels.
5. `render_cybrlight.py` feeds the baked character and CYBR ELEMENTS assets into CYBR LIGHT and performs the final offline spectral transport pass with explicit physical lights and participating media.
6. `run_pipeline.py --assemble` uses ffmpeg only to encode already-rendered frames. It does not fabricate or interpolate imagery.

## Setup

Clone the three repositories beside one another:

```text
workspace/
  cybr-scenes/
  cybr-light/
  cybr-elements/
```

For this unmerged integration, check out `feature/mythic-elemental-combat` in CYBR SCENES and
`feature/avatar-combat-vfx` in CYBR ELEMENTS. CYBR LIGHT stays on its existing branch; the
integration uses its public Python scene API rather than modifying the renderer.

Build CYBR LIGHT first using its normal native build instructions. On Windows, its repository currently recommends WSL for the tested native workflow.

Blender 4.x and Python 3.10+ are expected. Set these only if autodetection cannot find the repos/tools:

```bash
export CYBR_LIGHT_ROOT=/path/to/cybr-light
export CYBR_ELEMENTS_ROOT=/path/to/cybr-elements
export BLENDER=/path/to/blender
```

## Run

A quick end-to-end proof:

```bash
cd scenes/mythic-elemental-combat
python run_pipeline.py --preset smoke --step 4
```

A full 30 fps preview:

```bash
python run_pipeline.py --preset preview --assemble
```

High-sample offline output:

```bash
python run_pipeline.py --preset reference --assemble
```

Render one diagnostic frame after the bake:

```bash
python render_cybrlight.py --frame 111 --preset preview
```

## Coordinate contract

Blender is Z-up. CYBR LIGHT/CYBR ELEMENTS integration data is Y-up. Every baked point and vertex is transformed as:

```text
CYBR = (Blender.x, Blender.z, -Blender.y)
```

The actor mesh, weapon endpoints, elemental simulation bounds, and dynamic lights therefore share the same coordinates.

## Quality boundaries

This is a real integration path, but the generic avatar bridge is intentionally distinct from the specialized production sigil solvers already in CYBR ELEMENTS. The bridge gives arbitrary animated characters a deterministic element pipeline; final hero shots can subsequently replace an individual bridge effect with a higher-resolution CYBR ELEMENTS solver while preserving the same trajectory contract.

CYBR LIGHT remains an experimental offline spectral renderer. Its own capability matrix documents limits in measured-material fidelity, deformation motion, and advanced transport algorithms. The scene does not claim film/game-studio parity merely because it uses high sample counts.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the avatar license.
