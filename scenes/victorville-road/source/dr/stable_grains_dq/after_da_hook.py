from pathlib import Path
import importlib.util,hashlib,sys,json
import numpy as np

def load(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def apply(scene,cfg,out):
 for p,h in cfg['source_pins'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
 sys.path.insert(0,str(Path(cfg['install_source']).parent/'core'))
 prior=load(cfg['dh_hook'],'dq_pinned_dh');report={'DH_geometry_and_DB':prior.apply(scene,cfg['dh_config'],out)}
 installer=load(cfg['install_source'],'dq_install');report['DQ']=installer.apply(scene,cfg['catalog_config'],out)
 layer=load(cfg['layer_source'],'dq_fixed_DM');report['DM']=layer.apply(scene,cfg['layer'],out)
 expected=np.load(Path(out)/'DQ_SELECTED_IDENTITY.npz');positions=[];identities=[]
 for name in ['U approved R5D density / projected chip and grit supplement','CZ current-view original sand instances']:
  ob=scene.objects[name];co=np.empty((len(ob.data.vertices),3),'f4');ob.data.vertices.foreach_get('co',co.ravel());positions.append(co)
  lo=np.empty(len(co),'i4');hi=lo.copy();ob.data.attributes['grain_id_lo'].data.foreach_get('value',lo);ob.data.attributes['grain_id_hi'].data.foreach_get('value',hi);identities.append((hi.view('u4').astype('u8')<<np.uint64(32))|lo.view('u4').astype('u8'))
 actual=np.concatenate(positions);ids=np.concatenate(identities);assert np.array_equal(ids,expected['id']);assert np.array_equal(actual,expected['xyz']),float(np.max(abs(actual-expected['xyz'])))
 proof={'stored_blender_XYZ_and_uint64_ID_bitwise_match_frozen_catalog':True,'count':len(ids),'xyz_sha256':hashlib.sha256(actual.tobytes()).hexdigest(),'id_sha256':hashlib.sha256(ids.tobytes()).hexdigest()};(Path(out)/'DQ_ACTUAL_GEOMETRY_CHECK.json').write_text(json.dumps(proof,indent=2)+'\n');report['actual_geometry_check']=proof;return report
