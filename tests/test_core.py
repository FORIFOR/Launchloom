from __future__ import annotations
import asyncio
import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from launchloom.config import Settings
from launchloom.models import Brief,BuildOptions,Approval,CaptureStep
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.planning import make_plan,make_posts,with_utm,x_weight
from launchloom.providers import PostizPublisher,validate_publication,FalFilm,ComfyFilm
from launchloom.security import safe_path,origin,check_capture_url,digest,file_sha,tracking_token,scrub_error
from launchloom.store import Store
from launchloom.server import create_app
from launchloom.site import build_site

@pytest.fixture
def brief():return Brief.model_validate(copy.deepcopy(SAMPLE_BRIEF))
@pytest.fixture
def store(tmp_path):return Store(tmp_path/'state.db')
@pytest.fixture
def configured(tmp_path):return Settings(data_dir=tmp_path/'data',token='test-local-token-with-32-characters',postiz_base='https://postiz.example/public/v1',postiz_key='test-key',no_sandbox=False)

@pytest.mark.parametrize('field,value',[('accent','red'),('product_url','javascript:alert(1)'),('product_url','https://user:password@example.com'),('name','')])
def test_invalid_brief(brief,field,value):
    data=brief.model_dump();data[field]=value
    with pytest.raises(ValidationError):Brief.model_validate(data)
def test_evidence_required(brief):
    data=brief.model_dump();data['features'][0]['evidence']=''
    with pytest.raises(ValidationError):Brief.model_validate(data)
def test_unapproved_features_excluded(brief):
    brief.features[0].approved=False;brief.features[0].title='UNVERIFIED CLAIM'
    assert 'UNVERIFIED' not in make_plan(brief).model_dump_json()
    assert 'UNVERIFIED' not in json.dumps(make_posts(brief,'test'))
def test_all_unapproved_blocks_build(brief):
    for f in brief.features:f.approved=False
    with pytest.raises(ValueError,match='approved'):make_plan(brief)
@pytest.mark.parametrize('options',[{'capture_mode':'url','capture_url':'https://example.com'}, {'film_provider':'fal'}, {'film_provider':'fal','external_data_consent':True}, {'llm_plan':True}, {'allow_site_writes':True}])
def test_build_requires_authorization(options):
    with pytest.raises(ValidationError):BuildOptions(**options)
def test_capture_cannot_execute_arbitrary_code():
    with pytest.raises(ValidationError):CaptureStep(action='evaluate',value='window.alert(1)')
@pytest.mark.parametrize('values',[(False,True,True),(True,False,True),(True,True,False)])
def test_approval_all_checks(values):
    with pytest.raises(ValidationError):Approval(fingerprint='0'*64,content_reviewed=values[0],rights_confirmed=values[1],account_authorized=values[2])
def test_utm_preserves_query_fragment():
    result=with_utm('https://example.com/path?ref=abc#join','x','campaign')
    assert 'ref=abc' in result and result.endswith('#join') and 'utm_source=x' in result
    assert with_utm('','x','a')==''
def test_x_preflight_counts_japanese_and_urls():
    assert x_weight('あa')==3
    assert x_weight('https://example.com/a-long-url')==23
@pytest.mark.parametrize('attack',['../secret','../../etc/passwd','/etc/passwd'])
def test_path_escape(tmp_path,attack):
    with pytest.raises(ValueError):safe_path(tmp_path,attack)
def test_symlink_escape(tmp_path):
    (tmp_path/'link').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):safe_path(tmp_path,'link')
def test_capture_origin_is_explicit():
    with pytest.raises(ValueError):check_capture_url('https://example.com',set())
def test_cloud_metadata_always_blocked():
    u='http://169.254.169.254/latest/meta-data'
    with pytest.raises(ValueError,match='Unsafe'):check_capture_url(u,{origin(u)})
def test_studio_api_never_capturable():
    u='http://127.0.0.1:8787';o=origin(u)
    check_capture_url(u+'/demo-app',{o},o)
    with pytest.raises(ValueError):check_capture_url(u+'/api/config',{o},o)
def test_origin_normalizes_port():assert origin('https://example.com/abc')=='https://example.com:443'
def test_redacts_tokens():assert 'super-secret' not in scrub_error(ValueError('key super-secret'),['super-secret'])

def test_queue_idempotence(store,brief):
    cid=store.create_campaign(brief.model_dump())['id'];opts=BuildOptions().model_dump()
    first=store.enqueue(cid,opts);second=store.enqueue(cid,opts)
    assert first['id']==second['id']
    assert store.claim_job()['id']==first['id']
    assert store.claim_job() is None

def test_retry_numeric_normalization(store,brief):
    cid=store.create_campaign(brief.model_dump())['id'];opts=BuildOptions().model_dump()
    job=store.enqueue(cid,opts);store.finish_job(job['id'],'failed');store.progress(cid,'failed',0,state='failed')
    opts['estimated_cost_usd']=0.0
    assert store.enqueue(cid,opts)['state']=='queued'

def test_ready_campaign_rejects_an_unmarked_rebuild(store,brief):
    cid=store.create_campaign(brief.model_dump())['id'];store.progress(cid,'ready',100,state='ready')
    with pytest.raises(ValueError,match='finished'):store.enqueue(cid,BuildOptions().model_dump())

def test_revision_requires_a_finished_campaign(store,brief):
    cid=store.create_campaign(brief.model_dump())['id']
    with pytest.raises(ValueError,match='finished or reviewable'):store.enqueue(cid,BuildOptions().model_dump(),revision=True)

