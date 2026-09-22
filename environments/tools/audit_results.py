#!/usr/bin/env python3
"""Cross-check completed execution receipts against the actual source and assets."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cybr_scenes import SCENES,sha,atomic_json,dependency_fingerprint,now

def audit():
 result=[]
 for scene in SCENES.values():
  d=ROOT/'renders'/scene['id']/'hero';receipt=json.loads((d/'receipt.json').read_text());meta=json.loads((d/'hero.json').read_text())
  mesh=ROOT/scene['upgraded_mesh'];g=json.loads((mesh.parent/'geometry-upgrade.json').read_text())
  binary=ROOT/'build'/f'{scene["engine"]}_r2';build=json.loads(binary.with_suffix('.build.json').read_text())
  meshsha=sha(mesh);exesha=sha(binary)
  checks={'mesh_matches_execution_receipt':meshsha==receipt['mesh_sha256'],
   'mesh_matches_upgrade_record':meshsha==g['result_sha256'],
   'executable_matches_execution_receipt':exesha==receipt['executable_sha256'],
   'source_matches_compiled_snapshot':dependency_fingerprint(scene['engine'])==build['source_fingerprint']==receipt['source_fingerprint'],
   'native_count_within_stream':0<meta['triangles']<=g['triangles'],
   'renderer_reported_zero_invalid':meta.get('nonfinite_path_samples',0)==0}
  assets=[];engine=scene['engine'];prefix=ROOT/'engines'/engine
  if engine in ['geo','hot']:
   assets.extend([prefix/'cybr-geo/examples/desert_hot_springs/assets'/name for name in ['gravel_periodic.pgm','granular_relief.bin']])
   assets.append(ROOT/'assets/mineral_detail.cdt')
   if (mesh.parent/'surface_frames.bin').exists():assets.append(mesh.parent/'surface_frames.bin')
  elif engine=='geode':assets=list((mesh.parent/'textures').glob('*.cvtex'))+[ROOT/'assets/mineral_detail.cdt']
  else:assets=[prefix/'assets'/name for name in ['rock_texture.bin','scan_texture_0.bin','scan_texture_1.bin','lava_skin.bin','sky.bin']]
  row={'scene':scene['id'],'passed':all(checks.values()),'checks':checks,
   'input_mesh_triangles':g['triangles'],'native_traced_triangles':meta['triangles'],
   'loader_rejected_near_degenerate_triangles':g['triangles']-meta['triangles'],
   'assets':{str(p.relative_to(ROOT)):sha(p) for p in assets},
   'scope':'Actual compiled source, executable, geometry, and loaded material/lighting sidecars; not an aesthetic score.'}
  result.append(row)
  if not row['passed']:raise RuntimeError('Receipt/source/geometry audit failed: '+scene['id'])
 report={'passed':len(result)==6,'checked_at':now(),'scenes':result};atomic_json(ROOT/'evidence/execution-integrity.json',report);return report
if __name__=='__main__':print(json.dumps(audit(),indent=2))
