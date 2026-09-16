"""Validate both deployable pages, local links and all videos in a real browser."""
from __future__ import annotations
import argparse
import functools
import http.server
import json
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent


def main(site:Path,evidence:Path):
    evidence.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='launchloom-site-') as tmp:
        root=Path(tmp);shutil.copytree(ROOT,root,dirs_exist_ok=True);shutil.copytree(site,root,dirs_exist_ok=True)
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root))
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        errors=[];report={}
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
                for lang,path in [('ja','/ja/'),('en','/')]:
                    page=browser.new_page(viewport={'width':1440,'height':960},locale='ja-JP' if lang=='ja' else 'en-US')
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(base+path,wait_until='load')
                    assert page.locator('html').get_attribute('lang')==lang
                    ids=page.locator('[id]').evaluate_all('(nodes)=>nodes.map(n=>n.id)');assert len(ids)==len(set(ids))
                    for href in page.locator('a[href]').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("href"))'):
                        if href.startswith('#'):assert href[1:] in ids
                        elif not href.startswith(('http:','https:','mailto:')):
                            r=page.request.get(base+path+href);assert r.ok,f'Missing link {path+href}: {r.status}'
                    assert page.locator('video').count()==3
                    for index,video in enumerate(page.locator('video').all()):
                        assert video.get_attribute('controls') is not None
                        await_result=video.evaluate('(v)=>{v.muted=true;return v.play()}')
                        page.wait_for_timeout(500)
                        metadata=video.evaluate('(v)=>({time:v.currentTime,width:v.videoWidth,height:v.videoHeight,error:v.error?.message})')
                        assert metadata['time']>0 and metadata['width']>0 and not metadata['error'],metadata
                        video.evaluate('(v)=>v.pause()')
                        report[f'{lang}_video_{index}']=metadata
                    page.locator('#posts summary').click();assert page.locator('.drafts li').count()==7
                    page.locator('#posts summary').click()
                    for width in [1440,390]:
                        page.set_viewport_size({'width':width,'height':960 if width==1440 else 844})
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'{lang} {width}px overflow'
                        page.screenshot(path=str(evidence/f'homepage-{lang}-{width}.png'),full_page=True)
                    page.close()
                browser.close()
            assert not errors,errors
            report.update(page_errors=errors,languages=['ja','en'],widths=[1440,390],local_links=True)
            (evidence/'homepage-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps(report,ensure_ascii=False))
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True)
    a=p.parse_args();main(a.site,a.evidence)
