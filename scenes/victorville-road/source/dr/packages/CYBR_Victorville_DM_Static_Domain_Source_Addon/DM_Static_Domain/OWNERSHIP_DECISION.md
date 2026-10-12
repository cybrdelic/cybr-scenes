# DM static support ownership correction

DL is retained as the previous candidate. Its cap was pointwise inventory-bounded, but its original-stock basis inherited a numerical-domain boundary: CE used finite AH mobile remainder inside the AH rectangle and an authored 18 mm regional parent outside. AH's zero collar denotes immobility, not absence of the underlying ground. The older AI surface code already distinguishes these meanings by falling back to initial_class_fractions at zero mobile stock.

Source evidence:
- `visible_shoulder_flow_ad.py::inventory_mobility` sets a complete immobile support collar before transport.
- `sediment_surface_ai.py::surface_fields` recognizes the parent material at zero mobile stock.
- `coupled_shoulder_ce.py::evaluate` replaces its regional stock with AH remainder inside a hard rectangle.
- `assemble_coupled_shoulder_ce.py` derives matrix from `remaining/max(sum,1e-20)`, losing the old zero-stock fallback.

The visible AH y=8.2 m boundary runs approximately from pixel (2,752) to (1005,651) in the retained 2000x1334 camera. DL cap median is zero on the inside collar and several millimetres immediately outside. This is a source ownership artifact, not a natural soil boundary.

## Selected bounded experiment

Use DL's exact same total fine-cap volume and the exact stored continuous AP coverage w. Set constant fully-covered cap thickness H = old cap bulk / integral(w), then new cap = H*w. Keep each original mixed reserve and every event array unchanged. Recompute original fine stock as fixed mixed reserve plus this new static cap. Medium/coarse original totals are unchanged; the fine total is also unchanged to floating precision. Record the per-cell geographic reassignment rather than invent a transport trajectory.

H is 10.2661156 mm. About 0.030489 m3 (half the L1 difference) is reassigned geographically. This is authored static initial-condition revision, not recovered stratigraphy, simulated runoff, new geological mass, or a measured Victorville site. The old DL per-cell original assignment is intentionally changed; its global class totals and mixed reserves remain fixed.

The same cap governs clast support and fractional optical coverage. Support is mean-column H*w; optical thickness on the covered fraction is H. This is an explicit unresolved packing closure. Fine source grain sizes, actual sand bank, deposited representatives, road, terrain, camera, lighting and material endpoints remain as before.

## Scope and unresolved effects

This experiment does not modify CE's existing terrain/erosion or its matrix field. Their inherited ownership discontinuity can still contribute an approximately millimetre-scale local feature. It is a cap-cause isolation, not a claim that every domain-dependent response has been fixed. No image smoothing or scatter was added.

A separate common-parent/immobile-complement model was numerically assessed but not selected here: it would newly account for 0.225148 m3 of underlying material. That is a legitimate authored geology extension only with its own ledger, not conservation of the already tracked material. Its source evidence is kept as this decision record; no such extra ledger is applied in DM.
