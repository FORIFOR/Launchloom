"""Exercise the real application, actual MP4 inspection and publication gates."""
import io
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from launchloom.config import Settings
from launchloom.models import Brief, PublicationDraft
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.server import create_app
from launchloom.security import file_sha
from launchloom import finished_films as ff
from launchloom.production_api import register_production_routes


@pytest.fixture(scope='module')
def movie(tmp_path_factory):
    out=tmp_path_factory.mktemp('final')/'movie.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','1.25',
        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-metadata','title=PRIVATE CAMERA TITLE',str(out)],check=True)
    return out.read_bytes()


@pytest.fixture
def setup(tmp_path):
    s=Settings(data_dir=tmp_path/'workspace',token='testing-real-studio-token-1234567890',
        postiz_base='https://postiz.example/api/public/v1',postiz_key='test-key',enable_live_publish=True)
    app=create_app(s,run_worker=False)
    c=TestClient(app)
    c.headers['Authorization']='Bearer '+s.token
    cid=c.post('/api/campaigns',json=SAMPLE_BRIEF).json()['id']
    return c,app,cid


def upload(setup,movie,**values):
    c,_,cid=setup
    return c.post(f'/api/campaigns/{cid}/final-films/media',params={
        'rights_confirmed':'true','ai_generated':'false','title':'Final v1',**values},
        content=movie,headers={'Content-Type':'application/octet-stream'})


def publication(setup,film):
    c,_,cid=setup
    return c.post(f'/api/campaigns/{cid}/publications',json={
        'channel':'x','content':'Watch this real product demo.','integration_id':'account',
        'media':film['media']})


def approve(c,p):
    return c.post(f"/api/publications/{p['id']}/approve",json={
        'fingerprint':p['fingerprint'],'content_reviewed':True,'rights_confirmed':True,'account_authorized':True})


def test_factory_registers_board_once(setup):
    c,app,cid=setup
    assert c.get('/production').status_code==200
    register_production_routes(app)
    assert len([r for r in app.routes if getattr(r,'path','')=='/production'])==1
    assert c.get(f'/api/campaigns/{cid}/production').status_code==200
    assert 'production-link' in c.get('/').text


def test_actual_auth_and_csrf_middleware(setup,movie):
    c,_,cid=setup
    c.headers.clear()
    assert c.get(f'/api/campaigns/{cid}/final-films').status_code==401
    assert upload(setup,movie).status_code==401
    c.headers['Authorization']='Bearer testing-real-studio-token-1234567890'
    c.headers['Origin']='https://attacker.invalid'
    assert upload(setup,movie).status_code==403


def test_import_preserves_originals_and_returns_posts(setup,movie):
    c,app,cid=setup
    originals=app.state.settings.data_dir/'campaigns'/cid
    originals.mkdir();(originals/'landscape.mp4').write_bytes(b'keep original')
    app.state.store.release_campaign(cid,True)
    r=upload(setup,movie);assert r.status_code==201,r.text
    film=r.json()
    assert film['width']==320 and film['height']==180 and film['duration']>1
    assert film['ai_generated'] is False
    path=originals/film['media']
    assert file_sha(path)==film['sha256']
    assert (originals/'landscape.mp4').read_bytes()==b'keep original'
    assert not list(originals.rglob('*.upload'))
    data=c.get(f'/api/campaigns/{cid}').json()
    assert data['state']=='draft'  # No pretend local render or fake ready state.
    assert data['released']==0 and data['posts']
    assert data['outputs'][film['media']]==film['url']
    assert c.get(film['url']).content==path.read_bytes()
    assert c.get(film['url'],headers={'Range':'bytes=0-99'}).status_code==206
    metadata=ff.validate_media(path)
    assert 'PRIVATE CAMERA TITLE' not in json.dumps(metadata)
    assert any(s['codec_type']=='audio' for s in metadata['streams'])


def test_new_version_has_new_fingerprint_and_holds_publishing(setup,movie):
    c,app,cid=setup
    f1=upload(setup,movie).json();p1=publication(setup,f1).json()
    assert approve(c,p1).status_code==200
    app.state.store.release_campaign(cid,True)
    f2=upload(setup,movie,title='Final v2').json();p2=publication(setup,f2).json()
    assert f1['media']!=f2['media']
    assert p1['fingerprint']!=p2['fingerprint']
    assert app.state.store.publication(p2['id'])['state']=='draft'
    assert app.state.store.campaign(cid)['released']==0
    app.state.store.publication_result(p1['id'],'cancelled')
    bad=c.post(f"/api/publications/{p2['id']}/approve",json={
      'fingerprint':p1['fingerprint'],'content_reviewed':True,'rights_confirmed':True,'account_authorized':True})
    assert bad.status_code==422


def test_existing_remote_posts_are_never_rewritten(setup,movie):
    c,db,cid=setup[0],setup[1].state.store,setup[2]
    f=upload(setup,movie).json();p=publication(setup,f).json()
    db.publication_result(p['id'],'submitted',receipt={'id':'remote-existing'})
    before=db.publication(p['id'])
    assert upload(setup,movie,title='Second').status_code==201
    assert db.publication(p['id'])==before


