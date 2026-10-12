from pathlib import Path
import json,hashlib,shutil,argparse
ap=argparse.ArgumentParser();ap.add_argument('--cz',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--width',type=int);ap.add_argument('--height',type=int);ap.add_argument('--shadow-probe',action='store_true');a=ap.parse_args();base=a.cz.resolve();out=a.out.resolve();here=Path(__file__).resolve().parent;assert not out.exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();m=json.loads((base/'runtime/pipeline/manifest.json').read_text());pin=hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest();assert pin=='a3c6b0ddfd71e3925243e073daab18d94ed1f88cff32e123fbf77c264e8b20ad';bank=base/'runtime/pipeline/pipeline_snapshots'/pin
if not bank.is_dir():bank=base/'runtime/pipeline'
for n,h in m.items():assert sha(bank/n)==h
shutil.copytree(base/'runtime',out/'runtime',ignore=shutil.ignore_patterns('pipeline_snapshots','__pycache__'))
for n in m:
 shutil.copyfile(bank/n,out/'runtime/pipeline'/n)
 if n.endswith('.py'):shutil.copyfile(bank/n,out/'runtime/src'/n)
s=(out/'runtime/pipeline/render_landform_candidate.py').read_text();anchor="  if job.get('visible_fine_grains_cz'):\n   extra_sources['visible_fine_grains_cz.py']";assert s.count(anchor)==1;s=s.replace(anchor,"  if job.get('source_relative_burial_da'):\n   extra_sources['source_relative_burial_da.py']=pathlib.Path(__file__).resolve().parent.parent/'src/source_relative_burial_da.py'\n\n"+anchor)
anchor=' cull_adaptation=camera_cull_dense_offscreen(job,s)';assert s.count(anchor)==1;s=s.replace(anchor," if job.get('source_relative_burial_da'):\n  from source_relative_burial_da import apply as apply_source_relative_burial_da\n  report=apply_source_relative_burial_da(s,job['source_relative_burial_da'],pathlib.Path(job['output']).parent);adaptations.append({'source_relative_burial_da':report})\n"+anchor)
for n in ('render.py','render_landform_candidate.py'):
 for sub in ('pipeline','src'):(out/'runtime'/sub/n).write_text(s)
 m[n]=sha(out/'runtime/pipeline'/n)
for sub in ('pipeline','src'):shutil.copyfile(here/'source_relative_burial_da.py',out/'runtime'/sub/'source_relative_burial_da.py')
m['source_relative_burial_da.py']=sha(here/'source_relative_burial_da.py')
if a.shadow_probe:
 anchor="  if job.get('source_relative_burial_da'):";assert s.count(anchor)==1;s=s.replace(anchor,"  if job.get('shadow_probe_da'):\n   extra_sources['shadow_probe.py']=pathlib.Path(__file__).resolve().parent.parent/'src/shadow_probe.py'\n\n"+anchor)
 anchor=' cull_adaptation=camera_cull_dense_offscreen(job,s)';assert s.count(anchor)==1;s=s.replace(anchor," if job.get('shadow_probe_da'):\n  from shadow_probe import probe as shadow_probe_da\n  shadow_probe_da(s,pathlib.Path(job['output']).parent)\n"+anchor)
 for n in ('render.py','render_landform_candidate.py'):
  for sub in ('pipeline','src'):(out/'runtime'/sub/n).write_text(s)
  m[n]=sha(out/'runtime/pipeline'/n)
 for sub in ('pipeline','src'):shutil.copyfile(here/'shadow_probe.py',out/'runtime'/sub/'shadow_probe.py')
 m['shadow_probe.py']=sha(here/'shadow_probe.py')
(out/'runtime/pipeline/manifest.json').write_text(json.dumps(m,indent=2)+'\n');j=json.loads((base/'job.json').read_text());j['output']=str(out/'INTERNAL_PANEL.png');j['source_relative_burial_da']=dict(datums=str(here/'source_datums.json'),datums_sha256=sha(here/'source_datums.json'),sand_bank=j['visible_fine_grains_cz']['sand_bank']);j['view_scope']='DA same CZ geometry/XY/mineral/lighting and camera, only source-measured original fine-bed reference offsets restored on the new sand population. Local-plane approximation; older chip/grit and coarse bodies unchanged.'
if a.width:j['width']=a.width
if a.height:j['height']=a.height
if a.shadow_probe:j['shadow_probe_da']=True
j['view_scope']+=' Image resolution may differ from held CZ geometry allocation; both dimensions are explicit in the job. The optional solar-ray probe is read-only.'
(out/'job.json').write_text(json.dumps(j,indent=2)+'\n');print(out)
