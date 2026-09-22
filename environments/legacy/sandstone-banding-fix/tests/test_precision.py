"""Execute isolated copies of the delivered GLSL, not CPU stand-ins.
Planar receivers isolate false self-shadowing; ramps isolate display quantization.
"""
from pathlib import Path
import json,base64,re,os,hashlib
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
JS=r'''(input)=>{
const canvas=document.createElement('canvas'), gl=canvas.getContext('webgl2',{antialias:false});
if(!gl||!gl.getExtension('EXT_color_buffer_float'))throw Error('Float render target unavailable');
gl.disable(gl.DITHER);
const vertex=`#version 300 es
precision highp float;out vec2 vUV;
void main(){vec2 p=gl_VertexID==0?vec2(-1,-1):gl_VertexID==1?vec2(3,-1):vec2(-1,3);vUV=p*.5+.5;gl_Position=vec4(p,0,1);}`;
function program(fragment){
 const compile=(t,s)=>{let x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(x));return x;};
 const p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,vertex));gl.attachShader(p,compile(gl.FRAGMENT_SHADER,'#version 300 es\n'+fragment));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return p;
}
function target(w,h,format){
 const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
 gl.texImage2D(gl.TEXTURE_2D,0,format,w,h,0,gl.RGBA,format===gl.RGBA8?gl.UNSIGNED_BYTE:gl.FLOAT,null);
 const f=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,f);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,t,0);if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('Invalid FBO');return {t,f,w,h,format};
}
function use(p,t){gl.useProgram(p);gl.bindFramebuffer(gl.FRAMEBUFFER,t.f);gl.viewport(0,0,t.w,t.h);}
function tex(p,name,t,unit){gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,t);gl.uniform1i(gl.getUniformLocation(p,name),unit);}
function draw(){gl.drawArrays(gl.TRIANGLES,0,3);if(gl.getError()!==gl.NO_ERROR)throw Error('Draw error');}
function bytes(array){let s='';const a=new Uint8Array(array.buffer);for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return btoa(s);}
function read(t,byte=false){gl.bindFramebuffer(gl.FRAMEBUFFER,t.f);let a=byte?new Uint8Array(t.w*t.h*4):new Float32Array(t.w*t.h*4);gl.readPixels(0,0,t.w,t.h,gl.RGBA,byte?gl.UNSIGNED_BYTE:gl.FLOAT,a);if(gl.getError())throw Error('Readback error');return bytes(a);}
const result={};
if(input.shadow){
 const size=256,data=new Float32Array(size*size*4);
 for(let y=0;y<size;y++)for(let x=0;x<size;x++){
  const wx=(x+.5)/size*2-1,wy=(y+.5)/size*2-1;
  const slope=input.edge?.35:2.5;const z=Math.min(1,Math.max(0,.5-(slope*wx+.15*wy)*.5))-(input.edge&&x<size/2?.30:0);
  data[(y*size+x)*4]=z;data[(y*size+x)*4+3]=1;
 }
 const dt=target(size,size,gl.RGBA32F);gl.bindTexture(gl.TEXTURE_2D,dt.t);gl.texSubImage2D(gl.TEXTURE_2D,0,0,0,size,size,gl.RGBA,gl.FLOAT,data);
 const p=program('precision highp float;precision highp int;'+input.shadow+`
in vec2 vUV;out vec4 outColor;uniform highp sampler2D testDepth;uniform vec3 testNormal;uniform float testSlope,testWidth;
void main(){vec2 xy=(vUV*2.-1.)*vec2(testWidth,.15);vec3 P=vec3(xy,testSlope*xy.x+.15*xy.y);
mat4 vp=mat4(1,0,0,0,0,1,0,0,0,0,-1,0,0,0,0,1);
float v=swShadow(testDepth,vp,vec3(2),P,testNormal,1.);outColor=vec4(v,v,v,1);}`);
 const out=target(1024,64,gl.RGBA32F);use(p,out);tex(p,'testDepth',dt.t,0);
 gl.uniformMatrix3fv(gl.getUniformLocation(p,'uSunViewRotation'),false,new Float32Array([1,0,0,0,1,0,0,0,1]));gl.uniform1f(gl.getUniformLocation(p,'uSunTexel'),1/size);
 gl.uniform3fv(gl.getUniformLocation(p,'testNormal'),new Float32Array(input.normal));gl.uniform1f(gl.getUniformLocation(p,'testSlope'),input.edge?.35:2.5);gl.uniform1f(gl.getUniformLocation(p,'testWidth'),input.edge?.02:.15);draw();result.shadow=read(out);
} else {
 const w=1024,h=256,cur=target(w,h,input.fixed?gl.RGBA32F:gl.RGBA16F),hist=[target(w,h,input.fixed?gl.RGBA32F:gl.RGBA16F),target(w,h,input.fixed?gl.RGBA32F:gl.RGBA16F)];
 const ramp=program('precision highp float;in vec2 vUV;out vec4 outColor;void main(){outColor=vec4(vec3(0.014+vUV.x*.012),1.0);}');
 use(ramp,cur);draw();
 const accum=program(input.accum);let index=0;
 for(let k=0;k<8;k++){
  use(accum,hist[1-index]);tex(accum,'uCurrent',cur.t,0);tex(accum,'uPrevious',hist[index].t,1);gl.uniform1f(gl.getUniformLocation(accum,'uSamples'),k);draw();index=1-index;
 }
 result.linear=read(hist[index]);
 const pres=program(input.present),dst=target(w,h,gl.RGBA8),ref=target(w,h,gl.RGBA32F);
 function present(t,dither){use(pres,t);tex(pres,'uImage',hist[index].t,0);gl.uniform3f(gl.getUniformLocation(pres,'uWhite'),1.099015594,.9783981442,.9230282903);gl.uniform1f(gl.getUniformLocation(pres,'uExposure'),2.5);gl.uniform1i(gl.getUniformLocation(pres,'uMode'),0);gl.uniform1i(gl.getUniformLocation(pres,'uDither'),dither);draw();}
 present(dst,input.fixed?1:0);result.display=read(dst,true);
 present(dst,input.fixed?1:0);result.repeat=read(dst,true);
 present(ref,0);result.encodedReference=read(ref);
}
const e=gl.getExtension('WEBGL_debug_renderer_info');result.renderer=gl.getParameter(e.UNMASKED_RENDERER_WEBGL);return result;
}'''
def fragments(q):
 return [x for x in re.findall(r'fragmentShader:`(.*?)`',q,re.S)][:2]
