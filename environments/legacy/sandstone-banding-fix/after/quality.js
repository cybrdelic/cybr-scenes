/* SPDX-License-Identifier: GPL-2.0-only
 * Camera-local progressive supersampling in linear HDR, explicit resolution
 * policy, and a static geometric sun-depth map. No old frames are reprojected.
 * Source triangles, positions, spectral sky and macro bounce buffers are intact.
 */
'use strict';
window.SandstoneQuality=class SandstoneQuality {
 constructor({renderer,scene,skyScene,camera,uniforms,skyUniforms,detail,bounds}){
  Object.assign(this,{renderer,scene,skyScene,camera,uniforms,skyUniforms,detail});
  this.limit=8;this.samples=0;this.draws=0;this.lastSceneTriangles=0;this.lastKey='';
  this.exporting=false;this.width=1;this.height=1;this.resolution='native';this.shadowSize=4096;
  this.maxPixels=8388608;this.elapsedDrawMs=0;this.cachedFrames=0;
  if(!renderer.extensions.has('EXT_color_buffer_float'))throw new Error('HDR detail rendering needs EXT_color_buffer_float. No unlabelled low-quality fallback is used.');
  this.screenScene=new THREE.Scene();this.screenCamera=new THREE.Camera();
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute([-1,-1,0,3,-1,0,-1,3,0],3));
  this.screenMesh=new THREE.Mesh(geometry);this.screenMesh.frustumCulled=false;this.screenScene.add(this.screenMesh);
  const vertex=`precision highp float; in vec3 position; out vec2 vUV; void main(){vUV=position.xy*.5+.5;gl_Position=vec4(position,1.0);}`;
  this.accumUniforms={uCurrent:{value:null},uPrevious:{value:null},uSamples:{value:0}};
  this.accumMaterial=new THREE.RawShaderMaterial({glslVersion:THREE.GLSL3,vertexShader:vertex,
   fragmentShader:`precision highp float;precision highp int;precision highp sampler2D;in vec2 vUV;uniform sampler2D uCurrent,uPrevious;uniform float uSamples;out vec4 outColor;
   void main(){vec3 c=texture(uCurrent,vUV).rgb;if(uSamples>0.0)c=mix(texture(uPrevious,vUV).rgb,c,1.0/(uSamples+1.0));outColor=vec4(c,1.0);}`,
   uniforms:this.accumUniforms,depthTest:false,depthWrite:false,toneMapped:false});
  this.presentUniforms={uDither:{value:1},uPixelOffset:{value:new THREE.Vector2(0,0)},uImage:{value:null},uWhite:uniforms.uWhite,uExposure:uniforms.uExposure,uMode:uniforms.uMode};
  this.presentMaterial=new THREE.RawShaderMaterial({glslVersion:THREE.GLSL3,vertexShader:vertex,
   fragmentShader:`precision highp float;precision highp int;precision highp sampler2D;in vec2 vUV;uniform sampler2D uImage;uniform vec3 uWhite;uniform float uExposure;uniform int uMode;uniform int uDither;uniform vec2 uPixelOffset;out vec4 outColor;
   vec3 encodeNative(vec3 rgb){vec3 a=max(rgb/uWhite*uExposure,vec3(0));a=a*a/(a+vec3(.035));float p=max(max(a.r,a.g),max(a.b,1e-7));a*=(1.0-exp(-p))/p;a=clamp(a,0.0,1.0);return mix(12.92*a,1.055*pow(a,vec3(1.0/2.4))-.055,step(vec3(.0031308),a));}
   // Stable, achromatic triangular dither: at most one 8-bit display step.
   // Never changes with frame index and never enters the accumulated radiance.
   uint swMixBits(uint v){v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;return v^(v>>16);}
   float swDisplayNoise(ivec2 p){uint a=swMixBits(uint(p.x)*0x9e3779b9u^uint(p.y)*0x85ebca6bu);uint b=swMixBits(a^0xc2b2ae35u);return (float(a>>8)+float(b>>8))*(1.0/16777216.0)-1.0;}
   void main(){
    vec3 c=texelFetch(uImage,ivec2(gl_FragCoord.xy),0).rgb;
    c=uMode>=3?c:encodeNative(c*4.0);
    if(uDither==1&&uMode<3)c+=vec3(swDisplayNoise(ivec2(gl_FragCoord.xy)+ivec2(uPixelOffset))/255.0);
    outColor=vec4(clamp(c,0.0,1.0),1.0);
   }`,
   uniforms:this.presentUniforms,depthTest:false,depthWrite:false,toneMapped:false});
  const rt=(depth)=>new THREE.WebGLRenderTarget(1,1,{format:THREE.RGBAFormat,type:THREE.FloatType,
   minFilter:THREE.NearestFilter,magFilter:THREE.NearestFilter,depthBuffer:depth,stencilBuffer:false,generateMipmaps:false});
  this.current=rt(true);this.history=[rt(false),rt(false)];this.historyIndex=0;
  // Probe the selected framebuffer format rather than silently dropping precision.
  const previousTarget=renderer.getRenderTarget();
  renderer.setRenderTarget(this.current);
  const gl=renderer.getContext();
  const framebufferStatus=gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  renderer.setRenderTarget(previousTarget);
  if(framebufferStatus!==gl.FRAMEBUFFER_COMPLETE)throw new Error('RGBA32F render targets are unavailable on this device.');
  this.projection=new THREE.Matrix4();this.vp=new THREE.Matrix4();
  this.detail.uniforms.uLinearOutput.value=1;this.skyUniforms.uLinearOutput=this.detail.uniforms.uLinearOutput;this.skyUniforms.uMode=uniforms.uMode;
  this.createSunMap(bounds);
 }
 createSunMap(bounds){
  const {renderer,scene}=this,center=bounds.getCenter(new THREE.Vector3()),radius=bounds.getSize(new THREE.Vector3()).length();
  const light=new THREE.OrthographicCamera(-1,1,1,-1,1,radius*5);light.up.set(0,0,1);
  light.position.copy(center).addScaledVector(this.uniforms.uSun.value,radius*2);light.lookAt(center);light.updateMatrixWorld(true);
  const lightBounds=new THREE.Box3();
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z])
   lightBounds.expandByPoint(new THREE.Vector3(x,y,z).applyMatrix4(light.matrixWorldInverse));
  light.left=lightBounds.min.x-.25;light.right=lightBounds.max.x+.25;light.bottom=lightBounds.min.y-.25;light.top=lightBounds.max.y+.25;
  light.near=Math.max(.1,-lightBounds.max.z-.5);light.far=-lightBounds.min.z+.5;light.updateProjectionMatrix();
  const size=Math.min(this.shadowSize,renderer.capabilities.maxTextureSize);
  this.shadowSize=size;
  const target=new THREE.WebGLRenderTarget(size,size,{minFilter:THREE.NearestFilter,magFilter:THREE.NearestFilter,depthBuffer:true,stencilBuffer:false});
  target.depthTexture=new THREE.DepthTexture(size,size,THREE.UnsignedIntType);target.depthTexture.format=THREE.DepthFormat;
  target.depthTexture.minFilter=target.depthTexture.magFilter=THREE.NearestFilter;
  const depth=new THREE.MeshDepthMaterial({depthPacking:THREE.BasicDepthPacking,side:THREE.DoubleSide});
  const previousTarget=renderer.getRenderTarget(),previousOverride=scene.overrideMaterial;
  try{
   scene.overrideMaterial=depth;renderer.setRenderTarget(target);renderer.clear();renderer.render(scene,light);
   this.shadowTriangles=renderer.info.render.triangles;
  }finally{scene.overrideMaterial=previousOverride;renderer.setRenderTarget(previousTarget);depth.dispose();}
  this.shadowTarget=target;this.shadowCamera=light;
  this.nearShadowTarget=target.clone();
  this.nearShadowTarget.depthTexture=new THREE.DepthTexture(size,size,THREE.UnsignedIntType);
  this.nearShadowTarget.depthTexture.format=THREE.DepthFormat;
  this.nearShadowTarget.depthTexture.minFilter=this.nearShadowTarget.depthTexture.magFilter=THREE.NearestFilter;
  this.nearShadowCamera=light.clone();this.nearShadowKey='';this.nearShadowDraws=0;
  Object.assign(this.uniforms,{
   uSunViewRotation:{value:new THREE.Matrix3().setFromMatrix4(light.matrixWorldInverse)},
   uNearSunDepth:{value:this.nearShadowTarget.depthTexture},uNearSunVP:{value:new THREE.Matrix4()},uNearSunExtent:{value:new THREE.Vector3(1,1,1)},
   uGeometricSun:{value:1},uSunDepth:{value:target.depthTexture},
   uSunVP:{value:new THREE.Matrix4().multiplyMatrices(light.projectionMatrix,light.matrixWorldInverse)},
   uSunExtent:{value:new THREE.Vector3(light.right-light.left,light.top-light.bottom,light.far-light.near)},uSunTexel:{value:1/size}});
 }
 updateNearShadow(){
  // Stable four-metre cells avoid rebuilding a 16M-texel depth map for every step.
  const x=Math.floor(this.camera.position.x/4)*4,y=Math.floor(this.camera.position.y/4)*4;
  const key=x+','+y;if(key===this.nearShadowKey)return;
  const light=this.nearShadowCamera,extent=new THREE.Box3();
  for(const px of [x-9,x+13])for(const py of [y-6,y+20])for(const pz of [-2,21])
   extent.expandByPoint(new THREE.Vector3(px,py,pz).applyMatrix4(light.matrixWorldInverse));
  const span=extent.getSize(new THREE.Vector3()),mid=extent.getCenter(new THREE.Vector3());
  const tx=span.x/this.shadowSize,ty=span.y/this.shadowSize;
  mid.x=Math.round(mid.x/tx)*tx;mid.y=Math.round(mid.y/ty)*ty;
  light.left=mid.x-span.x*.5;light.right=mid.x+span.x*.5;light.bottom=mid.y-span.y*.5;light.top=mid.y+span.y*.5;light.updateProjectionMatrix();
  const old=this.renderer.getRenderTarget(),override=this.scene.overrideMaterial;
  const material=new THREE.MeshDepthMaterial({depthPacking:THREE.BasicDepthPacking,side:THREE.DoubleSide});
  try{this.scene.overrideMaterial=material;this.renderer.setRenderTarget(this.nearShadowTarget);this.renderer.clear();this.renderer.render(this.scene,light);}
  finally{this.scene.overrideMaterial=override;this.renderer.setRenderTarget(old);material.dispose();}
  this.uniforms.uNearSunVP.value.multiplyMatrices(light.projectionMatrix,light.matrixWorldInverse);
  this.uniforms.uNearSunExtent.value.set(light.right-light.left,light.top-light.bottom,light.far-light.near);
  this.nearShadowKey=key;this.nearShadowDraws++;this.invalidate();
 }
 setResolution(value){
  if(!['native','ultra','1','.75'].includes(String(value)))throw new Error('Unknown pixel-resolution profile');
  this.resolution=String(value);this.resize(innerWidth,innerHeight);
 }
 resize(cssWidth,cssHeight){
  if(this.exporting)return;
  this.cssWidth=Math.max(1,cssWidth);this.cssHeight=Math.max(1,cssHeight);
  const native=Math.max(1,window.devicePixelRatio||1);
  const desired=this.resolution==='native'?native:this.resolution==='ultra'?native*1.5:Number(this.resolution);
  const max=this.renderer.capabilities.maxTextureSize;
  this.pixelRatio=Math.min(desired,Math.sqrt(this.maxPixels/(this.cssWidth*this.cssHeight)),max/this.cssWidth,max/this.cssHeight);
  this.requestedRatio=desired;this.renderer.setPixelRatio(this.pixelRatio);this.renderer.setSize(this.cssWidth,this.cssHeight,false);
  this.allocate(this.renderer.domElement.width,this.renderer.domElement.height);
 }
 allocate(width,height){
  this.width=width;this.height=height;
  this.current.setSize(width,height);for(const t of this.history)t.setSize(width,height);
  this.invalidate();
 }
 invalidate(){this.samples=0;this.lastKey='';}
 key(){
  const c=this.camera,u=this.uniforms,d=this.detail.uniforms;
  return [...c.position.toArray(),...c.quaternion.toArray(),c.fov,c.aspect,c.near,c.far,this.width,this.height,
   u.uMode.value,d.uDetail.value,d.uParallax.value,d.uMicroShadows.value,u.uGeometricSun.value].join(',');
 }
 halton(index,base){let value=0,f=1;for(;index>0;index=Math.floor(index/base)){f/=base;value+=f*(index%base);}return value;}
 render({force=false,outputTarget=null}={}){
  this.updateNearShadow();
  const start=performance.now(),key=this.key();
  if(key!==this.lastKey){this.samples=0;this.lastKey=key;}
  if(this.samples<this.limit||force){
   this.camera.updateMatrixWorld(true);this.projection.copy(this.camera.projectionMatrix);
   // The first moving-camera sample is centred. Only stationary refinement jitters.
   const k=this.samples,jx=k===0?0:this.halton(k,2)-.5,jy=k===0?0:this.halton(k,3)-.5;
   this.projection.elements[8]-=2*jx/this.width;this.projection.elements[9]-=2*jy/this.height;
   this.vp.multiplyMatrices(this.projection,this.camera.matrixWorldInverse);
   this.uniforms.uVP.value.copy(this.vp);this.skyUniforms.uInvVP.value.copy(this.vp).invert();
   this.renderer.setRenderTarget(this.current);this.renderer.clear();
   this.renderer.render(this.skyScene,this.camera);this.renderer.render(this.scene,this.camera);
   this.lastSceneTriangles=this.renderer.info.render.triangles;this.draws++;
   const destination=1-this.historyIndex;
   this.accumUniforms.uCurrent.value=this.current.texture;this.accumUniforms.uPrevious.value=this.history[this.historyIndex].texture;
   this.accumUniforms.uSamples.value=this.samples;this.screenMesh.material=this.accumMaterial;
   this.renderer.setRenderTarget(this.history[destination]);this.renderer.render(this.screenScene,this.screenCamera);
   this.historyIndex=destination;this.samples++;this.elapsedDrawMs=performance.now()-start;
  }else this.cachedFrames++;
  this.screenMesh.material=this.presentMaterial;this.presentUniforms.uImage.value=this.history[this.historyIndex].texture;
  this.renderer.setRenderTarget(outputTarget);this.renderer.render(this.screenScene,this.screenCamera);
 }
 async capture4K({download=true,samples=8,onProgress=()=>{},width=null,height=null,tileSize=1024}={}){
  if(this.exporting)throw new Error('A capture is already running');
  if(!Number.isInteger(samples)||samples<1||samples>32)throw new Error('Invalid capture sample count');
  if((width===null)!==(height===null))throw new Error('Specify both capture dimensions, or neither');
  if(width===null){const a=this.camera.aspect;width=a>=1?3840:Math.round(3840*a);height=a>=1?Math.round(3840/a):3840;}
  if(!Number.isInteger(width)||!Number.isInteger(height)||Math.min(width,height)<1||Math.max(width,height)>8192||width*height>16777216)throw new Error('Capture dimensions exceed the CPU image budget');
  if(!Number.isInteger(tileSize)||tileSize<128||tileSize>2048)throw new Error('Invalid capture tile size');
  const guard=2;
  tileSize=Math.min(tileSize,this.renderer.capabilities.maxTextureSize-2*guard);
  // Keep GPU allocations bounded: never allocate full-4K RGBA32F histories.
  // The assembled image is 8-bit only AFTER each tile's final tone/dither pass.
  const output=document.createElement('canvas');output.width=width;output.height=height;
  const ctx=output.getContext('2d',{alpha:false,colorSpace:'srgb'});
  if(!ctx)throw new Error('PNG assembly canvas is unavailable');
  const target=new THREE.WebGLRenderTarget(1,1,{format:THREE.RGBAFormat,type:THREE.UnsignedByteType,
   minFilter:THREE.NearestFilter,magFilter:THREE.NearestFilter,depthBuffer:false,stencilBuffer:false});
  target.texture.colorSpace=THREE.NoColorSpace;
  const previous={limit:this.limit,projection:this.camera.projectionMatrix.clone(),inverse:this.camera.projectionMatrixInverse.clone(),inert:document.body.inert};
  const columns=Math.ceil(width/tileSize),rows=Math.ceil(height/tileSize),total=columns*rows*samples;
  let completed=0,tiles=0,maxTilePixels=0;
  this.exporting=true;document.body.inert=true;
  try{
   this.limit=samples;
   for(let y=0;y<height;y+=tileSize)for(let x=0;x<width;x+=tileSize){
    const w=Math.min(tileSize,width-x),h=Math.min(tileSize,height-y),tw=w+2*guard,th=h+2*guard;
    // Off-axis sub-frustum of the ORIGINAL projection. No camera pose, FOV,
    // aspect or texture scale is changed. Guard pixels preserve derivatives.
    const crop=new THREE.Matrix4().set(width/tw,0,0,(width-2*x-w)/tw,
     0,height/th,0,(2*y+h-height)/th,0,0,1,0,0,0,0,1);
    this.camera.projectionMatrix.multiplyMatrices(crop,previous.projection);
    this.camera.projectionMatrixInverse.copy(this.camera.projectionMatrix).invert();
    this.allocate(tw,th);target.setSize(tw,th);
    this.presentUniforms.uPixelOffset.value.set(x-guard,height-y-h-guard);
    for(let i=0;i<samples;i++){
     onProgress(completed,total);this.render({outputTarget:target});completed++;
     await new Promise(resolve=>setTimeout(resolve,0));
    }
    const pixels=new Uint8Array(tw*th*4);
    this.renderer.readRenderTargetPixels(target,0,0,tw,th,pixels);
    if(this.renderer.getContext().isContextLost())throw new Error('Graphics context lost during tiled capture');
    const tile=ctx.createImageData(w,h);
    for(let row=0;row<h;row++){
     const start=((th-guard-1-row)*tw+guard)*4;
     tile.data.set(pixels.subarray(start,start+w*4),row*w*4);
    }
    ctx.putImageData(tile,x,y);tiles++;maxTilePixels=Math.max(maxTilePixels,tw*th);
   }
   const blob=await new Promise((resolve,reject)=>output.toBlob(b=>b?resolve(b):reject(new Error('PNG encoder failed')),'image/png'));
   let sourceTriangles=0;this.scene.traverse(o=>{if(o.isMesh&&o.geometry.index)sourceTriangles+=o.geometry.index.count/3;});
   const report={width,height,samples,bytes:blob.size,sourceTriangles,upscaled:false,
    method:'Native-resolution off-axis tiled WebGL render; RGBA32F supersampling and lossless 8-bit tile assembly after tone mapping',
    tiles,tileSize,guardPixels:guard,maxTilePixels,maxColorTargetBytes:maxTilePixels*(3*16+4),
    ditherPhase:'Global output pixel coordinates; no noise discontinuity at tile boundaries'};
   if(download){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='Sandstone_Walk_BandingFixed_4K.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
   this.lastCapture=report;onProgress(completed,total);return {blob,report};
  }finally{
   this.renderer.setRenderTarget(null);target.dispose();output.width=1;output.height=1;
   this.camera.projectionMatrix.copy(previous.projection);this.camera.projectionMatrixInverse.copy(previous.inverse);
   this.presentUniforms.uPixelOffset.value.set(0,0);document.body.inert=previous.inert;
   this.exporting=false;this.limit=previous.limit;this.resize(this.cssWidth,this.cssHeight);
   if(!this.renderer.getContext().isContextLost())this.render();
  }
 }
 report(){return {drawingBuffer:[this.width,this.height],cssSize:[this.cssWidth,this.cssHeight],pixelRatio:this.pixelRatio,
  requestedPixelRatio:this.requestedRatio,pixelBudget:this.maxPixels,capped:this.pixelRatio<this.requestedRatio-.001,
  samples:this.samples,sampleLimit:this.limit,sceneDraws:this.draws,lastSceneTriangles:this.lastSceneTriangles,
  shadowMapSize:this.shadowSize,shadowTriangles:this.shadowTriangles,nearShadowDraws:this.nearShadowDraws,linearHDR:true,linearHDRStorageScale:.25,renderTargetFormat:"RGBA32F",samplerPrecision:"highp",displayDither:"Static achromatic TPDF, final sRGB only",shadowFilter:"Fractional PCF with per-texel receiving-plane correction",
  latestCapture:this.lastCapture||null,history:'Stationary-camera sample averaging; reset on pose, projection or material changes; no reprojection'};}
 dispose(){this.current.dispose();for(const t of this.history)t.dispose();this.shadowTarget.dispose();this.nearShadowTarget.dispose();this.accumMaterial.dispose();this.presentMaterial.dispose();this.screenMesh.geometry.dispose();}
};
