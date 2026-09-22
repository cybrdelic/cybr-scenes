"""Run the scripts and embedded payloads from the exact delivered HTML in Chromium.
Local/file navigation is blocked by the environment's browser administrator.
This harness loads the identical document nodes/scripts in-memory and distinguishes
that from an HTTP/file-URL startup test. No substitute imagery or asset downloads.
"""
from pathlib import Path
import argparse,os,re,base64,json,time,hashlib,traceback,gc
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HOOK="""(()=>{const raf=requestAnimationFrame.bind(window);window.__next=null;window.requestAnimationFrame=cb=>{if(cb.name==='frame'){__next=cb;return 1;}return raf(cb)};window.__step=()=>{__next(performance.now());CYBR_RECOVERY.renderer.getContext().finish();};})();"""
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--file',type=Path,required=True);ap.add_argument('--name',required=True);ap.add_argument('--export',action='store_true');ap.add_argument('--quick',action='store_true');args=ap.parse_args()
 out=ROOT/'evidence'/args.name;out.mkdir(parents=True,exist_ok=True)
 report={'result':'FAIL','errors':[],'checks':[],'captures':{},'input_file':args.file.name,'entrypoint':'In-memory Chromium document using identical delivered script and JSON nodes; HTTP/file navigation blocked by administrator.','physical_phone_test':False}
 start=time.monotonic()
 try:
  text=args.file.read_text();report['html_sha256']=sha(text.encode())
  matches=list(re.finditer(r'<script([^>]*)>',text));blocks=[(m.end(),text.index('</script>',m.end())) for m in matches]
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=False,env={**os.environ,'DISPLAY':':94','LIBGL_ALWAYS_SOFTWARE':'1'},args=['--no-sandbox','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-gpu-watchdog','--disable-dev-shm-usage'])
   context=browser.new_context(viewport={'width':1200,'height':800},device_scale_factor=1,has_touch=True,is_mobile=True)
   page=context.new_page();page.set_default_timeout(240000)
   page.on('pageerror',lambda e:report['errors'].append(str(e)))
   page.on('console',lambda m:report['errors'].append(m.text) if m.type=='error' else None)
   page.set_content(text[:matches[0].start()]+'</body></html>');page.evaluate(HOOK)
   for a,b in blocks[:4]:page.add_script_tag(content=text[a:b])
   for idx,id in [(4,'sw-scene-data'),(5,'sw-detail-data')]:
    a,b=blocks[idx];page.evaluate('()=>{window.__chunks=[];}')
    for offset in range(a,b,4*1024*1024):page.evaluate('(s)=>__chunks.push(s)',text[offset:min(b,offset+4*1024*1024)])
    page.evaluate('''(id)=>{const n=document.createElement('script');n.type='application/json';n.id=id;n.textContent=__chunks.join('');window.__chunks=null;document.body.append(n);}''',id)
   a,b=blocks[6];page.add_script_tag(content=text[a:b]);del text;gc.collect()
   page.wait_for_function('window.CYBR_RECOVERY || !document.getElementById("error").hidden',polling=100)
   assert page.evaluate('!!window.CYBR_RECOVERY'),page.locator('#error').inner_text()
   print('LOADED',args.name,flush=True)
   def check(name,cond,details=None):
    assert cond,(name,details);report['checks'].append(name);print('PASS',name,flush=True)
   state=page.evaluate('''()=>{const a=CYBR_RECOVERY,g=a.renderer.getContext(),old=a.renderer.getRenderTarget();let targets=[];
     for(const t of [a.quality.current,...a.quality.history]){a.renderer.setRenderTarget(t);targets.push({complete:g.checkFramebufferStatus(g.FRAMEBUFFER)===g.FRAMEBUFFER_COMPLETE,bits:g.getFramebufferAttachmentParameter(g.FRAMEBUFFER,g.COLOR_ATTACHMENT0,g.FRAMEBUFFER_ATTACHMENT_RED_SIZE),type:t.texture.type});}
     a.renderer.setRenderTarget(old);const e=g.getExtension('WEBGL_debug_renderer_info');return {triangles:a.geometry.reduce((s,g)=>s+g.index.count/3,0),vertices:a.geometry.reduce((s,g)=>s+g.attributes.position.count,0),maps:a.detail.report(),targets,renderer:g.getParameter(e.UNMASKED_RENDERER_WEBGL),noDataNodes:!document.getElementById('sw-detail-data')&&!document.getElementById('sw-scene-data')};}''')
   report['runtime']=state
   check('All source geometry loaded',state['triangles']==5029800 and state['vertices']==2526592)
   check('All three HDR targets really have 32-bit float components',all(x['complete'] and x['bits']==32 for x in state['targets']),state['targets'])
   check('Actual embedded payload bootstrap completed',state['noDataNodes'])
   def step():page.evaluate('__step()')
   def capture(name,code=None,samples=8):
    if code:page.evaluate(code)
    if args.quick:samples=1
    page.evaluate('(s)=>{CYBR_RECOVERY.quality.limit=s;CYBR_RECOVERY.quality.invalidate()}',samples)
    for _ in range(samples-1):step()
    data=page.evaluate('''()=>{__step();const a=CYBR_RECOVERY;return {png:a.renderer.domElement.toDataURL('image/png'),quality:a.quality.report(),glError:a.renderer.getContext().getError(),eye:a.camera.position.toArray(),quaternion:a.camera.quaternion.toArray()}}''')
    raw=base64.b64decode(data.pop('png').split(',',1)[1]);(out/(name+'.png')).write_bytes(raw);data['sha256']=sha(raw)
    check(name+' completed without GL errors',data['glError']==0)
    report['captures'][name]=data;return data
   first=capture('hero')
   raw=page.evaluate('''()=>{__step();return CYBR_RECOVERY.renderer.domElement.toDataURL('image/png')}''')
   check('Stationary output is byte-identical; dither does not flicker',sha(base64.b64decode(raw.split(',',1)[1]))==first['sha256'])
   capture('visibility','CYBR_RECOVERY.setMode(4);CYBR_RECOVERY.detail.uniforms.uMicroShadows.value=0;')
   capture('forward','CYBR_RECOVERY.setMode(0);CYBR_RECOVERY.detail.uniforms.uMicroShadows.value=1;CYBR_RECOVERY.setPose([.25,4.8,1.6],[1.2,16,2.6]);')
   capture('sun','CYBR_RECOVERY.setPose([0,1,18],new THREE.Vector3(0,1,18).addScaledVector(CYBR_RECOVERY.material.uniforms.uSun.value,100).toArray());',samples=2)
   # Direct readback of RGBA32F catches NaN/Inf that an 8-bit screenshot hides.
   floats=page.evaluate('''()=>{const a=CYBR_RECOVERY,q=a.quality,g=a.renderer.getContext(),t=q.history[q.historyIndex];const data=new Float32Array(16*16*4);a.renderer.readRenderTargetPixels(t,Math.floor(q.width/2)-8,Math.floor(q.height/2)-8,16,16,data);return {finite:Array.from(data).every(Number.isFinite),max:Math.max(...data),error:g.getError()};}''')
   check('Bright HDR sun remains finite',floats['finite'] and floats['error']==0,floats);report['sun_probe']=floats
   # Reset before moving-camera / touch regressions.
   page.evaluate('CYBR_RECOVERY.setReference();CYBR_RECOVERY.quality.limit=2;');step();step()
   page.evaluate('CYBR_RECOVERY.setPose([.10,-5.0,1.6],[.15,9.8,3.12]);');step()
   check('Camera motion resets sample history to one',page.evaluate('CYBR_RECOVERY.quality.samples')==1)
   page.evaluate('CYBR_RECOVERY.setReference();');step()
   page.locator('canvas').focus();before=page.evaluate('CYBR_RECOVERY.camera.position.toArray()');page.keyboard.down('w');step();page.keyboard.up('w')
   moved=page.evaluate('CYBR_RECOVERY.camera.position.toArray()');check('Keyboard movement preserved',before!=moved)
   page.evaluate('CYBR_RECOVERY.setReference();');page.set_viewport_size({'width':390,'height':844});step()
   cdp=context.new_cdp_session(page)
   def touch(kind,pts):
    cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[{'id':i,'x':x,'y':y,'radiusX':5,'radiusY':5,'force':1} for i,x,y in pts]});page.wait_for_timeout(40)
    page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>resolve()))')
   box=page.locator('#joystick').bounding_box();check('Mobile joystick is available',bool(box))
   x=box['x']+box['width']/2;y=box['y']+box['height']/2
   page.evaluate("()=>{window.__pointerLog=[];for(const t of ['pointerdown','pointermove','pointercancel','pointerup'])document.addEventListener(t,e=>__pointerLog.push({type:e.type,id:e.pointerId,target:e.target.id||e.target.tagName,x:e.clientX,y:e.clientY}),true);}")
   startPose=page.evaluate('CYBR_RECOVERY.controls.snapshot()')
   touch('touchStart',[(1,x,y)]);touch('touchMove',[(1,x,y-35)]);step()
   touch('touchStart',[(1,x,y-35),(2,250,280)]);touch('touchMove',[(1,x,y-35),(2,290,260)]);step()
   endPose=page.evaluate('CYBR_RECOVERY.controls.snapshot()')
   report['touch_debug']={'before':startPose,'after':endPose,'events':page.evaluate('__pointerLog')};print(report['touch_debug'],flush=True)
   check('Simultaneous joystick movement and look preserved',endPose['eye']!=startPose['eye'] and endPose['quaternion']!=startPose['quaternion'],report['touch_debug'])
   touch('touchCancel',[]);step();idle=page.evaluate('CYBR_RECOVERY.controls.snapshot()')
   check('Touch cancellation clears held movement',idle['stick']==[0,0] and idle['pointers']==0 and idle['holds']==0)
   page.locator('#nav-orbit').tap();step();orbit=page.evaluate('CYBR_RECOVERY.controls.snapshot()');check('Orbit mode preserved',orbit['mode']=='orbit')
   touch('touchStart',[(1,90,300),(2,270,300)]);touch('touchMove',[(1,65,300),(2,295,300)]);touch('touchEnd',[]);step()
   check('Two-finger pinch changes orbit radius',page.evaluate('CYBR_RECOVERY.controls.radius')<orbit['radius'])
   capture('mobile_orbit',samples=2)
   page.set_viewport_size({'width':1200,'height':800});page.evaluate('CYBR_RECOVERY.setReference();');step()
   if not args.quick and not args.export:
    # Same native rays rendered in one tile versus six tiles. This catches tile
    # framing errors and dither-phase resets without relying on visual labels.
    import numpy as np
    from PIL import Image
    import io
    pair=[]
    for size in [1024,256]:
     data=page.evaluate("""async(size)=>{const a=CYBR_RECOVERY,{blob,report}=await a.quality.capture4K({download:false,width:768,height:512,samples:2,tileSize:size});const png=await new Promise(resolve=>{const f=new FileReader();f.onload=()=>resolve(f.result);f.readAsDataURL(blob);});return {png,report,error:a.renderer.getContext().getError()};}""",size)
     raw=base64.b64decode(data.pop('png').split(',',1)[1]);(out/f'tile_test_{size}.png').write_bytes(raw)
     pair.append(np.asarray(Image.open(io.BytesIO(raw)).convert('RGB')).astype(float))
     check('Tiled comparison export retains graphics context',data['error']==0)
    diff=np.abs(pair[0]-pair[1]);seam=np.zeros(diff.shape[:2],bool)
    for x in [256,512]:seam[:,x-2:x+2]=True
    seam[254:258,:]=True
    metrics={'mean_abs_code_error':float(diff.mean()),'rmse_codes':float(np.sqrt((diff*diff).mean())),
      'fraction_above_8_codes':float((diff.max(2)>8).mean()),'seam_mean_code_error':float(diff[seam].mean()),'interior_mean_code_error':float(diff[~seam].mean())}
    report['tile_equivalence']=metrics;print('TILE COMPARISON',metrics,flush=True)
    check('Tiled and single-tile native renders agree',metrics['mean_abs_code_error']<1.0 and metrics['fraction_above_8_codes']<.001,metrics)
    check('No coherent tile-boundary error',metrics['seam_mean_code_error']<3*metrics['interior_mean_code_error']+.1,metrics)
   if args.export:
    print('EXPORT 4K START',flush=True)
    result=page.evaluate('''async()=>{const a=CYBR_RECOVERY,old=[a.quality.width,a.quality.height];const {blob,report}=await a.quality.capture4K({download:false,samples:8});const png=await new Promise(resolve=>{const f=new FileReader();f.onload=()=>resolve(f.result);f.readAsDataURL(blob);});return {png,report,old,restored:[a.quality.width,a.quality.height],inert:document.body.inert};}''')
    raw=base64.b64decode(result.pop('png').split(',',1)[1]);(out/'hero_4k.png').write_bytes(raw);result['sha256']=sha(raw)
    check('4K export is fresh 3840x2560 with eight samples',result['report']['width']==3840 and result['report']['height']==2560 and result['report']['samples']==8)
    check('4K export restores viewport and controls',result['old']==result['restored'] and not result['inert'])
    report['export']=result
   check('No JavaScript or shader errors',not report['errors'],report['errors'])
   report['result']='PASS';browser.close()
 except Exception as e:report['exception']=str(e);report['traceback']=traceback.format_exc();print(report['traceback'],flush=True)
 report['seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2));print(report['result'],report['seconds'],flush=True)
 if report['result']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
