"""Prepare an additive DU5 runtime without editing the accepted DR source.
Requires already prepared/admitted DR and the explicit CYBR MATERIAL checkout.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,ast
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--dr-root',type=Path,default=R.parent/'dr');p.add_argument('--material-root',required=True,type=Path);p.add_argument('--output-root',required=True,type=Path);p.add_argument('--view',choices=['normal','crop','wide'],default='normal');args=p.parse_args()
D=args.dr_root.resolve();M=args.material_root.resolve();O=args.output_root.resolve();assert not O.exists(),'Use a fresh output directory'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins=json.loads((R/'MATERIAL_DEPENDENCY.json').read_text());base=D/'dr_recovered_whole';j=json.loads((base/'job.json').read_text());before=sha(base/'job.json')
assert Path(j['source']).is_file();assert sha(j['source'])==j['source_sha256']
for row in pins['files']:
 assert sha(M/row['path'])==row['sha256'],row['path']
O.mkdir(parents=True);runtime=O/'runtime';shutil.copytree(base/'runtime',runtime,ignore=shutil.ignore_patterns('pipeline_snapshots','__pycache__','cache'))
modules=['apply_du.py','field_du.py','exposure_du.py','root_contact_du.py','matrix_du.py','native_border.py']
for name in modules:shutil.copy2(R/name,runtime/'src'/name)
for row in pins['files']:shutil.copy2(M/row['path'],runtime/'src'/Path(row['path']).name)
# Only the copied runtime receives the additive adapters. Original recipes,
# source bytes, baseline preparation and its selected outputs remain untouched.
capabilities=json.loads((R/'DR_PIPELINE_CAPABILITIES.json').read_text());assert capabilities['schema_version']==1
for name in ['render.py','render_landform_candidate.py']:
 path=runtime/'pipeline'/name;s=path.read_text();renderer_sha=sha(path)
 assert renderer_sha in capabilities['renderer_sources'], 'Unsupported DR renderer source capability: '+renderer_sha
 capability=capabilities['renderer_sources'][renderer_sha];border_version=capability['native_border_version'];assert border_version in (0,1)
 native_handlers=[n for n in ast.walk(ast.parse(s)) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Constant) and n.test.left.value=='render_border' and len(n.test.ops)==1 and isinstance(n.test.ops[0],ast.In) and len(n.test.comparators)==1 and isinstance(n.test.comparators[0],ast.Name) and n.test.comparators[0].id=='job']
 assert len(native_handlers)==border_version, 'Ambiguous or inconsistent native-border capability'
 key='  pipeline=pipeline_snapshot(extra_sources)';assert s.count(key)==1
 s=s.replace(key,"  if job.get('du_connected_interspaces'):\n   for name in "+repr(tuple(modules+['granular_matrix.py','granular_matrix_profiles.json']))+":extra_sources[name]=pathlib.Path(__file__).resolve().parent.parent/'src'/name\n"+key)
 key=" if job.get('daylight_model_co'):\n  from daylight_model_co import apply as apply_daylight_model_co";assert s.count(key)==1
 s=s.replace(key," if job.get('du_connected_interspaces'):\n  from apply_du import material as du_material\n  report=du_material(s,job['du_connected_interspaces'],pathlib.Path(job['output']).parent);adaptations.append({'DU_material':report})\n"+key)
 key="width=job.get('width',960);height=job.get('height',round(width*s.render.resolution_y/s.render.resolution_x));s.render.resolution_x=width;s.render.resolution_y=height;s.render.resolution_percentage=100";assert s.count(key)==1;s=s.replace(key,key+'\n projection_resolution=[width,height]')
 key=" out=pathlib.Path(job['output']);out.parent.mkdir(parents=True,exist_ok=True);s.render.filepath=str(out);s.render.image_settings.file_format='PNG'";assert s.count(key)==1
 border=""" if 'render_border' in job or 'render_border_pixels' in job:
  from native_border import configure as configure_native_border
  width,height,border_capture=configure_native_border(s,job,width,height)
  adaptations.append({'native_render_border':border_capture})
"""
 # Replace exactly the admitted version1 AST span. Unknown layouts are rejected
 # above by source SHA and capability/handler agreement, never substring guesses.
 if border_version==1:
  node=native_handlers[0];lines=s.splitlines(keepends=True)
  # Earlier insertions change line numbers; find the sole admitted AST again.
  node=next(n for n in ast.walk(ast.parse(s)) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Constant) and n.test.left.value=='render_border')
  s=''.join(lines[:node.lineno-1])+border+''.join(lines[node.end_lineno:])
 else:s=s.replace(key,' border_capture=None\n'+border+key)
 key=" report['pipeline']=pipeline;";assert s.count(key)==1;s=s.replace(key," report['projection_resolution']=projection_resolution;report['render_border']=border_capture\n"+key);path.write_text(s)
hook=D/'stable_grains_dq/after_da_hook.py';bridge=f'''from pathlib import Path
import importlib.util,hashlib

def apply(scene,cfg,out):
 p=Path({str(hook)!r});assert hashlib.sha256(p.read_bytes()).hexdigest()=={sha(hook)!r}
 spec=importlib.util.spec_from_file_location('pinned_DR_before_DU5',p);baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
 result=baseline.apply(scene,cfg,out)
 from apply_du import geometry
 candidate=geometry(scene,cfg['du'],out)
 return {{'frozen_DR_before_candidate':result,'DU_candidate':candidate}}
''';(runtime/'src/geometry_soil_normals_db.py').write_text(bridge)
cfg={'revision':5,'cap':str(D/'static_domain_dm/STATIC_FINE_LAYER.npz')}
for key,name in [('matrix_source','granular_matrix.py'),('matrix_profile','granular_matrix_profiles.json')]:cfg[key]=str(runtime/'src'/name);cfg[key+'_sha256']=sha(runtime/'src'/name)
j['geometry_soil_normals_db']['du']=cfg;j['du_connected_interspaces']=cfg;j['output']=str(O/'INTERNAL_PANEL.png');j['width']=2000;j['height']=1334;j['samples']=32;j['time_limit_seconds']=750;j['view_scope']='Opt-in DU5 original procedural soil improvement. Same AV mountains/CN chromatic endpoints/CO22 daylight. Not photoreal completion.'
if args.view=='crop':j.pop('render_border',None);j['render_border_pixels']=[500,1800,0,680]
if args.view=='wide':j['lens']=24
(O/'job.json').write_text(json.dumps(j,indent=2)+'\n');assert sha(base/'job.json')==before
(O/'PREPARATION.json').write_text(json.dumps({'dr_job_before_and_after_sha256':before,'material_dependencies':pins,'source_files':{n:sha(R/n)for n in modules},'selected_DR_unchanged':True,'view':args.view,'source_scene_sha256':j['source_sha256']},indent=2)+'\n');print(O/'job.json')
