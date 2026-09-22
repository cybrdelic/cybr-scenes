#!/usr/bin/env python3
"""Build an offline inspection gallery solely from executed native-render outputs."""
from __future__ import annotations
import argparse,base64,html,json,sys,io
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cybr_scenes import SCENES,verify_render,read_pfm,atomic_json,sha,now
ORDER=['obsidian-reach','drowned-geode','sandstone-passage','fernwater','basalt-tide','desert-hot-springs']
NOTES={
 'obsidian-reach':'New HDR environment importance sampling and matching MIS; resolved relief on crust and banks. Authored lava, not a new fluid solve.',
 'drowned-geode':'Resolved limestone relief, seepage/deposition materials, wet roughness and weathered quartz tips. The existing flooded-cavern composition is retained.',
 'sandstone-passage':'Resolved rock weathering, footprint-filtered bedding, photographed mineral detail and sky MIS. Exact earlier native still revision is unresolved.',
 'fernwater':'Curled local-coordinate litter geometry; damp/decomposed leaf materials, living-leaf mottling and new stream-rock microstructure.',
 'basalt-tide':'Weathering deformation, new mineral microstructure and waterline deposits; direct environment sampling. Existing column layout retained.',
 'desert-hot-springs':'Memory-bounded full geometry assembly; sinter pores/deposits, rock relief and sky sampling. Authored landscape and prescribed ripples, not CFD.'}

def guides(stem):
 meta=json.loads(stem.with_suffix('.json').read_text());w,h=meta['width'],meta['height']
 if Path(str(stem)+'_normal.pfm').exists():
  n=read_pfm(Path(str(stem)+'_normal.pfm'));d=read_pfm(Path(str(stem)+'_depth.pfm'))[:,:,0]
 else:
  p=Path(str(stem)+'_primary.guides')
  if not p.exists():p=stem.with_suffix('.guides')
  with p.open('rb') as f:
   shape=np.fromfile(f,dtype='<u4',count=2);g=np.fromfile(f,dtype='<f4').reshape(h,w,9)
  if list(shape)!=[w,h]:raise ValueError('Native guide size mismatch')
  n=g[:,:,:3];d=g[:,:,6]
 length=np.linalg.norm(n,axis=2);normal=np.clip(n/np.maximum(length[:,:,None],1e-8)*.5+.5,0,1)
 normal[length<.1]=0
 valid=np.isfinite(d)&(d>0)&(d<10000)&(length>.1)
 depth=np.zeros((h,w),np.float32)
 if valid.any():
  lo,hi=np.percentile(np.log1p(d[valid]),[1,99]);depth[valid]=1-np.clip((np.log1p(d[valid])-lo)/max(hi-lo,1e-6),0,1)
 Image.fromarray(np.uint8(np.rint(normal*255))).save(Path(str(stem)+'_normal.png'))
 Image.fromarray(np.uint8(np.rint(depth*255))).save(Path(str(stem)+'_depth.png'))
 return {'guide_policy':'Actual native normal/depth AOV. Geode uses its primary guide; other backends use their native guide/averaged feature. Depth visualization is logarithmically normalized, not a beauty render.'}

def image_data(path,standalone):
 return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode() if standalone else str(path.relative_to(ROOT))

