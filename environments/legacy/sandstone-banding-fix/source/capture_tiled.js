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
