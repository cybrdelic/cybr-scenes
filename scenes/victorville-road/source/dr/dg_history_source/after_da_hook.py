"""Explicit pinned DB + optional DG hook for the reusable checkpoint driver."""
from pathlib import Path
import hashlib,importlib.util,sys

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def apply(scene,cfg,out):
 assert cfg['revision']==1
 for path,h in cfg['source_pins'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 db=load(cfg['db_source'],'dg_pinned_db');report={'geometry_soil_normals_db':db.apply(scene,{'revision':1},out)}
 if cfg['apply_history']:
  sys.path.insert(0,str(Path(cfg['dg_source']).parent));dg=load(cfg['dg_source'],'dg_pinned_history');report['historical_grain_roles_dg']=dg.apply(scene,cfg['history'],out)
 for path,h in cfg['source_pins'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 return report
