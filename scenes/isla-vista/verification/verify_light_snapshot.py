"""Verify the reviewed public snapshot and installed bytes before native replay."""
from pathlib import Path
import hashlib,json
import cybrlight
import cybrlight.scene_compat.runtime as runtime
ROOT=Path(__file__).resolve().parents[1];snapshot=ROOT/'vendor/light-scene-compat';pin=json.loads((snapshot/'PINNED_SOURCE.json').read_text());source=snapshot/'python/cybrlight/scene_compat';installed=Path(runtime.__file__).parent
for name,row in pin['files'].items():
    for location in [source,installed]:
        data=(location/name).read_bytes()
        assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],name
manifest=json.loads((installed/'DEPENDENCY_MANIFEST.json').read_text())
for name,row in manifest['files'].items():
    data=(installed/name).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],name
assert not (snapshot/'python/cybrlight/__init__.py').exists()
assert cybrlight.__file__ is None, 'The anonymous snapshot test must use a namespace parent, not a private root package'
assert manifest['executed_source_hash']==json.loads((ROOT/'LIGHT_DEPENDENCY.json').read_text())['executed_source_hash']
print(json.dumps({'passed':True,'reviewed_package_files':len(pin['files']),'upstream_manifest_files':len(manifest['files']),'namespace_parent':True,'canonical_commit':pin['canonical_commit']}))
