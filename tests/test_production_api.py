import io
import zipfile
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from launchloom.production_api import register_production_routes
from launchloom.store import Store


@pytest.fixture
def setup(tmp_path):
    app = FastAPI()
    campaign = {'brief': {'name': 'Test', 'tagline': 'A film', 'features': []}, 'released': False, 'state': 'draft'}
    # Production registration now includes the persisted creative routes. Keep
    # campaign lookup isolated, but use the real SQLite contract for migrations.
    app.state.store = Store(tmp_path / 'fixture.sqlite3')
    app.state.store.campaign = lambda cid: campaign if cid == 'abc123' else None
    app.state.settings = SimpleNamespace(data_dir=tmp_path)
    @app.middleware('http')
    async def auth(request, call_next):
        if request.url.path.startswith('/api/') and request.headers.get('Authorization') != 'Bearer test':
            return JSONResponse({'detail': 'Unauthorized'}, 401)
        if request.headers.get('Origin') and request.headers['Origin'] != 'http://testserver':
            return JSONResponse({'detail': 'Cross-origin'}, 403)
        return await call_next(request)
    register_production_routes(app)
    return TestClient(app), campaign, tmp_path


def test_routes_inherit_middleware(setup):
    c, _, _ = setup
    for path in ['/api/campaigns/abc123/production', '/api/campaigns/abc123/production/export']:
        assert c.get(path).status_code == 401
        assert c.post(path).status_code == 401
    assert c.put('/api/campaigns/abc123/production', headers={'Authorization': 'Bearer test', 'Origin': 'https://bad.example'}, json={}).status_code == 403


def test_plan_persistence_conflict_and_export(setup):
    c, campaign, root = setup
    c.headers['Authorization'] = 'Bearer test'
    url = '/api/campaigns/abc123/production'
    before = c.get(url).json()
    assert before['saved'] is False
    plan = before['plan']; plan['scenes'][0]['title'] = 'Changed'
    payload = {'plan': plan, 'expected_revision': before['revision']}
    saved = c.put(url, json=payload)
    assert saved.status_code == 200 and saved.json()['saved'] is True
    assert c.put(url, json=payload).status_code == 409
    assert c.get(url).json()['plan']['scenes'][0]['title'] == 'Changed'
    exported = c.post(url + '/export')
    assert exported.status_code == 200
    assert exported.headers['X-Production-Revision'] == saved.json()['revision']
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z: assert z.testzip() is None
    assert campaign['released'] is False and campaign['state'] == 'draft'
    assert (root / 'campaigns/abc123/production-plan.json').is_file()


def test_bad_payload_unknown_campaign_and_symlink(setup):
    c, _, root = setup
    c.headers['Authorization'] = 'Bearer test'
    url = '/api/campaigns/abc123/production'
    assert c.put(url, json=[]).status_code == 422
    assert c.put(url, content=b'x'*65537).status_code == 413
    assert c.get('/api/campaigns/unknown/production').status_code == 404
    (root / 'campaigns').mkdir()
    (root / 'outside').mkdir()
    (root / 'campaigns/abc123').symlink_to(root / 'outside', target_is_directory=True)
    assert c.get(url).status_code == 400
