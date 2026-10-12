#!/usr/bin/env python3
"""Stage the immutable CO capture in a portable layout; never launch Blender.

First run --check-sources for a read-only input audit. After fresh AV admission
and CA/CB payload regeneration, pass --av-cache, --z-admission, --ca-payload,
--cb-payload and a nonexistent --output-dir. Run its printed command only under
the whole-process-tree 4480 MiB guard while holding the shared heavy flock.
This stages exact CO (not CP) lighting and leaves all source packages unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MANIFEST_SHA = "5ddd71ae8fb59b98c7f1354bb4e8f99437ab2c25942f6235994470dd12d11d62"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new(path, data):
    with Path(path).open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def set_key(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def absolute_keys(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from absolute_keys(item, path + (key,))
    elif isinstance(value, list):
        for key, item in enumerate(value):
            yield from absolute_keys(item, path + (key,))
    elif isinstance(value, str) and value.startswith("/"):
        yield path


def stage_pipeline(source, runtime, spec):
    """All copied bytes stay exact; recreate the renderer's sibling lookups."""
    pipeline = runtime / "pipeline"
    helpers = runtime / "src"
    pipeline.mkdir(parents=True, exist_ok=False)
    helpers.mkdir(exist_ok=False)

    def exact_copy(name, target):
        original = source / name
        require(sha(original) == spec["co_pipeline_files"][name], "Changed CO helper: " + name)
        shutil.copyfile(original, target)
        target.chmod(0o755 if target.suffix == ".sh" else 0o644)
        require(sha(target) == spec["co_pipeline_files"][name], "Staged helper mismatch: " + name)

    for name in spec["co_pipeline_files"]:
        require(Path(name).name == name, "Non-flat source-bank entry")
        exact_copy(name, pipeline / name)
        if name.endswith(".py"):
            exact_copy(name, helpers / name)
    for directory, mapping in spec["runtime_sibling_copies"].items():
        destination = runtime / directory
        destination.mkdir(parents=True, exist_ok=False)
        for target, original in mapping.items():
            exact_copy(original, destination / target)
    write_new(pipeline / "manifest.json", spec["co_pipeline_files"])
    return pipeline


