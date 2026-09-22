# Optics and filtering: scope of the new checks

## Rough dielectric estimator

The surface normal is oriented toward the outgoing direction. The relative index is `eta_t / eta_i`. The microfacet distribution is isotropic GGX, and the sampled distribution is conditional on visibility from the outgoing direction. Reflection/transmission selection uses dielectric Fresnel, not a fixed 50/50 branch. The evaluator and density include the same branch probabilities.

In transmission the refractive half-vector is proportional to `wo + eta * wi`; the direction-change Jacobian and radiance-mode inverse-square index factor are both included. Consequently the sampled smooth-interface radiance integral when entering the material approaches `F + (1-F)/eta²`, not one. This is a radiance/adjoint convention, not a claim that the interface absorbs the missing fraction of energy. The exit interface carries the reciprocal index scaling.

`test_rough_quartz.cpp` checks finite sampled weights, the smooth-boundary limit, and the eta-scaled reverse-transmission convention. It is not a complete proof of the integrator, a guarantee that every difficult caustic path is efficiently sampled, or a birefringence/polarization test.

Primary formula reference: *Physically Based Rendering*, fourth edition, section 9.7, https://pbr-book.org/4ed/Reflection_Models/Rough_Dielectric_BSDF .

## Why the old filter produced a dotted grid

For the filter's luminance transform `g(L) = log(1 + 4 L)`, first-order uncertainty propagation is `var(g(L)) ≈ var(L) * [4 / (1 + 4 L)]²`.

The old code combined the two pixels' linear variances but applied only the **center** pixel's derivative. This was asymmetric: a high-luminance sample could strongly reject a dark neighbor while that neighbor accepted and spread the same bright sample. Spaced wavelet taps made the resulting halo visibly periodic.

The revised code transforms both variances separately and then adds them. The luminance-distance denominator is symmetric under swapping the two pixels. A more conservative propagated-variance floor also avoids treating earlier wavelet results as prematurely converged.

The included controlled fixture demonstrates the change on one fixed, low-sample raw frame. Neither comparison uses the optional bright-outlier control. The tests also check pairwise luminance-weight symmetry and preservation of a constant field. They do **not** say that all remaining noise is removed, that real highlights are never smoothed, or that the native path integral is fully converged. The raw frame is retained so these distinctions can be inspected.