def run():
 out=ROOT/'evidence/precision_tests';out.mkdir(exist_ok=True)
 results={'result':'FAIL','scope':'Actual WebGL2 execution of copied runtime GLSL; synthetic ramp and geometric receiver, driver dithering disabled to isolate final shader.','shadow':{},'ramp':{}}
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=False,env={**os.environ,'DISPLAY':':94','LIBGL_ALWAYS_SOFTWARE':'1'},args=['--no-sandbox','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-gpu-watchdog'])
  page=browser.new_page()
  for variant in ['before','precision_only','after']:
   sh=(ROOT/variant/'material.glsl').read_text().split('struct SWScan')[0]
   for edge in [False,True]:
    normal=np.array([-(.35 if edge else 2.5),-.15,1.]);normal/=np.linalg.norm(normal)
    data=page.evaluate(JS,{'shadow':sh,'normal':normal.tolist(),'edge':edge})
    a=np.frombuffer(base64.b64decode(data['shadow']),dtype=np.float32).reshape(64,1024,4)[...,:3]
    assert np.isfinite(a).all()
    Image.fromarray((np.clip(a[::-1],0,1)*255+.5).astype(np.uint8)).save(out/f'{variant}_shadow_{edge}.png')
    r=a[:,:,0];metrics={'min':float(r.min()),'max':float(r.max()),'mean':float(r.mean()),'unique_visibility_values':len(np.unique(r)),'false_shadow_fraction':float(np.mean(r<.99)) if not edge else None}
    results['shadow'][variant+('_edge' if edge else '_plane')]=metrics
   acc,prs=fragments((ROOT/variant/'quality.js').read_text())
   data=page.evaluate(JS,{'shadow':None,'accum':acc,'present':prs,'fixed':variant!='before'})
   linear=np.frombuffer(base64.b64decode(data['linear']),dtype=np.float32).reshape(256,1024,4)
   display=np.frombuffer(base64.b64decode(data['display']),dtype=np.uint8).reshape(256,1024,4)[...,:3]
   ideal=.014+(np.arange(1024)+.5)/1024*.012
   c=np.tile(ideal[None,:,None],(256,1,3))*4/np.array([1.099015594,.9783981442,.9230282903])*2.5
   c=c*c/(c+.035);peak=c.max(2,keepdims=True);c*=(-np.expm1(-peak))/peak
   c=np.where(c<.0031308,c*12.92,1.055*np.power(c,1/2.4)-.055)
   mean=display.mean(0)/255;err=mean-c[0]
   results['ramp'][variant]={'linear_rmse':float(np.sqrt(np.mean((linear[:,:,0]-ideal)**2))), 'mean_column_error_srgb':float(np.sqrt(np.mean(err**2))), 'max_pixel_error_in_codes':float(np.max(np.abs(display.astype(float)-255*c))), 'stationary_output_identical':data['display']==data['repeat']}
   Image.fromarray(display[::-1]).save(out/f'{variant}_ramp.png')
   results['renderer']=data['renderer']
   print(variant,results['shadow'][variant+'_plane'],results['ramp'][variant],flush=True)
  browser.close()
 results['result']='PASS' if (results['shadow']['after_plane']['false_shadow_fraction']<.001 and results['shadow']['after_edge']['unique_visibility_values']>100 and results['ramp']['after']['linear_rmse']<1e-7 and results['ramp']['after']['stationary_output_identical']) else 'FAIL'
 (out/'report.json').write_text(json.dumps(results,indent=2));print(results['result'],flush=True)
if __name__=='__main__':run()
