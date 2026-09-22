"""Capture real WebGL outputs, atomically after the completed draw."""
from pathlib import Path
import argparse,os,json,base64,time,traceback
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HOOK=r'''(()=>{const raf=requestAnimationFrame.bind(window);window.__next=null;window.requestAnimationFrame=cb=>{if(cb.name==='frame'){window.__next=cb;return 1;}return raf(cb);};window.__step=()=>{if(!__next)throw Error('No app frame');__next(performance.now());CYBR_RECOVERY.renderer.getContext().finish();};})();'''
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--variant',default='before');ap.add_argument('--samples',type=int,default=8);ap.add_argument('--width',type=int,default=1200);ap.add_argument('--height',type=int,default=800);ap.add_argument('--quick',action='store_true');ap.add_argument('--url');a=ap.parse_args()
 out=ROOT/'evidence'/a.variant;out.mkdir(exist_ok=True,parents=True)
 rep={'variant':a.variant,'result':'FAIL','errors':[],'captures':{},'start':time.time()}
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=False,env={**os.environ,'DISPLAY':':94','LIBGL_ALWAYS_SOFTWARE':'1'},args=['--no-sandbox','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-gpu-watchdog','--disable-dev-shm-usage'])
   page=browser.new_page(viewport={'width':a.width,'height':a.height},device_scale_factor=1)
   page.set_default_timeout(180000);page.add_init_script(HOOK)
   page.on('pageerror',lambda e:rep['errors'].append(str(e)))
   page.on('console',lambda m:print(m.type,m.text[:500],flush=True) if m.type=='error' else None)
   # Browser administrative policy blocks navigation to localhost. Execute the
   # exact local scripts with the same embedded assets in a blank document.
   # This proves renderer/control execution, not HTTP or file-URL navigation.
   folder=ROOT/a.variant if (ROOT/a.variant/'app.js').exists() else ROOT/'after'
   head=(folder/'index.html').read_text().split('<script src=')[0]
   page.set_content(head+'</body></html>')
   page.evaluate(HOOK)
   for path in [ROOT/'shared/three.bundle.js',ROOT/'shared/controls.js',folder/'runtime.js',folder/'quality.js']:
    page.add_script_tag(content=path.read_text())
   scene=json.loads((ROOT/'shared/scene.json').read_text())
   page.evaluate('(s)=>{window.CYBR_BAKE=s;}',scene)
   for i,m in enumerate(scene['meshes']):
    for key in ['position','normal','surface','giR','giG','giB','index']:
     if key not in m:continue
     raw=(ROOT/'shared'/Path(m[key]['url']).name).read_bytes()
     page.evaluate('([i,k,s])=>{CYBR_BAKE.meshes[i][k]=s;}',[i,key,base64.b64encode(raw).decode()])
   page.evaluate('(s)=>{CYBR_BAKE.sky.data=s;}',base64.b64encode((ROOT/'shared/sky.z').read_bytes()).decode())
   manifest=json.loads((ROOT/'shared/detail_manifest.json').read_text())
   shader=(folder/'material.glsl').read_text()
   import hashlib
   manifest['shader_sha256']=hashlib.sha256(shader.encode()).hexdigest()
   page.evaluate('([manifest,shader])=>{window.SW_DETAIL_ASSETS={manifest,shader,resolution:2048,images:{}};}',[manifest,shader])
   for tex in manifest['textures'].values():
    for entry in tex['levels']['2048'].values():
     raw=(ROOT/'shared'/Path(entry['url']).name).read_bytes()
     page.evaluate('([k,s])=>{SW_DETAIL_ASSETS.images[k]=s;}',[entry['url'],base64.b64encode(raw).decode()])
   page.add_script_tag(content=(folder/'app.js').read_text())
   rep['entrypoint']='In-memory Chromium document; exact local JS, GLSL and asset bytes. Browser navigation blocked by administrator.'
   page.wait_for_function('window.CYBR_RECOVERY || !document.getElementById("error").hidden',polling=100)
   assert page.evaluate('!!window.CYBR_RECOVERY'),page.locator('#error').inner_text()
   print('LOADED',a.variant,flush=True)
   page.evaluate('(n)=>{CYBR_RECOVERY.quality.limit=n;}',a.samples)
   rep['renderer']=page.evaluate('''()=>{const a=CYBR_RECOVERY,g=a.renderer.getContext();const e=g.getExtension('WEBGL_debug_renderer_info');return {renderer:g.getParameter(e.UNMASKED_RENDERER_WEBGL),floatPrecision:g.getShaderPrecisionFormat(g.FRAGMENT_SHADER,g.HIGH_FLOAT).precision,halfFloatCurrent:a.quality.current.texture.type,history:a.quality.history.map(t=>t.texture.type),triangles:a.geometry.reduce((s,x)=>s+x.index.count/3,0),quality:a.quality.report()}}''')
   def capture(name,code=''):
    if code:page.evaluate(code)
    page.evaluate('CYBR_RECOVERY.quality.invalidate()')
    for _ in range(a.samples-1):page.evaluate('__step()')
    png=page.evaluate('''()=>{__step();return document.querySelector('canvas').toDataURL('image/png')}''')
    (out/(name+'.png')).write_bytes(base64.b64decode(png.split(',',1)[1]))
    state=page.evaluate('''()=>{const a=CYBR_RECOVERY;return {eye:a.camera.position.toArray(),quaternion:a.camera.quaternion.toArray(),glError:a.renderer.getContext().getError(),samples:a.quality.samples,triangles:a.quality.lastSceneTriangles}}''')
    assert state['glError']==0 and 0<state['triangles']<=5029800,state
    rep['captures'][name]=state;print('CAPTURE',name,flush=True)
   capture('hero')
   capture('visibility','CYBR_RECOVERY.setMode(4);CYBR_RECOVERY.detail.uniforms.uMicroShadows.value=0;')
   if not a.quick:
    capture('forward','CYBR_RECOVERY.setMode(0);CYBR_RECOVERY.detail.uniforms.uMicroShadows.value=1;CYBR_RECOVERY.setPose([.25,4.8,1.6],[1.2,16,2.6]);')
    capture('sky','CYBR_RECOVERY.setPose([0,1,2],[0,8,16]);')
    capture('sun','CYBR_RECOVERY.setPose([0,1,18],new THREE.Vector3(0,1,18).addScaledVector(CYBR_RECOVERY.material.uniforms.uSun.value,100).toArray());')
   rep['errors']+=page.evaluate('window.__errors||[]')
   assert not rep['errors'],rep['errors']
   rep['result']='PASS';browser.close()
 except Exception as e:rep['exception']=str(e);rep['traceback']=traceback.format_exc();print(rep['traceback'],flush=True)
 rep['seconds']=time.time()-rep.pop('start');(out/'report.json').write_text(json.dumps(rep,indent=2));print(rep['result'],rep['seconds'],flush=True)
 if rep['result']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
