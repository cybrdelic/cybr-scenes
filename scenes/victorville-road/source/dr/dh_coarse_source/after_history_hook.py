"""Pinned late coarse morphology and actual-terrain contact after exact DG."""
from pathlib import Path
import hashlib,importlib.util,sys

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def apply(scene,cfg,out):
 assert cfg['revision']==1
 def verify():
  for path,h in cfg['source_pins'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 verify();prior=load(cfg['dg_hook'],'dh_pinned_dg_hook');r={'DG':prior.apply(scene,cfg['dg_config'],out)}
 if cfg['apply_coarse']:
  m=load(cfg['coarse_source'],'dh_pinned_coarse');r['coarse_geometry']=m.apply(scene,cfg['coarse_config'],out)
  cc=dict(cfg['contact_config']);cc['CG_prototypes']=[e['prototype_index'] for e in r['coarse_geometry']['entries'] if e['source_kind']=='CG'];cc['AS_mesh_names']=[e['new_mesh'] for e in r['coarse_geometry']['entries'] if e['source_kind']=='AS']
  c=load(cfg['contact_source'],'dh_pinned_contact');r['coarse_contact']=c.apply(scene,cc,out)
  assert r['coarse_contact']['unsupported_bodies']==0,'Changed clast has no exact soil contact witness'
 verify();return r
