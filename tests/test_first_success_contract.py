"""Creation/recovery contracts tested at the storage and authenticated HTTP layers."""
from concurrent.futures import ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from launchloom.config import Settings
from launchloom.models import Brief, BuildOptions
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.server import create_app
from launchloom.store import Store, CreationConflict


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, token='local-contract-test-token-only',
        enable_live_publish=False, enable_paid_generation=False), run_worker=False)


def test_concurrent_creation_survives_reopen(tmp_path):
    path=tmp_path/'old.db'
    # Upgrade a database whose schema predates creation keys.
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE campaigns(id TEXT PRIMARY KEY, brief TEXT NOT NULL, options TEXT, plan TEXT, state TEXT DEFAULT "draft", progress INTEGER DEFAULT 0, stage TEXT DEFAULT "brief", error TEXT, created REAL NOT NULL)')
    store=Store(path)
    brief=Brief.model_validate(SAMPLE_BRIEF).model_dump()
    options=BuildOptions(capture_mode='sample', review_plan=True).model_dump()
    def create(_):
        return Store(path).create_campaign(brief, options=options, idempotency_key='same-intent-001')['id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(create,range(16)))
    assert len(set(ids))==1
    assert len(store.campaigns())==1
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
    job=store.claim_job();store.finish_job(job['id'],'failed')
    store.progress(ids[0],'capture',26,state='failed',error='fixture capture unavailable')
    replay=Store(path).create_campaign(brief, options=options, idempotency_key='same-intent-001')
    assert replay['state']=='failed'
    assert store.claim_job() is None, 'a replay must never restart a failed job'
    with pytest.raises(CreationConflict):
        store.create_campaign({**brief,'tagline':'different'},options=options,idempotency_key='same-intent-001')
    assert len(store.campaigns())==1


def test_sample_http_lost_response_replay_and_legacy_default(app):
    with TestClient(app) as client:
        assert client.post('/api/demo',headers={'Idempotency-Key':'sample-key-001'}).status_code==401
        client.headers['Authorization']='Bearer '+app.state.settings.token
        first=client.post('/api/demo?review_plan=true',headers={'Idempotency-Key':'sample-key-001'})
        assert first.status_code==202
        same=client.post('/api/demo?review_plan=true',headers={'Idempotency-Key':'sample-key-001'})
        assert same.json()['id']==first.json()['id']
        assert same.json()['options']['review_plan'] is True
        assert client.post('/api/demo',headers={'Idempotency-Key':'sample-key-001'}).status_code==409
        assert client.post('/api/demo',headers={'Idempotency-Key':'short'}).status_code==422
        assert len(client.get('/api/campaigns').json())==1
        legacy=client.post('/api/demo')
        assert legacy.json()['options']['review_plan'] is False
        assert legacy.json()['id']!=first.json()['id']
        assert client.post('/api/demo',headers={'Origin':'https://other.example','Idempotency-Key':'other-origin'}).status_code==403


def test_transaction_rolls_back_campaign_when_first_job_cannot_be_saved(tmp_path):
    store=Store(tmp_path/'db')
    with store.connect() as db:
        db.execute("CREATE TRIGGER refuse_job BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT, 'disk fixture'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.create_campaign(SAMPLE_BRIEF,options=BuildOptions().model_dump(),idempotency_key='atomic-create')
    assert store.campaigns()==[]
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM campaign_requests').fetchone()[0]==0


def test_active_job_cannot_silently_accept_different_options(app):
    db=app.state.store
    c=db.create_campaign(SAMPLE_BRIEF)
    db.enqueue(c['id'],BuildOptions().model_dump())
    with pytest.raises(ValueError, match='original build options'):
        db.enqueue(c['id'],BuildOptions(quality='draft').model_dump())


def test_openapi_is_authenticated_and_primary_responses_are_typed(app):
    with TestClient(app) as client:
        assert client.get('/api/openapi.json').status_code==401
        client.headers['Authorization']='Bearer '+app.state.settings.token
        response=client.get('/api/openapi.json')
        assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        spec=response.json()
        assert spec['openapi'].startswith('3.1.')
        schema=spec['components']['schemas']
        assert schema['BuildOptions']['additionalProperties'] is False
        assert 'awaiting_review' in schema['CampaignRecord']['properties']['state']['enum']
        get=spec['paths']['/api/campaigns/{cid}']['get']
        assert get['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/CampaignSnapshot')
        assert get['security']==[{'LocalBearer':[]},{'LocalSession':[]}]
        create=spec['paths']['/api/campaigns']['post']
        assert any(p['name']=='idempotency-key' and p['in']=='header' for p in create['parameters'])
        assert '409' in create['responses']
        for path,method,code,model in [
            ('/api/campaigns/{cid}/plan','patch','200','CampaignRecord'),
            ('/api/campaigns/{cid}/render','post','202','BuildJob'),
        ]:
            operation=spec['paths'][path][method]
            assert operation['responses'][code]['content']['application/json']['schema']['$ref'].endswith('/'+model)
            assert '409' in operation['responses']
            assert operation['security']==get['security']
        assert app.state.settings.token not in response.text


def load_client():
    spec=spec_from_file_location('local_client_example',Path(__file__).resolve().parents[1]/'examples/client.py')
    module=module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('base',['http://external.example','https://user:password@example.com','http://localhost.evil.test','https://example.com/path','https://example.com?token=x'])
def test_client_refuses_unsafe_token_destination(base):
    with pytest.raises(ValueError):load_client().validate_base(base)


@pytest.mark.parametrize('base',['http://127.0.0.1:8787','http://[::1]:8787','https://studio.example'])
def test_client_accepts_documented_origin(base):
    assert load_client().validate_base(base)==base
