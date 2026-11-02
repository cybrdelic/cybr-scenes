import * as THREE from 'three';
import {SparkRenderer,SplatMesh} from '@sparkjsdev/spark';
import {TransformControls} from 'three/addons/controls/TransformControls.js';

// Afterlight Understory: one real reconstruction and a conventional editable
// mesh layer sharing a camera and depth-tested render pipeline. No panorama.
const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);
const state={ready:false,mode:'walk',tour:false,tourT:.36,quality:'native',drag:false,editing:false,hidden:false,frame:0,errors:[],sceneId:'259c0051'};
const keys=new Set(),meshes=[],undoStack=[],initialLayout=[];
const V=THREE.Vector3, tmp=new V(),tmp2=new V(),up=new V(0,1,0);
let renderer,spark,splats,scene,camera,transform,nav,curve,routeSamples=[],navMesh;
let yaw=0,pitch=0,raf=0,last=0,dirty=true,touchX=0,touchY=0,selected=null,statsTime=0,statsFrames=0;
let noticeTimer,sourceCamera,groundOffset=.82,disposed=false;
const renderTimes=[];

function notify(message,ms=3600){$('notice').textContent=message;$('notice').classList.add('visible');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').classList.remove('visible'),ms);}
function fatal(error){console.error(error);state.errors.push(String(error));document.body.classList.add('error-mode');$('loading').hidden=false;$('loadTitle').textContent='The 3D view could not start.';$('loadStatus').textContent=String(error.message||error)+' This view requires WebGL2. The build also includes rendered frames and a walkthrough.';$('retry').hidden=false;$('retry').onclick=()=>location.reload();}
async function json(url){const res=await fetch(url);if(!res.ok)throw Error('Failed to load '+url+' (HTTP '+res.status+')');return res.json();}
function requestRender(){dirty=true;if(!raf&&!disposed&&!document.hidden)raf=requestAnimationFrame(tick);}
function engage(){document.body.classList.add('engaged');}
function applyLook(){camera.quaternion.setFromEuler(new THREE.Euler(pitch,yaw,0,'YXZ'));requestRender();}
function syncLook(){const e=new THREE.Euler().setFromQuaternion(camera.quaternion,'YXZ');yaw=e.y;pitch=e.x;}
function setMode(mode){state.mode=mode;$('walk').classList.toggle('active',mode==='walk');$('fly').classList.toggle('active',mode==='fly');if(mode==='walk'&&state.ready){const q=closestRoute(camera.position);camera.position.x=q.point.x;camera.position.z=q.point.z;camera.position.y=heightAt(q.point.x,q.point.z,q.point.y)+groundOffset;}requestRender();}
function stopTour(){state.tour=false;$('tour').textContent='Guided walk';$('tour').classList.remove('active');}
function home(){stopTour();camera.position.fromArray(sourceCamera.position);camera.lookAt(new V().fromArray(sourceCamera.target));camera.fov=sourceCamera.fov;camera.updateProjectionMatrix();syncLook();requestRender();}
function setPanel(open){$('settings').hidden=!open;$('panelToggle').setAttribute('aria-expanded',String(open));if(open){engage();stopTour();}else{transform.detach();selected=null;$('object').value='';}requestRender();}
function quality(value){state.quality=value;const dpr=devicePixelRatio||1;let ratio=Math.min(dpr,2);spark.enableLod=value==='balanced'||value==='mobile';splats.enableLod=spark.enableLod;spark.lodSplatCount=value==='mobile'?450000:1000000;if(value==='mobile')ratio=Math.min(dpr,1);if(value==='ultra')ratio=Math.min(dpr*1.5,2.5);const cap=4096/Math.max(innerWidth,innerHeight);renderer.setPixelRatio(Math.min(ratio,cap));renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();$('resolution').textContent=renderer.domElement.width+' × '+renderer.domElement.height;$('quality').value=value;requestRender();}
function heightAt(x,z,fallback=0){if(!nav)return fallback;const [ox,oz]=nav.origin,[nx,nz]=nav.size,gx=(x-ox)/nav.step,gz=(z-oz)/nav.step,ix=Math.floor(gx),iz=Math.floor(gz);let sum=0,w=0;for(let dz=0;dz<=1;dz++)for(let dx=0;dx<=1;dx++){const xx=ix+dx,zz=iz+dz;if(xx<0||zz<0||xx>=nx||zz>=nz)continue;const h=nav.heights[zz*nx+xx];if(h===null)continue;const weight=(dx?gx-ix:1-gx+ix)*(dz?gz-iz:1-gz+iz);sum+=h*weight;w+=weight;}return w>.001?sum/w:fallback;}
function closestRoute(p){let best=Infinity,point=routeSamples[0],index=0;for(let i=0;i<routeSamples.length;i++){const q=routeSamples[i],d=(q.x-p.x)**2+(q.z-p.z)**2;if(d<best){best=d;point=q;index=i;}}return{point,distance:Math.sqrt(best),t:index/(routeSamples.length-1)};}
function move(dt){const x=(keys.has('KeyD')?1:0)-(keys.has('KeyA')?1:0)+touchX;const z=(keys.has('KeyW')?1:0)-(keys.has('KeyS')?1:0)-touchY;const y=(keys.has('KeyE')||keys.has('Space')?1:0)-(keys.has('KeyQ')||keys.has('ControlLeft')?1:0);if(!x&&!z&&!y)return false;
engage();stopTour();const speed=.7*(keys.has('ShiftLeft')?2.5:1);tmp.set(x,0,-z);if(tmp.length()>1)tmp.normalize();if(state.mode==='fly'){tmp.applyQuaternion(camera.quaternion);tmp.y+=y;tmp.multiplyScalar(speed*dt*1.7);camera.position.add(tmp);}else{tmp.applyAxisAngle(up,yaw).multiplyScalar(speed*dt);tmp2.copy(camera.position).add(tmp);const nearest=closestRoute(tmp2);if(nearest.distance>nav.corridorRadius){const vx=tmp2.x-nearest.point.x,vz=tmp2.z-nearest.point.z;tmp2.x=nearest.point.x+vx/nearest.distance*nav.corridorRadius;tmp2.z=nearest.point.z+vz/nearest.distance*nav.corridorRadius;}
// Editable benches and posts have conservative cylindrical walking bounds.
let blocked=false;for(const m of meshes)if(m.visible&&m.userData.walkRadius){const dx=tmp2.x-m.position.x,dz=tmp2.z-m.position.z;if(dx*dx+dz*dz<m.userData.walkRadius**2){blocked=true;break;}}if(!blocked){camera.position.x=tmp2.x;camera.position.z=tmp2.z;camera.position.y=THREE.MathUtils.lerp(camera.position.y,heightAt(tmp2.x,tmp2.z,nearest.point.y)+groundOffset,1-Math.exp(-16*dt));}}
return true;}
function tourPose(t){const p=curve.getPointAt(THREE.MathUtils.clamp(t,0,1));const q=curve.getPointAt(Math.min(t+.045,.999));camera.position.set(p.x,heightAt(p.x,p.z,p.y)+groundOffset,p.z);q.y=heightAt(q.x,q.z,q.y)+groundOffset*.95;camera.lookAt(q);syncLook();requestRender();}
function drawMap(){const c=$('minimap').querySelector('canvas'),ctx=c.getContext('2d');ctx.clearRect(0,0,180,180);ctx.strokeStyle='#63725a';ctx.lineWidth=8;ctx.lineCap='round';ctx.beginPath();const px=x=>22+(x+10.5)*9,pz=z=>20+(z+12)*7;routeSamples.forEach((p,i)=>i?ctx.lineTo(px(p.x),pz(p.z)):ctx.moveTo(px(p.x),pz(p.z)));ctx.stroke();ctx.strokeStyle='#c4c6ae';ctx.lineWidth=1;ctx.stroke();ctx.save();ctx.translate(px(camera.position.x),pz(camera.position.z));ctx.rotate(-yaw);ctx.fillStyle='#eee4c7';ctx.beginPath();ctx.moveTo(0,-8);ctx.lineTo(5,6);ctx.lineTo(0,3);ctx.lineTo(-5,6);ctx.closePath();ctx.fill();ctx.restore();}
function tick(time){raf=0;if(disposed||document.hidden)return;const dt=Math.min(.05,(time-last)/1000||.016);last=time;const moved=state.ready&&!state.editing&&move(dt);if(state.tour){state.tourT+=dt*.010;if(state.tourT>.88){stopTour();notify('End of the supported trail walk. Fly mode remains available.');}else tourPose(state.tourT);}
if(dirty||moved||state.tour){dirty=false;const start=performance.now();renderer.render(scene,camera);const cost=performance.now()-start;renderTimes.push(cost);if(renderTimes.length>180)renderTimes.shift();state.frame++;statsFrames++;if(state.ready&&state.frame%4===0)drawMap();}
if(time-statsTime>1000){const active=moved||state.tour||state.drag;$('fps').textContent=active?(statsFrames*1000/(time-statsTime)).toFixed(0)+' FPS':'IDLE';statsFrames=0;statsTime=time;}
if(moved||state.tour||state.drag||keys.size||touchX||touchY)requestRender();}

function woodTexture(){const c=document.createElement('canvas');c.width=512;c.height=128;const ctx=c.getContext('2d');let seed=90210;const rnd=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};ctx.fillStyle='#736e5a';ctx.fillRect(0,0,c.width,c.height);for(let i=0;i<420;i++){const y=rnd()*128,v=40+rnd()*90;ctx.strokeStyle=`rgba(${v+13},${v+10},${v},${.08+rnd()*.2})`;ctx.lineWidth=.2+rnd()*.8;ctx.beginPath();ctx.moveTo(0,y);for(let x=0;x<=512;x+=16)ctx.lineTo(x,y+Math.sin(x*.022+i)*(.2+rnd()*1.4));ctx.stroke();}const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());return t;}
function addBox(group,size,pos,mat){const obj=new THREE.Mesh(new THREE.BoxGeometry(...size),mat);obj.position.set(...pos);group.add(obj);return obj;}
function addEditable(id,label,x,z,make,radius=.12){const g=new THREE.Group();g.name=id;g.userData={label,editable:true,walkRadius:radius};g.position.set(x,heightAt(x,z),z);make(g);meshes.push(g);scene.add(g);const option=document.createElement('option');option.value=id;option.textContent=label;$('object').appendChild(option);return g;}
function makeMeshes(){const tex=woodTexture();const timber=new THREE.MeshStandardMaterial({map:tex,color:0xb0aa96,roughness:.98,metalness:0});const iron=new THREE.MeshStandardMaterial({color:0x252b27,roughness:.72,metalness:.55});const pale=new THREE.MeshStandardMaterial({color:0xb9b6a0,roughness:.95});
addEditable('waymark-entry','Entry waymark',.08,-1.15,g=>{addBox(g,[.048,.68,.048],[0,.34,0],timber);const plate=addBox(g,[.22,.095,.024],[0,.55,-.008],timber);plate.rotation.y=.72;addBox(g,[.024,.025,.005],[.015,.56,-.025],pale);},.11);
const bench=addEditable('trail-bench','Trail bench',-2.7,-.65,g=>{for(let i=0;i<4;i++)addBox(g,[.92,.035,.065],[0,.28,(i-1.5)*.073],timber);for(const x of [-.32,.32])for(const z of [-.09,.09])addBox(g,[.03,.28,.03],[x,.14,z],iron);for(const x of [-.32,.32])addBox(g,[.035,.28,.035],[x,.43,.135],iron);for(let j=0;j<2;j++)addBox(g,[.92,.055,.028],[0,.44+j*.07,.15],timber);},.4);bench.rotation.y=-.7;
addEditable('waymark-bend','Upper trail waymark',-4.9,-6.05,g=>{addBox(g,[.045,.57,.045],[0,.285,0],timber);addBox(g,[.16,.07,.025],[0,.46,0],timber);},.1);
for(const m of meshes)initialLayout.push(serialize(m));
const geometry=new THREE.BufferGeometry(),verts=[],indices=[];
for(let i=0;i<routeSamples.length;i+=3){const p=routeSamples[i],q=routeSamples[Math.min(i+3,routeSamples.length-1)],dx=q.x-p.x,dz=q.z-p.z,l=Math.hypot(dx,dz)||1;for(const side of [-1,1]){const x=p.x+side*dz/l*nav.corridorRadius,z=p.z-side*dx/l*nav.corridorRadius;verts.push(x,heightAt(x,z,p.y)+.025,z);}}
for(let i=0;i<verts.length/3-2;i+=2)indices.push(i,i+1,i+2,i+1,i+3,i+2);geometry.setAttribute('position',new THREE.Float32BufferAttribute(verts,3));geometry.setIndex(indices);geometry.computeVertexNormals();navMesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:0xe2bb75,wireframe:true,transparent:true,opacity:.7,depthTest:false}));navMesh.visible=false;navMesh.renderOrder=10;scene.add(navMesh);
transform=new TransformControls(camera,renderer.domElement);transform.setSize(.7);scene.add(transform.getHelper());transform.addEventListener('dragging-changed',e=>{state.editing=e.value;if(e.value)pushUndo();else persist();requestRender();});transform.addEventListener('objectChange',()=>{engage();requestRender();});}
function serialize(m){return{id:m.name,position:m.position.toArray(),rotation:[m.rotation.x,m.rotation.y,m.rotation.z],scale:m.scale.toArray()};}
function layout(){return{schema:'afterlight-layout',version:1,scene:state.sceneId,objects:meshes.map(serialize)};}
function validLayout(data){if(data?.schema!=='afterlight-layout'||data.version!==1||data.scene!==state.sceneId||!Array.isArray(data.objects))throw Error('Not an Afterlight forest layout.');if(data.objects.length!==meshes.length)throw Error('The object count does not match.');const seen=new Set();for(const o of data.objects){if(!meshes.some(m=>m.name===o.id)||seen.has(o.id))throw Error('Unknown or duplicated mesh ID.');seen.add(o.id);for(const k of ['position','rotation','scale'])if(!Array.isArray(o[k])||o[k].length!==3||!o[k].every(Number.isFinite))throw Error('Invalid '+k);if(o.position.some(v=>Math.abs(v)>100)||o.scale.some(v=>v<.05||v>8)||o.rotation.some(v=>Math.abs(v)>Math.PI*100))throw Error('Transform outside supported bounds.');}return data;}
function applyLayout(data){validLayout(data);for(const o of data.objects){const m=meshes.find(m=>m.name===o.id);m.position.fromArray(o.position);m.rotation.set(...o.rotation);m.scale.fromArray(o.scale);}requestRender();}
function pushUndo(){undoStack.push(layout());if(undoStack.length>40)undoStack.shift();}
function persist(){try{localStorage.setItem('afterlight-forest-layout-v1',JSON.stringify(layout()));}catch{}}
function selectMesh(id){selected=meshes.find(m=>m.name===id)||null;$('object').value=id;if(selected){transform.attach(selected);stopTour();engage();}else transform.detach();requestRender();}
function saveFile(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
async function saveFrame(){stopTour();transform.detach();const ratio=renderer.getPixelRatio();const captureRatio=Math.min(Math.max(ratio,1.5),4096/Math.max(innerWidth,innerHeight));renderer.setPixelRatio(captureRatio);renderer.setSize(innerWidth,innerHeight,false);await spark.update({scene,camera});renderer.render(scene,camera);renderer.domElement.toBlob(blob=>{if(blob)saveFile(blob,'afterlight-understory-v3.png');},'image/png');renderer.setPixelRatio(ratio);renderer.setSize(innerWidth,innerHeight,false);requestRender();notify('Saved an actual renderer frame. No generated image or sharpen filter.');}

function installControls(){
const canvas=renderer.domElement;let px=0,py=0;
canvas.addEventListener('pointerdown',e=>{if(e.button!==0||state.editing||!state.ready)return;canvas.focus();if(selected)return;state.drag=true;px=e.clientX;py=e.clientY;canvas.setPointerCapture(e.pointerId);engage();stopTour();requestRender();});
canvas.addEventListener('pointermove',e=>{if(!state.drag||state.editing)return;const dx=e.clientX-px,dy=e.clientY-py;px=e.clientX;py=e.clientY;yaw-=dx*.0025;pitch=THREE.MathUtils.clamp(pitch-dy*.0025,-1.48,1.48);applyLook();});
const release=()=>{state.drag=false;requestRender();};canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);
canvas.addEventListener('dblclick',()=>{if(!selected&&state.ready&&canvas.requestPointerLock)canvas.requestPointerLock();});
document.addEventListener('pointerlockchange',()=>{$('crosshair').hidden=document.pointerLockElement!==canvas;});
document.addEventListener('mousemove',e=>{if(document.pointerLockElement===canvas){yaw-=e.movementX*.002;pitch=THREE.MathUtils.clamp(pitch-e.movementY*.002,-1.48,1.48);engage();applyLook();}});
addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;if(['Space','ControlLeft','KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE'].includes(e.code))e.preventDefault();if(e.code==='KeyH'){document.body.classList.toggle('clean');return;}if(e.code==='Digit1')setMode('walk');if(e.code==='Digit2')setMode('fly');if(e.code==='Escape'){stopTour();setPanel(false);document.body.classList.remove('clean');}keys.add(e.code);requestRender();});
addEventListener('keyup',e=>{keys.delete(e.code);requestRender();});addEventListener('blur',()=>{keys.clear();touchX=touchY=0;});
canvas.addEventListener('wheel',e=>{e.preventDefault();camera.fov=THREE.MathUtils.clamp(camera.fov+e.deltaY*.02,35,90);camera.updateProjectionMatrix();engage();requestRender();},{passive:false});
const stick=$('touchStick'),knob=stick.querySelector('i');let stickId=null;
const stickMove=e=>{const r=stick.getBoundingClientRect();let x=(e.clientX-r.left-r.width/2)/35,y=(e.clientY-r.top-r.height/2)/35;const l=Math.max(1,Math.hypot(x,y));touchX=x/l;touchY=y/l;knob.style.transform=`translate(${touchX*28}px,${touchY*28}px)`;engage();requestRender();};
stick.onpointerdown=e=>{stickId=e.pointerId;stick.setPointerCapture(e.pointerId);stickMove(e);};stick.onpointermove=e=>{if(e.pointerId===stickId)stickMove(e);};const stopStick=()=>{stickId=null;touchX=touchY=0;knob.style.transform='';requestRender();};stick.onpointerup=stick.onpointercancel=stopStick;
for(const [id,key] of [['up','KeyE'],['down','KeyQ']]){$(id).onpointerdown=e=>{setMode('fly');keys.add(key);$(id).setPointerCapture(e.pointerId);requestRender();};$(id).onpointerup=$(id).onpointercancel=()=>{keys.delete(key);};}
$('walk').onclick=()=>{stopTour();setMode('walk');notify('Walk mode: terrain-following movement within the captured trail.');};$('fly').onclick=()=>{stopTour();setMode('fly');notify('Fly mode: WASD plus Q/E. Uncaptured areas are not reconstructed.');};$('home').onclick=home;
$('tour').onclick=()=>{if(state.tour){stopTour();requestRender();return;}transform.detach();selected=null;state.tourT=Math.max(.30,Math.min(.82,closestRoute(camera.position).t));state.tour=true;$('tour').textContent='Pause walk';$('tour').classList.add('active');engage();requestRender();};
$('capture').onclick=()=>saveFrame().catch(fatal);$('clean').onclick=()=>{document.body.classList.add('clean');notify('Press H to restore the interface.');};$('panelToggle').onclick=()=>setPanel($('settings').hidden);$('closePanel').onclick=()=>setPanel(false);$('quality').onchange=e=>quality(e.target.value);
$('showSplats').onchange=e=>{splats.visible=e.target.checked;requestRender();};$('showMeshes').onchange=e=>{for(const m of meshes)m.visible=e.target.checked;transform.detach();requestRender();};$('showNav').onchange=e=>{navMesh.visible=e.target.checked;requestRender();};
$('object').onchange=e=>selectMesh(e.target.value);for(const id of ['translate','rotate','scale'])$(id).onclick=()=>{transform.setMode(id);requestRender();};$('undo').onclick=()=>{const s=undoStack.pop();if(s){applyLayout(s);persist();}};
$('saveLayout').onclick=()=>saveFile(new Blob([JSON.stringify(layout(),null,2)],{type:'application/json'}),'afterlight-forest-layout.json');$('importLayout').onclick=()=>$('layoutFile').click();$('layoutFile').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>100000)throw Error('Layout is too large.');const data=validLayout(JSON.parse(await file.text()));pushUndo();applyLayout(data);persist();notify('Mesh layout imported.');}catch(err){notify(err.message,6000);}e.target.value='';};$('resetLayout').onclick=()=>{pushUndo();applyLayout({schema:'afterlight-layout',version:1,scene:state.sceneId,objects:initialLayout});persist();};
addEventListener('resize',()=>{if(state.ready)quality(state.quality);});document.addEventListener('visibilitychange',()=>{keys.clear();last=performance.now();if(!document.hidden)requestRender();});canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fatal(Error('Graphics context was lost; reload to recover.'));});
}

