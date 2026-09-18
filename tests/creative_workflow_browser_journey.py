"""Browser workflow with a labelled model test double; no live AI or social call.

Reuse real login/render/decode/adoption regression, then exercise proposal review,
apply/re-render, measured frame QA and synchronized ZIP creation in the same app.
"""
from __future__ import annotations
import io
import json
import os
import zipfile
from pathlib import Path

import creative_browser_journey as journey
from playwright.sync_api import expect
from launchloom.creative_assistant import EditPlan
import launchloom.creative_workflow_api as workflow

calls=[]
async def model_double(settings, context, frames=None):
    assert frames is None
    calls.append(context)
    return EditPlan(summary='Test double: a clearer opening',operations=[
        {'op':'text','scene_id':'opening','layer_id':'headline','text':'伝えたいことを、ひとつに。'},
        {'op':'duration','scene_id':'opening','seconds':1.2}]),{'total_tokens':0}


def extra_checks(page,client,cid,output):
    page.locator('#ai-edit-panel summary').click()
    expect(page.locator('#ai-provider')).to_contain_text('test-double')
    page.locator('#ai-consent').check()
    page.locator('#ai-instruction').fill('冒頭を短い日本語コピーにし、読むための時間を少し増やしてください。')
    before=client.get(f'/api/campaigns/{cid}/creative-spec').json()['revision']
    page.locator('#ai-propose').click()
    expect(page.locator('#proposal')).to_be_visible()
    assert client.get(f'/api/campaigns/{cid}/creative-spec').json()['revision']==before
    assert len(calls)==1
    page.locator('#proposal-reviewed').check()
    page.locator('#apply-render-proposal').click()
    expect(page.locator('#proposal')).to_be_hidden()
    expect(page.locator('#message')).to_contain_text('レンダーが完了',timeout=60000)
    after=client.get(f'/api/campaigns/{cid}/creative-spec').json()
    assert after['revision']!=before and after['spec']['scenes'][0]['seconds']==1.2
    jobs=client.get(f'/api/campaigns/{cid}/creative-renders').json()['items']
    assert jobs[0]['revision']==after['revision'] and jobs[0]['state']=='ready'
    assert all(x['scene_id']=='opening' for x in jobs[0]['result']['scenes'] if not x['reused'])
    page.locator('#inspect-quality').click()
    expect(page.locator('#workflow-status')).to_contain_text('品質検査が完了',timeout=30000)
    expect(page.locator('#quality-results')).to_contain_text('実フレーム')
    page.locator('#kit-panel summary').click()
    page.locator('#kit-reviewed').check()
    page.locator('#build-kit').click()
    expect(page.locator('#kit-links')).to_be_visible(timeout=30000)
    archive=client.get(page.locator('#kit-download').get_attribute('href'))
    archive.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(archive.content)) as kit:
        assert kit.testzip() is None
        assert '伝えたいことを、ひとつに。' in kit.read('site/index.html').decode()
        assert '伝えたいことを、ひとつに。' in kit.read('posts.json').decode()
        assert json.loads(kit.read('manifest.json'))['creative_revision']==after['revision']
    assert len(client.get(f'/api/campaigns/{cid}/final-films').json()['items'])==1
    page.screenshot(path=str(output/'creative-workflow-desktop.png'),full_page=True)
    (output/'workflow-result.json').write_text(json.dumps({
        'model':'test-double (not live AI)', 'model_calls':len(calls),'reviewed_multiscene_edit':True,
        'real_render':True,'synchronized_kit':True,'frame_qa':True,'existing_film_unchanged':True,
        'automatic_publication':False},ensure_ascii=False,indent=2))


if __name__=='__main__':
    workflow.request_plan=model_double
    original=journey.create_app
    def create_app(settings,**kwargs):
        settings.enable_creative_ai=True
        settings.llm_base='http://127.0.0.1:1/v1' # never contacted: injected test double
        settings.llm_model='test-double'
        return original(settings,**kwargs)
    journey.create_app=create_app
    journey.extra_checks=extra_checks
    os.environ['CREATIVE_BROWSER_ARTIFACTS']='creative-browser-artifacts/workflow'
    journey.main()
