from __future__ import annotations
import asyncio
import copy
import json
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

def test_ready_campaign_immutable(store,brief):
    cid=store.create_campaign(brief.model_dump())['id'];store.progress(cid,'ready',100,state='ready')
    with pytest.raises(ValueError,match='immutable'):store.enqueue(cid,BuildOptions().model_dump())

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
