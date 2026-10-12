#!/usr/bin/env python3
"""Strict AV replay with raw Cycles output and the original assembled cache.

This is a new recovery orchestrator, not a replacement for any pinned source.
Run it under the recovery whole-process-tree 4480 MiB guard while the caller
holds the caller-selected shared heavy lock. The external guard must
terminate descendant sessions too: the inherited admission/capture guards each
start their own process group. No lock is acquired here to avoid nested flock.

Only one non-relocation job setting changes: capture_mode guided -> unfiltered.
The original 24 samples, 1000 x 667 view, guides, grain allocation, geometry,
materials, source bank, strict Z admission, and optional pre-LOD cache all stay.
The captured bank has no supported cache-only stop, so this executes its bounded
raw render and precision/guide checks. No OIDN executable is required or invoked.

--check-sources verifies the immutable closure and prints the exact change;
it performs no staging, admission, rendering, cache creation, or file writes.
"""
from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
RECOVERY = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = RECOVERY / "unpacked/CYBR_Victorville_R6_AV_Current_Reproducible_Source_v15"


def write_new(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--source", type=Path, help="Fresh rebuilt strict Z scene")
    parser.add_argument("--tag", default="av_recovery_raw")
    parser.add_argument("--check-sources", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    sys.path.insert(0, str(package / "road_scene_r6/src"))
    av = importlib.import_module("render_checkpoint_av")
    av.require(Path(av.__file__).resolve() == package / "road_scene_r6/src/render_checkpoint_av.py",
               "Unexpected AV orchestrator import")
    av.require(av.ROOT.resolve() == package / "road_scene_r6", "Unexpected AV package root")
    av.require(not os.environ.get("MATERIAL_PATH_MAP_FILE"), "Unset MATERIAL_PATH_MAP_FILE")
    av.verify_lock()
    template = json.loads(av.TEMPLATES.read_text())
    inherited = json.loads((av.ROOT / "receipts/integrated_render_templates_ah.json").read_text())
    av.require(template["source_admission"] == inherited["source_admission"],
               "AV admission must remain the exact inherited strict Z contract")
    rows = av.selected_rows(template, "latest")
    av.require(len(rows) == 1 and rows[0].get("generation") == "AV",
               "Exactly one current AV capture is required")
    row = rows[0]
    manifest, pipeline_sha = av.expected_manifest(row, cache_output=True)
    av.require(row["settings"]["capture_mode"] == "guided", "Unexpected original capture mode")
    av.require(row["settings"]["samples"] == 24 and row["settings"]["save_guides"] is True,
               "Unexpected original AV sample/guide settings")
    av.require(row["settings"]["rss_cap_mib"] == 4480, "Keep original 4480 MiB capture cap")
    av.require(args.tag.replace("_", "").replace("-", "").isalnum(),
               "Use an alphanumeric run tag")
    change = {"capture_mode": {"before": "guided", "after": "unfiltered"}}
    preflight = {
        "source_lock_passed": True,
        "exact_inherited_Z_admission": True,
        "historical_capture": row["name"],
        "pipeline_sha256": pipeline_sha,
        "job_setting_changes_excluding_input_output_relocations": change,
        "samples": 24,
        "save_guides": True,
        "oidn_required": False,
        "cache_only_supported_by_captured_bank": False,
        "end_to_end_rebuild_verified": False,
        "whole_tree_guard_and_shared_flock_required": True,
    }
    if args.check_sources:
        print(json.dumps(preflight), flush=True)
        return

    source = (args.source or av.ROOT / "preview/road_r6_z_runoff_film.blend").resolve()
    av.require(source.is_file(), "Build the inherited strict Z prerequisite first")
    for relocation in row.get("input_relocations", []):
        path = av.local_path(relocation["package_path"])
        av.require(path.is_file() and av.digest(path) == relocation["sha256"],
                   "Exact generated input required: " + relocation["package_path"])

    run = av.ROOT / "captures" / args.tag
    run.mkdir(parents=True, exist_ok=False)
    write_new(run / "raw_replay_policy.json", {
        **preflight,
        "orchestrator": str(Path(__file__).resolve()),
        "orchestrator_sha256": av.digest(__file__),
        "source": str(source),
        "source_admission_contract": template["source_admission"],
    })
    env = dict(os.environ, OPENBLAS_NUM_THREADS="2", OMP_NUM_THREADS="2",
               MKL_NUM_THREADS="2", NUMEXPR_NUM_THREADS="2", PYTHONDONTWRITEBYTECODE="1")
    env.pop("OIDN_BIN", None)
    scene_sha, admission = av.admit_scene(source, run, env)
    capture = run / row["role"]
    capture.mkdir(exist_ok=False)
    pipeline = av.stage_pipeline(row, capture / "runtime")
    original = av.build_job(row, source, scene_sha, capture, cache_output=True)
    job = copy.deepcopy(original)
    job["capture_mode"] = "unfiltered"
    check = copy.deepcopy(job)
    check["capture_mode"] = "guided"
    av.require(check == original, "Recovery changed settings beyond raw capture mode")
    job_path = capture / "job.json"
    write_new(job_path, job)
    write_new(capture / "job_changes.json", {
        "changed_settings": change,
        "input_relocations": row["input_relocations"],
        "source": str(source),
        "source_sha256": scene_sha,
        "output": job["output"],
        "cache_output": job["assembled_scene_cache_av"],
        "historical_pipeline_sha256": pipeline_sha,
    })
    receipt = capture / "resource_receipt.json"
    subprocess.run([
        sys.executable, str(pipeline / "bounded_clean_run.py"), str(job_path),
        str(capture / "run.log"), str(receipt), str(job["rss_cap_mib"]),
    ], env=env, check=True)
    resources = json.loads(receipt.read_text())
    av.require(resources.get("resource_contract_passed") is True and resources.get("exit_code") == 0,
               "Raw capture failed its resource contract; preserve all evidence")
    raw = capture / "UNFILTERED_PANEL.png"
    report = json.loads(raw.with_suffix(".png.json").read_text())
    av.require(report["pipeline"]["files"] == manifest and report["pipeline"]["sha256"] == pipeline_sha,
               "Raw replay did not use the exact captured AV source manifest")
    av.require(report["source_sha256"] == scene_sha == av.digest(source),
               "Strict Z source changed during replay")
    av.require(report.get("capture_mode") == "unfiltered" and report.get("oidn_executed") is False,
               "Raw proof must not invoke OIDN")
    av.require(report.get("postprocess") == "none" and report["job"] == job,
               "Unexpected raw postprocessing or executed job")
    cache = Path(job["assembled_scene_cache_av"]["path"])
    meta = json.loads(cache.with_suffix(".blend.json").read_text())
    av.require(meta["sha256"] == av.digest(cache) and meta["bytes"] == cache.stat().st_size,
               "AV cache bytes differ from the original cache receipt")
    av.require(meta.get("saved_before_preview_reductions") is True and
               meta.get("immutable_source_verified") is True,
               "Require original pre-preview immutable-source cache contract")
    av.require(meta["pipeline"]["files"] == manifest and meta["pipeline"]["sha256"] == pipeline_sha,
               "Cache source closure differs from exact AV")
    av.require(meta["source_sha256"] == scene_sha == admission["actual_source_sha256"],
               "Strict Z admission does not belong to this AV cache")
    av.require(meta["assembly_job"] == job and
               meta["assembly_job"]["refresh_view_grains_au"] == row["settings"]["refresh_view_grains_au"],
               "Cache assembly job or original finite grain allocation differs")
    ready = {
        "role": row["role"], "path": str(raw), "bytes": raw.stat().st_size,
        "sha256": av.digest(raw), "source_sha256": scene_sha,
        "semantic_source_admission": admission,
        "source_admission_path": str(run / "source_admission.json"),
        "source_admission_resources_path": str(run / "source_admission_resources.json"),
        "historical_capture": row["name"], "historical_pipeline_sha256": pipeline_sha,
        "actual_pipeline_sha256": pipeline_sha,
        "job_setting_changes": change,
        "cache": str(cache), "cache_sha256": meta["sha256"],
        "cache_receipt": str(cache.with_suffix(".blend.json")),
        "oidn_executed": False, "quality_acceptance": False,
        "status": "Fresh strict-admitted AV cache and raw capture; separate visual review required",
        "scope": "This replay receipt does not replace evidence for every preceding clean rebuild stage.",
    }
    write_new(capture / "ready.json", ready)
    print(json.dumps(ready), flush=True)


if __name__ == "__main__":
    main()
