from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[1];base=R/'cq_candidate';out=R/sys.argv[1];mode=sys.argv[2];assert not out.exists();m=json.loads((base/'runtime/pipeline/manifest.json').read_text());bank=base/'runtime/pipeline/pipeline_snapshots/067ceffd2795b5c059b8341dd179bdd11ddb53cfbaf669298c50ff4d97999168'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for n,h in m.items():assert sha(bank/n)==h
shutil.copytree(base/'runtime',out/'runtime',ignore=shutil.ignore_patterns('pipeline_snapshots','__pycache__'))
for n in m:
 shutil.copyfile(bank/n,out/'runtime/pipeline'/n)
 if n.endswith('.py'):shutil.copyfile(bank/n,out/'runtime/src'/n)
s=(out/'runtime/pipeline/render_landform_candidate.py').read_text();anchor="  if job.get('victorville_reflectance_cn'):\n   extra_sources['victorville_reflectance_cn.py']";assert s.count(anchor)==1;s=s.replace(anchor,"  if job.get('visible_fine_grains_cz'):\n   extra_sources['visible_fine_grains_cz.py']=pathlib.Path(__file__).resolve().parent.parent/'src/visible_fine_grains_cz.py'\n\n"+anchor)
anchor=' cull_adaptation=camera_cull_dense_offscreen(job,s)';assert s.count(anchor)==1;s=s.replace(anchor," if job.get('visible_fine_grains_cz'):\n  from visible_fine_grains_cz import apply as apply_visible_fine_grains_cz\n  report=apply_visible_fine_grains_cz(s,job['visible_fine_grains_cz'],pathlib.Path(job['output']).parent);adaptations.append({'visible_fine_grains_cz':report})\n"+anchor)
for n in ('render.py','render_landform_candidate.py'):
 for sub in ('pipeline','src'):(out/'runtime'/sub/n).write_text(s)
 m[n]=sha(out/'runtime/pipeline'/n)
for sub in ('pipeline','src'):shutil.copyfile(R/'cz_source/visible_fine_grains_cz.py',out/'runtime'/sub/'visible_fine_grains_cz.py')
m['visible_fine_grains_cz.py']=sha(R/'cz_source/visible_fine_grains_cz.py');(out/'runtime/pipeline/manifest.json').write_text(json.dumps(m,indent=2)+'\n')
j=json.loads((base/'job.json').read_text());j['output']=str(out/'INTERNAL_PANEL.png');j['width']=900 if 'close' in mode else 1000;j['height']=675 if 'close' in mode else 667;j['samples']=48 if 'close'in mode else 32
cfg=dict(revision=1,sand_bank=str(R/'cz_source/sand_bank.json'),sand_bank_sha256=sha(R/'cz_source/sand_bank.json'),width=j['width'],height=j['height'],grit_budget=135000,sand_budget=85000)
if 'close'in mode:j['preview_hide_fully_offscreen_terrain']=True
if 'close'in mode:cfg.update(close_center=[-4.9,6.0],bounds=[-5.2,-4.55,5.5,6.35])
if 'baseline'in mode:cfg['audit_only']=True
j['visible_fine_grains_cz']=cfg;j['view_scope']='CZ actual source sand and current-frustum R5D grit allocation. Original source metric sizes/materials, CQ terrain/CN palette/CO22 sun. Budgeted instance geometry; microbed shader retained.'
(out/'job.json').write_text(json.dumps(j,indent=2)+'\n');(out/'CZ_STAGING.json').write_text(json.dumps(dict(baseline='CQ',mode=mode,pipeline=hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest(),bank_sha256=cfg['sand_bank_sha256']),indent=2)+'\n')
for p in (out/'runtime').rglob('*.py'):compile(p.read_text(),str(p),'exec')
print(out)
