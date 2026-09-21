"""Real offline first success/recovery. Chrome and FFmpeg required; no user data.

python tests/first_success_browser_journey.py --output /tmp/launchloom-first-success
The child --serve mode is internal and uses a disposable, explicitly offline studio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from playwright.sync_api import sync_playwright
from launchloom.config import Settings
from launchloom.models import Brief
from launchloom.pipeline import SAMPLE_BRIEF

TOKEN='first-success-local-test-token-only'


def offline_settings(data,port):
    return Settings(data_dir=data,port=port,token=TOKEN,
        llm_base='',llm_key='',llm_model='',fal_key='',fal_model='',comfy_base='',
        postiz_base='',postiz_key='',tracking_base='',deploy_dir='',capture_origins='',
        enable_live_publish=False,enable_paid_generation=False,budget_usd=0,
        enable_local_agents=False,enable_after_effects=False,enable_creative_ai=False,
        enable_creative_vision=False,openai_api_key='',anthropic_api_key='',
        codex_executable=None,claude_executable=None,afterfx_executable=None,aerender_executable=None)


def serve(data,port):
    import uvicorn
    from launchloom.server import create_app
    uvicorn.run(create_app(offline_settings(data,port)),host='127.0.0.1',port=port,
                log_level='error',access_log=False)


def source_fingerprint():
    paths=sorted(p for folder in ('launchloom','examples','tests') for p in (ROOT/folder).rglob('*')
                 if p.suffix in {'.py','.js','.css','.html'} and '__pycache__' not in p.parts)
    return hashlib.sha256(''.join(str(p.relative_to(ROOT))+':'+hashlib.sha256(p.read_bytes()).hexdigest()+'\n' for p in paths).encode()).hexdigest()


def main(output, browser_executable=None, revision=None):
    output.mkdir(parents=True,exist_ok=True)
    report={'revision':revision or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_sha256':source_fingerprint(),'environment':{'os':platform.platform(),'cpu':platform.machine(),'python':sys.version},
            'command':[sys.executable,*sys.argv], 'checks':[], 'external_requests':[], 'page_errors':[]}
    def record(name,observed,status='PASS'):
        report['checks'].append({'id':name,'status':status,'observed':observed})
        print(name,status,observed,flush=True)
    def wait_state(client,cid,states,timeout=180):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            data=client.get('/api/campaigns/'+cid).json()
            if data['state'] in states:return data
            if data['state']=='failed':raise AssertionError(data.get('error'))
            time.sleep(.2)
        raise AssertionError('Timed out waiting for '+str(states))
    process=None
    try:
        with tempfile.TemporaryDirectory(prefix='launchloom-first-success-') as tmp:
            data=Path(tmp)
            sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
            base=f'http://127.0.0.1:{port}'
            # Preserve installed runtime paths (e.g. Docker's /opt/playwright),
            # while excluding provider credentials and user feature settings.
            child_env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','SYSTEMROOT','LANG',
                                               'PLAYWRIGHT_BROWSERS_PATH','CHROMIUM_EXECUTABLE') if k in os.environ}
            child_env.update(PYTHONPATH=str(ROOT),LAUNCHLOOM_TOKEN=TOKEN)
            def start_server():
                log=(output/'server.log').open('a')
                child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(data),'--port',str(port)],
                    cwd=data,env=child_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                log.close()
                with httpx.Client(trust_env=False) as probe:
                    for _ in range(150):
                        try:
                            if probe.get(base+'/healthz',timeout=.5).status_code==200:return child
                        except httpx.HTTPError:pass
                        if child.poll() is not None:raise AssertionError('Server exited; see server.log')
                        time.sleep(.1)
                child.kill();child.wait();raise AssertionError('Server failed to start')
            process=start_server()
            with httpx.Client(base_url=base,headers={'Authorization':'Bearer '+TOKEN},trust_env=False,timeout=30) as api:
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(
                        executable_path=browser_executable,
                        channel=None if browser_executable else 'chrome',
                        chromium_sandbox=True,headless=True)
                    report['environment']['browser_executable']=browser_executable or 'Chrome channel'
                    report['environment']['chromium_sandbox']=True
                    report['environment']['chrome']=browser.version
                    report['environment']['ffmpeg']=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]
                    context=browser.new_context(viewport={'width':1440,'height':1000},locale='ja-JP')
                    requests=[]
                    def guard(route):
                        url=route.request.url
                        if url.startswith(base+'/'):route.continue_()
                        else:report['external_requests'].append(url);route.abort()
                    context.route('**/*',guard)
                    page=context.new_page()
                    page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
                    page.on('request',lambda request:requests.append((request.method,request.url.split('?',1)[0])))
                    def tab_to(selector):
                        for _ in range(160):
                            if page.locator(selector).first.evaluate('(el)=>el===document.activeElement'):return
                            page.keyboard.press('Tab')
                        raise AssertionError('Not reachable by Tab: '+selector)
                    def no_overflow(name):
                        dimensions=page.evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth})')
                        assert dimensions['document']<=dimensions['viewport']+1,(name,dimensions)
                        return dimensions
                    page.goto(base)
                    page.locator('#access-dialog[open]').wait_for()
                    assert page.locator('#access-token').evaluate('(el)=>el===document.activeElement')
                    page.keyboard.insert_text(TOKEN);page.keyboard.press('Tab');page.keyboard.press('Enter')
                    page.locator('#access-dialog').wait_for(state='hidden')
                    page.locator('#first-success-title').wait_for()
                    assert page.locator('[data-sample]').count()==1
                    assert page.locator('.production-entry').is_hidden()
                    page.screenshot(path=str(output/'empty-desktop.png'),full_page=True)
                    page.set_viewport_size({'width':390,'height':844});no_overflow('empty mobile')
                    page.screenshot(path=str(output/'empty-mobile.png'),full_page=True)
                    record('F1','Japanese empty state names results, first action, editable sample and no-charge boundary; 390px reflow')
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.locator('#language-toggle').click()
                    page.wait_for_function("() => document.documentElement.lang==='en'")
                    assert 'A film, landing page' in page.locator('#first-success-title').inner_text()
                    page.screenshot(path=str(output/'empty-english.png'),full_page=True)
                    page.locator('#language-toggle').click();page.wait_for_function("() => document.documentElement.lang==='ja'")
                    # Lose a response after the actual server has committed it, not a fake server.
                    lost=[]
                    def lose_creation(route):
                        response=route.fetch();lost.append(response.json()['id']);route.abort('failed')
                        page.unroute('**/api/demo?**',lose_creation)
                    page.route('**/api/demo?**',lose_creation)
                    started=time.monotonic();tab_to('[data-sample]');page.keyboard.press('Enter')
                    page.locator('#connection-notice').wait_for()
                    assert len(api.get('/api/campaigns').json())==1
                    assert page.locator('[data-sample]').is_enabled()
                    page.reload()
                    page.locator('#review-panel-title').wait_for(timeout=180000)
                    assert page.locator('#plan-concept').is_hidden()
                    assert page.locator('#plan-direction').is_hidden()
                    assert page.locator('#approve-plan').inner_text()=='保存して動画を作る →'
                    # A successful replay POST followed by a lost GET must retain the intent too.
                    cid=lost[0]
                    def lose_followup_read(route):
                        route.abort('failed');page.unroute('**/api/campaigns/'+cid,lose_followup_read)
                    page.route('**/api/campaigns/'+cid,lose_followup_read)
                    tab_to('#demo-button');page.keyboard.press('Enter')
                    page.locator('#connection-notice').wait_for()
                    tab_to('#demo-button');page.keyboard.press('Enter')
                    page.locator('#connection-notice').wait_for(state='hidden')
                    page.locator('#review-panel-title').wait_for(timeout=180000)
                    cid=lost[0]
                    assert len(api.get('/api/campaigns').json())==1
                    from launchloom.store import Store
                    store=Store(data/'launchloom.sqlite3')
                    with store.connect() as db:
                        assert db.execute('SELECT count(*) FROM jobs WHERE campaign_id=?',(cid,)).fetchone()[0]==1
                    record('R2','Lost committed demo response + reload; then lost follow-up GET after successful POST; same-key replay keeps exactly one campaign/job')
                    # Synthetic composition is recorded separately from a real OS IME trial.
                    tab_to('.scene-caption')
                    session=context.new_cdp_session(page)
                    session.send('Input.imeSetComposition',{'text':'へんしゅう','selectionStart':0,'selectionEnd':5})
                    assert page.locator('#review-panel-title').is_visible()
                    session.send('Input.insertText',{'text':'編集した字幕'})
                    page.keyboard.press('Meta+A' if sys.platform=='darwin' else 'Control+A')
                    caption='大切なことから、一つずつ。'
                    page.keyboard.insert_text(caption)
                    assert page.locator('#plan-save-state').inner_text()=='未保存の変更があります'
                    page.set_viewport_size({'width':390,'height':844});no_overflow('review mobile')
                    page.locator('.scene-title').first.fill('長い日本語の見出し'*8)
                    no_overflow('long Japanese headline')
                    page.screenshot(path=str(output/'review-mobile-long.png'),full_page=True)
                    original=api.get('/api/campaigns/'+cid).json()['plan']['scenes'][0]['title']
                    page.locator('.scene-title').first.fill(original)
                    tab_to('#save-plan');page.keyboard.press('Enter')
                    page.wait_for_function("() => document.querySelector('#toast').textContent.includes('保存しました')")
                    assert api.get('/api/campaigns/'+cid).json()['plan']['scenes'][0]['caption']==caption
                    assert page.locator('#save-plan').evaluate('(el)=>el===document.activeElement'), 'saving must retain keyboard focus'
                    assert page.locator('#plan-save-state').inner_text()=='保存済みの内容を表示しています'
                    page.reload();page.locator('#review-panel-title').wait_for()
                    assert page.locator('.scene-caption').first.input_value()==caption
                    # A newer fixture must not change the selected campaign on reload.
                    other=api.post('/api/campaigns',json=Brief.model_validate(SAMPLE_BRIEF).model_dump()).json()
                    page.reload();page.locator('#review-panel-title').wait_for()
                    assert page.locator('#campaign-select').input_value()==cid
                    # Lose one GET while unsaved copy is present; explicit recheck must preserve it.
                    unsaved='再接続しても残る字幕'
                    page.locator('.scene-caption').first.fill(unsaved)
                    def lose_get(route):
                        route.abort('failed');page.unroute('**/api/campaigns/'+cid,lose_get)
                    page.route('**/api/campaigns/'+cid,lose_get)
                    page.locator('#campaign-select').select_option(cid)
                    page.locator('#connection-notice').wait_for()
                    before=len(requests);tab_to('#check-connection');page.keyboard.press('Enter')
                    page.locator('#connection-notice').wait_for(state='hidden')
                    assert page.locator('.scene-caption').first.input_value()==unsaved
                    assert all(method=='GET' for method,url in requests[before:])
                    assert 'campaign='+cid in page.url
                    page.locator('.scene-caption').first.fill(caption)
                    record('R1','GET outage is explicitly unconfirmed; GET-only recheck retains unsaved caption and selected URL')
                    review_client=subprocess.run([sys.executable,str(ROOT/'examples/client.py'),'--base',base,'--campaign',cid],env=child_env,cwd=data,capture_output=True,text=True,timeout=30)
                    (output/'client-review.log').write_text(review_client.stdout+review_client.stderr)
                    assert review_client.returncode==2
                    page.emulate_media(reduced_motion='reduce')
                    assert page.evaluate("getComputedStyle(document.querySelector('.button')).animationName")=='none'
                    tab_to('#approve-plan');page.keyboard.press('Enter')
                    page.locator('#result-title').wait_for(timeout=180000)
                    elapsed=round(time.monotonic()-started,2)
                    assert elapsed<180
                    ready=api.get('/api/campaigns/'+cid).json()
                    assert ready['state']=='ready' and ready['released']==0 and ready['publications']==[]
                    record('F2',{'seconds_including_failure_exercises':elapsed,'caption':caption,'state':'ready','review_client_exit':2})
                    for ratio in ('landscape','portrait'):
                        page.locator('[data-ratio="'+ratio+'"]').click()
                        page.locator('#film-player').evaluate('(v)=>v.play()')
                        page.wait_for_function("() => document.querySelector('#film-player').currentTime>.4 && document.querySelector('#film-player').getVideoPlaybackQuality().totalVideoFrames>0")
                        page.locator('#film-player').evaluate('(v)=>v.pause()')
                    with page.expect_download() as download:
                        tab_to('a[download]');page.keyboard.press('Enter')
                    kit=output/'launch-kit.zip';download.value.save_as(kit)
                    with zipfile.ZipFile(kit) as archive:
                        manifest=json.loads(archive.read('manifest.json'))
                        for name,entry in manifest['files'].items():
                            assert hashlib.sha256(archive.read(name)).hexdigest()==entry['sha256'],name
                        assert caption in archive.read('captions.srt').decode()
                        assert json.loads(archive.read('storyboard.json'))['scenes'][0]['caption']==caption
                        names=archive.namelist()
                        assert not any(name.startswith(('input/','capture/')) or name in ('brief.json','access-token') for name in names)
                        for feature in SAMPLE_BRIEF['features']:
                            assert feature['evidence'] not in archive.read('campaign.json').decode()
                        for ratio,shape in [('landscape',(1920,1080)),('portrait',(1080,1920))]:
                            film=data/(ratio+'.mp4');film.write_bytes(archive.read(ratio+'.mp4'))
                            decoded=subprocess.run(['ffmpeg','-v','error','-i',str(film),'-f','null','-'],capture_output=True,text=True,timeout=60)
                            assert decoded.returncode==0,decoded.stderr
                            assert (manifest['videos'][ratio]['width'],manifest['videos'][ratio]['height'])==shape
                        assert 'disabled' in archive.read('site/index.html').decode()
                    record('F3',{'kit':str(kit),'members':len(names),'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),'both_browser_decoded':True,'both_ffmpeg_exit':0})
                    no_overflow('ready mobile');page.screenshot(path=str(output/'ready-mobile.png'),full_page=True)
                    page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(output/'ready-desktop.png'),full_page=True)
                    page.locator('[data-go="site"]').first.click();page.locator('.site-frame').wait_for()
                    lp=page.frame_locator('.site-frame');lp.locator('#product-film').evaluate('(v)=>v.play()')
                    page.wait_for_function("() => document.querySelector('iframe').contentDocument.querySelector('video').currentTime>.3")
                    lp.locator('#product-film').evaluate('(v)=>v.pause()')
                    page.locator('[data-tab="distribution"]').click();page.locator('.post-content').first.wait_for()
                    assert page.locator('.post-content').count()==3
                    # Native dialog keyboard Escape should restore the invoking control.
                    tab_to('#new-button');page.keyboard.press('Enter');page.locator('#create-dialog[open]').wait_for()
                    for _ in range(4):
                        page.keyboard.press('Tab')
                        assert page.evaluate("document.querySelector('#create-dialog').contains(document.activeElement)")
                    page.keyboard.press('Escape')
                    assert page.locator('#new-button').evaluate('(el)=>el===document.activeElement')
                    record('U2','Keyboard login/start/edit/save/render/download; native dialog focus containment/return; reduced-motion animations disabled')
                    record('U3-composition','Chrome CDP composition/commit preserves Japanese caption; no implicit submit')
                    record('U3-native-IME','OS input-method candidate selection was not exercised','BLOCKED')
                    record('U1-zoom','390px and long-input reflow passed; native 200% browser zoom requires separate interactive measurement','BLOCKED')
                    sdk=subprocess.run([sys.executable,str(ROOT/'examples/client.py'),'--base',base,'--campaign',cid,'--download',str(data/'client-kit.zip')],env=child_env,cwd=data,capture_output=True,text=True,timeout=40)
                    (output/'client-ready.log').write_text(sdk.stdout+sdk.stderr)
                    assert sdk.returncode==0
                    assert (data/'client-kit.zip').read_bytes()==kit.read_bytes()
                    assert len(api.get('/api/campaigns').json())==2
                    record('C2','Client --campaign exits 2 at review and 0 for ready; downloaded ZIP matches browser bytes; no new campaign')
                    # Kill the actual disposable server process while a real render is running.
                    recovery=other['id']
                    api.post('/api/campaigns/'+recovery+'/build',json={'capture_mode':'none','quality':'draft','animation_seconds':9}).raise_for_status()
                    deadline=time.monotonic()+40
                    while time.monotonic()<deadline:
                        state=api.get('/api/campaigns/'+recovery).json()
                        if state['stage']=='render' and state['state']=='building':break
                        time.sleep(.1)
                    else:raise AssertionError('Recovery fixture never entered real render')
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
                    process=start_server()
                    recovered=api.get('/api/campaigns/'+recovery).json()
                    assert recovered['state']=='interrupted'
                    page.goto(base+'/?campaign='+recovery)
                    page.locator('#retry-button').wait_for()
                    tab_to('#retry-button');page.keyboard.press('Enter')
                    page.locator('#result-title').wait_for(timeout=180000)
                    assert api.get('/api/campaigns/'+recovery).json()['state']=='ready'
                    assert 'campaign='+recovery in page.url
                    assert len(api.get('/api/campaigns').json())==2
                    record('R3','Actual process-group kill during FFmpeg render; restart reports interrupted; explicit UI retry completes same campaign')
                    assert not report['external_requests'],report['external_requests']
                    assert not report['page_errors'],report['page_errors']
                    record('network','No external browser requests; all external adapters explicitly disabled in server fixture')
                    browser.close()
        report['exit_code']=0
    except BaseException:
        report['exit_code']=1;report['failure']=traceback.format_exc()
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/launchloom-first-success'))
    parser.add_argument('--serve',type=Path);parser.add_argument('--port',type=int)
    parser.add_argument('--browser-executable',help='Explicit installed Chromium binary for Linux; defaults to Chrome channel')
    parser.add_argument('--revision',help='Host git revision when the isolated runtime has no git executable; source fingerprint is always computed')
    args=parser.parse_args()
    if args.serve:serve(args.serve,args.port)
    else:main(args.output.resolve(),args.browser_executable,args.revision)
