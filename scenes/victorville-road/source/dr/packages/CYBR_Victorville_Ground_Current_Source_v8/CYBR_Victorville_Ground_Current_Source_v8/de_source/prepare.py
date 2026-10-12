"""Prepare a config-only actual-output footprint allocation control.
No scene/map generation, no implicit render. Baseline runtime remains immutable.
"""
from pathlib import Path
import argparse,hashlib,json
p=argparse.ArgumentParser();p.add_argument('--baseline',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();b=a.baseline.resolve();o=a.out.resolve();assert not o.exists();raw=(b/'job.json').read_bytes();j=json.loads(raw)
assert j['width']==2000 and j['height']==1334 and j['samples']==32 and j['capture_mode']=='unfiltered'
assert j['visible_fine_grains_cz']['width']==1000 and j['visible_fine_grains_cz']['height']==667
assert not j.get('retire_grain_proxy_dd') and not j.get('restored_grit_contact_dc')
assert j['visible_fine_grains_cz']['grit_budget']==135000 and j['visible_fine_grains_cz']['sand_budget']==85000
j['visible_fine_grains_cz'].update(width=j['width'],height=j['height'])
j['output']=str(o/'INTERNAL_PANEL.png');j['view_scope']='DE actual native2000x1334 allocation footprint; same DB source-density/metric sizes/maximum counts, camera,1024contextmaps,lighting and32raw samples. Budgeted population approximation; point selection/layout may change.'
o.mkdir();(o/'job.json').write_text(json.dumps(j,indent=2)+'\n')
r={'baseline_job_sha256':hashlib.sha256(raw).hexdigest(),'candidate_job_sha256':hashlib.sha256((o/'job.json').read_bytes()).hexdigest(),'runtime':str(b/'runtime/pipeline/clean_render_landform_candidate.sh'),'changes':{'visible_fine_grains_cz.width':[1000,2000],'visible_fine_grains_cz.height':[667,1334]},'all_other_source_and_render_settings_unchanged':True,'no_render_started':True}
(o/'PREPARATION.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