def verify_av_cache(packages, cache, z_admission):
    """Preserve the delivered BY/CA entry requirements before CO rendering."""
    sys.path.insert(0, str(packages["av"] / "road_scene_r6/src"))
    av = importlib.import_module("render_checkpoint_av")
    require(Path(av.__file__).resolve() == (packages["av"] / "road_scene_r6/src/render_checkpoint_av.py").resolve(),
            "Unexpected AV admission module")
    av.verify_lock()
    template = json.loads(av.TEMPLATES.read_text())
    inherited = json.loads((av.ROOT / "receipts/integrated_render_templates_ah.json").read_text())
    require(template["source_admission"] == inherited["source_admission"], "Changed strict Z contract")
    rows = av.selected_rows(template, "latest")
    require(len(rows) == 1, "Expected one current AV capture")
    row = rows[0]
    meta_path = cache.with_suffix(".blend.json")
    meta = json.loads(meta_path.read_text())
    require(meta["sha256"] == sha(cache) and meta["bytes"] == cache.stat().st_size,
            "Fresh AV cache bytes do not match its receipt")
    require(meta.get("saved_before_preview_reductions") is True and
            meta.get("immutable_source_verified") is True, "Require original pre-LOD AV cache")
    require(meta["pipeline"]["sha256"] == row["pipeline_sha256"] and
            meta["pipeline"]["files"] == row["captured_pipeline_files_sha256"], "Wrong AV assembly closure")
    require(meta["assembly_job"]["refresh_view_grains_au"] == row["settings"]["refresh_view_grains_au"],
            "Original finite grain allocation differs")
    admission = json.loads(z_admission.read_text())
    resources_path = z_admission.with_name("source_admission_resources.json")
    resources = json.loads(resources_path.read_text())
    require(admission.get("semantic_match") is True and admission.get("scene_written") is False,
            "Strict Z semantic admission did not pass")
    require(resources.get("resource_contract_passed") is True and resources.get("exit_code") == 0,
            "Strict Z admission resource contract failed")
    require(admission["actual_source_sha256"] == meta["source_sha256"], "Z admission belongs to another AV build")
    z_source = Path(meta["source"])
    require(z_source.is_file() and sha(z_source) == meta["source_sha256"], "Immutable rebuilt Z source is missing or changed")
    return {"cache": str(cache), "cache_sha256": meta["sha256"],
            "cache_receipt_sha256": sha(meta_path), "z_admission": str(z_admission),
            "z_admission_sha256": sha(z_admission), "z_admission_resources_sha256": sha(resources_path),
            "pipeline_sha256": row["pipeline_sha256"], "serialized_historical_AV_hash_required": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unpacked", type=Path, default=HERE.parent / "unpacked")
    for name in ("av-cache", "z-admission", "ca-payload", "cb-payload", "output-dir"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--check-sources", action="store_true")
    args = parser.parse_args()
    require(not os.environ.get("MATERIAL_PATH_MAP_FILE"), "Unset MATERIAL_PATH_MAP_FILE")
    manifest_path = HERE / "co_relocation_manifest.json"
    require(sha(manifest_path) == MANIFEST_SHA, "Recovery relocation manifest changed")
    spec = json.loads(manifest_path.read_text())
    packages = {name: args.unpacked.resolve() / directory for name, directory in spec["packages"].items()}
    co = packages["co"]
    pipeline_source = co / "captured_pipeline"
    evidence = json.loads((co / "evidence/INTERNAL_PANEL.png.json").read_text())
    expected_digest = hashlib.sha256(json.dumps(spec["co_pipeline_files"], sort_keys=True).encode()).hexdigest()
    require(expected_digest == spec["co_pipeline_sha256"] == evidence["pipeline"]["sha256"],
            "CO captured manifest digest mismatch")
    require(evidence["pipeline"]["files"] == spec["co_pipeline_files"], "CO evidence closure differs")
    require(sha(co / "evidence/job.json") == spec["co_job_sha256"], "CO historical job changed")
    original = json.loads((co / "evidence/job.json").read_text())
    require(original == evidence["job"], "CO captured job/evidence mismatch")
    require(original["capture_mode"] == "unfiltered" and original["raw_png_only"] is True and
            original["samples"] == 32 and original["rss_cap_mib"] == 4480, "Unexpected CO capture contract")
    for name, expected in spec["co_pipeline_files"].items():
        require(sha(pipeline_source / name) == expected, "Changed CO source: " + name)
    relocations = []
    for item in spec["static_input_relocations"]:
        path = packages[item["package"]] / item["path"]
        require(path.is_file() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"],
                "Missing or changed pinned input: " + str(path))
        relocations.append({**item, "resolved_path": str(path)})
    generated = []
    for item in spec["generated_payload_relocations"]:
        builder = packages[item["builder_package"]] / item["builder_path"]
        require(builder.is_file(), "Missing payload builder: " + str(builder))
        path = getattr(args, item["argument"])
        if path:
            path = path.resolve()
            require(path.is_file() and sha(path) == item["sha256"], "Generated payload mismatch: " + str(path))
        generated.append({**item, "builder": str(builder), "resolved_path": str(path) if path else None})
    intended = {("source",), ("output",)} | {tuple(r["job_key"]) for r in relocations + generated}
    require(set(absolute_keys(original)) == intended, "An absolute CO job input has no explicit relocation")
    audit = {"co_source_closure_passed": True, "pipeline_sha256": expected_digest,
             "static_inputs_verified": len(relocations), "generated_inputs": generated,
             "missing_static_dependencies": [], "launches_Blender": False,
             "requires_fresh_admitted_AV_cache": True, "uses_original_CO_card_not_CP": True,
             "whole_tree_4480_MiB_guard_and_shared_flock_required": True}
    if args.check_sources:
        print(json.dumps(audit), flush=True)
        return
    for name in ("av_cache", "z_admission", "ca_payload", "cb_payload", "output_dir"):
        require(getattr(args, name) is not None, "Missing --" + name.replace("_", "-"))
    cache, admission_path = args.av_cache.resolve(), args.z_admission.resolve()
    source_proof = verify_av_cache(packages, cache, admission_path)
    out = args.output_dir.resolve()
    require(not out.exists(), "A fresh output directory is required")
    job = copy.deepcopy(original)
    for item in relocations + generated:
        set_key(job, item["job_key"], item["resolved_path"])
    job.update(source=str(cache), source_sha256=source_proof["cache_sha256"], output=str(out / "INTERNAL_PANEL.png"))
    out.mkdir(parents=True, exist_ok=False)
    pipeline = stage_pipeline(pipeline_source, out / "runtime", spec)
    write_new(out / "job.json", job)
    command = ["bash", str(pipeline / "clean_render_landform_candidate.sh"), str(out / "job.json")]
    record = {**audit, "input_relocations": relocations + generated,
              "source_admission": source_proof, "job": str(out / "job.json"),
              "non_relocation_setting_changes": {}, "historical_AV_hash_not_reused": True,
              "command": command, "command_shell": shlex.join(command),
              "expected_output": str(out / "UNFILTERED_PANEL.png"),
              "expected_pipeline_sha256": expected_digest, "stage_only": True,
              "orchestrator_sha256": sha(__file__), "relocation_manifest_sha256": MANIFEST_SHA}
    write_new(out / "CO_REPLAY_STAGING.json", record)
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
