import asyncio
import copy
import shutil
import subprocess
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from launchloom.config import Settings
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.server import create_app

@pytest.fixture
def studio(tmp_path):
    s=Settings(data_dir=tmp_path/'data',token='test-abcdefghijklmnopqrstuvwxyz',fal_key='test-fal-key',enable_paid_generation=True,budget_usd=2)
    app=create_app(s,run_worker=False);c=TestClient(app);c.headers['Authorization']='Bearer '+s.token
    brief=copy.deepcopy(SAMPLE_BRIEF);brief['description']='PRIVATE_DESCRIPTION';brief['features'][0]['evidence']='PRIVATE_EVIDENCE'
    cid=c.post('/api/campaigns',json=brief).json()['id']
    p=c.get(f'/api/campaigns/{cid}/production').json()
    r={'expected_revision':p['revision'],'scene_id':'opening','resolution':'480p','generate_audio':False,'take':0,'estimated_cost_usd':0.5,'external_data_consent':True,'charge_confirmed':True}
    return c,app,cid,s,r


def test_job_auth_consent_schema_and_no_side_effects(studio):
    c,app,cid,s,r=studio;url=f'/api/campaigns/{cid}/scene-jobs'
    assert TestClient(app).get(url).status_code==401
    assert c.post(url,headers={'Origin':'https://bad.example'},json=r).status_code==403
    for k in ['external_data_consent','charge_confirmed']:
        assert c.post(url,json=dict(r,**{k:False})).status_code==422
        assert c.post(url,json=dict(r,**{k:'true'})).status_code==422
    assert c.post(url,json=dict(r,resolution='1080p')).status_code==422
    assert c.post(url,json=dict(r,expected_revision='0'*64)).status_code==409
    assert c.post(url,json=dict(r,scene_id='product')).status_code==422
    j=c.post(url,json=r);assert j.status_code==202,j.text
    data=j.json();assert data['state']=='queued'
    assert set(data['spec']['input'])=={'prompt','duration','aspect_ratio','resolution','generate_audio'}
    assert 'PRIVATE_' not in j.text
    assert not app.state.store.campaign(cid)['released']
    assert app.state.store.publications(cid)==[]
    assert c.get(url).json()['live_verified'] is False


def test_idempotency_budget_cancellation_and_disabled(studio):
    c,app,cid,s,r=studio;url=f'/api/campaigns/{cid}/scene-jobs'
    j=c.post(url,json=r).json()
    assert c.post(url,json=r).json()['id']==j['id']
    assert c.post(url,json=dict(r,estimated_cost_usd=0.6)).json()['id']==j['id']
    assert c.post(url,json=dict(r,take=1,estimated_cost_usd=1.6)).status_code==409
    assert c.post(url+'/'+j['id']+'/cancel').json()['state']=='cancelled'
    assert c.post(url+'/'+j['id']+'/cancel').status_code==409
    s.enable_paid_generation=False
    assert c.post(url,json=dict(r,take=1)).status_code==409


def test_worker_receives_video_and_does_not_regenerate_on_repeat(studio,tmp_path,monkeypatch):
    c,app,cid,s,r=studio;url=f'/api/campaigns/{cid}/scene-jobs'
    movie=tmp_path/'scene.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24','-t','4','-c:v','libx264','-threads','1','-y',str(movie)],check=True)
    calls=[]
    async def generate(self,prompt,options,path):
        calls.append((prompt,options.provider_input));shutil.copyfile(movie,path)
    monkeypatch.setattr('launchloom.scene_jobs.FalFilm.generate',generate)
    j=c.post(url,json=r).json()
    assert asyncio.run(app.state.scene_jobs.run_once())
    out=c.get(url).json()['items'][0];assert out['state']=='ready'
    assert c.get(out['media_url']).content[4:8]==b'ftyp'
    assert c.post(url,json=r).json()['id']==j['id']
    assert not asyncio.run(app.state.scene_jobs.run_once())
    assert len(calls)==1
    assert app.state.final_media.selected(cid)==[]
    assert not app.state.store.campaign(cid)['released']


def test_failure_redaction_and_explicit_resume(studio,monkeypatch):
    c,app,cid,s,r=studio;url=f'/api/campaigns/{cid}/scene-jobs'
    async def fail(*args):raise RuntimeError('Provider failed with '+s.fal_key)
    monkeypatch.setattr('launchloom.scene_jobs.FalFilm.generate',fail)
    j=c.post(url,json=r).json();asyncio.run(app.state.scene_jobs.run_once())
    failed=c.get(url).json()['items'][0]
    assert failed['state']=='failed' and s.fal_key not in failed['error']
    assert not asyncio.run(app.state.scene_jobs.run_once())
    resumed=c.post(url+'/'+j['id']+'/resume').json();assert resumed['id']==j['id'] and resumed['state']=='queued'
    app.state.scene_jobs.recover()
    assert c.get(url).json()['items'][0]['state']=='interrupted'
    assert c.get(url+'/'+j['id']+'/media').status_code==409
