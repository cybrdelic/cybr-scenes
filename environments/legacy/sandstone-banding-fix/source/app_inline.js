for(const [id,key] of [['sw-scene-data','CYBR_BAKE'],['sw-detail-data','SW_DETAIL_ASSETS']]){const node=document.getElementById(id);window[key]=JSON.parse(node.textContent);node.remove();}
const SURFACE_VERTEX="precision highp float;\nuniform mat4 uVP;\nin vec3 position;\nin vec3 bakeNormal;\nin vec3 giR;\nin vec3 giG;\nin vec3 giB;\nin vec2 surface;\nout vec3 vWorld;\nout vec3 vNormal;\nout vec3 vGiR;\nout vec3 vGiG;\nout vec3 vGiB;\nout vec2 vSurface;\nvoid main(){\n vWorld=position;vNormal=bakeNormal;\n vGiR=giR;vGiG=giG;vGiB=giB;vSurface=surface;\n gl_Position=uVP*vec4(position,1.0);\n}\n";
const SURFACE_FRAGMENT="precision highp float;\nprecision highp int;\nuniform vec3 uEye;\nuniform vec3 uSun;\nuniform vec3 uSolar;\nuniform vec3 uWhite;\nuniform float uExposure;\nuniform int uMode;\nuniform mat3 uRGBToAnchors;\nuniform mat3 uSolarResponse;\nin vec3 vWorld;\nin vec3 vNormal;\nin vec3 vGiR;\nin vec3 vGiG;\nin vec3 vGiB;\nin vec2 vSurface;\nout vec4 outColor;\nconst float PI=3.141592653589793;\n// SPDX-License-Identifier: GPL-2.0-only\n// Shared GLSL / C++ material field. P is in metres, N is a GEOMETRIC normal.\n// All stochastic coordinates are isotropic 3D. No UVs, chart indices, normal-\n// dependent projection or camera-space coordinates enter color/height.\n// Footprint controls bandwidth only; it never changes the feature locations.\nstruct SWNoise { float value; vec3 gradient; };\nstruct SWMaterial { vec3 color; vec3 normal; float rough; };\nuint swHash(int x, int y, int z) {\n    uint h = uint(x)*0x8da6b343u ^ uint(y)*0xd8163841u ^ uint(z)*0xcb1ab31fu ^ 0x9e3779b9u;\n    h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;\n    return h;\n}\nfloat swSaturate(float x) { return min(1.0,max(0.0,x)); }\nfloat swSmooth(float a,float b,float x) { float t=swSaturate((x-a)/(b-a)); return t*t*(3.0-2.0*t); }\nSWNoise swNoise(vec3 p) {\n    int ix=int(floor(p.x)), iy=int(floor(p.y)), iz=int(floor(p.z));\n    vec3 f=p-vec3(float(ix),float(iy),float(iz));\n    vec3 t=f*f*f*(f*(f*6.0-vec3(15.0))+vec3(10.0));\n    vec3 dt=30.0*f*f*(f-vec3(1.0))*(f-vec3(1.0));\n    SWNoise n; n.value=0.0; n.gradient=vec3(0.0);\n    for(int a=0;a<2;a++) for(int b=0;b<2;b++) for(int c=0;c<2;c++) {\n        float v=float(swHash(ix+a,iy+b,iz+c)>>8)*(1.0/8388608.0)-1.0;\n        float x=a==1?t.x:1.0-t.x, y=b==1?t.y:1.0-t.y, z=c==1?t.z:1.0-t.z;\n        float dx=a==1?dt.x:-dt.x, dy=b==1?dt.y:-dt.y, dz=c==1?dt.z:-dt.z;\n        n.value+=v*x*y*z;\n        n.gradient+=v*vec3(dx*y*z,x*dy*z,x*y*dz);\n    }\n    return n;\n}\n// Fade unresolved octaves to their analytic zero mean. The conservative largest\n// singular screen footprint is provided by the fragment shader. The path tracer\n// supplies its native ray footprint. Derivatives are never evaluated in branches.\nSWNoise swBand(vec3 p, float frequency, float footprint, vec3 offset) {\n    float weight=1.0-swSmooth(0.20,0.65,frequency*footprint);\n    SWNoise n; n.value=0.0; n.gradient=vec3(0.0);\n    if(weight>0.00001) {\n        // A fixed orthonormal rotation avoids aligning the value-noise lattice\n        // with horizontal/vertical rock faces. It changes no metric scale.\n        vec3 q=vec3(.8*p.y+.6*p.z,-.8*p.x+.36*p.y-.48*p.z,-.6*p.x-.48*p.y+.64*p.z);\n        n=swNoise(q*frequency+offset);\n        vec3 gradient=n.gradient;\n        n.gradient=vec3(-.8*gradient.y-.6*gradient.z,\n            .8*gradient.x+.36*gradient.y-.48*gradient.z,\n            .6*gradient.x-.48*gradient.y+.64*gradient.z);\n        n.value*=weight; n.gradient*=weight*frequency;\n    }\n    return n;\n}\nSWMaterial swMaterial(vec3 p,vec3 geometric,int family,float footprint) {\n    vec3 n=normalize(geometric);\n    SWNoise broad=swBand(p,.37,footprint,vec3(13.1,-8.4,2.3));\n    SWNoise mottled=swBand(p,1.65,footprint,vec3(-17.2,3.8,29.1));\n    SWNoise broken=swBand(p,5.8,footprint,vec3(4.9,27.7,-11.8));\n    SWNoise pore=swBand(p,23.0,footprint,vec3(-5.7,-14.2,35.6));\n    SWNoise grain=swBand(p,92.0,footprint,vec3(31.2,-3.1,7.6));\n    SWNoise fine=swBand(p,368.0,footprint,vec3(-12.7,51.2,16.5));\n    float macro=.65*broad.value+.25*mottled.value+.10*broken.value;\n    float oxidation=swSmooth(-.04,.28,.55*broad.value+.35*mottled.value+.22*broken.value);\n    float abrasion=swSmooth(-.04,.42,broken.value*.7+pore.value*.22);\n    SWMaterial m;\n    if(family==0 || family==4) {\n        // Alluvial sediment: the same metre scale on level and inclined ground.\n        m.color=mix(vec3(.282,.200,.132),vec3(.417,.314,.216),.56+.30*macro);\n        m.color*=1.0+.10*broken.value+.12*pore.value+.20*grain.value+.10*fine.value;\n        m.rough=.92+.025*broken.value;\n    } else {\n        m.color=mix(vec3(.245,.134,.063),vec3(.475,.305,.167),.61+.45*macro);\n        float varnish=oxidation*(1.0-.70*abrasion);\n        // Mottled, finite patches; no p.z*.12 vertical smearing or per-wall axes.\n        m.color=mix(m.color,vec3(.108,.073,.045),.58*varnish);\n        m.color*=1.0+.16*broken.value+.12*pore.value+.21*grain.value+.07*fine.value;\n        if(family==2 || family==14) m.color=mix(m.color,vec3(.362,.243,.143),.20);\n        m.rough=.84-.075*varnish+.020*pore.value;\n    }\n    vec3 slope=broken.gradient*.0035+pore.gradient*.0025+grain.gradient*.00085+fine.gradient*.00012;\n    if(family==0 || family==4) slope*=1.12;\n    // True scalar-height gradient projected into the tangent plane. This avoids\n    // tangent handedness/projection seams and cannot rotate with the camera.\n    slope=slope-n*dot(n,slope);\n    float magnitude=length(slope);\n    slope*=min(1.0,.22/max(magnitude,.000001));\n    m.normal=normalize(n-slope);\n    m.color=clamp(m.color,vec3(.008),vec3(.82));\n    m.rough=clamp(m.rough,.65,.98);\n    return m;\n}\n\nfloat fresnel(float c){\n const float eta=1.49;\n float st2=(1.0-c*c)/(eta*eta),ct=sqrt(max(0.0,1.0-st2));\n float rs=(c-eta*ct)/(c+eta*ct),rp=(eta*c-ct)/(eta*c+ct);\n return .5*(rs*rs+rp*rp);\n}\nfloat ggxD(float nh,float a){float a2=a*a;float d=nh*nh*(a2-1.0)+1.0;return a2/(PI*d*d);}\nfloat smithG1(float c,float a){return c>0.0?2.0*c/(c+sqrt(a*a+(1.0-a*a)*c*c)):0.0;}\nvec3 encodeNative(vec3 rgb){\n vec3 a=max(rgb/uWhite*uExposure,vec3(0.0));\n a=a*a/(a+vec3(.035));float peak=max(max(a.r,a.g),max(a.b,.0000001));\n a*=(1.0-exp(-peak))/peak;\n a=clamp(a,0.0,1.0);\n return mix(12.92*a,1.055*pow(a,vec3(1.0/2.4))-.055,step(vec3(.0031308),a));\n}\nfloat screenFootprint(vec3 dx,vec3 dy){\n float a=dot(dx,dx),b=dot(dx,dy),c=dot(dy,dy);\n return sqrt(max(.5*(a+c+sqrt(max(0.0,(a-c)*(a-c)+4.0*b*b))),1e-12));\n}\nvec3 encodeAlbedo(vec3 a){return mix(12.92*a,1.055*pow(max(a,0.0),vec3(1.0/2.4))-.055,step(vec3(.0031308),a));}\nvoid main(){\n vec3 dx=dFdx(vWorld),dy=dFdy(vWorld);\n float footprint=screenFootprint(dx,dy);\n vec3 geometric=normalize(vNormal),V=normalize(uEye-vWorld),L=uSun;\n vec3 Ng=normalize(cross(dx,dy));\n if(dot(Ng,V)<0.0)Ng=-Ng;\n if(dot(geometric,Ng)<0.0)geometric=-geometric;\n if(dot(geometric,Ng)<.1||dot(geometric,V)<.01)geometric=Ng;\n int family=int(floor(vSurface.y*255.0+.5));\n SWMaterial material=swMaterial(vWorld,geometric,family,footprint);\n vec3 N=material.normal;\n if(dot(N,Ng)<.1||dot(N,V)<.01)N=geometric;\n float nv=max(dot(N,V),.0001),nl=max(dot(N,L),0.0);\n float rough=material.rough,visibility=clamp(vSurface.x,0.0,1.0);\n vec3 anchors=clamp(uRGBToAnchors*material.color,vec3(0.0),vec3(.985));\n vec3 H=normalize(V+L);float fr=fresnel(clamp(dot(V,H),0.0,1.0));\n float s2=pow(rough*.52,2.0),A=1.0-s2/(2.0*(s2+.33)),B=.45*s2/(s2+.09);\n float vi=sqrt(max(0.0,1.0-nv*nv)),li=sqrt(max(0.0,1.0-nl*nl));\n float cosPhi=vi*li>.00000001?max(0.0,(dot(V,L)-nv*nl)/(vi*li)):0.0;\n float oren=A+B*cosPhi*max(vi,li)*min(vi/max(nv,.00001),li/max(nl,.00001));\n float alpha=max(.018,rough*rough);\n vec3 direct=(uSolarResponse*anchors)*(1.0-fr)*oren*nl*visibility;\n if(nl>0.0)direct+=uSolar*(visibility*fr*ggxD(max(dot(N,H),0.0),alpha)*smithG1(nv,alpha)*smithG1(nl,alpha)/(4.0*nv));\n const float F0=(.49*.49)/(2.49*2.49);\n vec3 indirect=max((vGiR*anchors.x+vGiG*anchors.y+vGiB*anchors.z)*((1.0-F0)*A),0.0);\n vec3 radiance=direct+indirect;\n if(uMode==1)radiance=direct;\n else if(uMode==2)radiance=indirect;\n else if(uMode==3){outColor=vec4(N*.5+.5,1.0);return;}\n else if(uMode==4){outColor=vec4(vec3(visibility),1.0);return;}\n else if(uMode==5){outColor=vec4(encodeAlbedo(material.color),1.0);return;}\n else if(uMode==6){\n  // 25-cm volumetric checker: no UVs or chart-dependent coordinates.\n  vec3 q=vWorld*4.0,w=max(fwidth(q),vec3(.0001));\n  vec3 integral=2.0*(abs(fract((q-.5*w)*.5)-.5)-abs(fract((q+.5*w)*.5)-.5))/w;\n  float pattern=.5-.5*integral.x*integral.y*integral.z;\n  outColor=vec4(mix(vec3(.15),vec3(.85),pattern),1.0);return;\n }\n else if(uMode==7){outColor=vec4(vec3(rough),1.0);return;}\n else if(uMode==8){outColor=vec4(geometric*.5+.5,1.0);return;}\n outColor=vec4(encodeNative(radiance),1.0);\n}\n";
const SKY_VERTEX="precision highp float;\nin vec3 position;\nuniform mat4 uInvVP;\nuniform vec3 uEye;\nout vec3 vDirection;\nvoid main(){\n vec4 q=uInvVP*vec4(position.xy,1.0,1.0);\n vDirection=q.xyz/q.w-uEye;\n gl_Position=vec4(position.xy,1.0,1.0);\n}\n";
const SKY_FRAGMENT="precision highp float;\nuniform sampler2D uSky;\nuniform vec3 uWhite;\nuniform vec3 uSun;\nuniform vec3 uSolar;\nuniform float uExposure;\nin vec3 vDirection;\nout vec4 outColor;\nvec3 encodeNative(vec3 rgb){\n vec3 a=max(rgb/uWhite*uExposure,vec3(0.0));a=a*a/(a+vec3(.035));float p=max(max(a.r,a.g),max(a.b,.0000001));a*=(1.0-exp(-p))/p;\n a=clamp(a,0.0,1.0);return mix(12.92*a,1.055*pow(a,vec3(1.0/2.4))-.055,step(vec3(.0031308),a));\n}\nvoid main(){\n vec3 d=normalize(vDirection);vec2 uv=vec2(fract(atan(d.y,d.x)/6.28318530718+1.0),acos(clamp(d.z,-1.0,1.0))/3.14159265359);\n vec3 c=texture(uSky,uv).rgb;\n if(dot(d,uSun)>=.999989189)c+=uSolar/.000067928;\n outColor=vec4(encodeNative(c),1.0);\n}\n";
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
