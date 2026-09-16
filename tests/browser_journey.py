"""Real localhost browser journey. No provider keys or external publishing.

Run: python tests/browser_journey.py
Optional: LAUNCHLOOM_BROWSER_ARTIFACTS=/path/to/screenshots
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright
from launchloom.config import Settings
from launchloom.models import Brief
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.server import create_app


def main():
    artifacts=Path(os.getenv('LAUNCHLOOM_BROWSER_ARTIFACTS','/tmp/launchloom-browser-artifacts'))
    artifacts.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='launchloom-browser-') as temp:
        settings=Settings(data_dir=Path(temp),token='browser-test-local-access-token-only',
            fal_key='',llm_key='',postiz_key='',postiz_base='',comfy_base='',tracking_base='',
            enable_live_publish=False,enable_paid_generation=False)
        app=create_app(settings,run_worker=False)
        first=app.state.store.create_campaign(Brief.model_validate(SAMPLE_BRIEF).model_dump())
        other=Brief.model_validate(SAMPLE_BRIEF).model_dump();other['name']='別キャンペーン'
        app.state.store.create_campaign(other)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
        worker=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);worker.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        base=f'http://127.0.0.1:{port}'
        errors=[];unexpected=[]
        try:
            with sync_playwright() as p:
                executable=os.getenv('BROWSER_EXECUTABLE') or shutil.which('chromium')
                browser=p.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':1440,'height':1000},locale='ja-JP')
                def route(r):
                    if r.request.url.startswith(base+'/'):r.continue_()
                    else:unexpected.append(r.request.url);r.abort()
                context.route('**/*',route)
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/?campaign='+first['id'])
                page.locator('#access-token').fill(settings.token)
                page.locator('#access-form button').click()
                page.wait_for_function("!document.querySelector('#access-dialog').open")
                page.wait_for_function('(id)=>document.querySelector("#campaign-select").value===id',arg=first['id'])
                assert page.locator('#campaign-select').input_value()==first['id']
                page.locator('#production-link').click()
                page.locator('#editor').wait_for(state='visible')
                assert 'campaign='+first['id'] in page.url
                assert page.locator('#campaign').input_value()==first['id']
                page.locator('#title').fill('Launchloom — 制作から公開前確認まで')
                page.locator('#save').click()
                page.wait_for_function("document.querySelector('#save-state').textContent.includes('保存済み')")
                with page.expect_download() as download:
                    page.locator('#export').click()
                assert download.value.suggested_filename=='launchloom-production.zip'
                page.locator('.final-import input[name=file]').set_input_files(str(root/'homepage/ja/film.mp4'))
                page.locator('.final-import input[name=title]').fill('紹介動画 v1 — ローカル出力の検証用')
                page.locator('.final-import input[name=rights]').check()
                page.locator('.final-import button[type=submit]').click()
                page.locator('.final-review video').wait_for(timeout=120000)
                page.wait_for_function("document.querySelector('.final-review video').readyState>=1")
                page.locator('.final-review video').evaluate('(video)=>video.play()')
                page.wait_for_function("document.querySelector('.final-review video').currentTime>0.2")
                page.locator('.final-review video').evaluate('(video)=>video.pause()')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(artifacts/'production-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(artifacts/'production-mobile.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('.final-review a').click()
                page.locator('[data-post]').first.wait_for()
                page.wait_for_function('(id)=>document.querySelector("#campaign-select").value===id',arg=first['id'])
                assert page.locator('#campaign-select').input_value()==first['id']
                assert page.locator('.media').first.input_value().startswith('finals/')
                page.locator('[data-review]').first.click()
                page.locator('#review-dialog').wait_for(state='visible')
                assert '/finals/' in page.locator('.review-video').get_attribute('src')
                assert page.locator('#submit-publication').is_disabled()
                page.locator('#dry-run').click()
                page.wait_for_function("document.querySelector('#dry-run-output').textContent.includes('network_requests')")
                dry=json.loads(page.locator('#dry-run-output').text_content())
                assert dry['network_requests']==0
                page.screenshot(path=str(artifacts/'publication-review.png'),full_page=True)
                assert not errors,errors
                assert not unexpected,unexpected
                browser.close()
        finally:
            server.should_exit=True;worker.join(timeout=5);sock.close()
        report={'real_http_application':True,'campaign_preserved':True,'plan_saved':True,
                'handoff_downloaded':True,'mp4_imported':True,'preview_playback':True,
                'publication_media_preserved':True,'dry_run_network_requests':0,
                'live_publish_disabled':True,'desktop_mobile_overflow':False,
                'page_errors':errors,'unexpected_requests':unexpected}
        (artifacts/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
