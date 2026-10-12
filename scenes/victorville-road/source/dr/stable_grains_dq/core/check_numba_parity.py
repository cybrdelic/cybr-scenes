"""Optional 105-candidate parity check using an already available Numba package."""
from dataclasses import fields
import time
from stable_catalog import CatalogSpec, Prototype, build_catalog


def main():
    start = time.monotonic()
    prototypes = [Prototype(13, 0, 0, 43.25, .041), Prototype(297, 1, 1, 61.75, .026)]
    spec = CatalogSpec(seed=2610100225, cell_size=.5, bounds=(-.5, .5, -.5, .5),
                       thinning_by_band={0: .9, 1: .72}, catalog_epoch="numba-parity-tiny",
                       source_pins={"geometry": "unchanged-fixture"})
    a = build_catalog(spec, prototypes, [[0, 0, .2]], backend="numpy")
    b = build_catalog(spec, prototypes, [[0, 0, .2]], backend="numba")
    for f in fields(a.grains):
        assert getattr(a.grains, f.name).tobytes() == getattr(b.grains, f.name).tobytes(), f.name
    assert a.rejected_ids.tobytes() == b.rejected_ids.tobytes()
    assert a.rejection_reason.tobytes() == b.rejection_reason.tobytes()
    print("NUMBA_PARITY_PASSED", a.report["full_cell_virtual_count"], "virtual;",
          len(a.grains), "accepted;", len(a.rejected_ids), "rejected; seconds",
          round(time.monotonic() - start, 3))


if __name__ == "__main__":
    main()
