#!/usr/bin/env python3
"""Recompute the delivered PNGs from unchanged native films and compare hashes."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cybr_scenes import SCENES,render_command,run,sha,atomic_json,now

def verify_all():
 results=[]
 for scene in SCENES.values():
  stem=ROOT/'renders'/scene['id']/'hero/hero';meta=json.loads(stem.with_suffix('.json').read_text())
  before_png=sha(stem.with_suffix('.png'));before_raw=sha(stem.with_suffix('.pfm'))
  _,cwd,command=render_command(scene,ROOT/'build'/f'{scene["engine"]}_r2',ROOT/scene['upgraded_mesh'],stem,
      meta['width'],meta['height'],meta['spp'],meta.get('water_spp',meta['spp']),2)
  record=run(command,cwd,stem.parent/'finish-reproduction.log',2)
  png=sha(stem.with_suffix('.png'));raw=sha(stem.with_suffix('.pfm'))
  result={'scene':scene['id'],'png_byte_identical':png==before_png,'raw_film_unchanged':raw==before_raw,
      'png_sha256':png,'raw_pfm_sha256':raw,'command_record':str((stem.parent/'finish-reproduction.command.json').relative_to(ROOT)),
      'seconds':record['seconds']}
  results.append(result)
  if not result['png_byte_identical'] or not result['raw_film_unchanged']:
   atomic_json(ROOT/'evidence/finish-reproduction.json',{'passed':False,'scenes':results});raise RuntimeError('Native-film PNG reproduction failed: '+scene['id'])
 result={'passed':True,'checked_at':now(),'scenes':results,
  'scope':'Each PNG was recomputed from its unchanged native PFM/AOV files using the same documented display code; byte equality is checked. This is not a second full native transport run.'}
 atomic_json(ROOT/'evidence/finish-reproduction.json',result);return result
if __name__=='__main__':print(json.dumps(verify_all(),indent=2))
