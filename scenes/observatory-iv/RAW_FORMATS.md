# Native film formats

All raw arrays are the actual renderer outputs, before the reconstruction and display transform. RGB may contain small negative components after converting the finite-band spectral estimate into linear RGB. Those values are preserved in the raw EXR and PFM. PNG necessarily uses a display transform and is not a radiance file.

## PFM

`Observatory_IV.pfm` is combined scene-linear RGB. `Observatory_IV_direct.pfm`, `Observatory_IV_indirect.pfm`, and `Observatory_IV_volume.pfm` are the additive components. Header: ASCII `PF`, width and height, then `-1.0` for little-endian 32-bit float RGB. Scanlines are stored bottom first. The supplied `finish.read_pfm` reads this layout.

## Spectral framebuffer

`Observatory_IV.spectral`: four little-endian uint32 header values: magic `0x36315053`, width, height, 16. Followed by a top-to-bottom, row-major `(height, width, 16)` array of little-endian float32 spectral radiance samples. The 16 midpoint wavelengths are `380 + (k + 0.5) * 25` nanometres. Conversion weights and the approximate observer are in `src/spectrum.h`.

## Geometry/variance guides

`Observatory_IV.guides`: little-endian uint32 width, height; then row-major `(height, width, 9)` float32 values: normal XYZ, linear material color RGB, camera-ray depth, estimated variance of mean luminance, and material ID. `Observatory_IV_guides.npz` contains the same array in standard NumPy format. The first-surface guides for reflected or transmitted images are an approximation, not a full path-space feature representation.

`Observatory_IV_transmitted.guides` uses the same nine-float layout, but glass pixels contain features from the dominant 550-nm refracted path. Reconstruction uses only its normal and depth for glass. It is not another radiance render or a full spectral path-space feature representation.

## Sampling counts

`Observatory_IV.samples`: little-endian uint32 width, height, then `(height, width)` uint32 per-pixel camera-sample counts. The sixteen wavelength continuations at a quartz surface are not counted as sixteen new camera samples. The metadata reports the histogram and sum.

## EXR

The raw RGB and component EXRs contain the corresponding float32 PFM values without normalization or reconstruction. `Observatory_IV_finished.exr` is reconstructed, scene-linear RGB. The verification script checks exact preservation in the raw EXR conversion.

## Display transform and reconstruction

Both finished and unfiltered PNGs use the recorded RGB white normalization, exposure, ACES fitted shoulder, and sRGB encoding. Only the finished PNG has component-separated, geometry-guided non-neural reconstruction. No path-radiance clamp, generative edit, or post-render isolated-pixel replacement is used. Reconstruction changes image values and is not an unbiased estimator or a convergence certificate.