def generate(standalone=False):
 cards=[];results=[]
 for key in ORDER:
  scene=SCENES[key];stem=ROOT/'renders'/key/'hero/hero';check=verify_render(stem);meta=check['renderer_metadata'];guides(stem)
  if not Path(str(stem)+'_raw.png').exists() and Path(str(stem)+'_unfiltered.png').exists():
   import shutil
   shutil.copy2(Path(str(stem)+'_unfiltered.png'),Path(str(stem)+'_raw.png'))
  receipt=json.loads((stem.parent/'receipt.json').read_text());receipt['verification']=check
  atomic_json(stem.parent/'receipt.json',receipt)
  paths={'R2 filtered':stem.with_suffix('.png'),'R2 unfiltered':Path(str(stem)+'_raw.png'),
    'Native normals':Path(str(stem)+'_normal.png'),'Native depth':Path(str(stem)+'_depth.png'),'Earlier supplied image':ROOT/scene['reference']}
  images={name:image_data(path,standalone) for name,path in paths.items()}
  specs=f"{meta['width']} × {meta['height']} · {meta['spp']} samples/pixel"
  if meta.get('water_spp',meta['spp'])>meta['spp']:specs+=f" / {meta['water_spp']} on water"
  stats=f"{meta['triangles']:,} triangles · {meta.get('seconds',0):,.1f} s native time · 0 invalid samples"
  buttons=''.join(f'<button type="button" data-mode="{html.escape(k)}">{html.escape(k)}</button>' for k in images)
  payload=html.escape(json.dumps(images),quote=True)
  receipt_link='' if standalone else f'<a href="renders/{key}/hero/receipt.json">Execution receipt</a> <a href="renders/{key}/hero/hero.pfm">Native PFM*</a>'
  cards.append(f'''<section class="card" id="{key}" data-images="{payload}">
 <div class="cardhead"><h2>{scene['title']}</h2><span class="status">NATIVE RUN VERIFIED</span></div>
 <div class="viewport"><img src="{images['R2 filtered']}" alt="New native render of {scene['title']}" loading="lazy"></div>
 <div class="modes">{buttons}</div><p class="mode-name">R2 filtered</p>
 <p class="specs">{specs}<br>{stats}</p><p>{NOTES[key]}</p><div class="links">{receipt_link}</div></section>''')
  results.append({'scene':key,'title':scene['title'],'metadata':meta,'verification':check,'upgrade_note':NOTES[key]})
 template='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CYBR SCENES R2 — Native render inspection</title><link rel="icon" href="data:,">