@pytest.mark.parametrize('stage',['submitting','needs_reconciliation'])
def test_import_cannot_obscure_uncertain_send(setup,movie,stage):
    c,app,cid=setup
    f=upload(setup,movie).json();p=publication(setup,f).json()
    app.state.store.publication_result(p['id'],stage)
    assert upload(setup,movie).status_code==409
    assert len(ff.list_films(app.state.store,cid))==1


def test_dry_run_then_mocked_live_send(setup,movie,monkeypatch):
    c,app,cid=setup
    integrations=AsyncMock(return_value=[{'id':'account'}]);send=AsyncMock(return_value={'id':'post-123'})
    monkeypatch.setattr('launchloom.server.PostizPublisher.integrations',integrations)
    monkeypatch.setattr('launchloom.server.PostizPublisher.submit',send)
    f=upload(setup,movie,ai_generated='true').json();p=publication(setup,f).json()
    assert p['payload']['ai_generated'] is True
    dry=c.get(f"/api/publications/{p['id']}/dry-run").json()
    assert dry['network_requests']==0
    assert dry['postiz_body']['posts'][0]['settings']['made_with_ai'] is True
    send.assert_not_awaited();integrations.assert_not_awaited()
    assert c.post(f"/api/publications/{p['id']}/submit").status_code==409
    assert c.post(f'/api/campaigns/{cid}/release',json={'confirmed':True}).status_code==200
    assert approve(c,p).status_code==200
    result=c.post(f"/api/publications/{p['id']}/submit")
    assert result.status_code==200,result.text
    assert result.json()['state']=='submitted' and result.json()['remote_state'] is None
    send.assert_awaited_once()
    assert send.call_args.args[1].read_bytes()==c.get(f['url']).content
    assert c.post(f"/api/publications/{p['id']}/submit").status_code!=200
    send.assert_awaited_once()


@pytest.mark.parametrize('step',['prepare','approve','submit','preview'])
def test_tampered_media_fails_closed(setup,movie,step,monkeypatch):
    c,app,cid=setup
    f=upload(setup,movie).json();p=publication(setup,f).json()
    approve(c,p);app.state.store.release_campaign(cid,True)
    (app.state.settings.data_dir/'campaigns'/cid/f['media']).write_bytes(b'changed')
    send=AsyncMock();monkeypatch.setattr('launchloom.server.PostizPublisher.submit',send)
    if step=='prepare':r=publication(setup,f)
    elif step=='approve':r=approve(c,p)
    elif step=='submit':r=c.post(f"/api/publications/{p['id']}/submit")
    else:r=c.get(f['url'])
    assert r.status_code in {404,409,422}
    send.assert_not_awaited()


def test_cross_campaign_media_cannot_be_selected(setup,movie):
    c,app,cid=setup
    f=upload(setup,movie).json()
    other=c.post('/api/campaigns',json=SAMPLE_BRIEF).json()['id']
    assert publication((c,app,other),f).status_code==422
    assert c.get(f'/artifacts/{other}/{f["media"]}').status_code==404


@pytest.mark.parametrize('media',['../private.mp4','finals/../../x.mp4','/tmp/a.mp4','finals/a.mp4','finals/'+'a'*16+'\n'+'a'*16+'.mp4'])
def test_unsafe_media_is_rejected(media):
    with pytest.raises(ValueError):PublicationDraft(channel='x',content='demo',integration_id='a',media=media)


def test_false_rights_or_unknown_ai_are_rejected(setup,movie):
    assert upload(setup,movie,rights_confirmed='false').status_code==422
    assert upload(setup,movie,ai_generated='unknown').status_code==422


@pytest.mark.parametrize('payload',[b'',b'not a movie'])
def test_bad_media_is_not_registered(setup,payload):
    c,app,cid=setup
    assert upload(setup,payload).status_code==422
    assert ff.list_films(app.state.store,cid)==[]
    assert not list((app.state.settings.data_dir/'campaigns'/cid).rglob('*.mp4'))
    assert not list((app.state.settings.data_dir/'campaigns'/cid).rglob('*.upload'))


def test_limits_are_enforced_while_streaming(setup,movie,monkeypatch):
    monkeypatch.setattr(ff,'MAX_FINAL_BYTES',32)
    assert upload(setup,movie).status_code==413
    assert ff.list_films(setup[1].state.store,setup[2])==[]


def test_concurrent_render_rejects_import(setup,movie):
    c,app,cid=setup
    app.state.store.progress(cid,'render',50,'building')
    assert upload(setup,movie).status_code==409


def test_symlink_directory_is_rejected(setup,movie,tmp_path):
    c,app,cid=setup
    root=app.state.settings.data_dir/'campaigns'/cid;root.mkdir()
    (root/'finals').symlink_to(tmp_path,target_is_directory=True)
    assert upload(setup,movie).status_code==422
    assert not list(tmp_path.glob('*.mp4'))
