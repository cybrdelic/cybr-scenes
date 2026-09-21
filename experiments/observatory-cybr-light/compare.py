#!/usr/bin/env python3
"""Build a matched display comparison from two completed native render runs.

Raw PFM films are never changed. Both views receive the same display transform
and optional non-neural geometry/variance filter; no upscaling or outlier removal.
Different material models mean this is not a ground-truth error benchmark.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.ndimage import gaussian_filter

LUMA=np.array([.2126,.7152,.0722],np.float32)

def read_pfm(path:Path):
    with path.open('rb') as f:
        if f.readline().strip()!=b'PF':raise ValueError('Expected RGB PFM: '+str(path))
        width,height=map(int,f.readline().split());scale=float(f.readline())
        data=np.frombuffer(f.read(),'<f4' if scale<0 else '>f4')
    if len(data)!=width*height*3:raise ValueError('Invalid PFM length')
    a=data.reshape(height,width,3)[::-1].copy()*abs(scale)
    if not np.isfinite(a).all():raise ValueError('Nonfinite PFM')
    return a

def display(a,white,exposure):
    x=np.maximum(a/np.asarray(white,np.float32)*exposure,0)
    x=np.clip(x*(2.51*x+.03)/(x*(2.43*x+.59)+.14),0,1)
    x=np.where(x<=.0031308,12.92*x,1.055*x**(1/2.4)-.055)
    return np.uint8(np.clip(x,0,1)*255+.5)

def guides(stem:Path,engine:str):
    if engine=='baseline':
        with Path(str(stem)+'.guides').open('rb') as f:
            w,h=struct.unpack('<II',f.read(8));g=np.frombuffer(f.read(),'<f4').reshape(h,w,9).copy()
        return g[:,:,:3],g[:,:,6],np.maximum(0,g[:,:,7])
    n=read_pfm(Path(str(stem)+'_normal.pfm'))*2-1
    d=read_pfm(Path(str(stem)+'_depth.pfm'))[:,:,0]
    n=np.where((d>0)[:,:,None],n,0)
    return n,d,read_pfm(Path(str(stem)+'_stderr.pfm'))[:,:,0]**2

def reconstruct(a,n,d,v,iterations=4):
    """Symmetric pairwise weights. No learned model, clamp, or peak replacement."""
    a=np.asarray(a,np.float32).copy();n=np.asarray(n,np.float32);d=np.asarray(d,np.float32)
    v=gaussian_filter(np.maximum(v,0).astype(np.float32),.7)
    n/=np.maximum(np.linalg.norm(n,axis=-1,keepdims=True),1e-20)
    h,w=d.shape;kernel=np.array([1,4,6,4,1],np.float32)
    for it in range(iterations):
        step=1<<it;pad=2*step;lum=np.maximum(a@LUMA,0);log=np.log1p(3*lum)
        padded=[np.pad(x,((pad,pad),(pad,pad))+((0,0),)*(x.ndim-2),mode='edge') for x in (a,n,d,v,log)]
        total=np.zeros_like(a);weights=np.zeros_like(d);varsum=np.zeros_like(v)
        for j in range(-2,3):
            for i in range(-2,3):
                sl=(slice(pad+j*step,pad+j*step+h),slice(pad+i*step,pad+i*step+w))
                c,nn,dd,vv,ll=[x[sl] for x in padded]
                surface=((d>0)==(dd>0))
                normal=np.where(d>0,np.exp(-64*np.maximum(0,1-np.sum(n*nn,axis=-1))),1)
                depth=np.exp(-np.abs(d-dd)/(.012+.003*step*np.maximum(d,dd)))
                mean_lum=(np.expm1(log)+np.expm1(ll))/6
                sigma=.035+4*np.sqrt(np.maximum(v+vv,0))*3/(1+3*mean_lum)
                color=np.exp(-np.abs(log-ll)/np.maximum(.04,sigma))
                weight=kernel[i+2]*kernel[j+2]*surface*normal*depth*color
                total+=weight[:,:,None]*c;weights+=weight;varsum+=weight*weight*vv
        a=total/np.maximum(weights[:,:,None],1e-20)
        v=np.maximum(varsum/np.maximum(weights*weights,1e-20),v*.10)
    return a

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def make_comparison(baseline:Path,light:Path,out:Path,original:Path|None=None,iterations=4):
    out.mkdir(parents=True,exist_ok=True)
    a=read_pfm(baseline.with_suffix('.pfm'));b=read_pfm(light.with_suffix('.pfm'))
    if a.shape!=b.shape:raise ValueError('Comparison requires matching native resolutions')
    h,w=a.shape[:2];ma=json.loads(baseline.with_suffix('.json').read_text());mb=json.loads(light.with_suffix('.json').read_text())
    if mb.get('renderer')!='CYBR LIGHT 0.2' or mb.get('invalid_path_samples',-1)!=0:raise ValueError('Missing successful native CYBR LIGHT record')
    white=ma['film_white_rgb'];exposure=ma['exposure'];records={}
    for name,stem,raw,engine in [('baseline',baseline,a,'baseline'),('cybr_light',light,b,'light')]:
        n,d,v=guides(stem,engine)
        if n.shape!=raw.shape or not all(np.isfinite(x).all() for x in (n,d,v)):raise ValueError('Invalid guide arrays')
        finished=reconstruct(raw,n,d,v,iterations)
        Image.fromarray(display(raw,white,exposure)).save(out/f'{name}_raw.png')
        Image.fromarray(display(finished,white,exposure)).save(out/f'{name}_filtered.png')
        records[name]={'native_width':w,'native_height':h,'raw_pfm_sha256':digest(stem.with_suffix('.pfm')),
                       'negative_channel_fraction':float(np.mean(raw<0)),'mean_linear_luminance':float(np.mean(raw@LUMA)),
                       'median_standard_error':float(np.median(np.sqrt(v))),'render_record':ma if engine=='baseline' else mb}
    try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',max(11,min(20,w//32)))
    except OSError:font=ImageFont.load_default()
    for mode in ('raw','filtered'):
        canvas=Image.new('RGB',(w*2,h+48),(17,20,24));draw=ImageDraw.Draw(canvas)
        for i,(name,label) in enumerate([('baseline','EXISTING RENDERER  /  MATCHED RERENDER'),('cybr_light','CYBR LIGHT  /  NATIVE ENGINE')]):
            canvas.paste(Image.open(out/f'{name}_{mode}.png'),(i*w,48))
            draw.text((i*w+12,12),label,font=font,fill=(230,230,230))
        canvas.save(out/f'comparison_{mode}.png')
    if original is not None:
        original_bytes=original.read_bytes();(out/'original_preserved.png').write_bytes(original_bytes)
        records['original_preserved_sha256']=digest(original)
    info={'scope':'Same source geometry and camera; native material/spectral/transport models differ. Not a ground-truth or equal-work benchmark.',
          'baseline':records['baseline'],'cybr_light':records['cybr_light'],
          'common_finish':{'exposure':exposure,'white_rgb':white,'iterations':iterations,'method':'Identical normal/depth/variance-guided a-trous filter on total linear radiance',
                           'neural':False,'upscaling':False,'outlier_replacement':False,'radiance_clamping':False,
                           'limitation':'Center-sampled first-surface guides do not follow internal refraction or match depth-of-field integration.'},
          'original_preserved_sha256':records.get('original_preserved_sha256')}
    (out/'comparison.json').write_text(json.dumps(info,indent=2)+'\n')
    files={p.name:base64.b64encode(p.read_bytes()).decode() for p in out.glob('*.png')}
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CYBR LIGHT / Observatory comparison</title>
<style>:root{color-scheme:dark;font-family:system-ui;background:#111418;color:#e2e5e8}body{margin:0;padding:24px}main{max-width:1600px;margin:auto}h1{font-size:30px}p{max-width:1000px;line-height:1.6;color:#b7bec8}button{padding:12px;margin:6px 8px 12px 0;background:#252c35;color:#fff;border:1px solid #687280;border-radius:5px;cursor:pointer}img{display:block;width:100%;height:auto}small{display:block;margin:20px 0}a{color:#b7d7ff}</style>
<main><h1>Observatory IV — two actual rendering pipelines</h1><p>The existing scene, renderer, and delivered image remain intact. The comparison below uses two fresh native renders at the same resolution and camera. CYBR LIGHT runs its own spectral volume-path integrator, not a renamed Observatory executable. Material models and sampling work differ.</p>
<button onclick="show('comparison_filtered.png')">Same filter on both</button><button onclick="show('comparison_raw.png')">Both unfiltered</button><button id="original" onclick="show('original_preserved.png')">Preserved original delivery</button><button onclick="downloadCurrent()">Download current image</button>
<img id="view" alt="Native renderer comparison"><p id="caption"></p><small>No image generation, upscaling, or raw radiance replacement. Filtering uses identical normal/depth/variance weights on both total-radiance films. It can soften detail, especially inside the refractive objects. Raw films and render records are retained separately.</small></main><script>
const files=FILES;let current='comparison_filtered.png';function show(name){current=name;document.getElementById('view').src='data:image/png;base64,'+files[name];document.getElementById('caption').textContent=name==='original_preserved.png'?'Original delivered image, unchanged. Different resolution and original finishing settings; not the matched benchmark.':(name.includes('raw')?'Matched camera and native dimensions. Neither side is denoised.':'Matched camera and native dimensions. Identical non-neural filtering and display transform on both sides.');}function downloadCurrent(){const a=document.createElement('a');a.href='data:image/png;base64,'+files[current];a.download=current;a.click();}if(!files['original_preserved.png'])document.getElementById('original').remove();show(current);</script></html>'''.replace('FILES',json.dumps(files,separators=(',',':')))
    (out/'comparison.html').write_text(html)
    return info

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--light',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--original',type=Path);p.add_argument('--iterations',type=int,default=4)
    a=p.parse_args()
    if not 0<=a.iterations<=7:p.error('Iterations must be between 0 and 7')
    make_comparison(a.baseline,a.light,a.out,a.original,a.iterations)
if __name__=='__main__':main()
