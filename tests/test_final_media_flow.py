from __future__ import annotations
import copy
import json
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from launchloom.config import Settings
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.server import create_app
from launchloom.security import file_sha
from launchloom.production_api import register_production_routes


@pytest.fixture(scope='module')
def clip(tmp_path_factory):
    path=tmp_path_factory.mktemp('film')/'real.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                    '-f','lavfi','-i','sine=frequency=500:sample_rate=44100','-t','1',
                    '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-y',str(path)],check=True)
    return path.read_bytes()


@pytest.fixture
def studio(tmp_path):
    settings=Settings(data_dir=tmp_path/'data',token='test-local-token-with-32-characters',
                      enable_live_publish=True,postiz_base='https://postiz.example/public/v1',postiz_key='mock')
    app=create_app(settings,run_worker=False)
    client=TestClient(app)
    client.headers['Authorization']='Bearer '+settings.token
    brief=copy.deepcopy(SAMPLE_BRIEF);brief['name']='External film';brief['channels']=['x']
    cid=client.post('/api/campaigns',json=brief).json()['id']
    return client,app,cid,settings


def upload(studio,clip,*,ai=True,title='After Effects export'):
    c,_,cid,_=studio
    r=c.post(f'/api/campaigns/{cid}/finals/media',params={'rights_confirmed':'true','ai_generated':str(ai).lower(),'title':title},content=clip)
    assert r.status_code==201,r.text
    return r.json()


def select(studio,asset,epoch):
    c,_,cid,_=studio
    return c.post(f"/api/campaigns/{cid}/finals/{asset['id']}/select",json={'sha256':asset['sha256'],'expected_epoch':epoch,'content_reviewed':True,'rights_confirmed':True})


def draft(studio,asset):
    c,_,cid,_=studio
    return c.post(f'/api/campaigns/{cid}/publications',json={'channel':'x','integration_id':'account-1','content':'Product overview','media':asset['media']})


def approve(studio,pub):
    return studio[0].post(f"/api/publications/{pub['id']}/approve",json={'fingerprint':pub['fingerprint'],'content_reviewed':True,'rights_confirmed':True,'account_authorized':True})


def test_real_factory_includes_routes_once_and_auth(studio):
    c,app,cid,_=studio
    before=len(app.routes);register_production_routes(app);assert len(app.routes)==before
    assert c.get('/production').status_code==200
    assert c.get(f'/api/campaigns/{cid}/production').status_code==200
    assert c.get('/').text.count('id="production-link"')==1
    anon=TestClient(app)
    assert anon.get(f'/api/campaigns/{cid}/finals').status_code==401
    assert anon.post(f'/api/campaigns/{cid}/finals/media').status_code==401
    assert c.post(f'/api/campaigns/{cid}/finals/media',headers={'Origin':'https://bad.example'}).status_code==403


def test_import_review_draft_approve_submit_with_real_mp4(studio,clip,monkeypatch):
    c,app,cid,_=studio
    a=upload(studio,clip)
    assert c.get(f'/api/campaigns/{cid}').json()['state']=='draft'
    assert draft(studio,a).status_code==409
    assert c.post(f'/api/campaigns/{cid}/release',json={'confirmed':True}).status_code==409
    assert select(studio,a,0).status_code==200
    current=c.get(f'/api/campaigns/{cid}').json()
    assert current['publication_ready'] and not current['released'] and current['posts']
    response=c.get(current['outputs'][a['media']]);assert response.status_code==200
    assert response.content[4:8]==b'ftyp'
    assert c.get(f"/artifacts/{cid}/finals/{a['id']}.jpg").status_code==200
    p=draft(studio,a).json();assert p['payload']['ai_generated'] is True
    assert c.get(f"/api/publications/{p['id']}/dry-run").json()['network_requests']==0
    assert approve(studio,p).status_code==200
    assert c.post(f"/api/publications/{p['id']}/submit").status_code==409
    assert c.post(f'/api/campaigns/{cid}/release',json={'confirmed':True}).status_code==200
    calls=[]
    async def integrations(self):return [{'id':'account-1'}]
    async def submit(self,payload,media):
        calls.append((payload,file_sha(media)))
        return [{'postId':'mock-receipt'}]
    monkeypatch.setattr('launchloom.server.PostizPublisher.integrations',integrations)
    monkeypatch.setattr('launchloom.server.PostizPublisher.submit',submit)
    r=c.post(f"/api/publications/{p['id']}/submit")
    assert r.status_code==200,r.text
    assert r.json()['state']=='submitted'
    assert len(calls)==1 and calls[0][1]==a['sha256']
    assert c.post(f"/api/publications/{p['id']}/submit").status_code in {409,422}
    assert len(calls)==1