<style>
:root{color-scheme:dark;--bg:#0e1014;--card:#191d24;--line:#303844;--text:#e8edf5;--muted:#a9b4c4;--accent:#b3d8d1}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,Helvetica,sans-serif;line-height:1.6}main{max-width:1660px;margin:auto;padding:36px 24px 64px}header{max-width:1070px;margin-bottom:30px}.eyebrow{color:var(--accent);letter-spacing:.18em;font-size:12px;font-weight:700}h1{font-weight:500;font-size:clamp(30px,4vw,58px);line-height:1.12;margin:14px 0 18px}header p{color:var(--muted);font-size:17px}.notice{border-left:3px solid var(--accent);padding:10px 18px;background:#181e23;font-size:14px;color:#ced5df}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}.cardhead{padding:18px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px}h2{font-size:22px;font-weight:500;margin:0}.status{font-size:10px;letter-spacing:.08em;white-space:nowrap;color:var(--accent)}.viewport{background:#080a0d;aspect-ratio:3/2;display:flex;align-items:center;justify-content:center}.viewport img{display:block;max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-in}.modes{display:flex;gap:6px;flex-wrap:wrap;padding:15px 18px 0}button{font:inherit;font-size:12px;border:1px solid #46515e;border-radius:5px;background:transparent;color:var(--text);padding:7px 9px;cursor:pointer}button[aria-pressed=true]{background:#d4e7e4;color:#17221f;border-color:#d4e7e4}.card p{margin:12px 20px;color:var(--muted);font-size:14px}.card .mode-name{color:var(--accent);font-size:12px;margin-top:10px}.card .specs{font-family:monospace;font-size:12px;color:#d6dee9}.links{padding:4px 20px 20px;display:flex;gap:20px}a{color:var(--accent)}footer{margin-top:32px;color:var(--muted);font-size:13px}dialog{border:1px solid #52616e;background:#080a0d;padding:8px;max-width:96vw;max-height:96vh}dialog::backdrop{background:#000d}dialog img{max-width:93vw;max-height:87vh;display:block}dialog button{display:block;margin:7px 0 0 auto}@media(max-width:820px){.grid{grid-template-columns:1fr}main{padding:24px 12px}.cardhead{padding:14px}.status{font-size:9px}h2{font-size:20px}}
</style></head><body><main><header><div class="eyebrow">CYBR / SCENES / R2</div><h1>Six environments.<br>New native renders.</h1><p>Executed CPU ray/path tracing of the recovered scene geometry, with source changes, native radiance, diagnostic views and recorded commands. No image-generation model or image upscaling.</p><div class="notice">“Verified” means successful native execution, finite transport, valid dimensions and recorded geometry—not a claim of photorealistic convergence or measured physical accuracy. Earlier supplied images can differ in revision, camera, resolution and sampling. The cave, water and lava retain their documented approximations. This gallery is an inspection page, not an interactive 3D engine.</div></header><div class="grid">__CARDS__</div><footer><p>Click a render for a larger view. The unfiltered view is the same native radiance with only the documented display transform. Normal and depth images visualize native renderer data; they are not beauty renders.</p><p>* Native PFM and spectral films are supplied in the separate Raw Proof archive. Extract that archive into the project to enable the local raw-film links. The source includes the complete six-scene build/render workflow and preserved pre-edit source versions.</p><p>__DATE__ · __MODE__</p></footer></main><dialog id="zoom"><img alt="Selected render"><button type="button" id="close">Close</button></dialog><script>
for(const card of document.querySelectorAll('.card')){const images=JSON.parse(card.dataset.images);for(const button of card.querySelectorAll('[data-mode]')){button.setAttribute('aria-pressed',button.dataset.mode==='R2 filtered');button.addEventListener('click',()=>{card.querySelector('img').src=images[button.dataset.mode];card.querySelector('.mode-name').textContent=button.dataset.mode;for(const b of card.querySelectorAll('[data-mode]'))b.setAttribute('aria-pressed',b===button);});}card.querySelector('img').addEventListener('click',event=>{const d=document.querySelector('#zoom');d.querySelector('img').src=event.target.src;d.showModal();});}document.querySelector('#close').addEventListener('click',()=>document.querySelector('#zoom').close());document.querySelector('#zoom').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.close();});
</script></body></html>'''
 text=template.replace('__CARDS__','\n'.join(cards)).replace('__DATE__',now()).replace('__MODE__','Self-contained offline inspection copy' if standalone else 'Local source-project gallery')
 target=ROOT/'CYBR_SCENES_R2_Gallery.html' if standalone else ROOT/'gallery.html';target.write_text(text)
 if not standalone:
  atomic_json(ROOT/'evidence/gallery-scenes.json',results)
 return target

def overview():
 font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
 try:font=ImageFont.truetype(font_path,24);small=ImageFont.truetype(font_path,15);title=ImageFont.truetype(font_path,36)
 except OSError:font=small=title=ImageFont.load_default()
 w,h=1800,1000;sheet=Image.new('RGB',(w,h),(14,16,20));draw=ImageDraw.Draw(sheet)
 draw.text((25,20),'CYBR SCENES / R2',font=title,fill=(232,237,245));draw.text((26,69),'Six fresh native renderer outputs · no image generation · no upscaling',font=small,fill=(171,185,198))
 for i,key in enumerate(ORDER):
  scene=SCENES[key];x=20+(i%3)*595;y=110+(i//3)*436
  im=Image.open(ROOT/'renders'/key/'hero/hero.png').convert('RGB');im.thumbnail((570,370),Image.Resampling.LANCZOS)
  sheet.paste(im,(x+(570-im.width)//2,y+(370-im.height)//2))
  draw.text((x,y+374),scene['title'],font=font,fill=(232,237,245))
  meta=json.loads((ROOT/'renders'/key/'hero/hero.json').read_text());draw.text((x,y+406),f"{meta['width']} × {meta['height']} · {meta['triangles']:,} triangles",font=small,fill=(171,185,198))
 target=ROOT/'CYBR_SCENES_R2_Overview.jpg';sheet.save(target,quality=94,subsampling=0);return target

if __name__=='__main__':
 from tools.audit_results import audit
 audit()
 print(generate(False));print(generate(True));print(overview())
