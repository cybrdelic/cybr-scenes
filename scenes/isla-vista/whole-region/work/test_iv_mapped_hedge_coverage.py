"""Actual retained coverage rejection gate; reads only, builds no mesh."""
import json,sys,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
from iv_mapped_hedges_v1 import require_resolved_support,source,footprint
from shapely.geometry import shape
from collections import Counter
out=R/'evidence/mapped-hedges-v1';coverage=json.loads((out/'COVERAGE.json').read_text())
normalized=R/'evidence/full-iv-roofs/normalized.geojson'
assert hashlib.sha256(normalized.read_bytes()).hexdigest()==coverage['normalized_source_sha256']
excluded=coverage['excluded_from_preliminary_rollout'];eligible=coverage['preliminary_conflict_free_source_ids']
assert len(excluded)==19 and len(eligible)==84 and set(excluded).isdisjoint(eligible)
for sid in excluded:
 try:require_resolved_support(coverage,[sid])
 except ValueError:pass
 else:raise AssertionError('Excluded source admitted: '+sid)
require_resolved_support(coverage,eligible)
assert 'osm:way:822177699' in eligible
byid={x['id']:x for x in source()};kinds=Counter()
for row in coverage['building_support_conflicts']:
 f=byid[row['source_id']];s,_=footprint(f);g=shape(f['geometry'])
 b=[shape(byid[x]['geometry']) for x in row['intersected_building_source_ids']]
 from shapely import union_all
 building=union_all(b)
 if g.geom_type=='LineString':
  length=g.intersection(building.buffer(-1e-6)).length
  classification='mapped line crosses building interior' if length>1e-6 else 'estimated width only; mapped line clear of building interior'
  assert abs(length-row['mapped_line_inside_building_m'])<1e-6
 else:classification='mapped polygon overlap'
 assert classification==row['classification'];kinds[classification]+=1
 assert abs(s.intersection(building).area-row['building_overlap_area_m2'])<1e-6
assert sorted(kinds.values())==[1,1,8]
receipt={'passed':True,'normalized_source_sha256':coverage['normalized_source_sha256'],'coverage_sha256':hashlib.sha256((out/'COVERAGE.json').read_bytes()).hexdigest(),'excluded_features_individually_refused':excluded,'preliminary_conflict_free_passes_selection_only':len(eligible),'building_conflict_classifications_independently_recomputed':dict(kinds),'fixture_eligible':True,'scope':'Exclusion checks only; no unbuilt feature claimed as geometrically or visually qualified.'}
(out/'ACTUAL_EXCLUSION_TESTS.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
