# Sandstone Walk — local banding correction

This is a local patch of the two supplied Sandstone Walk v0.5 standalone viewers. Nothing in this delivery is pushed to a repository. The original HTML files remain intact.

## What was actually wrong

The original viewer already had half-float current/history render targets and a half-float spectral-response bake. It was not simply an 8-bit-lighting implementation. Promoting an already quantized bake to a different container would not recover missing information, so this patch does not pretend to do that.

A freshly executed, texture-independent shadow-visibility capture reproduced a dense periodic pattern across the canyon walls. The custom shadow routine sampled nearest depth texels but corrected the receiver depth at the requested sample coordinates, rather than at the coordinates of the texels actually returned. It also derived the receiving plane from a smooth shading normal. On sloping surfaces this mismatch caused false self-shadowing. Its sixteen binary comparisons could produce only seventeen visibility values before later spatial/temporal interpolation.

The final presentation shader also rounded smooth encoded gradients to the 8-bit display without explicit dithering. Intermediate buffers were RGBA16F, and HDR/depth samplers relied on the GLSL ES default sampler precision. A `highp float` declaration is not a `highp sampler2D` declaration. That is an independent portability issue, particularly on hardware that implements lower sampler precision than the desktop test device.

## Changes

**Shadow comparisons.** Depth values are fetched at known texel centres with high-precision samplers. The receiving plane is evaluated at those same centres, using the raster triangle normal rather than the normal used for smooth lighting. The four comparison outcomes are bilinearly combined. Sixteen area samples therefore produce fractional coverage instead of a seventeen-level staircase. The blocker search is also fractionally weighted. A bounded normal offset scales with the shadow texel's world-space footprint; it is not an arbitrary screen-space blur. Faces turned away from the emitter do not receive direct sunlight. The sun direction, 4096² shadow maps, scene geometry and geometric occluders remain.

**HDR precision.** The current-frame target and both history targets are RGBA32F. Their filtering remains nearest; no float-linear-filtering extension is required. Construction fails explicitly when the requested framebuffer is incomplete. The original storage exposure of 0.25 and its inverse are retained so there is no exposure or tone-curve change.

**Final quantization.** A deterministic, achromatic triangular-distribution dither is added after the existing tone transform and sRGB encoding, immediately before display quantization. Its continuous amplitude is bounded by one 8-bit code value. It has no frame counter, never enters the HDR history and does not replace or smooth image detail. Numeric diagnostic views are not dithered. The existing display transform itself is unchanged.

**Memory-bounded 4K export.** A full-frame allocation of three 32-bit histories caused context loss during the first full-map 4K-export test in this memory-limited environment. The delivered capture path instead renders off-axis native-resolution tiles, with two-pixel derivative guards, using the original camera projection. Each tile completes its RGBA32F sample accumulation and final tone/dither pass before lossless placement into the PNG canvas. Dither uses global image pixel coordinates so tile borders cannot restart the noise pattern. The default 1024-pixel tile has about 52.4 MiB of color-target storage rather than allocating three full-4K histories. This is genuine 4K rendering, not a resized lower-resolution screenshot. The initial context-loss report is retained in the test evidence and is not counted as a passing delivery.

**Sampler precision.** The photographic-data, depth, sky, accumulation and display sampling paths explicitly request high precision.

## What is deliberately unchanged

All 5,029,800 triangles, 2,526,592 vertices, position/index buffers, source normals, baked spectral-response buffers and photographic image payloads are preserved. The native scene hash remains `7522cf1848ef94af2593e4a2d2a9df382df11c2e85e9ac4662a364a107656c79`.

The photographic 4K/2K maps are not re-encoded, enlarged, regenerated or blurred. The material's parallax and small-scale shading code are retained. Walk/orbit controls, camera framing, exposure and the tone transform are retained. No new spectral bake, photo projection, neural reconstruction or image generation is involved. Natural rock bedding and actual ledge geometry are not removed as if they were numerical bands.

## Apply to an original standalone file

Only Python's standard library is required for the patch:

```sh
python apply_local_fix.py --input Sandstone_Walk_Detail_4K.html --output Sandstone_Walk_BandingFixed_4K.html
python apply_local_fix.py --input Sandstone_Walk_Detail_Compact.html --output Sandstone_Walk_BandingFixed_Compact.html
```

