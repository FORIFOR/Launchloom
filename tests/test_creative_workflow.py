import copy
import io
import json
import zipfile

import pytest

from launchloom.creative import CreativeSpec, creative_revision
from launchloom.creative_assistant import EditPlan, VisualReview
from launchloom.creative_quality import inspect_layout, repair_layout
from launchloom.creative_package import campaign_copy
from launchloom.models import Brief
from launchloom.planning import x_weight
from test_creative_api import studio, get, save, render, fixture_spec, BRIEF


def refs(client,cid):
    value=get(client,cid)
    return {k:value[k] for k in ('production_revision',)}|{'expected_revision':value['revision']}


def enable_ai(app):
    app.state.settings.enable_creative_ai=True
    app.state.settings.llm_base='https://model.example/v1'
    app.state.settings.llm_model='fake-for-tests'


def test_real_app_optional_workflows_off_by_default(studio):
    client,app,cid,_=studio
    value=client.get(f'/api/campaigns/{cid}/creative-workflow').json()
    assert not value['assistant']['enabled'] and not value['automatic_publishing']
    assert set(value['external_verification'].values())=={'not_verified_here'}


def test_ai_review_apply_is_explicit_revision_bound_and_idempotent(studio,monkeypatch):
    client,app,cid,_=studio
    save(client,cid);enable_ai(app);before=get(client,cid)
    app.state.store.release_campaign(cid,True)
    calls=[]
    async def fake(settings,ctx,frames=None):
        calls.append(ctx)
        return EditPlan(summary='Less copy',operations=[{'op':'text','scene_id':'opening','layer_id':'headline','text':'A smaller opening.'}]),{'total_tokens':30}
    monkeypatch.setattr('launchloom.creative_workflow_api.request_plan',fake)
    args={**refs(client,cid),'instruction':'冒頭を短いコピーにして','external_data_consent':False}
    url=f'/api/campaigns/{cid}/creative-spec/ai-proposal'
    assert client.post(url,json=args).status_code==422 and not calls
    args['external_data_consent']=True
    result=client.post(url,json=args)
    assert result.status_code==200,result.text
    proposal=result.json();assert proposal['changes'] and not proposal['saved']
    assert get(client,cid)['revision']==before['revision']
    apply_url=f"/api/campaigns/{cid}/creative-proposals/{proposal['id']}/apply"
    apply_args={**refs(client,cid),'fingerprint':proposal['fingerprint'],'content_reviewed':False}
    assert client.post(apply_url,json=apply_args).status_code==422
    apply_args['content_reviewed']=True
    wrong={**apply_args,'fingerprint':'0'*64}
    assert client.post(apply_url,json=wrong).status_code==409
    applied=client.post(apply_url,json=apply_args)
    assert applied.status_code==200,applied.text
    assert applied.json()['spec']['scenes'][0]['layers'][0]['text']=='A smaller opening.'
    assert client.post(apply_url,json=apply_args).status_code==200
    assert app.state.store.campaign(cid)['released']==1 and not app.state.store.publications(cid)


def test_ai_stale_response_is_rejected(studio,monkeypatch):
    client,app,cid,_=studio;save(client,cid);enable_ai(app)
    async def fake(settings,ctx,frames=None):
        with app.state.store.connect() as c:c.execute("UPDATE creative_specs SET revision='changed' WHERE campaign_id=?",(cid,))
        # Context recomputes spec hash, so change the actual document too.
        changed=fixture_spec();changed['title']='changed in other editor'
        with app.state.store.connect() as c:c.execute('UPDATE creative_specs SET spec=? WHERE campaign_id=?',(json.dumps(changed),cid))
        return EditPlan(summary='Stale',operations=[]),{}
    monkeypatch.setattr('launchloom.creative_workflow_api.request_plan',fake)
    args={**refs(client,cid),'instruction':'Change','external_data_consent':True}
    assert client.post(f'/api/campaigns/{cid}/creative-spec/ai-proposal',json=args).status_code==409


def test_bounded_repair_preserves_copy_and_semantic_fields():
    data=fixture_spec();data['scenes'][0]['layers'][0]['text']='長い文章の読みやすさを検証します。'*10
    data['scenes'][0]['layouts']={'landscape':{'y':.90,'size':.10}}
    spec=CreativeSpec.model_validate(data);before=inspect_layout(spec)
    assert before['technical_errors']>0
    plan,report=repair_layout(spec,3)
    assert report['passes']<=3 and report['provider_calls']==0
    assert all(x.op=='layout' for x in plan.operations)
    assert report['after']['technical_errors']<=before['technical_errors']
    with pytest.raises(ValueError):repair_layout(spec,4)


def test_local_repair_api_does_not_save(studio):
    client,_,cid,_=studio
    data=fixture_spec();data['scenes'][0]['layouts']={'landscape':{'y':.90,'size':.1}}
    data['scenes'][0]['layers'][0]['text']='Large text. '*15
    assert save(client,cid,data).status_code==200
    before=refs(client,cid)
    response=client.post(f'/api/campaigns/{cid}/creative-spec/repair-proposal',json={**before,'max_passes':3})
    assert response.status_code==200,response.text
    assert response.json()['report']['provider_calls']==0
    assert refs(client,cid)==before


