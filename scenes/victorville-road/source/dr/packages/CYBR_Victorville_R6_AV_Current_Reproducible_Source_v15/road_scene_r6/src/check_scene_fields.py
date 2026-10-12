"""Bounded physical cross-section checks; does not assert visual acceptance."""
import numpy as np, json, ast, hashlib
from pathlib import Path
r=Path(__file__).resolve().parents[1];src=(r/'src/build_scene.py').read_text();tree=ast.parse(src);names={'field','grade','edge_y','road_z','wash','terrain','tint_ground'};body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names];ns={'np':np};exec(compile(ast.Module(body=body,type_ignores=[]),'<scene-fields>','exec'),ns)
y=np.linspace(-10,200,15000);bounds={}
for side in(-1,1):
 x=ns['edge_y'](y,side);h=ns['road_z'](x,y)-ns['terrain'](x,y);assert np.isfinite(h).all() and h.min()>-.031 and h.max()<.031;bounds[str(side)]={'min_exposed_edge_m':float(h.min()),'max_exposed_edge_m':float(h.max()),'fraction_ground_at_or_above_road':float((h<=0).mean())}
height=ns['road_z'](0,y)-ns['road_z'](3.2,y);assert .060<height.min() and height.max()<.065
result={'samples_per_side':len(y),'edge_bounds':bounds,'crown_range_m':[float(height.min()),float(height.max())],'finite':True,'threads':2,'source_sha256':hashlib.sha256(src.encode()).hexdigest(),'scope':'Cross-section functions and Python syntax only; actual renders separately inspected.'}
(r/'receipts/field_checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
