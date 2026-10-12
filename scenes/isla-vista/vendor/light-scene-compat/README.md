# Reviewed LIGHT dependency snapshot

This is the exact reviewed `cybrlight.scene_compat` source subset from canonical
CYBR LIGHT commit ef2b14ec4e815db00509098cbdc48b2363d312b7 (merged PR9).
The canonical LIGHT repository is private as checked 2026-10-12. This public
snapshot enables anonymous SCENES replay without granting access to that
repository, publishing its unrelated history, or using credentials.

Runtime code, native source, notices and DEPENDENCY_MANIFEST.json are unchanged.
The snapshot is installed as a PEP 420 namespace package. There is deliberately
no cybrlight/__init__.py and no import of the canonical root workflow/API.
Ownership and further renderer development remain in CYBR LIGHT. This is an
explicit reproducibility boundary, not a fork advertised as the current engine.

Install from the Isla Vista scene directory:

    python -m pip install './vendor/light-scene-compat[portable]'

A C++17/OpenMP compiler and libdl are required for native rendering. No compiler
or executable is downloaded. The package contains GPL 2-only source with the
retained original MIT notice; see the included native/LICENSE and LICENSES.
PINNED_SOURCE.json records every copied source byte. Historical access labels
inside the unchanged upstream manifest do not establish public repository access.
