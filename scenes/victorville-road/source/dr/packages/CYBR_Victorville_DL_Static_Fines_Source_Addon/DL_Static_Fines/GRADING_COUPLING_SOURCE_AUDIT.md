# Retained grading/geometry coupling audit

Audit mode: existing source, JSON/NPZ metadata and retained image only. No Blender load, scene export, render or source edits. Paths below are relative to recovery-20261011. Numeric diagnostics and pins are in `GRADING_COUPLING_SOURCE_AUDIT.json`.

## Immediate correction

Restore the exact lost AI historical burial on the rebuilt chip/grit supplement: `historical_matrix * prototype_diameter * .30`, sampled from the evaluated current ground. Apply it only to the static/non-selected DG role; retain DG's existing stock-budgeted surface-representative override. Do not apply that historical chip/grit rule indiscriminately to original fine sand.

- Original rule and selected-role override: `unpacked/CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15/road_scene_r6/src/assemble_sediment_surface_ai.py:59–68`.
- CZ deletes and restores supplement with current-terrain origins: `dh_native_bodies_a/runtime/src/visible_fine_grains_cz.py:25–27`.
- DG only subtracts net surviving cover before selected-role override: `dh_native_bodies_a/runtime/src/historical_grain_roles_dg.py:52–57`.
- Current terrain matrix and compaction: `dh_native_bodies_a/runtime/src/assemble_coupled_shoulder_ce.py:54–59`.

This corrects a real loss, but should be described as a fine-grain restoration, not the completed scene-scale gravel correction. In the rebuilt-bank forward world envelope x=[−7,−3.52], y=[4.7,11.5], the CE full-authority matrix has XY-area-weighted mean about 0.153. In y=[4.7,8.2], it is about 0.0865, median zero, with only about 27% of lumped XY area above 0.01. Beyond y=8.2 it is broadly near 0.25 from CE's declared uniform 72/23/5 parent mixture. These are not projected camera-visible fractions. The rule typically gives tenths of a millimetre and has no effect on 7–60 mm tiers.

## Additional exact gaps

1. Original AP also embedded existing fine-bank origins by `.00075 * fines * (1-coarse)` and its new 7–31 mm clasts by `height * (.16 + .58*fines)`: original `assemble_road_margin_ap.py:88–96`. The rebuild drops the former. CQ replaces the latter within its relocation domain with a CE-deposit-only embedding rule.
2. `dh_native_bodies_a/runtime/src/correct_historical_gravel_domain_cq.py:219–226` places relocated AP bodies at current terrain minus `height*(.23+.52*coat)`, with `coat` from CE deposited matrix alone. It does not apply AH net retained cover or current historical matrix/compaction.
3. `dh_native_bodies_a/runtime/src/fixed_gravel_support_ci.py:22–26` only moves the CG 18–60 mm bank below `max(max(AH net,0)+CE net,0)`. Of 6,284 CG bodies at y≥4.7, 6,011 still have estimated nonzero exposure; the median and 75th-percentile net cover are zero. This is a forward-Y diagnostic, not a projected view test, and uses the pre-DH CI exposure estimate.
4. The merged coarse tiers are separate objects: `Sparse physical 7–31 mm roadside mineral lag`, `Gravel lag pockets beside shallow runoff arms`, and `Connected drainage / margin gravel bars`. CE moves their connected components by the minimum footprint foundation-plus-erosion shift (`assemble_coupled_shoulder_ce.py:33–39`); neither CI nor DG updates them. Any eventual broad support interpretation must include each visible, supported connected body exactly once, preserving rigid shape. AS sparse fragments likewise need an explicit static-support policy; do not blindly use the same origin formula for transformed mesh objects.

## Domains and authority

- AH retained ledger and historical fields: world x=[−6.2,−3.25], y=[−0.6,8.2], 5 cm grid, 12 cm boundary feather.
- CE active gate: x=[−7,−3.36], y=[−0.9,18]. Payload triangles extend farther as sampling support; this is not authority to apply a nonzero field there.
- CZ rebuilt source-size fine bank: x=[−7,−3.52], y=[4.7,11.5]. Original retained near-camera R5D bank is entirely off-frustum in the current CZ receipt.
- CQ relocated AP subset: x=(−6.4,−3.50), y=(−0.65,8). Other AP bodies remain and can appear in the forward view.
- CG worked-transition stock: x=[−6.4,−3.35], y=[−0.58,10.8].
- AP has a much broader authored road-margin chronology, to y≈85. It is historical exposure/composition, not finite deposited stock.

CC/CE suppresses duplicate BW/AP overcoat deliberately. Keep that authority ordering. Do not restore the old coat solely because explicit particles currently lack a matching support rule.

The old AK drainage reaches are behind the current camera-forward region: for retained AH rows y≥4.7, historical wash, winnowing and sand-opportunity fields are all zero. The remaining prior skin there is only 25–210 μm in active interiors. It is explicitly already inside the ground, not an added layer or new inventory (`.../src/substrate_history_ak.py:10–14`). Do not extend those earlier reaches beyond their data domain.

## Exact field availability

The NPZ archive-member scan found no explicitly named exported `ap_fines`, `ap_coarse`, `graded`, or evaluated `ak_historical_compaction` dataset. AP stores only `ap_fines` and `ap_coarse` on ground vertices (`.../src/assemble_road_margin_ap.py:27–32`); `graded` is analytic XY-only in `road_margin_composition_ap.fields`, while fine/coarse include the source slope. Re-evaluating AP with new normals would not reproduce the stored field. One bounded current-ground attribute export is the appropriate exact input if needed. CE full-authority matrix/compaction can be reconstructed from the payload, but the feather blends retained source attributes.

## If a static original-stock cap follows

A cap can be a bounded reinterpretation of existing original material, with no added terrain or transport. Separate ownership first, class by class:

- Let S = CE `stock`, P = sampled AH `retained_deposit_by_class_m` inside AH and zero outside, and O = S−P.
- Charge CE removal R to prior deposited P first, exactly matching DG: deposited debit = min(P,R); original debit = R−deposited debit.
- Surviving original = O−original debit. Surviving event-deposit representation = P−deposited debit + CE `deposited`.
- Verify nonnegativity and that both sum to S−R+CE deposited. In AH this separates original remaining bed from old deposits; outside AH O is CE's already-declared 18 mm regional parent stock.
- Bound any original-fine cap by surviving-original class 0 and keep its complementary reserve. Do not allocate the same class-0 amount to both an original cap and DG's retained-deposit budget. Do not add old AK skin thickness or an independent AP optical coat as extra material.
- A support layer is shared by all bodies occupying that region. Applying its depth to multiple clasts is not multiple new deposits; volume/optical representation accounting must nevertheless be explicit. Avoid adding a new total-cap depth to CI's net-cover correction if that cap already includes the event-deposit component.
- Derive any eventual total support target once, distinguish existing intrinsic embedding from cap-induced burial, and compare against current support. Preserve retained finite surface representatives and use actual mesh contact for every moved rigid body.

No stratigraphy or particle-trajectory solution exists in the retained sources. Any cap is an authored static mixed-layer interpretation and should be reported as such.
