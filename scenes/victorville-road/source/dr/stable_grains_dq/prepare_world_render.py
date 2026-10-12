from pathlib import Path
import json,hashlib,copy,argparse,shutil
import numpy as np
O=Path(__file__).resolve().parent;R=O.parent
p=argparse.ArgumentParser();p.add_argument('--view',choices=['normal_2000','macro_1800'],required=True);a=p.parse_args();macro=a.view.startswith('macro');j=json.loads((R/'scene_structure_dl/job_close.json'if macro else R/'dm_static_domain_a/job.json').read_text());prior=copy.deepcopy(json.loads((R/'scene_structure_dl/job_close.json').read_text())['geometry_soil_normals_db']['dh_config']);prior['dg_config']['apply_history']=False;q=json.loads((R/'low_ground_dp_native/job.json').read_text());v=O/('VIEW_'+a.view+'.npz');receipt=json.loads(v.with_suffix('.json').read_text());proj=receipt['projection'];j['width']=proj['width'];j['height']=proj['height'];j['samples']=32
budget=np.load(O/'WORLD_ROLE_BUDGET.npz');roles=np.load(O/'roles/WORLD_ROLES.npz');combined=budget['macro_spent_volume']+roles['selected_volume'];assert np.all(combined<=budget['original_budget']);bp=O/'WORLD_DISPLAY_BUDGET.npz'
if bp.exists():
 old=np.load(bp);assert np.array_equal(old['selected_volume'],combined)
else:np.savez_compressed(bp,x=budget['x'],y=budget['y'],budget=budget['original_budget'],selected_volume=combined)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();cfg={**q['visible_fine_grains_cz'],'width':j['width'],'height':j['height'],'catalog':str(v),'catalog_sha256':sha(v),'catalog_receipt':str(v.with_suffix('.json')),'budget':str(bp),'frozen_installer_sha256':sha(O/'install_catalog.py')}
if macro:cfg['close_center']=[-4.9,5.5]
else:cfg.pop('close_center',None)
j['visible_fine_grains_cz']['width']=j['width'];j['visible_fine_grains_cz']['height']=j['height'];j['output']=str(R/'current_cache_source/runs'/('dq_world_'+a.view)/'INTERNAL_PANEL.png');j['view_scope']='DQ compact fixed foreground-world identities, roles and pure contact. Same DM terrain/material/light. Camera only selects immutable bodies. Bounded23.664m2 source domain; not full distant-landscape physical particle coverage.'
paths=[O/'after_da_hook.py',O/'install_world_view.py',O/'install_catalog.py',O/'core/stable_catalog.py',R/'static_domain_dm/apply_static_layer.py',v.with_suffix('.json'),bp];j['geometry_soil_normals_db']={'revision':1,'source_pins':{str(p):sha(p)for p in paths},'dh_hook':str(R/'dh_coarse_source/after_history_hook.py'),'dh_config':prior,'install_source':str(O/'install_world_view.py'),'catalog_config':cfg,'layer_source':str(R/'static_domain_dm/apply_static_layer.py'),'layer':q['static_fine_layer_dl']};
if not macro:
 # The prior wide cache attempt exceeded RSS. Use the established source path,
 # without changing geometry, texture tier or the guard.
 dest=R/'dq_world_normal_a';assert not dest.exists(),'Use a fresh whole-view directory';dest.mkdir()
 shutil.copytree(R/'dm_static_domain_a/runtime',dest/'runtime',ignore=shutil.ignore_patterns('__pycache__','pipeline_snapshots'))
 bridge=dest/'runtime/src/geometry_soil_normals_db.py';bridge.write_text('from pathlib import Path\nimport importlib.util,hashlib\ndef apply(scene,cfg,out):\n p=Path('+repr(str(O/'after_da_hook.py'))+')\n assert hashlib.sha256(p.read_bytes()).hexdigest()=='+repr(sha(O/'after_da_hook.py'))+'\n s=importlib.util.spec_from_file_location("dq_pinned_whole_hook",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m.apply(scene,cfg,out)\n')
 for key in ['historical_grain_roles_dg','coarse_geometry_dh','static_fine_layer_dl']:j.pop(key,None)
 j['output']=str(dest/'INTERNAL_PANEL.png');(dest/'job.json').write_text(json.dumps(j,indent=2)+'\n')
target=O/('job_world_'+a.view+'.json');target.write_text(json.dumps(j,indent=2)+'\n');print(target)