def test_revision_reuses_options_and_counts_up(store,brief):
    options=BuildOptions().model_dump()
    cid=store.create_campaign(brief.model_dump())['id']
    job=store.enqueue(cid,options);store.claim_job();store.finish_job(job['id'],'complete')
    store.progress(cid,'ready',100,state='ready')
    second=store.enqueue(cid,options,revision=True)
    assert store.campaign(cid)['revision']==1
    store.claim_job();store.finish_job(second['id'],'complete');store.progress(cid,'ready',100,state='ready')
    with pytest.raises(ValueError,match='original build options'):
        store.enqueue(cid,{**options,'quality':'draft'},revision=True)

def test_publication_hash_binds_content_account_and_media(store):
    a=store.create_publication('a',{'content':'hello','integration_id':'one','media_sha256':'old'})
    same=store.create_publication('a',{'content':'hello','integration_id':'one','media_sha256':'old'})
    b=store.create_publication('a',{'content':'hello','integration_id':'two','media_sha256':'old'})
    assert a['id']==same['id'] and a['fingerprint']!=b['fingerprint']
    with pytest.raises(ValueError):store.approve(b['id'],a['fingerprint'])

def test_concurrent_publication_claim(store):
    p=store.create_publication('a',{'content':'test'});store.approve(p['id'],p['fingerprint'])
    def claim(_):
        try:store.claim_publication(p['id']);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(claim,range(8)))==1

def test_recovery_never_blind_republishes(store):
    p=store.create_publication('a',{'content':'test'});store.approve(p['id'],p['fingerprint']);store.claim_publication(p['id']);store.recover()
    assert store.publication(p['id'])['state']=='needs_reconciliation'
    with pytest.raises(ValueError):store.claim_publication(p['id'])

def test_budget_and_ticket_resumption(store):
    assert store.reserve_provider('a','fal',1,2) is None
    assert store.reserve_provider('a','fal',1,2)['state']=='submitting'
    with pytest.raises(ValueError,match='budget'):store.reserve_provider('b','fal',2,2)
    store.provider_update('a','queued',{'request_id':'abc'})
    assert store.reserve_provider('a','fal',1,2)['request']['request_id']=='abc'

def test_empty_metrics_are_not_fake_success(store):
    m=store.metrics('empty');assert m['page_views']==0 and m['conversion_rate'] is None and m['social_impressions'] is None

def test_metric_events_not_unique_people(store):
    store.record_metric('a','page_view','x');store.record_metric('a','cta_click','x');store.record_metric('a','signup','x')
    assert store.metrics('a')['conversion_rate']==1


def payload():return {'channel':'x','content':'A real product, demonstrated.','integration_id':'account-1','media':'landscape.mp4','settings':{}}

def test_postiz_upload_then_submit(configured,tmp_path):
    calls=[];media=tmp_path/'film.mp4';media.write_bytes(b'test-media')
    def handle(request):
        calls.append(request)
        assert request.headers['Authorization']=='test-key'
        if request.url.path.endswith('/upload'):
            assert b'test-media' in request.content;assert b'name="file"' in request.content
            return httpx.Response(200,json={'id':'asset-1','path':'https://cdn.example/film.mp4'})
        body=json.loads(request.content)
        assert body['posts'][0]['integration']['id']=='account-1'
        assert body['posts'][0]['value'][0]['image']==[{'id':'asset-1','path':'https://cdn.example/film.mp4'}]
        assert body['posts'][0]['settings']['__type']=='x'
        return httpx.Response(201,json=[{'postId':'post-1','integration':'account-1'}])
    r=asyncio.run(PostizPublisher(configured,httpx.MockTransport(handle)).submit(payload(),media))
    assert r[0]['postId']=='post-1' and len(calls)==2

