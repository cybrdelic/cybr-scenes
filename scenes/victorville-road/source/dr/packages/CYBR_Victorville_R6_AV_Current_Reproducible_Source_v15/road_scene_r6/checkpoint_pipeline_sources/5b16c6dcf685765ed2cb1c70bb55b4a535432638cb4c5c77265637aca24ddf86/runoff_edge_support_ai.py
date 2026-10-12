"""AI: a bounded bank-support interpretation of the already solved AH terrain.

Pure NumPy only: no Blender, file I/O, scene edits, transport solve, or noise.
AH stops short of the pavement and protects its inner stock collar. Therefore
this module MUST NOT be described as simulated erosion/deposition at the edge.
It continues a short, explicitly reported bank grade from outside the old AC
contact band. The local AH net bed change is carried once as a support-height
offset; retained deposition is already in that change and is never added twice.
Flow strength is provenance, not an extra unbudgeted excavation multiplier.

The only spatial pattern comes from the supplied foundation/transport fields
and original road datum. There are no authored exposure sectors, random terms,
or post-transport filters. This does not produce or certify sediment mass.

Explicit integration seam in live AC (no module monkeypatching):
    ContactSpec(..., sectors=(), support_profile=profile)
    sector_fields(y, spec): return spec.support_profile.sample(y)
AC must validate the profile against its existing exposure/recession bounds.
Both its boundary and section builders then see the same zero structural loss.
The returned exposure is relative to the ORIGINAL road datum, so AC's existing
thin-crown transfer still preserves the actual AA top seam exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


def _require(ok, message):
    if not ok:
        raise ValueError(message)


@dataclass(frozen=True)
class EdgeSupportSpec:
    # Both anchors are outside AC's original x >= -3.43 contact reconstruction.
    outer_anchor_x_m: float = -3.70
    inner_anchor_x_m: float = -3.50
    excluded_contact_x_min_m: float = -3.43
    max_continuation_m: float = .40
    max_abs_grade: float = .10
    bank_clearance_m: float = .0008
    max_exposure_m: float = .032
    max_sediment_delta_m: float = .018
    max_grid_samples: int = 120_000
    max_edge_samples: int = 10_000

    def validate(self):
        values = [self.outer_anchor_x_m, self.inner_anchor_x_m,
                  self.excluded_contact_x_min_m, self.max_continuation_m,
                  self.max_abs_grade, self.bank_clearance_m,
                  self.max_exposure_m, self.max_sediment_delta_m]
        _require(np.isfinite(values).all(), 'Support limits must be finite')
        _require(.10 <= self.inner_anchor_x_m-self.outer_anchor_x_m <= .35,
                 'Use a 10--35 cm source bank-grade span')
        _require(self.inner_anchor_x_m <= self.excluded_contact_x_min_m-.02,
                 'Support anchors must be outside the authored AC contact band')
        _require(0 < self.max_continuation_m <= .40,
                 'Bank continuation must remain at most 40 cm')
        _require(0 < self.max_abs_grade <= .10,
                 'Bank-grade continuation must remain shallow (at most 10%)')
        _require(.0004 <= self.bank_clearance_m <= .002,
                 'Bank clearance must remain 0.4--2 mm')
        _require(self.bank_clearance_m < self.max_exposure_m <= .032,
                 'Never deepen exposure beyond the existing 32 mm cap')
        _require(0 < self.max_sediment_delta_m <= .018,
                 'Do not amplify the existing AH 18 mm sediment bound')
        _require(type(self.max_grid_samples) is int and 9 <= self.max_grid_samples <= 120_000,
                 'Grid allocation must remain bounded by 120000 samples')
        _require(type(self.max_edge_samples) is int and 2 <= self.max_edge_samples <= 10_000,
                 'Edge allocation must remain bounded by 10000 samples')
        return self


def _axis(value, name):
    a = np.asarray(value, dtype=float)
    _require(a.ndim == 1 and len(a) >= 3 and np.isfinite(a).all(),
             name+' must contain at least three finite coordinates')
    d = np.diff(a)
    _require(np.all(d > 0) and np.allclose(d, d[0], atol=1e-10, rtol=1e-6),
             name+' must increase uniformly')
    return a


def _sample(a, x, y, query_x, query_y):
    """Bilinear source sampling with a hard coverage check, never clamping gaps."""
    qx, qy = np.broadcast_arrays(np.asarray(query_x, float), np.asarray(query_y, float))
    _require(np.all((qx >= x[0]) & (qx <= x[-1]) &
                    (qy >= y[0]) & (qy <= y[-1])),
             'Support anchors must lie inside actual AH field coverage')
    ix = np.clip(np.searchsorted(x, qx, side='right')-1, 0, len(x)-2)
    iy = np.clip(np.searchsorted(y, qy, side='right')-1, 0, len(y)-2)
    u = (qx-x[ix])/(x[ix+1]-x[ix])
    v = (qy-y[iy])/(y[iy+1]-y[iy])
    return ((1-v)*((1-u)*a[iy, ix]+u*a[iy, ix+1])
            + v*((1-u)*a[iy+1, ix]+u*a[iy+1, ix+1]))


def _readonly(a):
    result = np.asarray(a).copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class EdgeSupportProfile:
    y_m: np.ndarray
    base_edge_xyz: np.ndarray
    exposure_m: np.ndarray
    bank_top_z_m: np.ndarray
    raw_bank_top_z_m: np.ndarray
    foundation_grade: np.ndarray
    anchor_net_sediment_delta_m: np.ndarray
    anchor_retained_deposit_m: np.ndarray
    anchor_flow_strength: np.ndarray
    continuation_distance_m: np.ndarray
    spec: EdgeSupportSpec
    report: dict

    def sample(self, y):
        """AC-compatible nominal exposure, with no invented structural fracture.

        The other fields expose source provenance for audits; bank top is a
        reconstructed support datum, not AH coverage or newly deposited mass.
        Querying outside the supplied actual road boundary fails explicitly.
        """
        q = np.asarray(y, float)
        _require(np.isfinite(q).all() and np.all((q >= self.y_m[0]) & (q <= self.y_m[-1])),
                 'Support query outside supplied actual road boundary')
        out = {name: np.interp(q, self.y_m, getattr(self, name)) for name in (
            'exposure_m', 'bank_top_z_m', 'raw_bank_top_z_m', 'foundation_grade',
            'anchor_net_sediment_delta_m', 'anchor_retained_deposit_m',
            'anchor_flow_strength', 'continuation_distance_m')}
        out['structural_loss_m'] = np.zeros_like(q)
        out['sector_id'] = np.zeros(q.shape, dtype=np.int32)
        return out


def build_edge_support(x_m, y_m, foundation_z_m, sediment_delta_m,
                       retained_deposit_by_class_m, flow_strength,
                       base_edge_xyz, *, spec=None):
    """Derive a bounded support profile without changing inputs or external state.

    Inputs are AH's saved arrays and the actual ORIGINAL road edge XYZ. Source
    samples at the two anchors determine crossfall. Continue this foundation
    grade toward the road, then carry the inner anchor's net sediment offset
    once. Erosion/deposition retain the solver's signs and metre scale. Retained
    deposition validates this net offset and is reported, not added again.

    The 0.4--2 mm crown clearance and <=32 mm exposure limit are geometric
    contact constraints. Any constrained part is reported as a reconstruction;
    it is not a conservation correction or a claim of transported soil volume.
    """
    spec = (spec or EdgeSupportSpec()).validate()
    x = _axis(x_m, 'x_m'); y = _axis(y_m, 'y_m')
    shape = (len(y), len(x))
    _require(len(x)*len(y) <= spec.max_grid_samples, 'AH support grid allocation cap exceeded')
    z = np.asarray(foundation_z_m, float)
    delta = np.asarray(sediment_delta_m, float)
    retained = np.asarray(retained_deposit_by_class_m, float)
    flow = np.asarray(flow_strength, float)
    _require(z.shape == delta.shape == flow.shape == shape,
             'Foundation, sediment delta, and flow must match the AH grid')
    _require(retained.shape == shape+(3,), 'Supply the three actual retained sediment classes')
    _require(all(np.isfinite(a).all() for a in (z, delta, retained, flow)),
             'AH support fields must be finite')
    _require(np.all(retained >= 0) and np.all((flow >= 0) & (flow <= 1)),
             'Retained stock must be nonnegative and AH flow strength must be in [0,1]')
    _require(np.max(np.abs(delta)) <= spec.max_sediment_delta_m+1e-12,
             'AH sediment offset exceeds its unchanged metric bound')
    deposited = retained.sum(axis=-1)
    _require(np.max(delta-deposited) <= 1e-12,
             'Positive net sediment rise cannot exceed actual retained deposition')
    base = np.asarray(base_edge_xyz, float)
    _require(base.ndim == 2 and base.shape[1] == 3 and 2 <= len(base) <= spec.max_edge_samples,
             'Supply 2--10000 ordered actual original road-edge XYZ samples')
    _require(np.isfinite(base).all() and np.all(np.diff(base[:, 1]) > 0),
             'Actual original road edge must be finite and strictly increasing in Y')
    _require(y[0] <= base[0, 1] < base[-1, 1] <= y[-1],
             'Actual AH source must cover the complete road-edge Y extent')
    # Preserve every actual road knot and distinct source Y breakpoint. Source
    # linspace/arange axes can represent the same Y a few ulps apart. Keep the
    # actual road value in that case rather than creating near-zero-width rows.
    source_y = y[(y >= base[0, 1]) & (y <= base[-1, 1])]
    index = np.searchsorted(base[:, 1], source_y)
    near = np.minimum(np.abs(source_y-base[np.minimum(index, len(base)-1), 1]),
                      np.abs(source_y-base[np.maximum(index-1, 0), 1]))
    tolerance = 64*np.finfo(float).eps*max(1., float(np.max(np.abs(base[:, 1]))))
    knots = np.sort(np.r_[base[:, 1], source_y[near > tolerance]])
    _require(len(knots) <= spec.max_edge_samples+len(y), 'Profile knot allocation cap exceeded')
    edge = np.column_stack([np.interp(knots, base[:, 1], base[:, k]) for k in range(3)])
    distance = edge[:, 0]-spec.inner_anchor_x_m
    _require(np.all((distance >= 0) & (distance <= spec.max_continuation_m)),
             'Actual road lies beyond the bounded bank-grade continuation')
    outer = _sample(z, x, y, spec.outer_anchor_x_m, knots)
    inner = _sample(z, x, y, spec.inner_anchor_x_m, knots)
    slope = (inner-outer)/(spec.inner_anchor_x_m-spec.outer_anchor_x_m)
    _require(np.max(np.abs(slope)) <= spec.max_abs_grade+1e-12,
             'Actual source bank grade is too steep to continue safely')
    net = _sample(delta, x, y, spec.inner_anchor_x_m, knots)
    deposit = _sample(deposited, x, y, spec.inner_anchor_x_m, knots)
    strength = _sample(flow, x, y, spec.inner_anchor_x_m, knots)
    raw_bank = inner+slope*distance+net
    raw_exposure = edge[:, 2]-raw_bank
    exposure = np.clip(raw_exposure, spec.bank_clearance_m, spec.max_exposure_m)
    bank = edge[:, 2]-exposure
    report = dict(
        model='Short bank-grade continuation from actual AH foundation and finite-stock response',
        source_anchor_x_m=[spec.outer_anchor_x_m, spec.inner_anchor_x_m],
        excluded_authored_contact_x_min_m=spec.excluded_contact_x_min_m,
        source_grid_shape_yx=list(shape), source_spacing_xy_m=[float(x[1]-x[0]), float(y[1]-y[0])],
        profile_knots=len(knots), bounds_y_m=[float(knots[0]), float(knots[-1])],
        bank_continuation_distance_range_m=[float(distance.min()), float(distance.max())],
        distance_beyond_AH_grid_range_m=[float(np.maximum(edge[:, 0]-x[-1], 0).min()),
                                       float(np.maximum(edge[:, 0]-x[-1], 0).max())],
        foundation_grade_range=[float(slope.min()), float(slope.max())],
        anchor_net_sediment_delta_range_m=[float(net.min()), float(net.max())],
        anchor_retained_deposit_range_m=[float(deposit.min()), float(deposit.max())],
        anchor_flow_strength_range=[float(strength.min()), float(strength.max())],
        raw_exposure_range_m=[float(raw_exposure.min()), float(raw_exposure.max())],
        exposure_range_m=[float(exposure.min()), float(exposure.max())],
        exposure_cap_m=spec.max_exposure_m, bank_clearance_m=spec.bank_clearance_m,
        clearance_constrained_knots=int(np.count_nonzero(raw_exposure < spec.bank_clearance_m)),
        depth_constrained_knots=int(np.count_nonzero(raw_exposure > spec.max_exposure_m)),
        maximum_bank_constraint_adjustment_m=float(np.max(np.abs(bank-raw_bank))),
        structural_loss_m=0., authored_exposure_sectors=False,
        periodic_or_random_displacement=False, post_transport_smoothing=False,
        retained_deposition_already_in_net_delta=True, retained_deposition_added_twice=False,
        flow_strength_role='Diagnostic only; causal weathering is already encoded in net bed change',
        conserves_or_introduces_sediment_mass=False, modeled_edge_deposition=False,
        original_top_or_material_modified=False,
        limits='AH has no simulated stock at the road edge. This is a bounded geometric bank interpretation '
               'continued through its protected collar, not surveyed terrain, validated hydraulics, '
               'or an edge sediment-mass ledger. Actual mesh contact and visual quality require separate checks.')
    return EdgeSupportProfile(*[_readonly(a) for a in (
        knots, edge, exposure, bank, raw_bank, slope, net, deposit, strength, distance)], spec, report)
