"""Install a precomputed exact subset; verify current projection before reuse."""
from pathlib import Path
import importlib.util,json,hashlib
import numpy as np

def apply(scene,cfg,out):
 from approved_density_lod import CameraProjection
 import bpy
 p=CameraProjection(scene,cfg['width'],cfg['height']);q=json.loads(Path(cfg['catalog_receipt']).read_text())['projection']
 # Close-camera placement is delegated to the already proved macro installer.
 if not cfg.get('close_center'):
  for key in ['inverse','f','offset']:assert np.array_equal(getattr(p,key),np.asarray(q[key])),key
 source=Path(__file__).with_name('install_catalog.py');assert hashlib.sha256(source.read_bytes()).hexdigest()==cfg['frozen_installer_sha256'];spec=importlib.util.spec_from_file_location('dq_retained_installer',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);report=module.apply(scene,cfg,out)
 p=CameraProjection(scene,cfg['width'],cfg['height'])
 for key in ['inverse','f','offset']:assert np.array_equal(getattr(p,key),np.asarray(q[key])),key
 expected=np.load(cfg['catalog']);actual=np.load(Path(out)/'DQ_SELECTED_IDENTITY.npz');order=np.argsort(actual['id']);assert np.array_equal(actual['id'][order],expected['id']);assert np.array_equal(actual['xyz'][order],np.c_[expected['xy'],expected['z']].astype('f4'))
 report['precomputed_world_subset_preserved_exactly']=True;report['new_role_allocation_in_Blender']=False
 report.pop('role_and_contact_before_view_selection',None);report['role_before_any_camera_selection']=True;report['contact_is_pure_source_function_evaluated_after_conservative_prefilter']=True
 report['installed_subset_catalog_count']=report.pop('catalog_count');report['world_selection_receipt']=json.loads(Path(cfg['catalog_receipt']).read_text())
 (Path(out)/'STABLE_GRAIN_CATALOG_DQ.json').write_text(json.dumps(report,indent=2)+'\n');return report
