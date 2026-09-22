# Execution recovery — six-scene R2 source

This delivery repairs the **local execution workflow**, not the chat hosting
service. The six scene sources are the recovered R2 release. The previously
claimed `/mnt/data/r3_work/CYBR_SCENES_R3` directory and its linked hot-springs
render were absent at inspection; no recovered R3 implementation is implied.

## Start and inspect real work

Linux/WSL, Python and the existing `requirements.txt` dependencies are required.
The native renderer targets remain the same as the R2 README.

```bash
python execctl.py doctor
python execctl.py start --id obsidian-check --threads 4 --timeout 14400 -- \
  python cybr_scenes.py render obsidian-reach --quality preview \
    --threads 4 --output renders/obsidian-check
python execctl.py status obsidian-check
python execctl.py wait obsidian-check --seconds 5
python execctl.py cancel obsidian-check
```

Each control call returns after a short interval. `status` reads durable JSON
and a bounded suffix of the native log. A running job's supervisor remains in
the current container when the short launch call exits. It does **not** survive
destruction of the container, and there is no external scheduling service.
Use unique job IDs; existing job directories are not silently overwritten.

For all six, replace `obsidian-reach` with `all`. Their render loop is sequential;
a failed scene is recorded and does not prevent later scenes from being tried.
Only one compile/prepare/render CLI workload owns the project's heavyweight
execution lock at a time. A conflicting invocation fails explicitly rather than
overlapping two multi-gigabyte scene builds.

## What is recorded

`execution-jobs/<id>/` stores argv, cwd, supervisor and child process identities,
start/finish times, a heartbeat, return status, peak sampled process-tree resident
memory, and `output.log`. Repeated step attempts preserve their old logs in `.execution-history/` and
start a clean new log, so archived JSON or old counters cannot contaminate the
current run. Native compile/render/export steps also write
`*.execution.json`, `*.command.json` and their own logs. A process identity includes
PID, process start ticks, boot ID and PID namespace, not PID alone.

States distinguish `starting`, `running`, `succeeded`, `failed`, `timed_out`,
`cancelled`, `resource_limit` and `interrupted`. No output file or old PID alone is
accepted as proof that an execution succeeded. The existing scene verifier still
checks dimensions, raw radiance, native metadata and output fingerprints.

Timeout and cancellation terminate owned descendants, including subprocesses
that created new sessions. The optional `--memory-mb` watchdog stops a job above
its sampled process-tree RSS budget; it is not a hard allocation reservation and
cannot guarantee prevention of every short-lived memory spike. The default
budget uses the actual container limit, not the host's apparent free RAM.
OpenMP/Numba use the same CPU budget; BLAS pools use one thread.

Kernel-managed file locks release on process death. Their on-disk lock inode is
retained deliberately to avoid an unlink/recreate locking race. Never delete
locks to force overlap with a known live job.

## Recovery and checkpoints

```bash
python execctl.py snapshot --output ../CYBR_Scenes_Source_Checkpoint.zip
```

This writes a temporary archive, verifies every ZIP entry and SHA-256 manifest,
and atomically publishes the completed archive. A failed checkpoint does not
replace the previous one. It includes source/input assets, not regenerated
multi-gigabyte geometry, binaries, live process state, or font files. Preserve the
checkpoint as a downloaded or attached artifact before abandoning a workspace.

After interruption, start a **new job ID** and use a new output directory. Valid
upstream mesh/build caches can be reused within the surviving project, but the
renderer has no implemented in-flight sample checkpoint: lost partial path
samples are restarted, not claimed to have resumed. The missing R3 source cannot
be reconstructed merely from a progress message or a nonexistent sandbox link.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

Tests cover subprocess success/failure, bounded log reads, timeout, cancellation,
memory watchdog, identity mismatch, missing supervisor reconciliation, orphan
cleanup, locking, cross-launch survival, batch failure isolation and atomic ZIP
publication. The separate proof render uses the native full Obsidian Reach mesh
at a small verification resolution; it is not a new artistic scene upgrade.
