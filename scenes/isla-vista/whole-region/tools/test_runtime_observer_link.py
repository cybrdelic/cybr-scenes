"""Reproduce and repair the fresh-wheel CIE alias defect without a render."""
from pathlib import Path
import hashlib,json,shutil,tempfile
from link_installed_runtime import link_runtime_paths,CIE_SHA256
R=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temporary:
 base=Path(temporary);root=base/'scene/whole-region';root.mkdir(parents=True)
 package=base/'installed/scene_compat';package.mkdir(parents=True)
 data=root.parent/'work/cybr-light/data';data.mkdir(parents=True)
 name='CIE_xyz_1931_2deg.csv';shutil.copyfile(R.parent/'work/cybr-light/data'/name,data/name)
 meta=root.parent/'verification';meta.mkdir();shutil.copyfile(R.parent/'verification/CIE_SOURCE_METADATA.json',meta/'CIE_SOURCE_METADATA.json')
 alias=root/'work/cybr-light/data';alias.parent.mkdir(parents=True)
 alias.symlink_to(package/'data',target_is_directory=True)
 assert alias.is_symlink() and not (alias/name).is_file(), 'Must reproduce missing table in runtime-only wheel'
 fixed=link_runtime_paths(root,package)
 assert fixed['links']['observer']=='repaired historical runtime-data alias'
 assert hashlib.sha256((alias/name).read_bytes()).hexdigest()==CIE_SHA256
 assert link_runtime_paths(root,package)['links']['observer']=='unchanged'
 # A fresh tree resolves directly to the repository-owned CIE table.
 alias.unlink();assert link_runtime_paths(root,package)['links']['observer']=='created'
 # Do not replace unexpected aliases even if their contents are readable.
 alias.unlink();other=base/'unrelated';other.mkdir();alias.symlink_to(other)
 try:link_runtime_paths(root,package)
 except RuntimeError:pass
 else:raise AssertionError('Unexpected alias was replaced')
 assert alias.resolve()==other
print(json.dumps({'passed':True,'historical_missing_table_reproduced':True,'fresh_alias':True,'known_old_alias_repaired':True,'idempotent':True,'unexpected_alias_refused':True,'table_sha256':CIE_SHA256}))
