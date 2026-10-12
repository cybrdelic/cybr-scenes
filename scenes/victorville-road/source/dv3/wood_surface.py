"""Thin binding to the sole CYBR MATERIAL bark code/profile owner."""
from pathlib import Path
import hashlib,importlib.util

def install(material,cfg):
 source=Path(cfg['bark_source']);profile=Path(cfg['bark_profile'])
 for key,path in [('bark_source',source),('bark_profile',profile)]:
  assert hashlib.sha256(path.read_bytes()).hexdigest()==cfg[key+'_sha256'],key
 spec=importlib.util.spec_from_file_location('pinned_CYBR_bark_flow',source);owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
 return owner.install(material,owner.load_profile(profile))
