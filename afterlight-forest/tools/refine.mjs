// Deterministic, idempotent v3.1 source refinements, applied before packaging.
// Published source/app.js includes the resolved implementation, not just a patch.
import fs from 'node:fs/promises';
let app=await fs.readFile('app.js','utf8');
function replace(before,after){if(app.includes(before))app=app.replace(before,after);else if(!app.includes(after))throw Error('Source refinement no longer matches: '+before.slice(0,90));}
replace("import {TransformControls} from 'three/addons/controls/TransformControls.js';", "import {TransformControls} from 'three/addons/controls/TransformControls.js';\nimport {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';");
replace("function requestRender(){dirty=true;if(!raf&&!disposed&&!document.hidden)raf=requestAnimationFrame(tick);}","function requestRender(){dirty=true;if(params.has('test')&&state.ready)return;if(!raf&&!disposed&&!document.hidden)raf=requestAnimationFrame(tick);}");
replace("function tick(time){raf=0;if(disposed||document.hidden)return;", "function tick(time){raf=0;if(disposed||document.hidden||(params.has('test')&&state.ready))return;");
replace('camera.fov=sourceCamera.fov;', 'camera.fov=Math.min(60,sourceCamera.fov);');
replace('maxPixelRadius:512','maxPixelRadius:256');
replace("ctx.fillStyle='#736e5a';", "ctx.fillStyle='#98917c';");
replace('new THREE.BoxGeometry(...size)', 'new RoundedBoxGeometry(...size,2,Math.min(.003,Math.min(...size)*.08))');
replace('g.position.set(x,heightAt(x,z),z);', 'g.position.set(x,heightAt(x,z)-.045,z);');
replace('map:tex,color:0xb0aa96', 'map:tex,color:0xf4eed9');
replace("'Entry waymark',.08,-1.15", "'Entry waymark',-.85,-2.55");
replace("'Trail bench',-2.7,-.65", "'Trail bench',-1.75,-.85");
replace("for(const m of meshes)initialLayout.push(serialize(m));", "for(const m of meshes){if(m.name.startsWith('waymark'))m.scale.setScalar(.78);initialLayout.push(serialize(m));}");
replace("version:'3.0.0'", "version:'3.1.0'");
replace("renderSubmissionMs:renderTimes.length?", "lastCaptureMs:state.lastCaptureMs??null,renderSubmissionMs:renderTimes.length?");
replace("async settle(frames=3){await ready;for(let i=0;i<frames;i++){await spark.update({scene,camera});renderer.render(scene,camera);await new Promise(r=>setTimeout(r,80));}return diagnostics();},", "async settle(frames=1){await ready;for(let i=0;i<frames;i++){await spark.update({scene,camera});renderer.render(scene,camera);renderer.getContext().finish();}drawMap();return diagnostics();},\nasync capturePng(){await ready;const start=performance.now();await spark.update({scene,camera});renderer.render(scene,camera);renderer.getContext().finish();const png=renderer.domElement.toDataURL('image/png');state.lastCaptureMs=performance.now()-start;return png;},\nsetFov(value){camera.fov=THREE.MathUtils.clamp(value,35,90);camera.updateProjectionMatrix();requestRender();},");
if(!app.includes("addEventListener('pageshow'"))app+="\naddEventListener('pageshow',event=>{if(event.persisted)location.reload();});\n";
await fs.writeFile('app.js',app);
let html=await fs.readFile('index.html','utf8');html=html.replace('>V3.0<','>V3.1<');await fs.writeFile('index.html',html);
console.log('Applied v3.1: deterministic capture, bounded near-splat footprint, beveled props, corrected placement and framing.');
