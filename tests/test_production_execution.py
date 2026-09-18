import os
import stat
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from launchloom.config import Settings
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.production import initial_plan, revision
from launchloom.production_execution import (
    SEEDANCE_MODEL, agent_command, prepare_workspace, run_agent,
    run_after_effects_project, run_after_effects_render, seedance_estimate_usd,
    validate_agent_jsx,
)
from launchloom.server import create_app


@pytest.fixture(scope='module')
def movie(tmp_path_factory):
    out=tmp_path_factory.mktemp('production-exec')/'movie.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
        '-f','lavfi','-i','sine=frequency=330:sample_rate=44100','-t','5',
        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(out)],check=True)
    return out


@pytest.fixture
def setup(tmp_path):
    settings=Settings(data_dir=tmp_path/'data',token='production-execution-test-token-123456',
        seedance_price_per_1k_tokens_usd=.0214,production_execution_timeout_seconds=30)
    app=create_app(settings,run_worker=False)
    client=TestClient(app);client.headers['Authorization']='Bearer '+settings.token
    cid=client.post('/api/campaigns',json=SAMPLE_BRIEF).json()['id']
    production=client.get(f'/api/campaigns/{cid}/production').json()
    for scene in production['plan']['scenes']:
        if scene['id']=='product': scene['seconds']=4
    saved=client.put(f'/api/campaigns/{cid}/production',json={
        'plan':production['plan'],'expected_revision':production['revision']}).json()
    return client,app,cid,saved


def test_seedance_cost_formula_and_duration_gate():
    expected=1280*720*4*24/1024/1000*.0214
    assert seedance_estimate_usd(4,'16:9','720p',.0214)==round(expected,6)
    with pytest.raises(ValueError,match='integer scene duration'):
        seedance_estimate_usd(3,'16:9','720p',.0214)
    with pytest.raises(ValueError,match='integer scene duration'):
        seedance_estimate_usd(4.5,'16:9','720p',.0214)


def test_execution_status_is_safe_and_disabled_by_default(setup):
    client,_,cid,saved=setup
    data=client.get(f'/api/campaigns/{cid}/production/execution').json()
    assert data['revision']==saved['revision'] and data['saved'] is True
    assert data['notes']['seedance_model']==SEEDANCE_MODEL
    assert data['notes']['live_publish'] is False
    assert data['capabilities']=={'seedance':False,'codex':False,'claude':False,'after_effects_project':False,'aerender':False}


def test_scene_upload_requires_rights_and_accepts_large_media_route(setup,movie):
    client,_,cid,saved=setup
    url=f'/api/campaigns/{cid}/production/scenes/product/media'
    assert client.post(url,params={'expected_revision':saved['revision']},content=movie.read_bytes()).status_code==422
    ok=client.post(url,params={'expected_revision':saved['revision'],'rights_confirmed':'true'},
                   content=movie.read_bytes(),headers={'Content-Type':'application/octet-stream'})
    assert ok.status_code==200,ok.text
    assert ok.json()['sha256'] and ok.json()['duration']>=4
    # The route ends in /media, so the generic 2 MB JSON/request cap does not reject it.
    bad=client.post(url,params={'expected_revision':saved['revision'],'rights_confirmed':'true'},
                    content=b'x'*(3*1024*1024),headers={'Content-Type':'application/octet-stream'})
    assert bad.status_code==422


def test_revision_binding_and_save_lock(setup):
    client,app,cid,saved=setup
    plan=client.get(f'/api/campaigns/{cid}/production').json()
    changed=plan['plan'];changed['title']='new revision'
    newer=client.put(f'/api/campaigns/{cid}/production',json={'plan':changed,'expected_revision':saved['revision']})
    assert newer.status_code==200
    assert client.post(f'/api/campaigns/{cid}/production/prepare',json={'expected_revision':saved['revision']}).status_code==409
    app.state.production_execution_busy.add(cid)
    try:
        current=newer.json()
        assert client.put(f'/api/campaigns/{cid}/production',json={'plan':current['plan'],'expected_revision':current['revision']}).status_code==409
    finally:app.state.production_execution_busy.discard(cid)


def test_seedance_requires_confirmation_and_paid_configuration(setup):
    client,_,cid,_=setup
    current=client.get(f'/api/campaigns/{cid}/production').json()
    # opening is 4 seconds and Seedance-sourced in the default production plan.
    path=f'/api/campaigns/{cid}/production/scenes/opening/seedance'
    missing=client.post(path,json={'expected_revision':current['revision'],'resolution':'720p','confirmed':False})
    assert missing.status_code==422
    configured=client.post(path,json={'expected_revision':current['revision'],'resolution':'720p','confirmed':True})
    assert configured.status_code==422 and ('disabled' in configured.text.lower() or 'FAL_KEY' in configured.text)