def test_new_version_invalidates_old_approval_without_overwrite(studio,clip):
    c,app,cid,_=studio
    a=upload(studio,clip);assert select(studio,a,0).status_code==200
    p=draft(studio,a).json();assert approve(studio,p).status_code==200
    c.post(f'/api/campaigns/{cid}/release',json={'confirmed':True})
    before=app.state.final_media.path(cid,a['media']).read_bytes()
    b=upload(studio,clip,ai=False,title='Revised')
    assert c.get(f'/api/campaigns/{cid}').json()['released']==1 # upload alone is not adoption
    assert select(studio,b,0).status_code==409
    assert select(studio,b,1).status_code==200
    assert c.get(f'/api/campaigns/{cid}').json()['released']==0
    assert app.state.store.publication(p['id'])['state']=='superseded'
    assert approve(studio,p).status_code==409
    assert draft(studio,a).status_code==409
    assert app.state.final_media.path(cid,a['media']).read_bytes()==before
    q=draft(studio,b).json();assert q['fingerprint']!=p['fingerprint']
    assert q['payload']['ai_generated'] is False


def test_inflight_blocks_adoption(studio,clip):
    c,app,cid,_=studio
    a=upload(studio,clip);select(studio,a,0)
    p=draft(studio,a).json();approve(studio,p);app.state.store.claim_publication(p['id'])
    b=upload(studio,clip)
    assert select(studio,b,1).status_code==409


def test_checksum_tampering_and_cross_campaign(studio,clip):
    c,app,cid,_=studio
    a=upload(studio,clip)
    app.state.final_media.path(cid,a['media']).write_bytes(b'corrupt')
    assert select(studio,a,0).status_code==409
    cid2=c.post('/api/campaigns',json=copy.deepcopy(SAMPLE_BRIEF)).json()['id']
    assert c.get(f"/artifacts/{cid2}/{a['media']}").status_code==404


@pytest.mark.parametrize('params',[{}, {'rights_confirmed':'true'}, {'rights_confirmed':'false','ai_generated':'true'}])
def test_upload_requires_rights_and_provenance(studio,clip,params):
    c,_,cid,_=studio
    assert c.post(f'/api/campaigns/{cid}/finals/media',params=params,content=clip).status_code==422


def test_reject_invalid_movie_and_paths(studio):
    c,_,cid,_=studio
    r=c.post(f'/api/campaigns/{cid}/finals/media?rights_confirmed=true&ai_generated=false',content=b'#EXTM3U\n/etc/passwd')
    assert r.status_code==422
    assert not list((studio[3].data_dir/'campaigns'/cid/'finals').glob('.upload-*'))
    for media in ['../../etc/passwd','finals/x.mp4','finals/'+'a'*16+'.jpg']:
        assert c.post(f'/api/campaigns/{cid}/publications',json={'channel':'x','integration_id':'a','content':'test','media':media}).status_code==422


def test_select_requires_real_booleans(studio,clip):
    a=upload(studio,clip);c,_,cid,_=studio
    r=c.post(f"/api/campaigns/{cid}/finals/{a['id']}/select",json={'sha256':a['sha256'],'expected_epoch':0,'content_reviewed':'false','rights_confirmed':True})
    assert r.status_code==422
