import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
await fs.mkdir('renders',{recursive:true});await fs.mkdir('test-results',{recursive:true});
const server=spawn(process.execPath,['tools/serve.mjs'],{stdio:'inherit'});
let browser,page;const errors=[],checks=[],log=[],timings=[];
async function capture(file){const start=Date.now();const url=await page.evaluate(()=>window.afterlight.capturePng());assert(url.startsWith('data:image/png;base64,'));await fs.writeFile(file,Buffer.from(url.split(',')[1],'base64'));timings.push({file,ms:Date.now()-start});}
try{
for(let i=0;i<50;i++){try{if((await fetch('http://127.0.0.1:4173/')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
page=await browser.newPage({viewport:{width:1280,height:800},deviceScaleFactor:1});page.setDefaultTimeout(120000);
page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE_ERROR',e.message);});page.on('console',m=>{log.push(m.type()+': '+m.text());if(m.type()==='error')console.error('CONSOLE',m.text());});
await page.goto('http://127.0.0.1:4173/?test=1',{waitUntil:'domcontentloaded'});
await page.waitForFunction(()=>window.afterlight?.diagnostics().ready,{},{timeout:240000});await page.evaluate(()=>window.afterlight.settle());
let info=await page.evaluate(()=>window.afterlight.diagnostics());assert.equal(info.gaussians,2142439);checks.push('Original 2142439 Gaussians decoded');assert.deepEqual(info.resolution,[1280,800]);checks.push('Native 1280x800 framebuffer, no hidden downscale');
await page.screenshot({path:'renders/01-understory-interface.png',timeout:120000});
await page.evaluate(()=>window.afterlight.setClean(true));await capture('renders/02-understory-trail.png');
const before=info.camera;await page.evaluate(()=>{window.afterlight.setMode('fly');window.afterlight.stepMovement('KeyD',.25);});const after=await page.evaluate(()=>window.afterlight.diagnostics().camera);assert(Math.hypot(...after.map((v,i)=>v-before[i]))>.05);checks.push('Free flight translates the 3D camera');
await page.evaluate(()=>{window.afterlight.home();window.afterlight.setMode('walk');window.afterlight.stepMovement('KeyW',.25);});const walk=await page.evaluate(()=>{const d=window.afterlight.diagnostics();return{camera:d.camera,ground:window.afterlight.getGround(d.camera[0],d.camera[2])};});assert(Number.isFinite(walk.ground));assert(Math.abs(walk.camera[1]-walk.ground-.82)<.15);checks.push('Walk mode follows sampled capture terrain');
const original=await page.evaluate(()=>window.afterlight.layout());await page.evaluate(()=>window.afterlight.moveMesh('trail-bench',[.3,0,0]));const edited=await page.evaluate(()=>window.afterlight.layout());assert(Math.abs(edited.objects[1].position[0]-original.objects[1].position[0]-.3)<1e-6);await page.evaluate(data=>window.afterlight.applyLayout(data),original);checks.push('Mesh edit and layout restoration');
assert(await page.evaluate(()=>{try{window.afterlight.applyLayout({schema:'wrong'});return false;}catch{return true;}}));checks.push('Malformed layouts rejected');
await page.evaluate(()=>window.afterlight.tourPose(.47));await capture('renders/03-upper-trail.png');
await page.evaluate(()=>window.afterlight.tourPose(.64));await capture('renders/04-woodland-bend.png');
await page.evaluate(()=>{window.afterlight.setPose([-.25,1.05,-.05],[-1.75,.61,-.85]);window.afterlight.setClean(false);});await page.click('#panelToggle');await page.selectOption('#object','trail-bench');await page.evaluate(()=>window.afterlight.settle());await page.screenshot({path:'renders/05-editable-meshes.png',timeout:120000});await page.click('#closePanel');await page.evaluate(()=>{window.afterlight.setClean(true);window.afterlight.home();});
await page.evaluate(()=>window.afterlight.setMeshes(false));await capture('test-results/capture-only.png');await page.evaluate(()=>window.afterlight.setMeshes(true));await capture('test-results/hybrid.png');
await page.evaluate(()=>window.afterlight.quality('balanced'));await capture('test-results/balanced.png');checks.push('Balanced LoD mode renders');await page.evaluate(()=>window.afterlight.quality('native'));
const frames=Number(process.env.RENDER_FRAMES||144),fps=12;await fs.mkdir('renders/frames',{recursive:true});const started=Date.now();
for(let i=0;i<frames;i++){const u=i/Math.max(1,frames-1),t=.34+.34*(u*u*(3-2*u));await page.evaluate(t=>window.afterlight.tourPose(t),t);await capture(`renders/frames/${String(i).padStart(5,'0')}.png`);if(i%24===0)console.log('RENDER_FRAME',i,'of',frames);}
const elapsed=(Date.now()-started)/1000;info=await page.evaluate(()=>window.afterlight.diagnostics());checks.push('Actual renderer sequence: '+frames+' frames');
const report={version:'3.1.0',timestamp:new Date().toISOString(),environment:'GitHub Actions Ubuntu 24.04 / Chromium SwiftShader software rasterizer',passed:errors.length===0,checks,errors,diagnostics:info,sequence:{frames,fps,seconds:frames/fps,renderWallSeconds:elapsed},captureTimings:timings,limitations:['Not a hardware GPU/mobile performance benchmark','Fixed captured lighting and source reconstruction blur','Approximate trail navigation proxy','Original Afterlight publishing connection unavailable']};
await fs.writeFile('test-results/report.json',JSON.stringify(report,null,2));await fs.writeFile('test-results/browser.log',log.join('\n'));await fs.writeFile('renders/ATTRIBUTION.txt','Actual Afterlight renderer output. Forest Scan by draftmode, https://superspl.at/scene/259c0051, CC BY 4.0. Changes: camera framing and editable mesh additions. Original lighting remains baked.\n');
assert.equal(errors.length,0,'Browser errors present');
}catch(e){await fs.writeFile('test-results/failure.json',JSON.stringify({error:String(e),errors,checks,log,timings},null,2));throw e;}finally{await browser?.close();server.kill();}
