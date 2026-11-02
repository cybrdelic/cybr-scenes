# Afterlight v3 — Understory

An additive `/forest/` environment for the existing Afterlight lab. It is a real Gaussian reconstruction rendered with Spark/Three.js and a depth-tested editable mesh layer. It is not a procedural tree demo, panorama, or video masquerading as 3D.

## What is real

The forest, its trail, canopy and lighting come from **Forest Scan by draftmode**, published at https://superspl.at/scene/259c0051 under **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/). The original SOG WebP data is repacked losslessly into a local `.sog` ZIP. Runtime rendering uses the original learned Gaussian representation, not a newly trained model. The capture is 2,142,439 Gaussians. The benchmark artifacts contain actual browser output and measured conditions.

A second licensed woodland capture, **Tree work along the nature trail by alfred2010**, https://superspl.at/scene/0c75de4a, is retained in the source acquisition package, not misrepresented as part of the first capture. It is also CC BY 4.0. Each capture includes provenance and hashes.

## Hybrid rendering

Spark 2.4.0 and Three.js 0.180.0 share one WebGL2 renderer, camera, and depth buffer. Ordinary opaque editable meshes render before the transparent Gaussian pass. Native mode renders all original Gaussians; Balanced and Mobile use a generated LoD representation and explicit budgets. No general-purpose image blur, upscaling, or depth of field is used. Anti-alias covariance inflation is opacity compensated. Focal adjustment 2 matches the PlayCanvas source renderer convention.

Additions: two timber waymarks and a small weathered trail bench. They can be moved, rotated and scaled. Their transforms are locally persisted, undoable, and importable/exportable as validated JSON. The scan itself is not destructible or relightable. Added meshes do not physically alter baked lighting in the capture; this is not a jointly relit scene reconstruction.

## Navigation

Drag to look, WASD to move, Shift to move faster. 1 selects terrain-following trail walking; 2 selects unrestricted flight. Q/E or Control/Space moves vertically in flight. Double-click captures the mouse; Escape releases it. Touch devices have a movement joystick and vertical controls. H hides/restores the interface. Guided walk follows the captured winding trail rather than spinning around an object.

The visible dirt trail is from the capture, not a painted overlay. A height field derived from the Gaussian centers and a manually traced centerline constrain walking to a supported corridor. This is an approximate navigation proxy, not a surveyed collision mesh. The publisher provides collision *metadata*, but the binary collision volume was not supplied through the discovered source URL; this implementation does not claim to use it. Camera scale remains in capture units, not verified metres. Fly mode can expose missing, blurry or under-observed regions.

## Build and run

With the included `public/data` assets:

```sh
npm install
python -m pip install numpy pillow
python tools/prepare.py
npm run build
npm start
```

Open http://localhost:4173. The distributable `dist/` is static and includes pinned local runtime files and the capture; it makes no CDN/API calls during viewing. Any normal HTTP server works. File:// is not supported by browser ES module and fetch security rules.

## Render and verify

```sh
npx playwright install --with-deps chromium
npm run test:ci
```

The test harness opens the actual renderer with Chromium/SwiftShader, exports camera-view screenshots and a deterministic walkthrough frame sequence, and checks native resolution, free movement, navigation, transforms, layout validation and absence of fatal browser errors. Its measured software-renderer speed is not a phone or desktop-GPU benchmark. Hardware 60 fps is not asserted.

## Integration and publishing status

Copy the **contents** of `dist/` into a new `forest/` folder in the existing Afterlight site's static output, and add a navigation link to `/forest/`. This is additive: do not replace the lab root or remove its eight object scenes. An iframe is unnecessary. The original Sites project is `appgprj_6ae8835464f48191a3eacc533efe0180`.

The current connected tools do not include the original first-party Sites publisher or its source checkout. A build, repository commit, or successful GitHub Action is **not** a deployment to the original site. This package must not be described as live until that publisher returns success and `/forest/` is verified. ShipStatic is not used.

Code: MIT. Three.js and Spark: MIT. Forest data: separate CC BY 4.0 licenses; retain attribution in distributions and renders.
