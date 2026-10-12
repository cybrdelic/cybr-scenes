"""Lightweight source ownership and preparation contracts for opt-in DU5."""
import ast,json,unittest,hashlib,tempfile,subprocess,sys,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'scenes/victorville-road/source/du5'
class DU5Contract(unittest.TestCase):
 def test_all_source_parses(self):
  files=list(S.glob('*.py'));self.assertEqual(len(files),6)
  for p in files:ast.parse(p.read_text(),filename=str(p))
 def test_material_owner_is_pinned(self):
  p=json.loads((S/'MATERIAL_DEPENDENCY.json').read_text());self.assertEqual(p['repository'],'cybrdelic/cybr-material');self.assertEqual({x['path']for x in p['files']},{'source/granular_matrix.py','source/granular_matrix_profiles.json'});self.assertTrue(all(len(x['sha256'])==64 for x in p['files']))
 def test_no_duplicate_material_recipe(self):
  self.assertFalse((S/'granular_matrix.py').exists());self.assertFalse((S/'granular_matrix_profiles.json').exists());s=(S/'matrix_du.py').read_text();self.assertIn('owner.aggregate_fields',s);self.assertNotIn('ShaderNodeTexNoise',s)
 def test_baseline_is_only_read(self):
  s=(S/'prepare_du5.py').read_text();self.assertIn("assert not O.exists()",s);self.assertIn("assert sha(base/'job.json')==before",s);self.assertIn("runtime=O/'runtime'",s)
class DU5PreparationRegression(unittest.TestCase):
 def test_native_border_capability_admission(self):
  # Exercise the real preparer with a tiny admitted source closure. This is
  # preparation coverage, not a Blender scene or render-quality fixture.
  for inherited,state in [(False,'valid'),(True,'valid'),(True,'unknown'),(True,'ambiguous')]:
   with self.subTest(inherited_native_border=inherited,capability=state),tempfile.TemporaryDirectory() as tmp:
    T=Path(tmp);source=T/'du5';source.mkdir();material=T/'material';(material/'source').mkdir(parents=True);dr=T/'dr';base=dr/'dr_recovered_whole';(base/'runtime/pipeline').mkdir(parents=True);(base/'runtime/src').mkdir();(dr/'stable_grains_dq').mkdir()
    for name in ['prepare_du5.py','apply_du.py','field_du.py','exposure_du.py','root_contact_du.py','matrix_du.py']:shutil.copy2(S/name,source/name)
    pins={'repository':'cybrdelic/cybr-material','files':[]}
    for name in ['granular_matrix.py','granular_matrix_profiles.json']:
     p=material/'source'/name;p.write_text('fixture dependency');pins['files'].append({'path':'source/'+name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (source/'MATERIAL_DEPENDENCY.json').write_text(json.dumps(pins));scene=T/'admitted_source.blend';scene.write_bytes(b'preparation-only fixture');(dr/'stable_grains_dq/after_da_hook.py').write_text('fixture hook')
    job={'source':str(scene),'source_sha256':hashlib.sha256(scene.read_bytes()).hexdigest(),'geometry_soil_normals_db':{}};(base/'job.json').write_text(json.dumps(job))
    text="if True:\n if True:\n  pipeline=pipeline_snapshot(extra_sources)\n if job.get('daylight_model_co'):\n  from daylight_model_co import apply as apply_daylight_model_co\n width=job.get('width',960);height=job.get('height',round(width*s.render.resolution_y/s.render.resolution_x));s.render.resolution_x=width;s.render.resolution_y=height;s.render.resolution_percentage=100\n"
    if inherited:text+=" border_capture=None\n if 'render_border' in job:\n  pass # existing admitted native adapter\n"
    text+=" out=pathlib.Path(job['output']);out.parent.mkdir(parents=True,exist_ok=True);s.render.filepath=str(out);s.render.image_settings.file_format='PNG'\n report['pipeline']=pipeline;\n"
    for name in ['render.py','render_landform_candidate.py']:(base/'runtime/pipeline'/name).write_text(text)
    (source/'DR_PIPELINE_CAPABILITIES.json').write_text(json.dumps({'schema_version':1,'renderer_sources':{('0'*64 if state=='unknown' else hashlib.sha256(text.encode()).hexdigest()):{'native_border_version':0 if state=='ambiguous' else int(inherited),'label':'explicit unit fixture'}}}))
    run=subprocess.run([sys.executable,str(source/'prepare_du5.py'),'--dr-root',str(dr),'--material-root',str(material),'--output-root',str(T/'out'),'--view','crop'],capture_output=True,text=True)
    if state!='valid':
     self.assertNotEqual(run.returncode,0);self.assertIn('Unsupported DR renderer source capability' if state=='unknown' else 'Ambiguous or inconsistent native-border capability',run.stderr);continue
    self.assertEqual(run.returncode,0,run.stderr)
    for name in ['render.py','render_landform_candidate.py']:
     prepared=(T/'out/runtime/pipeline'/name).read_text();self.assertEqual(prepared.count(" if 'render_border' in job:"),1)
     if inherited:self.assertIn('existing admitted native adapter',prepared)

if __name__=='__main__':unittest.main()
