"""Create a self-contained, offline, full-resolution comparison page."""
from pathlib import Path
import base64,hashlib,json,shutil
from PIL import Image
R=Path(__file__).resolve().parent;O=R.parent
f=R/'renders/Observatory_IV.png';u=R/'renders/Observatory_IV_unfiltered.png'
m=json.loads(f.with_suffix('.json').read_text())
a=base64.b64encode(f.read_bytes()).decode();b=base64.b64encode(u.read_bytes()).decode()
# These are native pixel crops, never another camera, synthesis, or upscaling.
im=Image.open(f)
w,h=im.size
box=(int(w*.235),int(h*.255),int(w*.64),int(h*.795))
im.crop(box).save(O/'CYBR_Observatory_IV_Instrument_Crop.png')
box2=(int(w*.48),int(h*.57),int(w*.965),int(h*.98))
im.crop(box2).save(O/'CYBR_Observatory_IV_Bench_Crop.png')
for source,dest in [(f,'CYBR_Observatory_IV.png'),(u,'CYBR_Observatory_IV_Unfiltered.png'),(R/'renders/Observatory_IV_raw.exr','CYBR_Observatory_IV_Raw.exr')]:shutil.copy2(source,O/dest)
html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CYBR Observatory IV — Render comparison</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#111214;color:#e8e8e8;font:16px/1.5 system-ui,sans-serif}header,footer{max-width:1100px;margin:auto;padding:24px}h1{font-size:28px;margin:0 0 8px}p{color:#b8bbc0;margin:6px 0 14px}nav{display:flex;gap:12px;flex-wrap:wrap}button,a{display:inline-block;padding:12px 18px;border:1px solid #60656b;background:#24262a;border-radius:6px;color:inherit;text-decoration:none;font:inherit;cursor:pointer}button[aria-pressed="true"]{background:#e8dfcc;color:#222}main{overflow:auto;text-align:center;background:#070809}img{display:block;width:100%;height:auto;margin:0 auto}main.native img{width:1800px;max-width:none}small{display:block;margin:14px 0;color:#a9aeb5}code{overflow-wrap:anywhere}footer{font-size:14px}#label{font-size:15px;margin:15px 0 0}</style>
<header><h1>Quiet Observatory IV</h1><p>Native CPU spectral render · 1800 × 1200 · actual 3D geometry</p><nav><button id="finished" aria-pressed="true">Finished</button><button id="raw" aria-pressed="false">Unfiltered</button><button id="zoom" aria-pressed="false">100% pixels</button><a id="save" download="CYBR_Observatory_IV.png">Save displayed PNG</a></nav><p id="label">Finished: non-neural component-separated reconstruction. No upscaling.</p></header>
<main id="viewer"><img id="image" alt="Rendered observatory with brass armillary and quartz optics on a walnut workbench beside a stone window"></main>
<footer><p>These are two versions of the <strong>same executed render</strong>, with identical camera, sample data and display transform. Unfiltered has no reconstruction. The separate raw EXR preserves scene-linear floating-point radiance.</p><p>No generative images, neural denoising, painted corrections, or path-radiance clamping. Reconstruction changes fine highlights and is not proof of Monte Carlo convergence.</p><p id="settings"></p><small>Offline page: no external scripts, models, network requests, tracking or remote image assets.</small></footer><script>
const finished='data:image/png;base64,__FINISHED__',raw='data:image/png;base64,__RAW__';const im=document.getElementById('image'),save=document.getElementById('save'),vf=document.getElementById('finished'),vr=document.getElementById('raw');function show(which){const f=which==='finished';im.src=f?finished:raw;save.href=im.src;save.download=f?'CYBR_Observatory_IV.png':'CYBR_Observatory_IV_Unfiltered.png';vf.setAttribute('aria-pressed',f);vr.setAttribute('aria-pressed',!f);document.getElementById('label').textContent=f?'Finished: non-neural component-separated reconstruction. No upscaling.':'Unfiltered: untouched renderer samples with only the shared display transform.'}vf.onclick=()=>show('finished');vr.onclick=()=>show('raw');document.getElementById('zoom').onclick=e=>{const on=document.getElementById('viewer').classList.toggle('native');e.target.setAttribute('aria-pressed',on);e.target.textContent=on?'Fit to screen':'100% pixels'};show('finished');document.getElementById('settings').textContent=__SETTINGS__;
</script></html>'''
settings=f"{m['triangles']:,} traced triangles · 16 wavelength bins · {m['sampling']['minimum_spp']}–{m['sampling']['maximum_spp']} camera samples per pixel, allocated by visible material · {m['sampling']['camera_samples']:,} total camera samples · {m['nonfinite_paths']} nonfinite paths."
html=html.replace('__FINISHED__',a).replace('__RAW__',b).replace('__SETTINGS__',json.dumps(settings))
p=O/'CYBR_Observatory_IV_Gallery.html';p.write_text(html);print(p,p.stat().st_size)
