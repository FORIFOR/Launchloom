import json
import subprocess
from types import SimpleNamespace
import pytest
from launchloom import motion_runner as m
from launchloom.production import initial_plan
from launchloom.security import file_sha

@pytest.fixture
def setup(tmp_path):
    plan=tmp_path/'production.json';plan.write_text(json.dumps(initial_plan({'name':'Film','tagline':'Story','features':[]})))
    return plan,tmp_path/'candidate.jsx'

def test_confirmation_missing_credentials_and_overwrite(setup,monkeypatch):
    plan,dest=setup
    with pytest.raises(ValueError,match='confirm'):m.agent(plan,dest,'codex','codex',False)
    monkeypatch.setattr(m,'executable',lambda v:v)
    monkeypatch.delenv('CODEX_API_KEY',raising=False)
    with pytest.raises(ValueError,match='CODEX_API_KEY'):m.agent(plan,dest,'codex','codex',True)
    dest.write_text('Do not overwrite')
    with pytest.raises(ValueError,match='overwrite'):m.agent(plan,dest,'codex','codex',True)
    assert dest.read_text()=='Do not overwrite'

@pytest.mark.parametrize('provider',['codex','claude'])
def test_agent_contract_environment_and_no_ae_execution(setup,monkeypatch,provider):
    plan,dest=setup;calls=[]
    monkeypatch.setenv('CODEX_API_KEY','test-openai-key');monkeypatch.setenv('ANTHROPIC_API_KEY','test-anthropic-key')
    monkeypatch.setenv('POSTIZ_API_KEY','must-not-leave');monkeypatch.setenv('FAL_KEY','must-not-leave')
    monkeypatch.setattr(m,'executable',lambda v:v)
    candidate={'jsx':'// review me\n(function(){ var title="Film"; }());','notes':'Mock transport, not actual model output'}
    def run(args,**kw):
        calls.append(args)
        assert 'POSTIZ_API_KEY' not in kw['env'] and 'FAL_KEY' not in kw['env']
        assert 'must-not-leave' not in kw['input'].decode()
        assert kw.get('shell',False) is False
        if provider=='codex':
            assert 'ANTHROPIC_API_KEY' not in kw['env']
            assert 'features.shell_tool=false' in args and 'read-only' in args
            (kw['cwd']/'response.json').write_text(json.dumps(candidate))
        else:
            assert 'CODEX_API_KEY' not in kw['env']
            assert '--tools' in args and '' in args and '--bare' in args
            kw['stdout'].write(json.dumps({'structured_output':candidate}).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(m.subprocess,'run',run)
    r=m.agent(plan,dest,provider,provider,True)
    assert r['state']=='candidate_requires_review' and not r['adobe_executed']
    assert r['sha256']==file_sha(dest) and len(calls)==1


def test_rejects_model_errors_and_unsafe_candidate(setup,monkeypatch):
    plan,dest=setup;monkeypatch.setenv('CODEX_API_KEY','test');monkeypatch.setattr(m,'executable',lambda v:v)
    def run(args,**kw):
        (kw['cwd']/'response.json').write_text(json.dumps({'jsx':'system.callSystem("untrusted");','notes':''}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(ValueError,match='system/network'):m.agent(plan,dest,'codex','codex',True)
    assert not dest.exists()


def test_review_hash_and_build_platform_gate(tmp_path,monkeypatch):
    p=tmp_path/'script.jsx';p.write_text('// candidate')
    with pytest.raises(ValueError,match='hash'):m.reviewed(p,'0'*64)
    with pytest.raises(ValueError,match='confirm'):m.build(p,file_sha(p),'afterfx',False)
    monkeypatch.setattr(m.sys,'platform','darwin')
    with pytest.raises(ValueError,match='Windows-only'):m.build(p,file_sha(p),'afterfx',True)


def test_render_checks_real_media_and_never_overwrites(tmp_path,monkeypatch):
    project=tmp_path/'reviewed.aep';project.write_text('mock AE project')
    output=tmp_path/'final.mp4';sha=file_sha(project)
    real_run=subprocess.run
    monkeypatch.setattr(m,'executable',lambda v:v)
    def run(args,**kw):
        assert args[:3]==['aerender','-project',str(project)]
        real_run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=320x180:rate=24','-t','1','-c:v','libx264','-threads','1','-y',str(output)],check=True)
        return SimpleNamespace(returncode=0)
    # validate_media's probe uses the same subprocess module, so dispatch probe normally.
    def dispatch(args,**kw):return run(args,**kw) if args[0]=='aerender' else real_run(args,**kw)
    monkeypatch.setattr(m.subprocess,'run',dispatch)
    r=m.render(project,sha,output,'aerender','Launchloom_Film','User configured H264',True)
    assert r['state']=='rendered_requires_visual_review' and r['published'] is False
    with pytest.raises(ValueError,match='new'):m.render(project,sha,output,'aerender','Launchloom_Film','template',True)