Input SHA-256 is checked against the two exact original delivery files. The patch refuses an unknown version or an attempt to overwrite the input. It writes a JSON receipt alongside the output. After patching, it checks that the complete embedded scene payload is byte-identical and that every photographic image payload is identical. It updates the shader checksum to match the actual replacement shader.

The already-built corrected HTML files supplied with this conversation require no patch command. The source archive is a patch/reproduction kit, not a duplicate of the large original texture and geometry payloads. Keep one of the original v0.5 HTML files to reproduce it.

## Executed verification

The reports and images are under `evidence/`. `verification.json` summarizes the final delivery checks.

- An actual WebGL2 planar-receiver test holds geometry and lighting fixed. Before the correction, 99.246% of the tested unoccluded steep plane received some false shadow, with average visibility 0.849645. The corrected result is visibility 1.0 throughout and zero false-shadow pixels.
- A magnified analytic occluder-edge test produces 17 distinct floating-point visibility values with the old routine and 501 with the corrected one. This is a shader-stage measurement, not a claim that an 8-bit channel stores 501 different codes.
- For the supplied controlled gradient, linear accumulation root-mean-square error decreases from approximately `8.30e-6` to `5.13e-10`. After 8-bit output, column-averaged encoded error decreases from `0.0011363` to `0.0001240`. Dither trades tiny bounded pixel variation for reduced coherent quantization contours; it does not reduce every individual pixel's absolute error.
- Shader output is captured immediately after real draws. Repeating a converged stationary frame produces identical PNG bytes: no time-varying grain is introduced.
- The delivery tests query actual framebuffer attachment bit depth, rather than trusting a JavaScript format label. All three HDR targets report 32-bit components.
- Scene captures include the reference camera, a forward camera, shadow visibility and the bright sun. Mobile input is exercised with Chromium touch emulation, including simultaneous thumbstick/look, cancellation, orbit and pinch zoom. Geometry remains fully loaded; ordinary frustum culling is allowed for sky-facing views.

### Test environment and limits

The executed renderer is Chromium/WebGL2 with ANGLE and Mesa llvmpipe on Linux. This environment's browser administrator blocks navigation to local HTTP/file URLs. Consequently the final tests load the exact delivered script blocks and embedded JSON nodes in an in-memory Chromium document. They exercise the real bootstrap, decompression, map upload, shaders, framebuffers and controls; they are not a claim of successful HTTP or file-URL navigation in this environment. No native-render screenshot is substituted for a browser draw. The initial touch-harness failure was corrected by using a mobile browser context and flushing input to an actual browser animation frame; the runtime controller was not edited to make the test pass.

There is no physical-phone performance benchmark. The existing surface bake and finite shadow-map resolution are still approximations, not a new path-tracing implementation or a claim that every future camera pose is artifact-free.

## Memory

The three color targets now require 48 bytes per output pixel rather than 24. That is about 22 MiB of additional color-target storage at 1200×800, about 68 MiB at 1170×2532, and 192 MiB at the existing 8,388,608-pixel cap. This excludes depth, shadow maps, geometry and textures. Resolution policy and the pixel cap are unchanged; the patch does not silently lower native resolution. The compact download retains the same geometry and fixes with the original 2K photographic maps.

## Run the tests

Rendering tests additionally require NumPy, Pillow, Playwright, Chromium, Mesa and Xvfb. The scripts target the Linux environment described above; they do not install packages automatically.

```sh
Xvfb :94 -screen 0 1600x1000x24 &
python tests/test_delivery.py --file /path/to/Sandstone_Walk_BandingFixed_Compact.html --name compact_delivery
python tests/test_delivery.py --file /path/to/Sandstone_Walk_BandingFixed_4K.html --name full_delivery --export
python tests/test_precision.py
```

`test_precision.py` uses the included original/corrected shader sources; it does not need the large scene assets. `test_delivery.py` reads the corrected standalone itself and does not fetch assets. `source/prepare_local.py` and `source/patch_sources.py` retain the extraction and source-construction path used during development. The provided `apply_local_fix.py` is the simpler delivery path.

## Technical references

The GLSL ES 3.00 specification defines sampler precision separately from float precision (section 4.5.4 and the sampler-precision discussion). The Khronos `EXT_color_buffer_float` extension includes RGBA32F renderability. These references establish API behavior, not visual quality certification. Measurements above come from the included executed tests.

Software modifications retain the original GPL-2.0-only license. The original viewer's Three.js notices and photographic-map provenance remain embedded and unchanged.
