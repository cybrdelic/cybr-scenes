"""Small isolated parity/RSS receipt; refuses fixtures above 10,000 virtual grains."""
import argparse
from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import stable_catalog as ref
import compact_catalog as compact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("numpy", "numba"), default="numpy")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    frozen = "c50333339f4f4fe92c6ce03cf10704cec83812f7cb89db07b99906504f9e044c"
    assert hashlib.sha256(Path(ref.__file__).read_bytes()).hexdigest() == frozen
    pp = [ref.Prototype(13, 0, 0, 43.25, .041), ref.Prototype(297, 1, 1, 61.75, .026),
          ref.Prototype(885, 2, 2, 29.2, .021)]
    spec = ref.CatalogSpec(seed=2610100225, cell_size=.5, bounds=(-1., 1., -1., 1.),
                           thinning_by_band={0: 1., 1: 1., 2: 1.}, catalog_epoch="compact-isolated-parity-v1",
                           source_pins={"geometry": "unchanged-fixture"}, max_virtual_candidates=9000,
                           max_catalog_candidates=8000, max_grid_bins=10000, chunk_size=31)
    bb = [[0, 0, .2], [-.6, .3, .11], [3, 3, .02]]
    start = time.monotonic()
    baseline = compact.rss_bytes()
    actual = compact.build_compact_catalog(spec, pp, bb, backend=args.backend)
    compact_peak = compact.peak_rss_bytes()
    first_elapsed = time.monotonic() - start
    assert actual.serial_map.virtual_count <= 10000
    before = time.monotonic()
    warm = compact.build_compact_catalog(spec, pp, bb, backend=args.backend)
    warm_elapsed = time.monotonic() - before
    assert actual.status2.tobytes() == warm.status2.tobytes()
    expected = ref.build_catalog(spec, pp, bb, backend=args.backend)
    decoded = compact.reconstruct(actual)
    for f in fields(expected.grains):
        assert getattr(expected.grains, f.name).tobytes() == getattr(decoded.grains, f.name).tobytes(), f.name
    rejected = compact.reconstruct(actual, statuses=(2, 3))
    assert rejected.grains.ids.tobytes() == expected.rejected_ids.tobytes()
    assert rejected.rejection_reason.tobytes() == expected.rejection_reason.tobytes()
    assert actual.provenance == expected.provenance
    assert actual.report == expected.report
    validated = ["dense canonical fixture"]
    for label, variant in [("partial scope", replace(spec, bounds=(-.91, .73, -.84, .88))),
                           ("reversed evaluation and chunk size", replace(spec, chunk_size=7)),
                           ("one linked-grid bin", replace(spec, max_grid_bins=1))]:
        group_count = len(compact.build_serial_map(variant, pp).group_cell)
        c = compact.build_compact_catalog(variant, pp[::-1], bb[::-1], backend=args.backend,
                                           group_order=np.arange(group_count)[::-1])
        r = ref.build_catalog(variant, pp, bb, backend=args.backend)
        assert c.serial_map.virtual_count <= 10000
        cg = compact.reconstruct(c).grains
        for f in fields(r.grains):
            assert getattr(r.grains, f.name).tobytes() == getattr(cg, f.name).tobytes(), (label, f.name)
        cr = compact.reconstruct(c, statuses=(2, 3))
        assert cr.grains.ids.tobytes() == r.rejected_ids.tobytes(), label
        assert cr.rejection_reason.tobytes() == r.rejection_reason.tobytes(), label
        assert c.report == r.report and c.provenance == r.provenance, label
        validated.append(label)
    receipt = dict(status="bitwise parity passed", validated_cases=validated, backend=args.backend, numpy_version=np.__version__,
                   frozen_core_sha256=frozen, compact_source_sha256=hashlib.sha256(Path(compact.__file__).read_bytes()).hexdigest(),
                   virtual_count=actual.serial_map.virtual_count, eligible_count=actual.report["catalog_attempt_count"],
                   accepted_count=actual.report["packed_catalog_count"], rejected_count=len(expected.rejected_ids),
                   first_build_seconds=first_elapsed, warm_build_seconds=warm_elapsed,
                   baseline_rss_bytes=baseline, compact_build_process_peak_rss_bytes=compact_peak,
                   process_peak_after_reference_check_bytes=compact.peak_rss_bytes(),
                   measurement_note="Separate small-fixture process; first Numba build includes JIT/imports; process peak is not incremental live-array size",
                   compact_status_bytes=actual.status2.nbytes, compact_persistent_array_bytes=actual.storage["persistent_array_bytes"],
                   phases_seconds=actual.storage["seconds"], admitted_memory_plan=actual.storage["memory_plan"],
                   production_run_performed=False)
    content = json.dumps(receipt, indent=2) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(content)
    print(content, end="")


if __name__ == "__main__":
    main()
