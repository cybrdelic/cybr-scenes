# Optional mapped hedge candidate v1

This is new construction from retained mapped source, not exact recovery of the
earlier private hedge fixture. No baseline source, mapped geography, merged
facade or sidewalk, or dedicated landmark is changed.

The audited source contains 203 hedges: 69 OSM lines, 34 OSM polygons and 100
UCSB polygons. The original base exports no hedge parts. The OSM set is the
bounded candidate scope. Campus polygons remain deferred for overlap/epoch
review. The coverage receipt preserves every hedge's identity, geometry, tags
and chosen support semantics; it does not claim unbuilt features are integrated.

Use explicit source height/width tags when present. In the current OSM line set
both are absent, so 0.8 m line width and 1.2 m height are authored estimates.
Polygons keep their mapped outline rather than an invented line width. Leaves
are 4–8 cm in length. Their one-sided surface area was compared at authored LAI
2.80 and 4.50 per horizontal support area. Neither is a site measurement. The
denser 4.50 scenario is the current bounded context candidate. Four triangles
form one folded sheet; no coincident reverse sheet
is counted. Stem/shoot geometry supports the leaves. Generic species, pruning,
LAI, structure and retained leaf optics are authored, not surveyed biomass.

The first street gate is OSM way 822177699, beside mapped Pasado Road. It is a
standalone optional mesh rendered in fresh stage-1 geographic context, not a
replay of the entire 64-stage integrated scene. Base massing is an explicit
preview limitation. Nothing here replaces the accepted current facade scene.

## Bounded local replay

After the existing setup, verified inputs, and fresh stages 1–3, use the
optional bounded runner (which retains the exact AVX2/Haswell profile):

- export CYBR_HEAVY_LOCK=/workspace/shared/cybr-heavy.lock
- ./run.sh hedges-v1 build --lai 4.5
- ./run.sh hedges-v1 render --spp 32
- ./run.sh hedges-v1 baseline --spp 32

Its individual scripts are also available via tools/replay_retained_iv_script.py:

- iv_mapped_hedges_v1.py build
- iv_mapped_hedges_v1.py verify
- test_iv_mapped_hedge_coverage.py (after build or audit)
- capture_iv_mapped_hedges_v1.py --prepare-only
- capture_iv_mapped_hedges_v1.py --spp 32
- capture_iv_mapped_hedges_v1.py --spp 32 --baseline

Every heavy phase must hold /workspace/shared/cybr-heavy.lock, use CPUs 0/1,
the existing sampled 4,480 MiB process-tree guard, a 900-second deadline, and
at least 1 GiB free disk. Save this source before the first native render.
Do not run --all-osm or integrate before reviewing the fixture and validation.

The optional all-OSM builder is not qualified for every source shape. The
current form explicitly refuses nonconvex, holed and multipart supports rather
than connecting branches across unsupported space. Very narrow shapes also
fail. A final native mesh audit checks every blade, stem, primary branch and
twig triangle, including cylinder radii. Entire projected triangle surfaces
must remain inside support within 0.2 mm float32 tolerance. A conservative
continuous-surface certificate uses the exact SharedGround affine-gradient
Lipschitz bound to check terrain and declared maximum height between vertices.
Only basal stems receive an authored 20 mm burial allowance, for seating their
14 mm radius cylinders on sloped ground; this is not measured root depth.
Other geometry has no burial allowance. Bounds that cannot certify a shape
fail rather than clip or move geometry.
The current support audit also finds 10 OSM features overlapping mapped
building footprints (12.39 m² total), plus overlapping hedge supports. The
builder refuses those unresolved conflicts; the Pasado fixture has none.
Eight building conflicts arise only from estimated line width, one source
line crosses building interiors, and one source polygon itself overlaps a
building. Six overlapping hedge pairs bring the excluded set to 19 source
IDs, leaving 84 preliminary conflict-free candidates, not 84 accepted builds.

## Architecture qualification

The first two actual 700-pixel fixtures passed transport and geometry checks
but were rejected visually as stem-heavy isolated shrubs/saplings. They do not
qualify a regional rollout. Cheap 400 × 280 three-quarter gates compare lateral
branching at LAI 2.8 and 4.5. Short basal stems support lateral primary branches
and paired-leaf shoots; the latter scenario screens internal wood more fully.
The current context candidate adds deterministic per-plant crown-height scale
0.88–1.0 and bounded branch rotation ±0.35 radians, constrained by the same
source support. These are authored structural differences, not per-image noise.

The actual r4 700 × 490, 32-packet matched context gate rendered successfully
with zero invalid paths (287.16 s guarded wall time, 945.22 MiB sampled peak).
The source-preserving hedge geometry was accepted as an improvement over r1/r2.
This does not qualify the surrounding base ground, trees or building appearance.
The paired image keeps the same camera, base mesh and lighting; it compares the
combined architecture/density change from authored LAI 2.8 to 4.5, not a pure
single-variable architecture experiment. All 272,412 native hedge triangles pass
support, terrain and maximum-height checks, with no blade/backface area double
counting. The audit-only source additions reproduce the rendered mesh byte for
byte; a second identical render is not required for that verification.

Whole-region rollout is intentionally deferred. Even the 84 preliminary
conflict-free supports would request about 9.78 million explicit leaves at this
LAI, approximately 44.4 million triangles by fixture scaling. A regional
representation and resource strategy needs separate qualification within the
existing guard; this optional fixture does not make that scale claim.

The green patch behind the original Pasado fixture is retained mapped grass,
not a leftover hedge proxy: native object 270, OSM way 601207132, landuse=grass,
source version 2 dated 2020-01-12. Pixel-position checks independently locate
that ground in the source polygon. Its footprint and appearance are unchanged.

The broad bare ground band is a separate material experiment. This hedge
candidate gives no authority or source basis to place vegetation there.

## Fresh-install CIE input repair

The reviewed runtime-only wheel does not contain the separately licensed CIE
observer table. The prior path helper nevertheless linked its historical data
path into that wheel, making a fresh native render fail before tracing. The
shared helper now verifies and links the existing repository CIE input, whose
official SHA-256 remains fa663e3535a7e0763a745993a1f0a192eb0275ac46ad2d1befd7626841e713c1.
It repairs only the known obsolete alias and refuses unrelated directories or
links. The regression test covers a missing-table wheel, a fresh tree, repeated
calls and refusal of unrelated aliases. The original CC BY-SA 4.0 attribution
and verification metadata remain intact; the table and renderer are unchanged.

Compact coverage receipts retain OSM source coordinates under the existing
ODbL notices. Campus geometry and attributes are withheld from redistributable
receipts, with source identity and geometry digest retained. The original
consumer-fetched campus inputs and their access/terms remain necessary locally.
