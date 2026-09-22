#!/usr/bin/env python3
"""Apply the tested local-only banding correction to Sandstone Walk v0.5.
Usage: python apply_local_fix.py --input original.html --output corrected.html
No downloads, repository access, dependency installs or image synthesis.
The scene buffers and all photographic image payloads are preserved verbatim.
"""
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EXPECTED={
 '2775c4c32d80b52a768d7bd5bd95b16e51e482231046f7c793ab5ba7121b0dba':4096,
 '23c671a1218d52c56fabe65c159f0b6b4f48ced38bd82d76a3cdf2ce4b843a54':2048,
}
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def run(src:Path,dst:Path)->dict:
 raw=src.read_bytes();input_sha=sha(raw)
 if input_sha not in EXPECTED:raise ValueError('Input does not match either supplied v0.5 offline viewer. Refusing to patch an unknown version.')
 s=raw.decode();del raw
 tags=list(re.finditer(r'<script([^>]*)>',s))
 if len(tags)!=7:raise ValueError('Unexpected script layout.')
 blocks=[(m.end(),s.index('</script>',m.end())) for m in tags]
 old_scene=s[slice(*blocks[4])]
 scene_hash=sha(old_scene.encode());del old_scene
 detail=json.loads(s[slice(*blocks[5])]);maps_hash={k:sha(v.encode('ascii')) for k,v in detail['images'].items()}
 old_shader_sha=sha(detail['shader'].encode())
 if old_shader_sha!=detail['manifest']['shader_sha256']:raise ValueError('Original detail shader manifest is inconsistent.')
 replacements={}
 replacements[2]=(ROOT/'patch/runtime.js').read_text()
 replacements[3]=(ROOT/'patch/quality.js').read_text()
 detail['shader']=(ROOT/'patch/material.glsl').read_text()
 detail['manifest']['shader_sha256']=sha(detail['shader'].encode())
 detail['manifest']['local_banding_fix']={'revision':'local-1','original_shader_sha256':old_shader_sha,'geometry_changed':False,'image_payloads_changed':False}
 replacements[5]=json.dumps(detail,separators=(',',':'),ensure_ascii=True)
 original_app=s[slice(*blocks[6])]
 loader=original_app[:original_app.index('const SURFACE_VERTEX=')]
 replacements[6]=loader+(ROOT/'patch/app.js').read_text()
 del detail,original_app
 for idx in sorted(replacements,reverse=True):
  a,b=blocks[idx];s=s[:a]+replacements[idx]+s[b:]
 s=re.sub(r'<title>.*?</title>','<title>Sandstone Walk — Local banding fix</title>',s,count=1)
 # Verify the written payload after replacement rather than merely trusting patch intent.
 tags=list(re.finditer(r'<script([^>]*)>',s));blocks=[(m.end(),s.index('</script>',m.end())) for m in tags]
 assert sha(s[slice(*blocks[4])].encode())==scene_hash,'Scene payload changed'
 check=json.loads(s[slice(*blocks[5])]);newmaps={k:sha(v.encode('ascii')) for k,v in check['images'].items()}
 assert newmaps==maps_hash,'Photographic map payload changed'
 assert check['resolution']==EXPECTED[input_sha]
 dst.parent.mkdir(parents=True,exist_ok=True);encoded=s.encode();dst.write_bytes(encoded)
 report={'schema':'sandstone-local-banding-fix/1','input':src.name,'input_sha256':input_sha,'output':dst.name,'output_sha256':sha(encoded),'output_bytes':len(encoded),
  'map_resolution':check['resolution'],'scene_payload_sha256':scene_hash,'scene_payload_byte_identical':True,'all_photographic_map_payloads_identical':True,
  'map_payloads_checked':len(maps_hash),'geometry_vertices':2526592,'geometry_triangles':5029800,
  'changes':['Depth sampler precision explicitly highp','Compare depth at actual texel centres before bilinear PCF','Receiving slope from triangle plane with footprint-scaled normal bias','Fractional blocker search and fractional shadow visibility','RGBA32F current frame and both history targets','High-precision sky and HDR samplers','Static final-only achromatic triangular dither; unchanged tone transform','Memory-bounded native-resolution tiled 4K capture with derivative guards and global dither phase'],
  'not_changed':['Positions and indices','Baked spectral response data','Photographic maps','Material parallax and micro-shadowing','Walk/orbit controls','Exposure and tone transform'],
  'new_bake':False,'repo_accessed_by_this_patch':False}
 dst.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 if args.input.resolve()==args.output.resolve():parser.error('Choose a different output file; the original is preserved.')
 print(json.dumps(run(args.input,args.output),indent=2))
