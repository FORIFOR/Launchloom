"""Real local studio: empty views, setup dialog and unchanged consent defaults."""
from pathlib import Path
import json, secrets, tempfile, threading, time
import uvicorn
from playwright.sync_api import sync_playwright, expect
from launchloom.config import Settings
from launchloom.server import create_app

out=Path('ui-review');out.mkdir(exist_ok=True);report=[]
with tempfile.TemporaryDirectory() as directory:
    token=secrets.token_urlsafe(32)
    app=create_app(Settings(data_dir=Path(directory),token=token,port=8787,enable_live_publish=False,enable_paid_generation=False),run_worker=False)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8787,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.1)
    else:raise RuntimeError('Local studio failed to start')
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            for width in [390,1440]:
                for language in ['ja','en']:
                    context=browser.new_context(viewport={'width':width,'height':900},locale='ja-JP',reduced_motion='reduce')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto('http://127.0.0.1:8787/',wait_until='networkidle')
                    page.locator('#access-token').fill(token);page.locator('#access-form button').click()
                    page.locator('#access-dialog').wait_for(state='hidden')
                    for selector in ['#language-toggle','#settings-button']:
                        control=page.locator(selector)
                        expect(control).to_be_visible()
                        box=control.bounding_box()
                        assert box and box['width']>=44 and box['height']>=44, f'{selector} target too small'
                    if language=='en':page.locator('#language-toggle').click()
                    expect(page.locator('html')).to_have_attribute('lang',language)
                    page.locator('#settings-button').click()
                    page.locator('#settings-dialog').wait_for(state='visible')
                    page.keyboard.press('Escape');page.locator('#settings-dialog').wait_for(state='hidden')
                    report.append({'width':width,'language':language,'view':'language-and-settings','visible_targets':True,'native_click':True,'settings_open_and_close':True})
                    for tab in ['film','site','distribution','results','activity']:
                        page.locator(f'#nav [data-tab="{tab}"]').click()
                        page.wait_for_timeout(150)
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),f'{tab} overflow'
                        assert page.locator('#workbench').inner_text().strip(),f'{tab} empty DOM'
                        report.append({'width':width,'language':language,'view':tab,'actual_server':True,'no_overflow':True,'state':'empty workspace'})
                    page.locator('#new-button').click();dialog=page.locator('#create-dialog');dialog.wait_for(state='visible')
                    for name in ['external_data_consent','allow_site_writes','staging_confirmed','media_rights']:
                        assert not dialog.locator(f'[name="{name}"]').is_checked(),name
                    assert dialog.locator('[name="review_plan"]').is_checked()
                    assert dialog.locator('[name="claims_confirmed"]').get_attribute('required') is not None
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),'dialog overflow'
                    page.screenshot(path=str(out/f'studio-dialog-{language}-{width}.png'),full_page=True)
                    page.keyboard.press('Escape');dialog.wait_for(state='hidden')
                    assert not errors,errors
                    report.append({'width':width,'language':language,'view':'create-dialog','consent_defaults_preserved':True,'escape_closes':True})
                    context.close()
            browser.close()
    finally:server.should_exit=True;thread.join(timeout=10)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
