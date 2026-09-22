for(const [id,key] of [['sw-scene-data','CYBR_BAKE'],['sw-detail-data','SW_DETAIL_ASSETS']]){const node=document.getElementById(id);window[key]=JSON.parse(node.textContent);node.remove();}
;
;
;
;
'use strict';
(async function main(){
 const $=id=>document.getElementById(id);
 const status=$('status'),errorBox=$('error'),loading=$('loading');
 let failure=null;
 function fail(error){
  failure=error instanceof Error?error:new Error(String(error));
  loading.hidden=true;errorBox.hidden=false;errorBox.textContent='The viewer could not start.\n'+failure.message;
  console.error(failure);
 }
 try{
  if(THREE.REVISION!=='180')throw new Error('This scene is pinned to Three.js r180.');
  if(typeof DecompressionStream!=='function')throw new Error('This viewer needs a browser with DecompressionStream support.');
  const B=CYBR_BAKE;
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(50,1,.02,180);camera.up.set(0,0,1);
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,stencil:false,powerPreference:'high-performance',preserveDrawingBuffer:false});
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.NoToneMapping;renderer.autoClear=false;
  renderer.setPixelRatio(1);document.body.prepend(renderer.domElement);
  const canvas=renderer.domElement;canvas.tabIndex=0;canvas.setAttribute('aria-label','Interactive three-dimensional canyon');
  renderer.debug.checkShaderErrors=true;
  renderer.debug.onShaderError=(gl,program,vertex,fragment)=>{
   fail(new Error('Shader compilation/linking failed:\n'+gl.getProgramInfoLog(program)+'\n'+gl.getShaderInfoLog(vertex)+'\n'+gl.getShaderInfoLog(fragment)));
  };
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail(new Error('The graphics context was lost. Reload the viewer; exact geometry uses substantial GPU memory.'));});
  const sun=new THREE.Vector3(...B.meta.sun).normalize();
  const uniforms={uVP:{value:new THREE.Matrix4()},uEye:{value:camera.position},uSun:{value:sun},uSolar:{value:new THREE.Vector3(...B.meta.solar_rgb)},uWhite:{value:new THREE.Vector3(...B.meta.display_white_rgb)},uExposure:{value:B.meta.exposure},uMode:{value:0}};
  if(B.meta.material_schema!=='world-space-spectral-transfer/1')throw new Error('Missing per-pixel material transport data.');
  uniforms.uRGBToAnchors={value:new THREE.Matrix3().set(...B.meta.rgb_to_anchors.flat())};
  uniforms.uSolarResponse={value:new THREE.Matrix3().fromArray(B.meta.solar_anchor_response.flat())};
  const detail=await SandstoneDetail.create(renderer,{fragment:SURFACE_FRAGMENT,uniforms,status});
  const material=new THREE.RawShaderMaterial({glslVersion:THREE.GLSL3,vertexShader:SURFACE_VERTEX,fragmentShader:detail.fragmentShader,uniforms,side:THREE.DoubleSide,toneMapped:false});
  function base64(s){const raw=atob(s),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return bytes;}
  async function inflate(asset){
   if(typeof asset==='string')return await new Response(new Blob([base64(asset)]).stream().pipeThrough(new DecompressionStream('deflate'))).arrayBuffer();
   if(!asset||typeof asset.url!=='string')throw new Error('Invalid asset entry.');
   const response=await fetch(asset.url);
   if(!response.ok)throw new Error('Asset fetch failed: '+asset.url+' ('+response.status+')');
   const packed=await response.arrayBuffer();
   if(packed.byteLength!==asset.bytes)throw new Error('Truncated asset: '+asset.url);
   if(globalThis.crypto?.subtle){
    const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',packed));
    const hash=Array.from(digest,v=>v.toString(16).padStart(2,'0')).join('');
    if(hash!==asset.sha256)throw new Error('Asset hash mismatch: '+asset.url);
   }
   const decoded=await new Response(new Blob([packed]).stream().pipeThrough(new DecompressionStream('deflate'))).arrayBuffer();
   if(decoded.byteLength!==asset.decodedBytes)throw new Error('Decoded asset size mismatch: '+asset.url);
   return decoded;
  }
  async function attr(text,kind,items,expected){
   const bytes=await inflate(text);const Type=kind==='f32'?Float32Array:kind==='i16'?Int16Array:Uint16Array;
   const data=new Type(bytes);if(data.length!==items*expected)throw new Error('A packed mesh attribute has the wrong length.');
   if(kind==='f32')return new THREE.BufferAttribute(data,items);
   if(kind==='f16')return new THREE.Float16BufferAttribute(data,items);
   return new THREE.BufferAttribute(data,items,true);
  }
  function exactGridIndex(rows,cols,flip){
   const cells=(rows-1)*(cols-1),a=new Uint32Array(cells*6);let q=0;
   // This preserves the original source's face ordering as well as topology.
   for(let y=0;y<rows-1;y++)for(let x=0;x<cols-1;x++){
    const i=y*cols+x;
    if(flip){a[q++]=i+cols+1;a[q++]=i+1;a[q++]=i;}
    else{a[q++]=i;a[q++]=i+1;a[q++]=i+cols+1;}
   }
   for(let y=0;y<rows-1;y++)for(let x=0;x<cols-1;x++){
    const i=y*cols+x;
    if(flip){a[q++]=i+cols;a[q++]=i+cols+1;a[q++]=i;}
    else{a[q++]=i;a[q++]=i+cols+1;a[q++]=i+cols;}
   }
   return a;
  }
  let triangles=0,vertices=0;
  const geometry=[];
  for(let i=0;i<B.meshes.length;i++){
   const d=B.meshes[i];status.textContent=`Loading ${i+1}/${B.meshes.length}: ${d.name}`;
   await new Promise(resolve=>setTimeout(resolve,0));
   const g=new THREE.BufferGeometry();
   g.setAttribute('position',await attr(d.position,'f32',3,d.vertices));d.position=null;
   g.setAttribute('bakeNormal',await attr(d.normal,'i16',3,d.vertices));d.normal=null;
   for(const key of ['giR','giG','giB']){g.setAttribute(key,await attr(d[key],'f16',3,d.vertices));d[key]=null;}
   g.setAttribute('surface',await attr(d.surface,'u16',2,d.vertices));d.surface=null;
   const indices=d.kind==='grid'?exactGridIndex(d.rows,d.cols,d.flip):new Uint32Array(await inflate(d.index));d.index=null;
   if(indices.length!==d.triangles*3)throw new Error('Source topology count mismatch: '+d.name);
   g.setIndex(new THREE.BufferAttribute(indices,1));g.computeBoundingSphere();
   const mesh=new THREE.Mesh(g,material);mesh.name=d.name;scene.add(mesh);geometry.push(g);triangles+=d.triangles;vertices+=d.vertices;
  }
  if(triangles!==5029800||vertices!==2526592)throw new Error('Geometry integrity totals do not match the regenerated closed canyon.');
  const skyData=new Uint16Array(await inflate(B.sky.data));B.sky.data=null;
  if(skyData.length!==B.sky.width*B.sky.height*4)throw new Error('Invalid native sky data.');
  const skyTexture=new THREE.DataTexture(skyData,B.sky.width,B.sky.height,THREE.RGBAFormat,THREE.HalfFloatType);
  skyTexture.colorSpace=THREE.NoColorSpace;skyTexture.minFilter=THREE.LinearFilter;skyTexture.magFilter=THREE.LinearFilter;skyTexture.wrapS=THREE.RepeatWrapping;skyTexture.wrapT=THREE.ClampToEdgeWrapping;skyTexture.generateMipmaps=false;skyTexture.needsUpdate=true;
  const skyUniforms={uInvVP:{value:new THREE.Matrix4()},uEye:uniforms.uEye,uSun:uniforms.uSun,uSolar:uniforms.uSolar,uWhite:uniforms.uWhite,uExposure:uniforms.uExposure,uSky:{value:skyTexture}};
  const hdrSkyFragment=SKY_FRAGMENT.replace('uniform float uExposure;', 'uniform float uExposure; uniform int uLinearOutput; uniform int uMode;').replace('outColor=vec4(encodeNative(c),1.0);','outColor=vec4(uLinearOutput==1?(uMode>=3?encodeNative(c):c*.25):encodeNative(c),1.0);');
  const skyMat=new THREE.RawShaderMaterial({glslVersion:THREE.GLSL3,vertexShader:SKY_VERTEX,fragmentShader:hdrSkyFragment,uniforms:skyUniforms,depthTest:false,depthWrite:false,toneMapped:false});
  const skyGeom=new THREE.BufferGeometry();skyGeom.setAttribute('position',new THREE.Float32BufferAttribute([-1,-1,0,3,-1,0,-1,3,0],3));
  const skyScene=new THREE.Scene(),skyMesh=new THREE.Mesh(skyGeom,skyMat);skyMesh.frustumCulled=false;skyScene.add(skyMesh);
  let controls=null;
  const bounds=new THREE.Box3().setFromObject(scene);
  const quality=new SandstoneQuality({renderer,scene,skyScene,camera,uniforms,skyUniforms,detail,bounds});
  function resize(){
   if(quality.exporting)return;
   const w=Math.max(1,innerWidth),h=Math.max(1,innerHeight);
   quality.resize(w,h);camera.aspect=w/h;
   const nativeFov=2*Math.atan(Math.tan(B.meta.horizontalFov*Math.PI/360)/camera.aspect)*180/Math.PI;
   camera.fov=controls?.mode==='orbit'?55:Math.min(75,nativeFov);camera.updateProjectionMatrix();
  }
  controls=new SandstoneControls({camera,canvas,bounds,reference:B.meta,onModeChange:()=>resize()});
  $('mode').onchange=e=>{uniforms.uMode.value=Number(e.target.value);};
  $('exposure').oninput=e=>{uniforms.uExposure.value=Number(e.target.value);$('ev').textContent=uniforms.uExposure.value.toFixed(2);};
  $('resolution').onchange=e=>{quality.setResolution(e.target.value);resize();};
  $('photo-detail').onchange=e=>{detail.setEnabled(e.target.checked);quality.invalidate();};
  $('relief').onchange=e=>{detail.uniforms.uParallax.value=e.target.checked?1:0;detail.uniforms.uMicroShadows.value=e.target.checked?1:0;quality.invalidate();};
  $('capture4k').onclick=async()=>{
   controls.suspend();const button=$('capture4k');button.disabled=true;
   try{await quality.capture4K({onProgress:(n,total)=>{button.textContent='Rendering '+n+'/'+total;}});}
   catch(e){console.warn(e);button.title=e.message;}
   finally{button.disabled=false;button.textContent='Capture 4K PNG';resize();}
  };
  $('hide').textContent=controls.touch?'Settings':'Interface';
  $('hide').setAttribute('aria-expanded','false');
  $('hide').onclick=()=>{
   controls.clearInput();
   if(controls.touch){const open=document.body.classList.toggle('settings-open');if(open)controls.stopTour();$('hide').setAttribute('aria-expanded',String(open));}
   else $('hud').classList.toggle('compact');
  };
  addEventListener('resize',resize);resize();
  camera.updateMatrixWorld(true);uniforms.uVP.value.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);skyUniforms.uInvVP.value.copy(uniforms.uVP.value).invert();
  renderer.compile(scene,camera);renderer.compile(skyScene,camera);
  if(failure)throw failure;
  loading.hidden=true;
  let last=performance.now(),frames=0,mark=last;
  function frame(now){
   if(failure)return;
   const dt=Math.min(.05,(now-last)/1000);last=now;
   if(quality.exporting){requestAnimationFrame(frame);return;}
   controls.update(dt);
   camera.updateMatrixWorld(true);uniforms.uVP.value.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);skyUniforms.uInvVP.value.copy(uniforms.uVP.value).invert();
   quality.render();
   frames++;if(now-mark>1000){$('stats').textContent=`${quality.width}×${quality.height} · ${detail.resolution}² maps · ${quality.samples}/${quality.limit} AA · ${quality.report().capped?'pixel budget cap':'native-quality'} · ${triangles.toLocaleString()} tris`;frames=0;mark=now;}
   requestAnimationFrame(frame);
  }
  // Read-only inspection hook plus explicit test controls; no screenshots supply lighting.
  window.CYBR_RECOVERY={renderer,scene,camera,material,detail,quality,meta:B.meta,controls,setReference:()=>controls.setReference(),setMode:value=>{uniforms.uMode.value=Number(value);$('mode').value=String(value);},setPose:(eye,target)=>controls.setPose(eye,target),setNavigationMode:mode=>controls.setNavigationMode(mode),geometry};
  requestAnimationFrame(frame);
 }catch(error){fail(error);}
})();
