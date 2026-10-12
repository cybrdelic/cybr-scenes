"""Same complete-Isla-Vista camera, using the corrected current corridor scene."""
from pathlib import Path
import sys,json,shlex,re,hashlib
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Scene,render
from cybr_light.finishing import atrous,tonemap,save_png # Preflight before a long native trace.
source=r/'evidence/full-iv-del-playa-corridor/whole_iv_del_playa.cys';view=json.loads((r/'work/iv_current_overview_view.json').read_text());out=r/'evidence/full-iv-current-overview';out.mkdir(exist_ok=True)
controls=view['controls'];s=Scene();old=source.read_text().splitlines()
for line in old:
 key=line.split(' ',1)[0]
 if key in controls:line=controls[key]
 else:line=re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),line)
 s.lines.append(line)
s.save(out/'whole_iv_region_oblique.cys');resources=[]
for line in (out/'whole_iv_region_oblique.cys').read_text().splitlines():
 q=shlex.split(line)
 if not q:continue
 field=2 if q[0] in {'texture','roughness_texture'} else 1 if q[0] in {'observer','envmap','meshlets','meshlets_excluding'} else None
 if field is not None:
  p=(out/q[field]).resolve();assert p.is_file(),p;resources.append(str(p))
metadata={'scope':'Current complete Isla Vista geographic scene in the original full-region camera. Includes corrected mapped habitat/water/roof provenance, near-street botanical geometry, three identified Del Playa buildings and bounded continuous sidewalk/apron construction.','coordinate_contract':view['coordinate_contract'],'coverage':view['coverage'],'camera_coverage_check':view['camera_coverage_check'],'source_corridor_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'same_camera_settings_as_prior_regional_overview':True,'resource_references_verified':len(resources),'limits':'Current regional master view, not a photorealism claim. Most buildings and contextual vegetation remain simplified; local dimensions/finishes are estimates. No image generation, photo textures, scan, coupled simulation or realtime performance claim.'}
(out/'OVERVIEW_PREPARATION.json').write_text(json.dumps(metadata,indent=2)+'\n')
if '--prepare-only' in sys.argv:print(json.dumps(metadata));sys.exit(0)
report=render(s,out/'whole_iv_region_oblique',metadata=metadata);print(json.dumps(report),flush=True)
