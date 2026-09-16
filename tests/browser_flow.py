"""Real localhost browser acceptance: create → scenes → import → review → dry-run.

No external providers are enabled. The imported film is the repository's existing
local output sample. This is a real UI recording, not a fake Seedance/Adobe run.
Run: python tests/browser_flow.py --output /tmp/launchloom-browser
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
TOKEN='browser-fixture-local-access-token'


def main(output:Path,record:bool=False):
    output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='launchloom-browser-') as tmp:
        env={**os.environ,'LAUNCHLOOM_DATA':tmp,'LAUNCHLOOM_TOKEN':TOKEN,'ENABLE_LIVE_PUBLISH':'0',
             'ENABLE_PAID_GENERATION':'0','FAL_KEY':'','POSTIZ_API_KEY':'','POSTIZ_BASE_URL':'','COMFY_BASE_URL':'','LLM_BASE_URL':''}
        with (output/'server.log').open('wb') as log:
            server=subprocess.Popen([sys.executable,'-m','launchloom','serve','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    try:
                        if httpx.get(base+'/healthz',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    if server.poll() is not None:raise RuntimeError('Studio failed to start; see server.log')
                    time.sleep(.1)
                errors=[];report={}
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True, executable_path=os.getenv("CHROMIUM_EXECUTABLE") or shutil.which("chromium"))
                    context=browser.new_context(viewport={'width':1365,'height':900},locale='ja-JP',
                        **({'record_video_dir':str(output/'recording'),'record_video_size':{'width':1365,'height':900}} if record else {}))
                    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                    # No external requests are needed for this acceptance flow.
                    outbound=[]
                    def route(r):
                        if r.request.url.startswith(base+'/'):r.continue_()
                        else:outbound.append(r.request.url);r.abort()
                    page.route('**/*',route)
                    page.goto(base);page.locator('#access-token').fill(TOKEN)
                    page.locator('#access-form button').click();page.locator('#access-dialog').wait_for(state='hidden')
                    page.locator('#new-button').click()
                    form=page.locator('#create-form')
                    form.locator('[name="name"]').fill('Launchloom · ローカル操作例')
                    form.locator('[name="audience"]').fill('製品を紹介したい開発者')
                    form.locator('[name="tagline"]').fill('作った動画を、届ける準備まで。')
                    form.locator('[name="features"]').fill('完成動画を取り込む | MP4を確認して配信に使えます | このローカル操作例で確認')
                    form.locator('[name="claims_confirmed"]').check()
                    form.locator('[name="workflow"]').select_option('production')
                    for el in form.locator('[name="channels"]').all():
                        if el.get_attribute('value')=='x':el.check()
                        else:el.uncheck()
                    form.locator('#create-submit').click()
                    page.wait_for_url('**/production?campaign=*');page.locator('#editor').wait_for(state='visible')
                    cid=page.url.split('campaign=')[1];report['onboarding_to_board']=True
                    page.locator('#title').fill('製品紹介 / シーンから配信まで')
                    page.locator('#scenes textarea').first.fill('紙の質感と、静かな光。製品の操作画面とは分けて使用する。')
                    page.locator('#save').click();page.wait_for_function("document.querySelector('#save-state').textContent.includes('保存済み')")
                    page.locator('#add').click();assert page.locator('.scene').count()==4
                    page.locator('.scene').last.locator('[data-action="up"]').click()
                    page.locator('.scene').nth(2).locator('[data-action="remove"]').click();assert page.locator('.scene').count()==3
                    with page.expect_download() as download:page.locator('#export').click()
                    download.value.save_as(output/'production.zip');report['scene_edit_save_export']=True
                    page.locator('#final-title').fill('Launchloom紹介動画 / 確認用')
                    page.locator('#final-file').set_input_files(ROOT/'homepage/ja/film.mp4')
                    page.locator('#final-ai').select_option('false');page.locator('#final-rights').check()
                    page.locator('#final-upload').click()
                    page.locator('.final-card button').first.wait_for(state='visible',timeout=90000)
                    page.locator('.final-card button').first.click();page.locator('#film-review').wait_for(state='visible')
                    page.locator('#review-video').evaluate('(v)=>{v.muted=true;return v.play()}')
                    page.wait_for_timeout(1200)
                    assert page.locator('#review-video').evaluate('(v)=>v.currentTime>0.3')
                    page.locator('#final-content-reviewed').check();page.locator('#final-rights-reviewed').check()
                    page.locator('#adopt-film').click();page.locator('#film-review').wait_for(state='hidden')
                    page.locator('#to-distribution').wait_for(state='visible')
                    page.screenshot(path=str(output/'production-desktop.png'),full_page=True)
                    report['real_mp4_import_review_select']=True
                    page.locator('#to-distribution').click();page.wait_for_url('**tab=distribution')
                    page.locator('[data-review]').first.click();page.locator('#review-dialog').wait_for(state='visible')
                    page.locator('#dry-run').click();page.locator('#dry-run-output').wait_for(state='visible')
                    dry=json.loads(page.locator('#dry-run-output').inner_text())
                    assert dry['dry_run'] and dry['network_requests']==0
                    assert page.locator('#submit-publication').is_disabled()
                    report['publication_dry_run_and_live_gate']=True
                    page.screenshot(path=str(output/'publication-review.png'))
                    page.locator('[data-close="review-dialog"]').click()
                    page.locator('#production-link').click();page.wait_for_url('**/production?campaign='+cid)
                    page.locator('#editor').wait_for(state='visible');report['campaign_context_roundtrip']=True
                    page.set_viewport_size({'width':390,'height':844})
                    page.screenshot(path=str(output/'production-mobile.png'),full_page=True)
                    report['no_mobile_overflow']=page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert report['no_mobile_overflow']
                    # Final artifact must be visible to the main app, but never released.
                    c=page.request.get(base+'/api/campaigns/'+cid).json()
                    assert c['publication_ready'] and not c['released']
                    assert len(c['publications'])==1 and c['publications'][0]['state']=='draft'
                    assert not outbound,outbound
                    assert not errors,errors
                    report.update(page_errors=errors,external_requests=outbound,external_posting=False)
                    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
                    context.close();browser.close()
                print(json.dumps(report,ensure_ascii=False))
            finally:
                server.terminate()
                try:server.wait(timeout=8)
                except subprocess.TimeoutExpired:server.kill();server.wait()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--record',action='store_true')
    args=parser.parse_args();main(args.output,args.record)
