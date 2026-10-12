import ast,unittest,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'scenes/victorville-road/source/dv3'
class PlantContracts(unittest.TestCase):
 def test_source_parses(self):
  for p in S.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
 def test_material_source_not_duplicated(self):
  s=(S/'wood_surface.py').read_text();self.assertNotIn('ShaderNodeTexNoise',s);self.assertIn('owner.install',s);self.assertFalse((S/'bark_flow_profiles.json').exists())
 def test_protected_scene_scope(self):
  s=(S/'apply_woody_scene.py').read_text();self.assertIn('assert before==after',s);self.assertIn("all_basal_samples_below_substrate",s);self.assertIn('all_existing_object_matrices_byte_exact',s)
 def test_pins(self):
  p=json.loads((S/'MATERIAL_DEPENDENCY.json').read_text());self.assertEqual(p['repository'],'cybrdelic/cybr-material');self.assertEqual([x['path']for x in p['files']],['source/bark_flow.py','source/bark_flow_profiles.json']);self.assertTrue(all(len(x['sha256'])==64 for x in p['files']))
if __name__=='__main__':unittest.main()
