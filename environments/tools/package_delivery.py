#!/usr/bin/env python3
"""Package source, display renders and native proof separately; verify every ZIP."""
from __future__ import annotations
import argparse,json,hashlib,sys,zipfile,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cybr_scenes import SCENES,verify_render,atomic_json,sha,now

FONTS={'.ttf','.otf','.woff','.woff2','.ttc'}
TRANSIENT_TOOLS={'continue_builds.sh','prepare_initial.sh','render_remaining.sh','finish_audits.sh','refinish_first_two.sh','fix_verification.py','refinish_recorded.py','finalize_delivery.sh','refinish_forest.py','refinish_hot.py'}

def source_selected(p):
 r=p.relative_to(ROOT);parts=r.parts
 if p.suffix.lower() in FONTS or any(x in parts for x in ['__pycache__','.git','.part-spool','.execution-history']):return False
 if p.suffix in ['.pyc','.nbc','.nbi','.partial','.o','.lock']:return False
 if parts[0] in ['geometry','geometry-r2','build','execution-jobs']:return False
 if p.name=='ARCHIVE_MANIFEST.json' or p.suffix in ['.pid','.flock']:return False
 if r.as_posix()=='evidence/delivery.json':return False
 if parts[0]=='tools' and p.name in TRANSIENT_TOOLS:return False
 if parts[0]=='renders':
  return len(parts)>=4 and parts[1] in SCENES and parts[2]=='hero' and p.suffix in ['.png','.json','.log','.txt'] and 'before_demodulation' not in p.name
 if parts[0]=='engines':
  if 'built_v3' in parts:return False
  if r.as_posix().startswith('engines/obsidian/assets/') and len(parts)==4 and (p.suffix=='.bin' and p.name!='sky.bin'):return False
 if p.name in ['CYBR_SCENES_R2_Gallery.html','CYBR_SCENES_R2_Overview.jpg']:return False
 if p.suffix=='.zip':return False
 return True

def archive(output,files):
 """Publish only a closed, CRC-tested archive; preserve the previous checkpoint on failure."""
 output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix='.'+output.name+'-',suffix='.partial',dir=output.parent)
 os.close(fd);temporary=Path(name);manifest=[]
 try:
  with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
   for p in sorted(files):
    r=p.relative_to(ROOT)
    if p.suffix.lower() in FONTS:raise ValueError('Font files are not distributed')
    z.write(p,Path(ROOT.name)/r)
    manifest.append({'path':str(r),'bytes':p.stat().st_size,'sha256':sha(p)})
   z.writestr(ROOT.name+'/ARCHIVE_MANIFEST.json',json.dumps({'created_at':now(),'files':manifest},indent=2))
  with zipfile.ZipFile(temporary) as z:
   broken=z.testzip()
   if broken:raise RuntimeError(f'Corrupt ZIP entry: {broken}')
   # Detect any source change during compression before publishing a checkpoint.
   for entry in manifest:
    if hashlib.sha256(z.read(ROOT.name+'/'+entry['path'])).hexdigest()!=entry['sha256']:
     raise RuntimeError('Source changed while archiving: '+entry['path'])
  with temporary.open('rb') as f:os.fsync(f.fileno())
  os.replace(temporary,output)
 finally:temporary.unlink(missing_ok=True)
 return {'path':str(output),'bytes':output.stat().st_size,'sha256':sha(output),'files':len(manifest),'zip_crc_passed':True}


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT.parent);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 from tools.verify_finishing import verify_all
 verify_all()
 for s in SCENES.values():verify_render(ROOT/'renders'/s['id']/'hero/hero')
 files=[x for x in ROOT.rglob('*') if x.is_file()]
 sources=[x for x in files if source_selected(x)]
 displays=[x for x in files if (x.relative_to(ROOT).parts[0]=='renders' and len(x.relative_to(ROOT).parts)>=4 and x.relative_to(ROOT).parts[1] in SCENES and x.relative_to(ROOT).parts[2]=='hero' and x.suffix in ['.png','.json','.log','.txt'] and 'before_demodulation' not in x.name) or x.relative_to(ROOT).parts[0]=='references' or x.name in ['gallery.html','CYBR_SCENES_R2_Gallery.html','CYBR_SCENES_R2_Overview.jpg']]
 proof=[]
 for x in files:
  r=x.relative_to(ROOT)
  if len(r.parts)>=4 and r.parts[0]=='renders' and r.parts[1] in SCENES and r.parts[2]=='hero' and x.suffix in ['.pfm','.spectral','.guides','.samples','.json','.log','.txt']:
   proof.append(x)
  elif r.parts[0]=='geometry-r2' and x.name=='geometry-upgrade.json':proof.append(x)
  elif r.parts[0]=='build' and x.name.endswith('.build.json'):proof.append(x)
 result={'created_at':now(),'source':archive(a.output/'CYBR_SCENES_R2_Source.zip',sources)}
 atomic_json(ROOT/'evidence/delivery.json',result)
 print(json.dumps(result['source']),flush=True)
 result['renders']=archive(a.output/'CYBR_SCENES_R2_Renders.zip',displays);atomic_json(ROOT/'evidence/delivery.json',result);print(json.dumps(result['renders']),flush=True)
 result['raw_proof']=archive(a.output/'CYBR_SCENES_R2_Raw_Proof.zip',proof);atomic_json(ROOT/'evidence/delivery.json',result);print(json.dumps(result['raw_proof']),flush=True)

if __name__=='__main__':main()
