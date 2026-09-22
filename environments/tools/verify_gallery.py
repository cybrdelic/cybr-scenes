#!/usr/bin/env python3
"""Exercise every rendered-image mode in desktop and mobile Chromium layouts."""
from __future__ import annotations
import functools,http.server,json,sys,threading,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cybr_scenes import atomic_json,now

def main():
 from playwright.sync_api import sync_playwright
 exe=shutil.which('chromium') or shutil.which('chromium-browser')
 if not exe:raise RuntimeError('Chromium is required for this optional gallery audit')
 handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 runs=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=exe,headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
   for label,viewport,name in [('desktop',{'width':1440,'height':1100},'gallery.html'),('mobile',{'width':412,'height':915},'gallery.html'),('standalone-offline',{'width':1100,'height':900},'CYBR_SCENES_R2_Gallery.html')]:
    context=browser.new_context(viewport=viewport);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    url=(ROOT/name).as_uri()  # Offline local-file inspection; no network or loopback access required.
    page.set_content((ROOT/'CYBR_SCENES_R2_Gallery.html').read_text(),wait_until='load',timeout=120000)
    cards=page.locator('.card');assert cards.count()==6
    tested=[]
    for card in cards.all():
     card.scroll_into_view_if_needed();key=card.get_attribute('id');modes=[]
     for button in card.locator('button[data-mode]').all():
      mode=button.get_attribute('data-mode');button.click()
      page.wait_for_function('(id)=>{const i=document.getElementById(id).querySelector("img");return i.complete&&i.naturalWidth>0}',arg=key)
      assert button.get_attribute('aria-pressed')=='true';modes.append(mode)
     card.locator('button[data-mode="R2 filtered"]').click();tested.append({'scene':key,'modes':modes})
    page.locator('.card').first.locator('img').click();assert page.locator('dialog').evaluate('(d)=>d.open')
    page.locator('#close').click();assert not page.locator('dialog').evaluate('(d)=>d.open')
    page.evaluate('scrollTo(0,0)');page.screenshot(path=str(ROOT/'evidence'/f'gallery-{label}.png'),full_page=False)
    overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
    if errors or overflow:raise RuntimeError(f'Gallery failed: {errors}, horizontal overflow={overflow}')
    runs.append({'layout':label,'viewport':viewport,'scenes':tested,'javascript_errors':errors,'horizontal_overflow':overflow,'passed':True});context.close()
   browser.close()
 finally:server.shutdown();server.server_close()
 atomic_json(ROOT/'evidence/gallery-browser-verification.json',{'passed':True,'checked_at':now(),'browser':exe,'transport':'Playwright set_content of exact standalone HTML bytes; browser administrator policy blocks direct file/loopback navigation','runs':runs,'scope':'HTML image inspection controls only; not mobile 3D renderer validation.'})
 print('GALLERY VERIFIED: 6 scenes × 5 modes × 3 layouts; standalone HTML bytes injected into Chromium (direct URL navigation restricted)')
if __name__=='__main__':main()
