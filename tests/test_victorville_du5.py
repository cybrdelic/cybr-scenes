"""Lightweight source ownership and preparation contracts for opt-in DU5."""
import ast,json,unittest
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
if __name__=='__main__':unittest.main()
