# Controlled filter-artifact fixture

The two PNGs use the same raw 420 × 315, 8-sample frame, guides, exposure, and no highlight clamp. The `before` frame uses the legacy asymmetric log-luminance weights; `after` uses the corrected symmetric log-variance weights and propagated-variance floor. The raw EXRs and NPZ/NPY guides are preserved here. This is a filter comparison, not a render-convergence or physical-accuracy benchmark.

From the project root, replay the new finish with:

```bash
python finish_v3.py verification_v3/filter_fixture/detail_preview --exposure 1.4 --no-outlier-control
```

The old reference implementation is `verification_v3/legacy_filter_reference.py`. It is supplied for inspection and the controlled comparison only, not used to produce the final render.