def test_synchronized_copy_follows_layer_text_not_stale_scene_title():
    data=fixture_spec();data['scenes'][0]['title']='OLD TITLE'
    data['scenes'][0]['layers'][0]['text']='NEW HERO'
    data['scenes'][1]['layers'][0]['text']='NEW CTA'
    spec=CreativeSpec.model_validate(data)
    result=campaign_copy(spec,Brief.model_validate({**BRIEF,'product_url':'https://example.com','channels':['x','tiktok']}),'fixture')
    assert result['hero']=='NEW HERO' and result['cta']=='NEW CTA'
    assert 'OLD TITLE' not in json.dumps(result)
    assert all(p['revision']==creative_revision(spec) and p['state']=='draft' for p in result['posts'])
    assert x_weight(result['posts'][0]['content'])<=280
    assert result['posts'][1]['media']=='portrait.mp4'


def test_real_kit_is_consistent_escaped_immutable_and_nonpublishing(studio):
    client,app,cid,root=studio
    data=fixture_spec();data['outputs']=['landscape']
    data['scenes'][0]['layers'][0]['text']='<script>alert(1)</script> NEW COPY'
    save(client,cid,data);result=render(client,cid)
    args={**refs(client,cid),'content_reviewed':True,'rights_confirmed':True}
    path=f"/api/campaigns/{cid}/creative-renders/{result['id']}/kit"
    response=client.post(path,json=args)
    assert response.status_code==201,response.text
    kit=response.json();again=client.post(path,json=args)
    assert again.json()['id']==kit['id']
    archive=client.get(kit['download_url']);assert archive.status_code==200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert z.testzip() is None
        page=z.read('site/index.html').decode();assert '<script>alert' not in page and '&lt;script&gt;' in page
        assert 'NEW COPY' in page and 'NEW COPY' in z.read('posts.json').decode()
        assert 'PRIVATE' not in '\n'.join(z.read(n).decode() for n in z.namelist() if n.endswith(('.json','.html','.txt')))
        assert 'creative-spec.json' not in z.namelist()
        manifest=json.loads(z.read('manifest.json'))
        import hashlib
        for name,sha in manifest['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
        assert manifest['creative_revision']==result['revision']
    page_response=client.get(kit['preview_url']);assert page_response.status_code==200
    assert app.state.store.publications(cid)==[]
    assert not client.get(f'/api/campaigns/{cid}/final-films').json()['items']
    (root/'campaigns'/cid/'creative-kits'/kit['id']/'launch-kit.zip').write_bytes(b'changed')
    assert client.get(kit['download_url']).status_code==409


def test_kit_needs_all_formats_and_current_revision(studio):
    client,_,cid,_=studio;save(client,cid);result=render(client,cid)
    path=f"/api/campaigns/{cid}/creative-renders/{result['id']}/kit"
    args={**refs(client,cid),'content_reviewed':False,'rights_confirmed':True}
    assert client.post(path,json=args).status_code==422
    args['content_reviewed']=True
    assert client.post(path,json=args).status_code==409 # portrait has not been rendered
    updated=fixture_spec();updated['title']='New version';save(client,cid,updated)
    assert client.post(path,json=args).status_code==409


def test_render_quality_and_opt_in_visual_review(studio,monkeypatch):
    client,app,cid,_=studio;save(client,cid);result=render(client,cid)
    q=client.get(f"/api/campaigns/{cid}/creative-renders/{result['id']}/quality/landscape")
    assert q.status_code==200,q.text
    report=q.json();assert report['sample_count']==2 and not report['motion_assessed']
    enable_ai(app);app.state.settings.enable_creative_vision=True
    calls=[]
    async def fake(settings,ctx,frames=None):
        assert len(frames)==2 and frames[0]['data_url'].startswith('data:image/jpeg;base64,')
        calls.append(frames)
        return VisualReview(summary='Review sampled frames',operations=[],findings=[{'scene_id':'opening','severity':'suggestion','message':'Review pacing separately.'}]),{}
    monkeypatch.setattr('launchloom.creative_workflow_api.request_plan',fake)
    path=f"/api/campaigns/{cid}/creative-renders/{result['id']}/visual-review"
    args={**refs(client,cid),'output':'landscape','external_data_consent':True,'frames_reviewed':False}
    assert client.post(path,json=args).status_code==422 and not calls
    args['frames_reviewed']=True
    response=client.post(path,json=args);assert response.status_code==200,response.text
    assert response.json()['report']['sample_count']==2 and not response.json()['changes']
    assert refs(client,cid)['expected_revision']==result['revision']


def test_new_routes_inherit_auth_and_csrf(studio):
    client,_,cid,_=studio
    auth=client.headers.pop('Authorization')
    assert client.get(f'/api/campaigns/{cid}/creative-workflow').status_code==401
    assert client.post(f'/api/campaigns/{cid}/creative-spec/ai-proposal',json={}).status_code==401
    client.headers['Authorization']=auth
    assert client.post(f'/api/campaigns/{cid}/creative-spec/ai-proposal',json={},headers={'Origin':'https://evil.invalid'}).status_code==403