def test_postiz_no_automatic_timeout_retry(configured,tmp_path):
    calls=[];media=tmp_path/'film.mp4';media.write_bytes(b'test-media')
    def handle(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/upload'):return httpx.Response(200,json={'id':'a','path':'p'})
        raise httpx.ReadTimeout('Outcome uncertain',request=request)
    with pytest.raises(httpx.ReadTimeout):asyncio.run(PostizPublisher(configured,httpx.MockTransport(handle)).submit(payload(),media))
    assert len(calls)==2

def test_postiz_rejects_invalid_upload(configured,tmp_path):
    media=tmp_path/'film.mp4';media.write_bytes(b'fake')
    with pytest.raises(ValueError,match='upload'):asyncio.run(PostizPublisher(configured,httpx.MockTransport(lambda r:httpx.Response(200,json={}))).submit(payload(),media))

def test_schedule_timezone_normalized():
    p=payload();p['schedule_at']=(datetime.now(timezone(timedelta(hours=9)))+timedelta(days=1)).isoformat()
    result=validate_publication(p);assert result['type']=='schedule' and result['date'].endswith('+00:00')
@pytest.mark.parametrize('at',['2020-01-01T00:00:00+09:00','2030-01-01T00:00:00'])
def test_invalid_schedules(at):
    p=payload();p['schedule_at']=at
    with pytest.raises(ValueError):validate_publication(p)
def test_ai_disclosure():
    p=payload();p['ai_generated']=True
    assert validate_publication(p)['posts'][0]['settings']['made_with_ai'] is True
@pytest.mark.parametrize('channel',['youtube','instagram','tiktok'])
def test_platform_settings_are_required(channel):
    p=payload();p['channel']=channel
    with pytest.raises(ValueError):validate_publication(p)
def test_overlong_x_rejected():
    p=payload();p['content']='あ'*141
    with pytest.raises(ValueError):validate_publication(p)

@pytest.fixture
def client(configured):
    app=create_app(configured,run_worker=False)
    with TestClient(app) as c:yield c

def login(client,configured):
    r=client.post('/api/session',json={'token':configured.token});assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']

def test_unauthenticated_cannot_read_api(client):assert client.get('/api/campaigns').status_code==401

def test_unicode_wrong_token_is_not_server_error(client):assert client.post('/api/session',json={'token':'あいうえお'}).status_code==401

def test_session_and_secret_not_exposed(client,configured):
    login(client,configured);r=client.get('/api/config');assert r.status_code==200
    assert configured.token not in r.text and configured.postiz_key not in r.text

def test_csrf_rejected(client,configured):
    login(client,configured)
    assert client.post('/api/demo',headers={'Origin':'https://evil.example'}).status_code==403

def test_unknown_host_rejected(client):assert client.get('/healthz',headers={'Host':'evil.example'}).status_code==400

def test_source_escaped_in_generated_html(tmp_path,brief,configured):
    brief.name='<script>alert(1)</script>';brief.description='<img src=x onerror=alert(1)>'
    build_site(brief,'a'*16,tmp_path/'site',configured)
    html=(tmp_path/'site/index.html').read_text()
    assert '<script>alert(1)</script>' not in html and '&lt;script&gt;' in html

def seeded_ready(client,configured):
    login(client,configured);r=client.post('/api/campaigns',json=SAMPLE_BRIEF);cid=r.json()['id'];root=configured.data_dir/'campaigns'/cid;root.mkdir(parents=True)
    (root/'landscape.mp4').write_bytes(b'immutable-test-media')
    db=client.app.state.store;db.enqueue(cid,BuildOptions().model_dump());job=db.claim_job();db.finish_job(job['id'],'complete');db.progress(cid,'ready',100,state='ready')
    return cid,root

def test_sensitive_recordings_not_served(client,configured):
    cid,root=seeded_ready(client,configured);(root/'input').mkdir();(root/'input/capture.bin').write_bytes(b'secret')
    assert client.get(f'/artifacts/{cid}/input/capture.bin').status_code==404
    assert client.get(f'/artifacts/{cid}/landscape.mp4').status_code==200

def test_dry_run_has_no_network(client,configured,monkeypatch):
    cid,root=seeded_ready(client,configured)
    def forbidden(*a,**kw):raise AssertionError('Unexpected network operation')
    monkeypatch.setattr(PostizPublisher,'client',forbidden)
    p=client.post(f'/api/campaigns/{cid}/publications',json=payload()).json()
    r=client.get(f'/api/publications/{p["id"]}/dry-run');assert r.status_code==200 and r.json()['network_requests']==0
    assert client.post(f'/api/publications/{p["id"]}/submit').status_code==409

def test_tampered_media_invalidates_approval(client,configured):
    cid,root=seeded_ready(client,configured);p=client.post(f'/api/campaigns/{cid}/publications',json=payload()).json()
    (root/'landscape.mp4').write_bytes(b'changed')
    r=client.post(f'/api/publications/{p["id"]}/approve',json={'fingerprint':p['fingerprint'],'content_reviewed':True,'rights_confirmed':True,'account_authorized':True})
    assert r.status_code==409

def test_upload_requires_rights(client,configured):
    login(client,configured);cid=client.post('/api/campaigns',json=SAMPLE_BRIEF).json()['id']
    assert client.post(f'/api/campaigns/{cid}/media?kind=capture',content=b'fake').status_code==422

def test_fake_video_rejected(client,configured):
    login(client,configured);cid=client.post('/api/campaigns',json=SAMPLE_BRIEF).json()['id']
    r=client.post(f'/api/campaigns/{cid}/media?kind=capture&rights_confirmed=true',content=b'not a video')
    # ffprobe errors must be a controlled validation response, not HTTP 500.
    assert r.status_code==422

def test_sample_cannot_masquerade_as_real_product(configured,store,brief):
    from launchloom.pipeline import build
    brief.is_sample=False;cid=store.create_campaign(brief.model_dump())['id']
    with pytest.raises(ValueError,match='sample recording'):asyncio.run(build(configured,store,cid,BuildOptions(capture_mode='sample')))


# --- Environment readiness (P0: real-machine setup failures must be legible) ---

def test_version_is_single_sourced():
    import importlib.metadata
    from launchloom import __version__
    assert importlib.metadata.version('launchloom')==__version__

def test_manifest_records_the_running_version(tmp_path):
    from launchloom import __version__
    import launchloom.pipeline as pipeline
    assert "'version':__version__" in Path(pipeline.__file__).read_text()

def test_missing_browser_reports_the_install_command(configured,monkeypatch):
    from launchloom import capture as capture_module
    class Failing:
        class chromium:
            @staticmethod
            async def launch(**kwargs):
                raise RuntimeError("BrowserType.launch: Executable doesn't exist at /x/chrome-headless-shell")
    with pytest.raises(ValueError) as error:
        asyncio.run(capture_module.launch_chromium(Failing,configured))
    assert 'playwright install chromium' in str(error.value)

def test_unrelated_browser_failure_is_not_masked(configured):
    from launchloom import capture as capture_module
    class Failing:
        class chromium:
            @staticmethod
            async def launch(**kwargs):raise RuntimeError('Target page crashed')
    with pytest.raises(RuntimeError,match='Target page crashed'):
        asyncio.run(capture_module.launch_chromium(Failing,configured))

def test_font_resolution_prefers_japanese_coverage(monkeypatch,tmp_path):
    from launchloom import rendering
    latin=tmp_path/'Latin.ttf';latin.write_bytes(b'x')
    cjk=tmp_path/'CJK.ttc';cjk.write_bytes(b'x')
    monkeypatch.setattr(rendering,'LATIN_FONTS',{True:[str(latin)],False:[str(latin)]})
    monkeypatch.setattr(rendering,'CJK_FONTS',{True:[str(cjk)],False:[str(cjk)]})
    monkeypatch.delenv('LAUNCHLOOM_FONT',raising=False)
    assert rendering.font_source(False)==(str(cjk),True)
    monkeypatch.setattr(rendering,'CJK_FONTS',{True:[],False:[]})
    assert rendering.font_source(False)==(str(latin),False)

def test_this_machine_can_render_japanese():
    """Guards the tofu-box failure mode on the machine actually running a build."""
    from launchloom.rendering import font_source
    for bold in (False,True):
        path,cjk=font_source(bold)
        assert path and cjk, f'No Japanese-capable font found (bold={bold}). Set LAUNCHLOOM_FONT.'


# --- Review gate and revisions (P1) ---

def reviewable(client,configured,brief):
    """A campaign parked at the review gate, as the worker would leave it."""
    login(client,configured)
    cid=client.post('/api/campaigns',json=brief.model_dump()).json()['id']
    store=Store(configured.data_dir/'launchloom.sqlite3')
    options=BuildOptions(capture_mode='sample',review_plan=True).model_dump()
    job=store.enqueue(cid,options)
    store.claim_job();store.finish_job(job['id'],'complete')
    store.save_plan(cid,make_plan(brief).model_dump())
    store.progress(cid,'awaiting_review',40,state='awaiting_review')
    return cid,store

def test_review_gate_accepts_operator_wording(client,configured,brief):
    cid,store=reviewable(client,configured,brief)
    r=client.patch(f'/api/campaigns/{cid}/plan',json={'scenes':[{'index':1,'title':'書いた瞬間に、置き場所ができる。','caption':'書けば、そこに残る。'}]})
    assert r.status_code==200
    plan=r.json()['plan']
    assert plan['scenes'][1]['title']=='書いた瞬間に、置き場所ができる。'
    assert plan['scenes'][1]['caption']=='書けば、そこに残る。'
    assert plan['source']=='operator-edited'
    assert plan['scenes'][1]['feature_index']==0, 'an edit must not move a scene onto a different approved feature'

def test_edited_storyboard_survives_the_next_render(client,configured,brief):
    cid,store=reviewable(client,configured,brief)
    client.patch(f'/api/campaigns/{cid}/plan',json={'concept':'説明ではなく、手つきを見せる。'})
    assert client.post(f'/api/campaigns/{cid}/render').status_code==202
    record=store.campaign(cid)
    assert record['plan_approved']==1 and record['state']=='queued'
    assert record['plan']['concept']=='説明ではなく、手つきを見せる。'
    assert record['revision']==0, 'the first render after review is not a revision'

def test_plan_cannot_be_edited_mid_build(client,configured,brief):
    cid,store=reviewable(client,configured,brief)
    store.progress(cid,'render',60,state='building')
    assert client.patch(f'/api/campaigns/{cid}/plan',json={'concept':'途中で差し替える'}).status_code==409

def test_empty_scene_title_is_refused(client,configured,brief):
    cid,_=reviewable(client,configured,brief)
    assert client.patch(f'/api/campaigns/{cid}/plan',json={'scenes':[{'index':0,'title':''}]}).status_code==422

def test_revision_reuses_the_recording_and_counts_up(client,configured,brief):
    cid,store=reviewable(client,configured,brief)
    store.progress(cid,'ready',100,state='ready')
    r=client.post(f'/api/campaigns/{cid}/revise',json={'scenes':[{'index':3,'title':'次の一歩を、ここから。'}]})
    assert r.status_code==202
    record=store.campaign(cid)
    assert record['revision']==1 and record['plan']['scenes'][3]['title']=='次の一歩を、ここから。'
    assert record['options']==BuildOptions(capture_mode='sample',review_plan=True).model_dump(), 'a revision must not change what was recorded or requested from a provider'

def test_revision_requires_a_finished_campaign_over_the_api(client,configured,brief):
    cid,_=reviewable(client,configured,brief)
    assert client.post(f'/api/campaigns/{cid}/revise',json={'concept':'まだ早い'}).status_code==409

def test_imported_event_track_belongs_to_uploaded_footage():
    events=[{'time':1.0,'label':'追加する','action':'click','x':.4,'y':.3}]
    BuildOptions(capture_mode='upload',capture_events=events)
    with pytest.raises(ValidationError):BuildOptions(capture_mode='sample',capture_events=events)
    with pytest.raises(ValidationError):
        BuildOptions(capture_mode='upload',capture_events=[{'time':4.0},{'time':1.0}])

def test_each_visual_direction_is_a_different_picture(brief):
    from launchloom.rendering import render_frame
    from launchloom.planning import make_plan as plan_for
    frames={}
    for style in ('editorial','spotlight','grid'):
        image=render_frame(brief,plan_for(brief,style),480,270,1.0,9,None,[],None,style)
        frames[style]=image.tobytes()
    assert len(set(frames.values()))==3


# --- Release, pacing and reconciliation (P2) ---

def approve_body(p):return {'fingerprint':p['fingerprint'],'content_reviewed':True,'rights_confirmed':True,'account_authorized':True}

def test_release_is_a_separate_decision(client,configured):
    cid,root=seeded_ready(client,configured)
    assert client.post(f'/api/campaigns/{cid}/release',json={}).status_code==422
    r=client.post(f'/api/campaigns/{cid}/release',json={'confirmed':True})
    assert r.status_code==200 and r.json()['released']==1
    assert client.post(f'/api/campaigns/{cid}/hold').json()['released']==0

def test_unfinished_campaign_cannot_be_released(client,configured):
    login(client,configured);cid=client.post('/api/campaigns',json=SAMPLE_BRIEF).json()['id']
    assert client.post(f'/api/campaigns/{cid}/release',json={'confirmed':True}).status_code==409

def test_submit_requires_a_released_campaign(client,configured,monkeypatch):
    monkeypatch.setattr(configured,'enable_live_publish',True)
    cid,root=seeded_ready(client,configured)
    p=client.post(f'/api/campaigns/{cid}/publications',json=payload()).json()
    client.post(f'/api/publications/{p["id"]}/approve',json=approve_body(p))
    r=client.post(f'/api/publications/{p["id"]}/submit')
    assert r.status_code==409 and 'Release the campaign' in r.json()['detail']

def test_variants_on_one_channel_must_be_spaced(client,configured):
    cid,root=seeded_ready(client,configured)
    soon=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    close=(datetime.now(timezone.utc)+timedelta(hours=2,minutes=10)).isoformat()
    far=(datetime.now(timezone.utc)+timedelta(hours=6)).isoformat()
    first=client.post(f'/api/campaigns/{cid}/publications',json={**payload(),'schedule_at':soon}).json()
    assert client.post(f'/api/publications/{first["id"]}/approve',json=approve_body(first)).status_code==200
    second=client.post(f'/api/campaigns/{cid}/publications',json={**payload(),'content':'別の切り口で。','schedule_at':close}).json()
    r=client.post(f'/api/publications/{second["id"]}/approve',json=approve_body(second))
    assert r.status_code==409 and 'minutes' in r.json()['detail']
    third=client.post(f'/api/campaigns/{cid}/publications',json={**payload(),'content':'別の切り口で。','schedule_at':far}).json()
    assert client.post(f'/api/publications/{third["id"]}/approve',json=approve_body(third)).status_code==200

def test_daily_channel_limit_counts_approved_variants(client,configured):
    cid,root=seeded_ready(client,configured);approved=0
    for hour in (2,4,6,8):
        at=(datetime.now(timezone.utc)+timedelta(hours=hour)).isoformat()
        p=client.post(f'/api/campaigns/{cid}/publications',json={**payload(),'content':f'切り口{hour}','schedule_at':at}).json()
        if client.post(f'/api/publications/{p["id"]}/approve',json=approve_body(p)).status_code==200:approved+=1
    assert approved==configured.max_posts_per_channel_per_day

def uncertain(client,configured):
    cid,root=seeded_ready(client,configured)
    p=client.post(f'/api/campaigns/{cid}/publications',json=payload()).json()
    client.app.state.store.publication_result(p['id'],'needs_reconciliation',error='timeout')
    return cid,p

def test_reconciling_as_published_needs_the_real_post_id(client,configured):
    cid,p=uncertain(client,configured)
    assert client.post(f'/api/publications/{p["id"]}/reconcile',json={'resolution':'published'}).status_code==422
    r=client.post(f'/api/publications/{p["id"]}/reconcile',json={'resolution':'published','remote_id':'post-77'})
    assert r.status_code==200 and r.json()['state']=='submitted'
    assert r.json()['receipt'][0]['postId']=='post-77'

def test_reconciling_as_absent_restores_a_deliberate_retry(client,configured):
    cid,p=uncertain(client,configured)
    r=client.post(f'/api/publications/{p["id"]}/reconcile',json={'resolution':'not_published','note':'Postizに該当なし'})
    assert r.status_code==200 and r.json()['state']=='approved'
    assert client.post(f'/api/publications/{p["id"]}/reconcile',json={'resolution':'not_published'}).status_code==409

def test_remote_state_is_read_from_postiz_not_assumed(client,configured,monkeypatch):
    cid,root=seeded_ready(client,configured)
    p=client.post(f'/api/campaigns/{cid}/publications',json=payload()).json()
    client.app.state.store.publication_result(p['id'],'submitted',receipt=[{'postId':'remote-1'}])
    async def listing(self,start,end):
        return [{'id':'remote-1','state':'PUBLISHED','releaseURL':'https://example.test/p/1','integration':{'id':'account-1'}}]
    monkeypatch.setattr(PostizPublisher,'posts',listing)
    body=client.get(f'/api/campaigns/{cid}/publication-states').json()
    assert body['items'][0]['remote_state']=='published'
    assert body['items'][0]['remote_url']=='https://example.test/p/1'
    async def empty(self,start,end):return []
    monkeypatch.setattr(PostizPublisher,'posts',empty)
    assert client.get(f'/api/campaigns/{cid}/publication-states').json()['items'][0]['remote_state']=='absent'

def test_candidates_never_decide_for_the_operator(client,configured,monkeypatch):
    cid,p=uncertain(client,configured)
    async def listing(self,start,end):
        return [{'id':'other-9','state':'QUEUE','integration':{'id':'account-1'},'content':payload()['content']}]
    monkeypatch.setattr(PostizPublisher,'posts',listing)
    body=client.get(f'/api/publications/{p["id"]}/candidates').json()
    assert body['exact'] is None and len(body['candidates'])==1
    assert client.app.state.store.publication(p['id'])['state']=='needs_reconciliation'


# --- Landing page deployment (P2) ---

def test_deployment_preview_describes_exact_bytes(client,configured,tmp_path,brief):
    cid,root=seeded_ready(client,configured)
    site=root/'site';site.mkdir()
    for name in ('index.html','site.css','site.js','film.mp4','poster.jpg'):(site/name).write_bytes(name.encode())
    target=tmp_path/'public';target.mkdir();(target/'CNAME').write_text('example.test')
    object.__setattr__(configured,'deploy_dir',str(target))
    preview=client.get(f'/api/campaigns/{cid}/deployment-preview').json()
    assert {f['status'] for f in preview['files']}=={'adds'}
    assert 'CNAME' in preview['left_untouched']
    assert client.post(f'/api/campaigns/{cid}/deploy',json={'confirmed':True,'fingerprint':preview['fingerprint']}).status_code==409, 'an unreleased campaign must not deploy'
    client.post(f'/api/campaigns/{cid}/release',json={'confirmed':True})
    r=client.post(f'/api/campaigns/{cid}/deploy',json={'confirmed':True,'fingerprint':preview['fingerprint']})
    assert r.status_code==200
    assert (target/'index.html').read_bytes()==b'index.html' and (target/'CNAME').read_text()=='example.test'
    assert not list(target.glob('*.launchloom-partial'))
    again=client.get(f'/api/campaigns/{cid}/deployment-preview').json()
    assert {f['status'] for f in again['files']}=={'unchanged'}

def test_deploy_refuses_a_stale_approval(client,configured,tmp_path):
    cid,root=seeded_ready(client,configured)
    site=root/'site';site.mkdir()
    for name in ('index.html','site.css','site.js','film.mp4','poster.jpg'):(site/name).write_bytes(name.encode())
    target=tmp_path/'public';target.mkdir()
    object.__setattr__(configured,'deploy_dir',str(target))
    preview=client.get(f'/api/campaigns/{cid}/deployment-preview').json()
    client.post(f'/api/campaigns/{cid}/release',json={'confirmed':True})
    (site/'index.html').write_bytes(b'a later edit')
    r=client.post(f'/api/campaigns/{cid}/deploy',json={'confirmed':True,'fingerprint':preview['fingerprint']})
    assert r.status_code==422 and 'previewed' in r.json()['detail']
    assert not (target/'index.html').exists()

def test_deploy_target_must_not_overlap_studio_data(client,configured):
    cid,root=seeded_ready(client,configured)
    site=root/'site';site.mkdir()
    for name in ('index.html','site.css','site.js','film.mp4','poster.jpg'):(site/name).write_bytes(name.encode())
    object.__setattr__(configured,'deploy_dir',str(configured.data_dir))
    r=client.get(f'/api/campaigns/{cid}/deployment-preview')
    assert r.status_code==422 and 'overlaps' in r.json()['detail']

def test_deploy_refuses_to_write_through_a_symlink(client,configured,tmp_path):
    cid,root=seeded_ready(client,configured)
    site=root/'site';site.mkdir()
    for name in ('index.html','site.css','site.js','film.mp4','poster.jpg'):(site/name).write_bytes(name.encode())
    target=tmp_path/'public';target.mkdir();elsewhere=tmp_path/'elsewhere.html';elsewhere.write_text('other')
    (target/'index.html').symlink_to(elsewhere)
    object.__setattr__(configured,'deploy_dir',str(target))
    r=client.get(f'/api/campaigns/{cid}/deployment-preview')
    assert r.status_code==422 and 'symlink' in r.json()['detail']
    assert elsewhere.read_text()=='other'


# --- Signed, deduplicated conversions (P2) ---

def signed_post(client,configured,cid,body,secret=None):
    from launchloom.security import conversion_secret,signed_body
    raw=json.dumps(body).encode()
    key=secret if secret is not None else conversion_secret(configured.token,cid)
    return client.post('/conversions',content=raw,headers={'X-Launchloom-Signature':signed_body(key,raw),'Content-Type':'application/json'})

def test_conversion_requires_a_valid_signature(client,configured):
    cid,_=seeded_ready(client,configured)
    body={'campaign_id':cid,'conversion_id':'order-1','channel':'x'}
    assert signed_post(client,configured,cid,body,secret='not-the-key').status_code==403
    raw=json.dumps(body).encode()
    assert client.post('/conversions',content=raw).status_code==403
    assert signed_post(client,configured,cid,body).status_code==200

def test_conversion_key_is_campaign_scoped(client,configured):
    first,_=seeded_ready(client,configured);second,_=seeded_ready(client,configured)
    a=client.get(f'/api/campaigns/{first}/conversion-key').json()['secret']
    b=client.get(f'/api/campaigns/{second}/conversion-key').json()['secret']
    assert a!=b and configured.token not in (a,b)

def test_repeated_conversion_id_is_counted_once(client,configured):
    cid,_=seeded_ready(client,configured)
    body={'campaign_id':cid,'conversion_id':'order-77','channel':'linkedin'}
    assert signed_post(client,configured,cid,body).json()['counted'] is True
    repeat=signed_post(client,configured,cid,body)
    assert repeat.status_code==200 and repeat.json()['duplicate'] is True
    assert client.app.state.store.metrics(cid)['signups']==1

def test_conversion_replay_window(client,configured):
    cid,_=seeded_ready(client,configured)
    stale=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    r=signed_post(client,configured,cid,{'campaign_id':cid,'conversion_id':'order-9','at':stale})
    assert r.status_code==422 and 'replay' in r.json()['detail']

def test_conversion_needs_its_own_id(client,configured):
    cid,_=seeded_ready(client,configured)
    assert signed_post(client,configured,cid,{'campaign_id':cid,'conversion_id':''}).status_code==422


def test_store_upgrades_an_existing_database(tmp_path):
    """Schema changes must open a database written by an earlier version."""
    import sqlite3
    path=tmp_path/'old.sqlite3'
    old=sqlite3.connect(path)
    old.executescript('''
      CREATE TABLE campaigns(id TEXT PRIMARY KEY, brief TEXT NOT NULL, options TEXT, plan TEXT,
        state TEXT NOT NULL DEFAULT 'draft', progress INTEGER DEFAULT 0, stage TEXT DEFAULT 'brief',
        error TEXT, created REAL NOT NULL);
      CREATE TABLE publications(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, payload TEXT NOT NULL,
        fingerprint TEXT UNIQUE NOT NULL, state TEXT NOT NULL, receipt TEXT, error TEXT, created REAL NOT NULL);
      CREATE TABLE metrics(id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
        event TEXT NOT NULL, channel TEXT NOT NULL, created REAL NOT NULL);
      INSERT INTO campaigns(id,brief,state,created) VALUES('old1','{}','ready',1.0);
      INSERT INTO metrics(campaign_id,event,channel,created) VALUES('old1','page_view','x',1.0);
    ''')
    old.commit();old.close()
    store=Store(path)
    record=store.campaign('old1')
    assert record['released']==0 and record['revision']==0 and record['plan_approved']==0
    assert store.metrics('old1')['page_views']==1
    assert store.record_metric('old1','signup','x',dedupe_key='old1:a') is True
    assert store.record_metric('old1','signup','x',dedupe_key='old1:a') is False


def test_japanese_lines_never_start_with_closing_punctuation():
    """禁則処理: a wrapped line beginning with 、。」 reads as a typographic error."""
    from PIL import Image,ImageDraw
    from launchloom.rendering import wrapped,NO_LINE_START
    draw=ImageDraw.Draw(Image.new('RGB',(400,400)))
    captured=[]
    original=draw.text
    draw.text=lambda xy,line,**kw:captured.append(line)
    for text in ['一度の入力から、全部そろう。','終わったことが、見える。','思いつきを、その場で。',
                 'これは、とても長い一文で、折り返しが何度も起きる、そういう見出しです。']:
        captured.clear()
        for width in range(60,240,7):
            captured.clear()
            wrapped(draw,text,(0,0),width,18,'#000',max_lines=9)
            for line in captured[1:]:
                assert line[0] not in NO_LINE_START, f'{text!r} at width {width}: line starts with {line[0]!r}'
    draw.text=original

def test_wrapping_keeps_every_character():
    from PIL import Image,ImageDraw
    from launchloom.rendering import wrapped
    draw=ImageDraw.Draw(Image.new('RGB',(400,400)))
    captured=[]
    draw.text=lambda xy,line,**kw:captured.append(line)
    text='一度の入力から、全部そろう。横長・縦長のMP4、動画入りLP、原稿まで。'
    wrapped(draw,text,(0,0),150,18,'#000',max_lines=99)
    assert ''.join(captured)==text

def test_latin_words_are_not_split_mid_word():
    from PIL import Image,ImageDraw
    from launchloom.rendering import wrapped
    draw=ImageDraw.Draw(Image.new('RGB',(400,400)))
    captured=[]
    draw.text=lambda xy,line,**kw:captured.append(line)
    wrapped(draw,'横長・縦長のMP4、動画入りLP、原稿まで。',(0,0),150,18,'#000',max_lines=9)
    joined='|'.join(captured)
    assert 'MP4' in joined.replace('|','') and 'LP' in joined.replace('|','')
    for word in ('MP4','LP'):
        assert any(word in line for line in captured), f'{word} was split across lines: {captured}'

def test_vertical_keeps_the_recording_readable(brief):
    """A desktop capture cropped to a tall box loses the product it is proving."""
    from PIL import Image
    from launchloom.planning import make_plan
    from launchloom.rendering import render_frame,crop_camera
    source=Image.new('RGB',(1280,800),'#ffffff')
    plan=make_plan(brief)
    render_frame(brief,plan,720,1280,5.0,9,source,[],None,'editorial')
    # The proof box must stay close to the recording's own proportions, so that
    # most of the captured width survives into the vertical cut.
    box=crop_camera(source,(668,418),5.0,[])
    assert box.size==(668,418)
    assert abs(668/418-1280/800)<0.05


# --- Studio translation table ---

def i18n_entries():
    """Read the key/value pairs out of web/i18n.js without a JavaScript engine."""
    source=Path('launchloom/web/i18n.js').read_text()
    table=source.split('const EN = {',1)[1].split('\n};',1)[0]
    return re.findall(r"\n\s*'((?:[^'\\]|\\.)*)':\s*\n?\s*'((?:[^'\\]|\\.)*)'",table)

def test_translation_keys_are_unique():
    """A duplicate key in a JavaScript object literal silently wins, and the
    earlier translation disappears without any error."""
    keys=[key for key,_ in i18n_entries()]
    duplicates=sorted({key for key in keys if keys.count(key)>1})
    assert not duplicates, f'duplicate keys in web/i18n.js: {duplicates}'
    assert len(keys)>200, f'only {len(keys)} entries parsed; the extractor is out of step with the file'

def test_translations_are_not_still_japanese():
    japanese=re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')
    untranslated=[key for key,value in i18n_entries() if japanese.search(value)]
    assert untranslated==[], f'these values are still Japanese: {untranslated}'

def test_every_translation_key_appears_in_the_studio():
    """A key nothing renders is dead weight, and usually a typo. Compare with
    &nbsp; folded to a space, because that is what reaches the DOM."""
    corpus=''
    for path in sorted(Path('launchloom').rglob('*')):
        if path.suffix in {'.py','.js','.html'} and 'i18n' not in path.name:
            corpus+=path.read_text()+'\n'
    corpus=corpus.replace('&nbsp;',' ')
    orphans=[]
    for key,_ in i18n_entries():
        for candidate in (key, key.replace('&nbsp;',' '), key.replace('\\n','\n')):
            if candidate in corpus:break
        else:
            orphans.append(key)
    assert orphans==[], f'translation keys that no source string produces: {orphans}'


def test_the_sample_speaks_the_studio_language(client,configured):
    """An English studio handing back a Japanese film is a bad first run."""
    from launchloom.pipeline import SAMPLES
    login(client,configured)
    for language in ('ja','en'):
        r=client.post(f'/api/demo?language={language}')
        assert r.status_code==202
        assert r.json()['brief']['language']==language
        assert Brief.model_validate(SAMPLES[language]).is_sample
    assert client.post('/api/demo?language=xx').json()['brief']['language']=='ja', 'unknown languages fall back, they do not fail'

def test_both_sample_briefs_describe_the_same_bundled_app():
    from launchloom.pipeline import SAMPLES
    evidence={language:sorted(f['evidence'] for f in brief['features']) for language,brief in SAMPLES.items()}
    assert evidence['ja']==evidence['en'], 'the evidence points at the same code in both languages'

def test_translations_contain_no_html_entities():
    """Values land in text nodes, so &nbsp; would be shown to the reader literally."""
    offenders=[(key,value) for key,value in i18n_entries() if '&' in value and ';' in value.split('&',1)[1][:8]]
    assert offenders==[], f'HTML entities in translated values: {offenders}'

def test_vertical_does_not_say_the_headline_twice(brief):
    """With no event track the caption falls back to the headline, which is
    already set above the frame."""
    from PIL import Image, ImageDraw
    from launchloom.planning import make_plan
    from launchloom import rendering
    drawn=[]
    original=rendering.wrapped
    def spy(draw,text,xy,width,size,fill,bold=False,max_lines=4):
        drawn.append(str(text))
        return original(draw,text,xy,width,size,fill,bold,max_lines)
    rendering.wrapped=spy
    try:
        plan=make_plan(brief)
        rendering.render_frame(brief,plan,720,1280,5.0,12,None,[],None,'editorial')
    finally:
        rendering.wrapped=original
    proof=[s for s in plan.scenes if s.kind=='proof'][0]
    assert drawn.count(proof.title)==1, f'the headline was set {drawn.count(proof.title)} times: {drawn}'


# --- selftest: the command a tester runs ---

def test_selftest_reports_the_environment(configured):
    from launchloom.selftest import environment
    report=environment(configured)
    for key in ('launchloom','platform','python','ffmpeg','browser','browser_launches',
                'text_font','fonts_cover_japanese','packages'):
        assert key in report, f'{key} missing from the environment report'
    assert report['packages'], 'package versions are what tell two reports apart'

def test_selftest_report_is_readable_when_the_build_fails():
    """A failing report is the one that matters most, so it must still render."""
    from launchloom.selftest import render_report
    text=render_report({'environment':{'platform':'Windows 11','packages':{'Pillow':'12.3.0'}},
                        'build':{'ok':False,'seconds':3.2,'error':'RuntimeError: no ffmpeg'}})
    assert 'FAILED' in text and 'no ffmpeg' in text and 'Windows 11' in text

def test_selftest_report_lists_every_check():
    from launchloom.selftest import render_report
    checks={'landscape_decodes':True,'zip_intact':False}
    text=render_report({'environment':{'platform':'x','packages':{}},
                        'build':{'ok':True,'seconds':21.0,'kit_entries':16,
                                 'landscape':{'width':960,'height':540,'duration':14.4,'bytes':1},
                                 'portrait':{'width':540,'height':960,'duration':14.4,'bytes':1},
                                 'checks':checks}})
    assert 'PASS  landscape_decodes' in text and 'FAIL  zip_intact' in text

def test_issue_templates_are_valid_and_point_at_the_selftest():
    """The selftest prints this template's URL, so the template has to exist."""
    import yaml
    templates=Path('.github/ISSUE_TEMPLATE')
    names={p.name for p in templates.glob('*.yml')}
    assert 'tester-report.yml' in names, 'the selftest sends people to this form'
    for path in templates.glob('*.yml'):
        yaml.safe_load(path.read_text())
    from launchloom import selftest
    assert 'template=tester-report.yml' in Path(selftest.__file__).read_text()
