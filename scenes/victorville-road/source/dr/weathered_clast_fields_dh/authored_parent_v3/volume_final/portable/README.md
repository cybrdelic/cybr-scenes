# Two-specimen standalone replay

Inputs are exactly pinned in SOURCE_PINS.json and include original parent_v, parent_f, parent_color and parent_rough for CG146 and AS039. The geometry generator only uses the geometry/envelope plus its explicit authored field parameters. Live scene materials are handled by the final adapter outside this replay.

Run regenerate_bounded.sh with an empty output directory. DH_HEAVY_LOCK can override the current cloud's shared lock; DH_OUTPUT_DIR selects the output. The guard is an unchanged copy of the existing trusted helper. No package installation is performed.

NumPy and SciPy versions are recorded in RUNTIME_VERSIONS.json. A completed same-runtime replay used only these local inputs and regenerated every stored output array byte-for-byte. REGENERATION_VERIFIED.json is the actual test receipt; regeneration_guard.json records 10.37 seconds and 340.02 MiB peak with two threads. This check loaded no road scene and used none of the preceding audit-folder code or data.

The replay emits pinned-type NPZs and numerical receipts. Repeated ZIP container bytes are not the comparison criterion; decoded array bytes are. Use the final enclosing CANDIDATE_MANIFEST.json for the already-pinned scene inputs. A newly regenerated archive must be freshly hashed before creating a new manifest.