def test_workspace_is_revision_scoped_and_contains_no_parent_secrets(tmp_path):
    root=tmp_path/'campaign';root.mkdir();(root/'.env').write_text('SECRET=do-not-copy')
    plan=initial_plan({'name':'Demo','tagline':'Show it','features':[]})
    rev=revision(plan);workspace=prepare_workspace(root,rev,plan)
    assert workspace.name==rev
    assert (workspace/'production.json').is_file() and (workspace/'build.jsx').is_file()
    assert not (workspace/'.env').exists()
    assert 'do-not-copy' not in '\n'.join(p.read_text(errors='ignore') for p in workspace.rglob('*') if p.is_file())


def _fake_agent(path: Path, malicious=False):
    text='''#!/usr/bin/env python3\nfrom pathlib import Path\np=Path.cwd()/"build.jsx"\ns=p.read_text()\n'''
    if malicious:text+='p.write_text(s+"\\nSocket(\\\"bad\\\")")\n'
    else:text+='p.write_text(s+"\\n// agent refined")\n'
    path.write_text(text);path.chmod(path.stat().st_mode|stat.S_IXUSR)


def test_codex_command_is_workspace_scoped_and_network_disabled(tmp_path):
    exe=tmp_path/'codex';_fake_agent(exe)
    s=Settings(data_dir=tmp_path/'d',token='x'*30,enable_local_agents=True,codex_executable=str(exe),openai_api_key='test')
    cwd=tmp_path/'w';cwd.mkdir()
    args,env=agent_command(s,'codex',cwd,'task')
    joined=' '.join(args)
    assert '--sandbox workspace-write' in joined and '--cd '+str(cwd) in joined
    assert 'sandbox_workspace_write.network_access=false' in joined and 'web_search="disabled"' in joined
    assert '--ignore-user-config' in args and '--ignore-rules' in args and '--skip-git-repo-check' in args
    assert env.get('OPENAI_API_KEY')=='test' and 'FAL_KEY' not in env


def test_agent_accepts_only_reviewable_jsx(tmp_path):
    plan=initial_plan({'name':'Demo','tagline':'Show it','features':[]});rev=revision(plan)
    root=tmp_path/'campaign';root.mkdir();workspace=prepare_workspace(root,rev,plan)
    good=tmp_path/'good';_fake_agent(good)
    s=Settings(data_dir=tmp_path/'d',token='x'*30,enable_local_agents=True,codex_executable=str(good),openai_api_key='key')
    result=run_agent(s,workspace,plan,'codex')
    assert result['name']=='codex' and '// agent refined' in (workspace/'build.jsx').read_text()
    bad=tmp_path/'bad';_fake_agent(bad,malicious=True);s.codex_executable=str(bad)
    with pytest.raises(ValueError,match='blocked'):
        run_agent(s,workspace,plan,'codex')


def test_agent_validator_requires_scene_ids():
    plan=initial_plan({'name':'Demo','tagline':'Show it','features':[]})
    with pytest.raises(ValueError,match='required production identifiers'):
        validate_agent_jsx('Launchloom_Film launchloom-project.aep',plan)


def test_after_effects_project_never_runs_automatically_on_non_windows(tmp_path,monkeypatch):
    plan={'schema_version':1,'title':'AE only','aspect_ratio':'16:9','fps':30,
          'scenes':[{'id':'motion','source':'after_effects','title':'Motion','prompt':'','seconds':4}]}
    root=tmp_path/'c';root.mkdir();workspace=prepare_workspace(root,revision(plan),plan)
    s=Settings(data_dir=tmp_path/'d',token='x'*30,enable_after_effects=True,afterfx_executable='/fake/afterfx')
    monkeypatch.setattr('launchloom.production_execution.platform.system',lambda:'Darwin')
    with pytest.raises(ValueError,match='limited to Windows'):
        run_after_effects_project(s,workspace,plan)


def test_aerender_registers_new_immutable_final(tmp_path,monkeypatch,movie):
    from launchloom.store import Store
    from launchloom.models import Brief
    data=tmp_path/'data';settings=Settings(data_dir=data,token='x'*30,enable_after_effects=True,aerender_executable='/fake/aerender')
    settings.prepare();db=Store(data/'launchloom.sqlite3')
    brief=Brief.model_validate(SAMPLE_BRIEF);cid=db.create_campaign(brief.model_dump())['id']
    plan={'schema_version':1,'title':'AE only','aspect_ratio':'16:9','fps':30,
          'scenes':[{'id':'motion','source':'after_effects','title':'Motion','prompt':'','seconds':4}]}
    root=data/'campaigns'/cid;workspace=prepare_workspace(root,revision(plan),plan)
    (workspace/'launchloom-project.aep').write_bytes(b'fake-aep')
    def fake_run(args,cwd,env,timeout):
        (cwd/'render').mkdir(exist_ok=True);(cwd/'render'/'ae-master.mov').write_bytes(movie.read_bytes())
    monkeypatch.setattr('launchloom.production_execution.run_command',fake_run)
    film=run_after_effects_render(settings,db,cid,root,workspace,plan)
    assert film['media'].startswith('finals/') and film['ai_generated'] is False
    assert (root/film['media']).is_file() and db.campaign(cid)['released']==0
