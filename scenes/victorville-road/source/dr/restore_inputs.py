"""Reconstruct exact authored input bytes from bounded publication parts.
No network or render operations. Conflicting existing bytes are never replaced.
"""
from pathlib import Path
import hashlib,json,os,tempfile
ROOT=Path(__file__).resolve().parent

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def inside(relative):
 p=ROOT/relative
 if not p.resolve().is_relative_to(ROOT):raise ValueError('Input path escapes publication root: '+relative)
 return p

def main():
 entries=json.loads((ROOT/'SPLIT_INPUTS.json').read_text())['inputs']
 for row in entries:
  target=inside(row['path'])
  if target.exists() or target.is_symlink():
   if target.is_symlink() or not target.is_file() or target.stat().st_size!=row['bytes'] or digest(target)!=row['sha256']:
    raise ValueError('Conflicting existing input; refusing overwrite: '+row['path'])
   print('Exact input already restored:',row['path']);continue
  for part in row['parts']:
   path=inside(part['path'])
   if not path.is_file() or path.stat().st_size!=part['bytes'] or digest(path)!=part['sha256']:
    raise ValueError('Missing or conflicting byte part: '+part['path'])
  target.parent.mkdir(parents=True,exist_ok=True)
  fd,tmp=tempfile.mkstemp(prefix='.'+target.name+'.',dir=target.parent)
  temp=Path(tmp)
  try:
   with os.fdopen(fd,'wb') as output:
    for part in row['parts']:
     with inside(part['path']).open('rb') as source:
      for chunk in iter(lambda:source.read(1024*1024),b''):output.write(chunk)
    output.flush();os.fsync(output.fileno())
   if temp.stat().st_size!=row['bytes'] or digest(temp)!=row['sha256']:
    raise ValueError('Reconstructed bytes fail source identity: '+row['path'])
   # Atomic link creates without clobbering a concurrently created destination.
   os.link(temp,target)
   print('Restored exact source input:',row['path'],row['sha256'])
  finally:
   temp.unlink(missing_ok=True)
 return 0
if __name__=='__main__':raise SystemExit(main())
