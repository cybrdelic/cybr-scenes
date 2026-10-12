# DV3: authored plant form over retained DU5 soil

This opt-in correction targets the existing drought-thinned shrub prototype.
It is a structural improvement, not photoreal completion or a measured plant.
Other shrub kinds and the rejected clast experiments are not installed.

The existing CM generator supplies the connected branch hierarchy and exact
1,481-leaf budget. The reusable `woody_form.py` supplies shorter and thinner
basal sections, low forks, uneven tapered stem sections, voxel-fused coarse
wood and curved laminae. Fine branch tubes retain their original overlapping
attachments. Two fused coarse components reach the basal datum; all three
authored root caps are separately checked on the current actual substrate.
The root test is a sampled support witness, not complete grain/root collision
or plant-growth mechanics.

SCENES owns this geometry, scene placement and contact test. MATERIAL owns the
single bark closure and JSON profile. `wood_surface.py` only verifies hashes
and binds that dependency; no bark recipe is duplicated here. This focused
correction adds no FOREST dependency and moves no existing source between repos.

## Prepare

Prepare the adjacent DR source first. The adjacent DU5 preparer must include
the versioned native-border capability correction. Use a MATERIAL checkout
at commit `bb834962787b3781232c5d35f2170bd6051ab5b6`, containing both DU5 granular-matrix and DV3 bark source/profile files:

    python3 prepare_dv3.py --material-root /path/to/cybr-material --output-root /fresh/dv3-output --view crop

Explicit `--dr-root` and `--du5-root` options support another admitted source
checkout. The default native crop is 850 × 780 at the original 2000 × 1334
camera footprint. `--view normal` is a separate view and needs its own visual
qualification; crop acceptance does not imply normal-view acceptance.

Run the DR guarded renderer with the new `job.json` and
`runtime/pipeline/clean_render_landform_candidate.sh`. Keep the shared heavy
lock, CPUs 0 and 1, jemalloc configuration, 4480 MiB sampled process-tree cap,
900-second phase bound and at least 1 GiB disk reserve. Source preparation does
not edit DR or DU5, and the runtime keeps one shared plant prototype.

The adapter stops before tracing if a coarse branch component floats, a basal
cap lacks current terrain, a protected soil/grain coordinate hash changes, or
any existing object transform changes. Root support is not obtained by moving
the grains, changing light, or altering the terrain. Existing DU5 clast form,
mountains, road, source camera and daylight remain intact.

## Isolated actual renderer fixture

    blender -b -t 2 --python-exit-code 1 --python render_fixture.py -- --dr-runtime /path/to/prepared-dr/runtime --material-root /path/to/cybr-material --output /fresh/plant-fixture

The fixture retains the original palette and displays whole-crown and basal
comparisons. Read `EVIDENCE.json` for the exact checks actually completed.
