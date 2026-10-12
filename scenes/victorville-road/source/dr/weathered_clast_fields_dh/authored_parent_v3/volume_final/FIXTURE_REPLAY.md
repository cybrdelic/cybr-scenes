# Exact material-fixture source

Set DH_RUNTIME_SRC=/path/to/prepared/dg/runtime/src and DH_FIXTURE_OUT=/fresh/output, then run Blender4.3.2 --background --threads 2 --python replay_fixture.py. The source checks the three runtime helper hashes. Only input/output path configuration and these pins differ from the actually exercised fixture script; this relocated entrypoint is compile/path-checked, not a second rendered replay. Run it under the existing exclusive two-thread resource guard. The two-body numerical generator has separately passed the exact array replay.