async function boot(){
const canvas=$('scene');const gl=canvas.getContext('webgl2',{alpha:false,antialias:false,powerPreference:'high-performance'});if(!gl)throw Error('WebGL2 is unavailable on this browser/device.');
renderer=new THREE.WebGLRenderer({canvas,context:gl,antialias:false,alpha:false,powerPreference:'high-performance'});renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.NoToneMapping;renderer.setClearColor(0x111b13,1);renderer.setSize(innerWidth,innerHeight,false);
scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(75,innerWidth/innerHeight,.015,400);spark=new SparkRenderer({renderer,onDirty:requestRender,preBlurAmount:0,blurAmount:.3,focalAdjustment:2,apertureAngle:0,sortRadial:false,enableLod:false,maxPixelRadius:512,minSortIntervalMs:0});scene.add(spark);
scene.add(new THREE.HemisphereLight(0xe9efdc,0x373a2c,1.8));const sun=new THREE.DirectionalLight(0xfff6de,1.15);sun.position.set(-3,10,4);scene.add(sun);
const [capture,navigation]=await Promise.all([json('./data/259c0051/capture.json'),json('./data/259c0051/navigation.json')]);sourceCamera=capture.settings.cameras[0].initial;nav=navigation;groundOffset=nav.eyeHeight;curve=new THREE.CatmullRomCurve3(nav.route.map(p=>new V(...p)),false,'centripetal');routeSamples=curve.getSpacedPoints(600);home();
$('loadStatus').textContent='Loading 2.14 million learned Gaussians…';splats=new SplatMesh({url:'./data/259c0051/scene.sog',lod:true,nonLod:true,enableLod:false,raycastable:false,onProgress:e=>{if(e.total){$('progress').style.width=(8+75*e.loaded/e.total)+'%';$('loadStatus').textContent='Forest data · '+(e.loaded/1048576).toFixed(1)+' / '+(e.total/1048576).toFixed(1)+' MiB';}}});
// SuperSplat/PlayCanvas and raw Gaussian capture coordinate conventions differ.
// The published cameras are Y-up; the capture is rotated 180 degrees about Z.
splats.rotation.z=Math.PI;scene.add(splats);requestRender();await splats.initialized;
$('progress').style.width='90%';$('loadStatus').textContent='Preparing the shared depth buffer and editable scene…';makeMeshes();installControls();
if(!params.has('test')){try{const data=localStorage.getItem('afterlight-forest-layout-v1');if(data)applyLayout(JSON.parse(data));}catch{}}
quality(params.get('quality')||'native');await spark.update({scene,camera});renderer.render(scene,camera);state.ready=true;$('count').textContent=(splats.splats.getNumSplats()/1e6).toFixed(2)+'M SPLATS';$('progress').style.width='100%';$('loading').hidden=true;last=performance.now();requestRender();
const ext=gl.getExtension('WEBGL_debug_renderer_info');state.gpu=ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);console.log('AFTERLIGHT_READY',JSON.stringify(diagnostics()));
}
function diagnostics(){return{version:'3.0.0',ready:state.ready,frames:state.frame,gaussians:splats?.splats?.getNumSplats()||0,meshes:meshes.length,camera:camera?.position.toArray(),quaternion:camera?.quaternion.toArray(),fov:camera?.fov,quality:state.quality,resolution:renderer?[renderer.domElement.width,renderer.domElement.height]:[],gpu:state.gpu,renderSubmissionMs:renderTimes.length?renderTimes.reduce((a,b)=>a+b)/renderTimes.length:null,errors:state.errors,rendererCalls:renderer?.info.render.calls,rendererTriangles:renderer?.info.render.triangles};}
const ready=boot().catch(e=>{fatal(e);throw e;});
// Explicit testing API. It changes only this scene, not any external account.
window.afterlight={ready,diagnostics,layout,setMode,home,quality,tourPose,saveFrame,applyLayout,
async settle(frames=3){await ready;for(let i=0;i<frames;i++){await spark.update({scene,camera});renderer.render(scene,camera);await new Promise(r=>setTimeout(r,80));}return diagnostics();},
setPose(position,target){stopTour();camera.position.fromArray(position);camera.lookAt(new V().fromArray(target));syncLook();engage();requestRender();},
setOrientation(axis){splats.rotation.set(0,0,0);if(axis==='x')splats.rotation.x=Math.PI;if(axis==='z')splats.rotation.z=Math.PI;requestRender();},
setClean(value){document.body.classList.toggle('clean',value);},
setMeshes(value){meshes.forEach(m=>m.visible=value);requestRender();},
moveMesh(id,delta){const m=meshes.find(m=>m.name===id);if(!m)throw Error('Unknown mesh');pushUndo();m.position.add(new V(...delta));requestRender();},
getRoute(){return nav.route;},
getGround(x,z){return heightAt(x,z);},
stepMovement(code,seconds){keys.add(code);move(seconds);keys.delete(code);requestRender();},
};
addEventListener('error',e=>{if(e.message)state.errors.push(e.message);});
addEventListener('pagehide',()=>{disposed=true;if(raf)cancelAnimationFrame(raf);if(splats)splats.dispose();if(spark)spark.dispose();if(transform)transform.dispose();if(scene)scene.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material]){m.map?.dispose();m.dispose();}}});renderer?.dispose();});
