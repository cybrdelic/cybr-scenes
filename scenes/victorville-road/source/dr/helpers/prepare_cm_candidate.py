#!/usr/bin/env python3
"""Stage a CM woody-form candidate from a fresh CO replay directory.

Source-only: never opens Blender, a .blend, or an image. Does not change the CO
directory or immutable packages. Rebuilds a fresh runtime from the exact CO bank,
adds the recovered CM2 adapter and saved workshop, and moves the exact CL/CM
application blocks immediately after CI and before both camera/terrain culls.
The only job changes are a new output path and coherent_crown_cm configuration
using the unchanged CL layout. All baseline CO source/material/light/view data
and settings remain equal. Physical/visual acceptance requires a later guarded
Blender run; compilation and source closure do not establish geometry success.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import pathlib
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_co_replay as co

RECOVERY = Path(__file__).resolve().parents[1]
ADAPTER_SHA = "2ef531d47161a80715b69b2f2b63806061e74e808b726c9e453371d3d4239c27"
WORKSHOP_PINS = {
    "coherent_shrub_cm.py": "b309bedda2117358913f0a0c35d6b6cfbbb4d15489648a8610ec390b7998ad91",
    "architectural_scrub_cj_v2.py": "d4ec3b85500e21dcb2fcbc622b44bc7af453e47f38f977a42b3d17dde4715afb",
    "desert_scrub.py": "8f5840a371422effcf243dfb284f57241b219262386a1d7dc3b594264b1b2172",
}
SAMPLER_SHA = "02c719fae92f3b2c485445d5bc5e8609884829140be6651812c8bae8b2df271b"


def load_inputs():
    manifest_path = co.HERE / "co_relocation_manifest.json"
    co.require(co.sha(manifest_path) == co.MANIFEST_SHA, "CO relocation manifest changed")
    spec = json.loads(manifest_path.read_text())
    packages = {key: RECOVERY / "unpacked" / value for key, value in spec["packages"].items()}
    workshop = RECOVERY / "unpacked/CYBR_Victorville_CM_Connected_Shrub_Workshop_Source_v1"
    adapter = RECOVERY / "cm_recovery_source/coherent_crown_scene_cm.py"
    co.require(co.sha(adapter) == ADAPTER_SHA, "Recovered CM2 adapter changed; review a new source revision explicitly")
    archive_manifest = json.loads((workshop / "MANIFEST.json").read_text())["files"]
    for name, pin in WORKSHOP_PINS.items():
        co.require(archive_manifest[name] == pin and co.sha(workshop / name) == pin, "CM workshop source differs: " + name)
    co.require(WORKSHOP_PINS["architectural_scrub_cj_v2.py"] == spec["co_pipeline_files"]["architectural_scrub_cj.py"],
               "CM and CL use different original architectural helpers")
    co.require(WORKSHOP_PINS["desert_scrub.py"] == spec["co_pipeline_files"]["desert_scrub.py"],
               "CM and CL use different original botanical helpers")
    av_template = json.loads((packages["av"] / "road_scene_r6/receipts/integrated_render_templates_av.json").read_text())
    row = next(row for row in av_template["captures"] if row.get("default_latest"))
    sampler = packages["av"] / "road_scene_r6/checkpoint_pipeline_sources" / row["pipeline_sha256"] / "sample_final_surface_an.py"
    co.require(row["captured_pipeline_files_sha256"][sampler.name] == SAMPLER_SHA and co.sha(sampler) == SAMPLER_SHA,
               "Current-surface sampler differs from captured AV")
    sources = {"coherent_crown_scene_cm.py": adapter,
               "coherent_shrub_cm.py": workshop / "coherent_shrub_cm.py",
               "architectural_scrub_cj_v2.py": workshop / "architectural_scrub_cj_v2.py",
               "sample_final_surface_an.py": sampler}
    for source in sources.values():
        compile(source.read_text(), str(source), "exec")
    return spec, packages, workshop, sources


def move_apply_blocks(text):
    """Move exact statements; no source/body rewrite or guard removal."""
    tree = ast.parse(text)
    loop = next(node for node in tree.body if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "job")
    lines = text.splitlines(keepends=True)
    blocks = []
    for key in ("frozen_architecture_layout_cl", "coherent_crown_cm"):
        nodes = [node for node in loop.body if isinstance(node, ast.If) and
                 ast.unparse(node.test) == f"job.get('{key}')"]
        co.require(len(nodes) == 1, "Expected one runtime application block: " + key)
        node = nodes[0]
        blocks.append("".join(lines[node.lineno - 1:node.end_lineno]))
    result = text
    for block in blocks:
        co.require(result.count(block) == 1, "Ambiguous runtime block")
        result = result.replace(block, "", 1)
    anchor = " cull_adaptation=camera_cull_dense_offscreen(job,s)\n"
    co.require(result.count(anchor) == 1, "Expected one camera-cull anchor")
    result = result.replace(anchor, "".join(blocks) + anchor, 1)
    compile(result, "<CM reordered renderer>", "exec")
    # Ignore line positions: removing the two selected blocks from both ASTs
    # must leave identical code everywhere else.
    new_tree = ast.parse(result)
    new_loop = next(node for node in new_tree.body if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "job")
    def selected(node):
        return isinstance(node, ast.If) and ast.unparse(node.test) in (
            "job.get('frozen_architecture_layout_cl')", "job.get('coherent_crown_cm')")
    old_blocks = [node for node in loop.body if selected(node)]
    new_blocks = [node for node in new_loop.body if selected(node)]
    co.require([ast.dump(node, include_attributes=False) for node in old_blocks] ==
               [ast.dump(node, include_attributes=False) for node in new_blocks], "CL/CM block content changed")
    loop.body = [node for node in loop.body if not selected(node)]
    new_loop.body = [node for node in new_loop.body if not selected(node)]
    co.require(ast.dump(tree, include_attributes=False) == ast.dump(new_tree, include_attributes=False),
               "Renderer changed beyond block placement")
    calls = {}
    for node in ast.walk(ast.parse(result)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.setdefault(node.func.id, []).append(node.lineno)
    names = ("apply_fixed_gravel_support_ci", "apply_frozen_architecture_layout_cl", "apply_coherent_crown_cm",
             "camera_cull_dense_offscreen", "apply_preview_mesh_cull", "apply_victorville_reflectance_cn", "apply_daylight_model_co")
    for name in names:
        co.require(len(calls.get(name, [])) == 1, "Missing or duplicate runtime call: " + name)
    order = {name: calls[name][0] for name in names}
    co.require(list(order.values()) == sorted(order.values()), "CM runtime application/cull/material order is invalid")
    return result, order


def derive_snapshot(pipeline, job):
    """Run only pinned source collection plus file-copy snapshot code; no bpy."""
    renderer = pipeline / "render_landform_candidate.py"
    tree = ast.parse(renderer.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ("hash_file", "pipeline_snapshot")]
    loop = next(node for node in tree.body if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "job")
    branch = next(node for node in loop.body if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and
                  node.test.id == "mapping_config" and node.orelse and isinstance(node.orelse[0], ast.Assign))
    namespace = {"pathlib": pathlib, "hashlib": hashlib, "shutil": shutil, "json": json,
                 "job": job, "__file__": str(renderer)}
    exec(compile(ast.Module(body=functions + branch.orelse, type_ignores=[]), "<CM source snapshot only>", "exec"), namespace)
    return namespace["pipeline"]


def stage_candidate(bank, out, original_job, spec, workshop, sources):
    pipeline = co.stage_pipeline(bank, out / "runtime", spec)
    runtime = pipeline.parent
    base_text = (pipeline / "render_landform_candidate.py").read_text()
    candidate_text, order = move_apply_blocks(base_text)
    for name in ("render.py", "render_landform_candidate.py"):
        co.require((pipeline / name).read_text() == base_text, "CO renderer aliases differ")
        (pipeline / name).write_text(candidate_text)
        (runtime / "src" / name).write_text(candidate_text)
    for name in ("coherent_crown_scene_cm.py", "sample_final_surface_an.py"):
        shutil.copyfile(sources[name], runtime / "src" / name)
    (runtime / "vegetation_workshop_cm").mkdir()
    shutil.copyfile(sources["coherent_shrub_cm.py"], runtime / "vegetation_workshop_cm/coherent_shrub_cm.py")
    co.require(co.sha(runtime / "vegetation_workshop_cj/architectural_scrub_cj_v2.py") == WORKSHOP_PINS["architectural_scrub_cj_v2.py"],
               "Staged CL workshop is not exact CM dependency")
    job = copy.deepcopy(original_job)
    co.require("coherent_crown_cm" not in job and "architectural_communities_ck" not in job, "Expected unchanged frozen-CL CO job")
    job["coherent_crown_cm"] = copy.deepcopy(job["frozen_architecture_layout_cl"])
    job["output"] = str(out / "INTERNAL_PANEL.png")
    normalized = copy.deepcopy(job)
    del normalized["coherent_crown_cm"]
    normalized["output"] = original_job["output"]
    co.require(normalized == original_job, "CM job modified an unintended CO setting")
    snapshot = derive_snapshot(pipeline, job)
    expected = dict(spec["co_pipeline_files"])
    expected.update({name: co.sha(source) for name, source in sources.items()})
    expected.update({name: hashlib.sha256(candidate_text.encode()).hexdigest() for name in ("render.py", "render_landform_candidate.py")})
    co.require(snapshot["files"] == expected, "Candidate source closure has an unplanned change or missing source")
    (pipeline / "manifest.json").write_text(json.dumps(expected, indent=2) + "\n")
    for path in runtime.rglob("*.py"):
        compile(path.read_text(), str(path), "exec")
    report = {"source_only": True, "Blender_started": False, "geometry_or_render_verified": False,
              "base_CO_pipeline_sha256": spec["co_pipeline_sha256"], "candidate_pipeline_sha256": snapshot["sha256"],
              "candidate_pipeline_files": expected, "source_files": len(expected),
              "renderer_changes": "Only the exact CL and CM runtime blocks moved to after CI and before camera/terrain culling",
              "AST_unchanged_elsewhere": True, "runtime_call_lines": order, "duplicate_apply_calls": False,
              "job_changes": {"output": job["output"], "coherent_crown_cm": job["coherent_crown_cm"]},
              "all_other_CO_job_settings_equal": True,
              "CM_source_provenance": {name: {"path": str(source), "sha256": co.sha(source)} for name, source in sources.items()},
              "preservation_guards": "Adapter asserts exact frozen float32 matrices, keeps low crowns, source palette and leaf budgets; every changed plant needs a basal-support witness on complete CE/CI terrain",
              "limits": "Source-order/closure/compile checks only. No geometry, support clearance, memory or visual success is claimed."}
    return job, report, pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--co-staged-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check-sources", action="store_true")
    args = parser.parse_args()
    spec, packages, workshop, sources = load_inputs()
    if args.check_sources:
        # Tiny temporary file-only fixture; no scene is loaded or fabricated.
        original_job = json.loads((packages["co"] / "evidence/job.json").read_text())
        with tempfile.TemporaryDirectory(prefix="cm_source_fixture_", dir="/tmp") as directory:
            _, report, _ = stage_candidate(packages["co"] / "captured_pipeline", Path(directory), original_job, spec, workshop, sources)
        report["temporary_source_fixture_removed"] = True
        print(json.dumps(report), flush=True)
        return
    co.require(args.co_staged_dir is not None and args.output_dir is not None,
               "Provide --co-staged-dir and --output-dir")
    baseline, out = args.co_staged_dir.resolve(), args.output_dir.resolve()
    co.require(not out.exists() and out != baseline and not out.is_relative_to(baseline), "Use a distinct fresh candidate output directory")
    stage_receipt = json.loads((baseline / "CO_REPLAY_STAGING.json").read_text())
    co.require(stage_receipt["expected_pipeline_sha256"] == spec["co_pipeline_sha256"] and
               stage_receipt["non_relocation_setting_changes"] == {}, "Input is not the exact prepared CO baseline")
    original_job = json.loads((baseline / "job.json").read_text())
    cache = Path(original_job["source"])
    source_proof = co.verify_av_cache(packages, cache, Path(stage_receipt["source_admission"]["z_admission"]))
    co.require(original_job["source_sha256"] == source_proof["cache_sha256"], "Fresh AV source hash changed")
    expected_job = json.loads((packages["co"] / "evidence/job.json").read_text())
    for item in stage_receipt["input_relocations"]:
        co.require(co.sha(item["resolved_path"]) == item["sha256"], "CO input changed before CM staging")
        co.set_key(expected_job, item["job_key"], item["resolved_path"])
    expected_job.update(source=str(cache), source_sha256=source_proof["cache_sha256"],
                        output=str(baseline / "INTERNAL_PANEL.png"))
    co.require(original_job == expected_job, "Prepared CO job differs beyond its recorded source/output/input relocations")
    out.mkdir(parents=True, exist_ok=False)
    job, report, pipeline = stage_candidate(baseline / "runtime/pipeline", out, original_job, spec, workshop, sources)
    command = ["bash", str(pipeline / "clean_render_landform_candidate.sh"), str(out / "job.json")]
    report.update(base_CO_directory=str(baseline), base_CO_job_sha256=co.sha(baseline / "job.json"),
                  source_admission=source_proof, command=command, command_shell=shlex.join(command),
                  whole_tree_4480_MiB_guard_and_shared_flock_required=True,
                  orchestrator_sha256=co.sha(__file__))
    co.write_new(out / "job.json", job)
    co.write_new(out / "CM_CANDIDATE_STAGING.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
