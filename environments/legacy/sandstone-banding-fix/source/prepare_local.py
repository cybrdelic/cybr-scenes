"""Unpack the supplied offline viewer for local, network-independent testing.
Never contacts GitHub or changes any vertex, index, lighting or photographic map.
"""
from pathlib import Path
import base64,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
import argparse
_parser=argparse.ArgumentParser(description=__doc__);_parser.add_argument('--input',type=Path,required=True)
INPUT=_parser.parse_args().input
s=INPUT.read_text();matches=list(re.finditer(r'<script([^>]*)>',s))
shared=ROOT/'shared';shared.mkdir(exist_ok=True)
part=[]
for m in matches:part.append(s[m.end():s.index('</script>',m.end())])
scene=json.loads(part[4]);detail=json.loads(part[5])
files={}
for i,m in enumerate(scene['meshes']):
 for key in ['position','normal','surface','giR','giG','giB','index']:
  if key not in m:continue
  raw=base64.b64decode(m[key]);name=f'{i:02}_{key}.z'
  (shared/name).write_bytes(raw)
  entry={'url':'../shared/'+name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  import zlib
  entry['decodedBytes']=len(zlib.decompress(raw))
  files[name]=entry;m[key]=entry
raw=base64.b64decode(scene['sky']['data']);(shared/'sky.z').write_bytes(raw)
scene['sky']['data']={'url':'../shared/sky.z','bytes':len(raw),'decodedBytes':len(zlib.decompress(raw)),'sha256':hashlib.sha256(raw).hexdigest()}
(shared/'scene.json').write_text(json.dumps(scene))
for tex in detail['manifest']['textures'].values():
 for level,maps in tex['levels'].items():
  for role,entry in maps.items():
   if not isinstance(entry,dict) or 'url' not in entry:continue
   old=entry['url']
   if old in detail['images']:
    name=Path(old).name;raw=base64.b64decode(detail['images'][old]);(shared/name).write_bytes(raw)
    assert hashlib.sha256(raw).hexdigest()==entry['sha256']
   entry['url']='../shared/'+Path(old).name
(shared/'detail_manifest.json').write_text(json.dumps(detail['manifest']))
(shared/'three.bundle.js').write_text(part[0]);(shared/'controls.js').write_text(part[1])
head=s[:matches[0].start()]
for folder in ['before','after']:
 d=ROOT/folder;d.mkdir(exist_ok=True)
 (d/'runtime.js').write_text(part[2]);(d/'quality.js').write_text(part[3]);(d/'material.glsl').write_text(detail['shader'])
 (d/'app.js').write_text(part[6][part[6].index('const SURFACE_VERTEX='):])
 (d/'index.html').write_text(head+'''<script src="../shared/three.bundle.js"></script><script src="../shared/controls.js"></script>
<script src="runtime.js"></script><script src="quality.js"></script><script>
(async()=>{try{const [scene,manifest,shader]=await Promise.all([
 fetch('../shared/scene.json').then(r=>r.json()),fetch('../shared/detail_manifest.json').then(r=>r.json()),fetch('material.glsl').then(r=>r.text())]);
 window.CYBR_BAKE=scene;window.SW_DETAIL_ASSETS={manifest,resolution:2048,shader};
 const a=document.createElement('script');a.src='app.js';document.body.append(a);
}catch(e){document.getElementById('error').hidden=false;document.getElementById('error').textContent=String(e);console.error(e);}})();</script></body></html>''')
(ROOT/'evidence'/'source_identity.json').write_text(json.dumps({'input':INPUT.name,'sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),'geometry':{k:scene['meta'][k] for k in ['triangles','vertex_count','source_mesh_sha256']},'shared_buffers':files,'note':'Extracted unchanged compressed buffers and image bytes from the supplied offline file.'},indent=2))
print('Ready:',ROOT,scene['meta']['triangles'],len(files),'buffers')
