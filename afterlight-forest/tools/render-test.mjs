import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
await fs.mkdir('renders',{recursive:true});await fs.mkdir('test-results',{recursive:true});
const server=spawn(process.execPath,['tools/serve.mjs'],{stdio:'inherit'});
let browser;
const errors=[],checks=[],log=[];
try{
for(let i=0;i<50;i++){try{if((await fetch('http://127.0.0.1:4173/')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
const page=await browser.newPage({viewport:{width:1280,height:800},deviceScaleFactor:1});
page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE_ERROR',e.message);});page.on('console',m=>{log.push(m.type()+': '+m.text());if(m.type()==='error')console.error('CONSOLE',m.text());});
await page.goto('http://127.0.0.1:4173/?test=1',{waitUntil:'domcontentloaded'});
await page.waitForFunction(()=>window.afterlight?.diagnostics().ready,{},{timeout:240000});
await page.evaluate(()=>window.afterlight.settle(5));
let info=await page.evaluate(()=>window.afterlight.diagnostics());assert.equal(info.gaussians,2142439);checks.push('Original 2142439 Gaussians decoded');assert.deepEqual(info.resolution,[1280,800]);checks.push('Native 1280x800 framebuffer, no hidden downscale');
await page.screenshot({path:'renders/01-understory-interface.png'});
await page.evaluate(()=>window.afterlight.setClean(true));await page.screenshot({path:'renders/02-understory-trail.png'});
// Record raw orientation alternatives for inspection, not marketing output.
if(process.env.PROBE_ORIENTATION==='1'){for(const a of ['none','x','z']){await page.evaluate(a=>window.afterlight.setOrientation(a),a);await page.evaluate(()=>window.afterlight.settle(4));await page.screenshot({path:'test-results/orientation-'+a+'.png'});}await page.evaluate(()=>window.afterlight.setOrientation('z'));}
const before=info.camera;await page.evaluate(()=>{window.afterlight.setMode('fly');window.afterlight.stepMovement('KeyD',.25);});await page.evaluate(()=>window.afterlight.settle(3));const after=await page.evaluate(()=>window.afterlight.diagnostics().camera);assert(Math.hypot(...after.map((v,i)=>v-before[i]))>.05);checks.push('Unrestricted flight translates the 3D camera');
await page.evaluate(()=>window.afterlight.home());await page.evaluate(()=>{window.afterlight.setMode('walk');window.afterlight.stepMovement('KeyW',.25);});const walk=await page.evaluate(()=>{const d=window.afterlight.diagnostics();return{camera:d.camera,ground:window.afterlight.getGround(d.camera[0],d.camera[2])};});assert(Number.isFinite(walk.ground));assert(Math.abs(walk.camera[1]-walk.ground-.82)<.15);checks.push('Walk mode follows sampled capture terrain');
const original=await page.evaluate(()=>window.afterlight.layout());await page.evaluate(()=>window.afterlight.moveMesh('trail-bench',[.3,0,0]));const edited=await page.evaluate(()=>window.afterlight.layout());assert(Math.abs(edited.objects[1].position[0]-original.objects[1].position[0]-.3)<1e-6);await page.evaluate(data=>window.afterlight.applyLayout(data),original);checks.push('Mesh transform edit and layout restoration');
const rejected=await page.evaluate(()=>{try{window.afterlight.applyLayout({schema:'wrong'});return false;}catch{return true;}});assert(rejected);checks.push('Malformed layout is rejected');
await page.evaluate(()=>window.afterlight.tourPose(.47));await page.evaluate(()=>window.afterlight.settle(5));await page.screenshot({path:'renders/03-upper-trail.png'});
await page.evaluate(()=>window.afterlight.tourPose(.64));await page.evaluate(()=>window.afterlight.settle(5));await page.screenshot({path:'renders/04-woodland-bend.png'});
await page.evaluate(()=>window.afterlight.home());await page.evaluate(()=>window.afterlight.settle(4));await page.evaluate(()=>window.afterlight.setClean(false));await page.click('#panelToggle');await page.selectOption('#object','trail-bench');await page.screenshot({path:'renders/05-editable-meshes.png'});await page.click('#closePanel');await page.evaluate(()=>window.afterlight.setClean(true));
await page.evaluate(()=>window.afterlight.setMeshes(false));await page.evaluate(()=>window.afterlight.settle(3));await page.screenshot({path:'test-results/capture-only.png'});await page.evaluate(()=>window.afterlight.setMeshes(true));await page.evaluate(()=>window.afterlight.settle(3));await page.screenshot({path:'test-results/hybrid.png'});
// Deterministic viewpoints: encoded playback speed is not a realtime benchmark.
const frames=Number(process.env.RENDER_FRAMES||144),fps=12;await fs.mkdir('renders/frames',{recursive:true});const started=Date.now();
for(let i=0;i<frames;i++){const u=i/(frames-1),t=.34+.34*(u*u*(3-2*u));await page.evaluate(t=>window.afterlight.tourPose(t),t);await page.evaluate(()=>window.afterlight.settle(1));await page.screenshot({path:`renders/frames/${String(i).padStart(5,'0')}.png`});if(i%24===0)console.log('RENDER_FRAME',i,'of',frames);}
const elapsed=(Date.now()-started)/1000;info=await page.evaluate(()=>window.afterlight.diagnostics());checks.push('Deterministic real renderer frame sequence: '+frames+' frames');
const report={version:'3.0.0',timestamp:new Date().toISOString(),environment:'GitHub Actions ubuntu-latest / Chromium SwiftShader software rasterizer',passed:errors.length===0,checks,errors,diagnostics:info,sequence:{frames,fps,seconds:frames/fps,renderWallSeconds:elapsed},limitations:['No hardware GPU/mobile performance claim','Fixed captured lighting','Approximate trail navigation proxy','Original Afterlight publisher unavailable; no site deployment claimed']};
await fs.writeFile('test-results/report.json',JSON.stringify(report,null,2));await fs.writeFile('test-results/browser.log',log.join('\n'));
await fs.writeFile('renders/ATTRIBUTION.txt','Actual Afterlight renderer output. Forest Scan by draftmode, https://superspl.at/scene/259c0051, CC BY 4.0. Changes: camera framing and editable mesh additions. Original lighting remains baked.\n');
assert.equal(errors.length,0,'Browser errors present');
}catch(e){await fs.writeFile('test-results/failure.json',JSON.stringify({error:String(e),errors,checks,log},null,2));throw e;}finally{await browser?.close();server.kill();}
