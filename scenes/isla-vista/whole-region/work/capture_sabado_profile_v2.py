"""Native matched-camera capture, gated on independently verified closed geometry."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
from cybr_light import Scene,render
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--spp',type=int,default=32);p.add_argument('--mesh',type=Path,required=True);p.add_argument('--verification',type=Path,required=True);args=p.parse_args();assert args.spp in [32,128]
OUT=R/'evidence/sabado-profile-matched-v2';OUT.mkdir(exist_ok=True)
new=args.mesh.resolve();verification_path=args.verification.resolve();verification=json.loads(verification_path.read_text());assert verification['passed']
actual_hash=hashlib.sha256(new.read_bytes()).hexdigest();assert actual_hash==verification['target_sha256']
adjacent=json.loads((new.parent/'ADJACENT_CAP_EDGE_SCOPE_VERIFICATION.json').read_text())
assert adjacent['passed'] and adjacent['target_sha256']==actual_hash
source=R/'evidence/whole-iv-recovered-views/sabado_frontages_600_32.cys';old=R/'evidence/full-iv-path-uv-rebased/contact.clm'
text=re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source.parent/m[1]).resolve())),source.read_text())
assert text.count(str(old))==1;text=text.replace(str(old),str(new))
lines=[]
for line in text.splitlines():
 if line.startswith('settings '):
  tokens=line.split();assert tokens[1:4]==['600','420','32'];tokens[3]=str(args.spp);line=' '.join(tokens)
 lines.append(line)
s=Scene();s.lines=lines;stem=OUT/f'sabado_profile_600_{args.spp}';s.save(stem.with_suffix('.cys'))
(OUT/'CAPTURE_SOURCE_SNAPSHOT.py').write_bytes(Path(__file__).read_bytes())
subprocess.run([sys.executable,str(R/'work/audit_scene_metric_uv.py'),str(stem.with_suffix('.cys'))],check=True)
report=render(s,stem,metadata={'purpose':'Matched original Sabado camera; only bounded north-sidewalk authored crossfall/profile and closed-edge conformance changed.','source_baseline_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'closed_mesh_sha256':actual_hash,'independent_verification_sha256':hashlib.sha256(verification_path.read_bytes()).hexdigest(),'physical_material_camera_lighting_unchanged':True,'samples_changed_from_original':args.spp!=32,'estimated_geometry':'2% crossfall around mapped path centerline at source elevation +0.14 m, with source driveway transitions and edge tops reconciled to actual cap triangles. Exact underlying source terrain and XY footprints preserved.','limits':'Authored construction estimate, not measured engineering. Existing streetscape/material limitations remain. Native CYBR LIGHT; no image generation.'})
print(json.dumps({k:report[k] for k in ['width','height','primitives','render_seconds','invalid_path_samples']}),flush=True)
