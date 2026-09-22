"""Local banding correction. No network, repository writes or geometry edits."""
from pathlib import Path
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source';before=ROOT/'before';after=ROOT/'after'
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('Nonunique patch anchor: '+a[:120])
 return s.replace(a,b,1)
shader=(before/'material.glsl').read_text()
a=shader.index('float swShadow(');b=shader.index('float swSunVisibility(',a)
shader=shader[:a]+(SRC/'shadow_fix.glsl').read_text()+shader[b:]
shader=shader.replace('uniform sampler2D','uniform highp sampler2D')
shader=shader.replace('swScanPlane(sampler2D colorMap, sampler2D dataMap','swScanPlane(highp sampler2D colorMap, highp sampler2D dataMap')
shader=shader.replace('swScanMaterial(sampler2D colorMap, sampler2D dataMap','swScanMaterial(highp sampler2D colorMap, highp sampler2D dataMap')
(after/'material.glsl').write_text(shader)
runtime=(before/'runtime.js').read_text()
runtime=once(runtime,'swSunVisibility(vWorld,geometric,','swSunVisibility(vWorld,Ng,')
(after/'runtime.js').write_text(runtime)
q=(before/'quality.js').read_text()
q=q.replace('precision highp float;in vec2','precision highp float;precision highp int;precision highp sampler2D;in vec2')
q=once(q,'type:THREE.HalfFloatType','type:THREE.FloatType')
q=once(q,'this.presentUniforms={uImage:{value:null},','this.presentUniforms={uDither:{value:1},uImage:{value:null},')
q=once(q,'uniform float uExposure;uniform int uMode;out vec4 outColor;', 'uniform float uExposure;uniform int uMode;uniform int uDither;out vec4 outColor;')
old='void main(){vec3 c=texture(uImage,vUV).rgb;outColor=vec4(uMode>=3?c:encodeNative(c*4.0),1.0);}'
new='''// Stable, achromatic triangular dither: at most one 8-bit display step.
   // Never changes with frame index and never enters the accumulated radiance.
   uint swMixBits(uint v){v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;return v^(v>>16);}
   float swDisplayNoise(ivec2 p){uint a=swMixBits(uint(p.x)*0x9e3779b9u^uint(p.y)*0x85ebca6bu);uint b=swMixBits(a^0xc2b2ae35u);return (float(a>>8)+float(b>>8))*(1.0/16777216.0)-1.0;}
   void main(){
    vec3 c=texelFetch(uImage,ivec2(gl_FragCoord.xy),0).rgb;
    c=uMode>=3?c:encodeNative(c*4.0);
    if(uDither==1&&uMode<3)c+=vec3(swDisplayNoise(ivec2(gl_FragCoord.xy))/255.0);
    outColor=vec4(clamp(c,0.0,1.0),1.0);
   }'''
q=once(q,old,new)
q=once(q,'linearHDR:true,linearHDRStorageScale:.25,','linearHDR:true,linearHDRStorageScale:.25,renderTargetFormat:"RGBA32F",samplerPrecision:"highp",displayDither:"Static achromatic TPDF, final sRGB only",shadowFilter:"Fractional PCF with per-texel receiving-plane correction",')
q=once(q,'this.current=rt(true);this.history=[rt(false),rt(false)];this.historyIndex=0;', '''this.current=rt(true);this.history=[rt(false),rt(false)];this.historyIndex=0;
  // Probe the selected framebuffer format rather than silently dropping precision.
  const previousTarget=renderer.getRenderTarget();
  renderer.setRenderTarget(this.current);
  const gl=renderer.getContext();
  const framebufferStatus=gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  renderer.setRenderTarget(previousTarget);
  if(framebufferStatus!==gl.FRAMEBUFFER_COMPLETE)throw new Error('RGBA32F render targets are unavailable on this device.');''')
q=once(q,'uDither:{value:1},uImage:', 'uDither:{value:1},uPixelOffset:{value:new THREE.Vector2(0,0)},uImage:')
q=once(q,'uniform int uDither;out vec4 outColor;', 'uniform int uDither;uniform vec2 uPixelOffset;out vec4 outColor;')
q=once(q,'swDisplayNoise(ivec2(gl_FragCoord.xy))/255.0','swDisplayNoise(ivec2(gl_FragCoord.xy)+ivec2(uPixelOffset))/255.0')
q=once(q,'render({force=false}={})','render({force=false,outputTarget=null}={})')
q=once(q,'this.renderer.setRenderTarget(null);this.renderer.render(this.screenScene,this.screenCamera);','this.renderer.setRenderTarget(outputTarget);this.renderer.render(this.screenScene,this.screenCamera);')
a=q.index(' async capture4K(');b=q.index(' report(){',a)
q=q[:a]+(SRC/'capture_tiled.js').read_text()+q[b:]
(after/'quality.js').write_text(q)
app=(before/'app.js').read_text()
m=re.search('const SKY_FRAGMENT=',app);oldSky,n=json.JSONDecoder().raw_decode(app[m.end():])
newSky=oldSky.replace('precision highp float;','precision highp float;\nprecision highp sampler2D;',1)
app=app[:m.end()]+json.dumps(newSky,ensure_ascii=False)+app[m.end()+n:]
(after/'app.js').write_text(app)
print('Patched shadow comparisons, sampler precision, RGBA32F and final-only dither.')
