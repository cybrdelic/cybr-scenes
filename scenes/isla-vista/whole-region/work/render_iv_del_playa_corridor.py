from pathlib import Path
import sys,json,shlex,hashlib,re
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Scene,render
base=r/'evidence/full-iv-near-street/whole_iv_del_playa.cys';arch=r/'evidence/full-iv-del-playa-architecture';out=r/'evidence/full-iv-del-playa-corridor';out.mkdir(exist_ok=True);receipt=json.loads((arch/'ARCHITECTURE_RECEIPT.json').read_text());validation=json.loads((arch/'ARCHITECTURE_VALIDATION.json').read_text());assert validation['passed'];s=Scene();lines=base.read_text().splitlines();new=[];base_done=facade_done=False
for line in lines:
 q=shlex.split(line)
 if not q:continue
 if q[0]=='meshlets_excluding' and q[1].endswith('/full-iv-roofs/sector.clm'):
  old_ids=list(map(int,q[3:]));assert len(old_ids)==int(q[2]);assert not set(old_ids)&set(receipt['replace_sector_components']);ids=old_ids+receipt['replace_sector_components'];line='meshlets_excluding '+json.dumps(q[1])+' '+str(len(ids))+' '+' '.join(map(str,ids));base_done=True
 elif q[0]=='meshlets' and q[1].endswith('/full-iv-facades/facades.clm'):
  ids=receipt['exclude_prior_facade_objects'];line='meshlets_excluding '+json.dumps(q[1])+' '+str(len(ids))+' '+' '.join(map(str,ids));facade_done=True
 new.append(line)
assert base_done and facade_done
materials=[re.sub(r'"([^"]+)"',lambda m:json.dumps(str((arch/m[1]).resolve())),x) for x in (arch/'materials.cys').read_text().splitlines()];assert sum(x.startswith('material ') for x in new)==172;assert sum(x.startswith('material ') for x in materials)==receipt['material_count'];s.lines=new+materials;s.mesh(arch/'architecture.clm')
walk=r/'evidence/full-iv-del-playa-walks';walk_receipt=json.loads((walk/'WALKS_RECEIPT.json').read_text());walk_validation=json.loads((walk/'WALKS_VALIDATION.json').read_text());assert walk_validation['passed'];assert sum(x.startswith('material ') for x in s.lines)==walk_receipt['material_offset'];s.lines.extend((walk/'materials.cys').read_text().splitlines());s.mesh(walk/'walks.clm')
#Existing meshes use the original172 materials; new materials precede their new mesh.
#Camera, sampling, sky, finite sun and finishing controls remain exact.
controls=('settings ','camera ','observer ','envmap ','environment ','environment_sun ')
assert [x for x in s.lines if x.startswith(controls)]==[x for x in lines if x.startswith(controls)]
s.save(out/'whole_iv_del_playa.cys')
resource_checks=[]
for line in (out/'whole_iv_del_playa.cys').read_text().splitlines():
 q=shlex.split(line)
 if not q:continue
 field=2 if q[0] in {'texture','roughness_texture'} else 1 if q[0] in {'observer','envmap','meshlets','meshlets_excluding'} else None
 if field is not None:
  path=(out/q[field]).resolve();assert path.is_file(),str(path);resource_checks.append(str(path))
(out/'RESOURCE_PREFLIGHT.json').write_text(json.dumps({'passed':True,'resource_references_verified':len(resource_checks),'scope':'All referenced material, sky, observer and mesh files exist after resolving the actual saved scene paths.'},indent=2)+'\n')
if '--prepare-only' in sys.argv:print(json.dumps({'prepared_scene':str(out/'whole_iv_del_playa.cys'),'resource_references_verified':len(resource_checks)}));sys.exit(0)
record=render(s,out/'whole_iv_del_playa',metadata={'scope':'Three source-identified adjacent Del Playa buildings and continuous source-aligned sidewalk construction added to the complete preserved Isla Vista geographic scene. Original camera, native spectral integrator, lighting and finishing controls unchanged. No footprint-filter experiment applied.','baseline_scene_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'baseline_image':'evidence/full-iv-near-street/whole_iv_del_playa.png','architecture_receipt':receipt,'serialized_validation':validation,'sidewalk_receipt':walk_receipt,'sidewalk_validation':walk_validation,'reference_manifest':'references/del-playa-corridor/REFERENCE_MANIFEST.json','limits':'Photos guide original procedural modeling only. Dimensions, optics, unseen details and roof pitch are estimates.6574 manager evidence supersedes its conflicting OSM floor tag only in this authored component. Other whole-IV buildings remain simplified.'});print(json.dumps(record),flush=True)
