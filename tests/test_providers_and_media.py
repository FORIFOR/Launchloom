"""Contract tests use mocked HTTP responses, not paid services or real SNS accounts."""
from __future__ import annotations
import asyncio
import json
import subprocess
from pathlib import Path
import httpx
import pytest
from launchloom.config import Settings
from launchloom.models import BuildOptions,Brief
from launchloom.pipeline import SAMPLE_BRIEF
from launchloom.providers import FalFilm,ComfyFilm,llm_plan,download_public_media
from launchloom.rendering import normalize_upload,validate_media
from launchloom.store import Store

@pytest.fixture
def s(tmp_path):
    return Settings(data_dir=tmp_path,token='test-token-with-enough-characters',fal_key='fake-key',fal_model='test-owner/test-video',enable_paid_generation=True,budget_usd=2,comfy_base='http://comfy.example',llm_base='https://llm.example/v1',llm_model='operator-selected-model',llm_key='fake-llm-key')
@pytest.fixture
def db(tmp_path):return Store(tmp_path/'db.sqlite')
def install_http(monkeypatch,handler):
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda *args,**kwargs:original(*args,**kwargs,transport=httpx.MockTransport(handler)))

def test_fal_queue_ticket_resumes_without_new_charge(monkeypatch,s,db,tmp_path):
    calls=[]
    def handle(r):
        calls.append((r.method,r.url.path))
        assert r.headers['Authorization']=='Key fake-key'
        if r.method=='POST':return httpx.Response(200,json={'request_id':'job-1','status_url':'https://queue.fal.run/status/1','response_url':'https://queue.fal.run/result/1'})
        if '/status/' in r.url.path:return httpx.Response(200,json={'status':'COMPLETED'})
        return httpx.Response(200,json={'video':{'url':'https://cdn.example/video.mp4'}})
    install_http(monkeypatch,handle)
    async def fake_download(client,url,path):path.write_bytes(b'contract-test-media')
    monkeypatch.setattr('launchloom.providers.download_public_media',fake_download)
    o=BuildOptions(film_provider='fal',external_data_consent=True,estimated_cost_usd=.5)
    p=FalFilm(s,db,'campaign');out=tmp_path/'film.mp4'
    asyncio.run(p.generate('original concept',o,out));out.unlink()
    asyncio.run(p.generate('original concept',o,out))
    assert sum(method=='POST' for method,path in calls)==1
    assert out.read_bytes()==b'contract-test-media'

def test_fal_unknown_submission_does_not_resubmit(monkeypatch,s,db,tmp_path):
    calls=[]
    def handle(r):calls.append(r);raise httpx.ReadTimeout('Uncertain',request=r)
    install_http(monkeypatch,handle)
    p=FalFilm(s,db,'campaign');o=BuildOptions(film_provider='fal',external_data_consent=True,estimated_cost_usd=.5)
    with pytest.raises(httpx.ReadTimeout):asyncio.run(p.generate('original concept',o,tmp_path/'film.mp4'))
    with pytest.raises(ValueError,match='uncertain'):asyncio.run(p.generate('original concept',o,tmp_path/'film.mp4'))
    assert len(calls)==1

def test_fal_rejects_credential_exfiltration_ticket(monkeypatch,s,db,tmp_path):
    calls=[]
    def handle(r):
        calls.append(r)
        return httpx.Response(200,json={'request_id':'x','status_url':'https://evil.example/steal','response_url':'https://evil.example/steal'})
    install_http(monkeypatch,handle)
    o=BuildOptions(film_provider='fal',external_data_consent=True,estimated_cost_usd=.5)
    with pytest.raises(ValueError,match='queue host'):asyncio.run(FalFilm(s,db,'campaign').generate('concept',o,tmp_path/'film.mp4'))
    assert len(calls)==1

def test_comfy_workflow_preserves_prompt_escaping(monkeypatch,s,db,tmp_path):
    calls=[];prompt='Original "blue" light\n日本語'
    def handle(r):
        calls.append(r)
        if r.url.path=='/prompt':
            assert json.loads(r.content)['prompt']['1']['inputs']['text']==prompt
            return httpx.Response(200,json={'prompt_id':'job-1'})
        if r.url.path.startswith('/history/'):
            return httpx.Response(200,json={'job-1':{'status':{'completed':True},'outputs':{'9':{'videos':[{'filename':'film.mp4','subfolder':'','type':'output'}]}}}})
        assert r.url.path=='/view';return httpx.Response(200,content=b'contract-test-media')
    install_http(monkeypatch,handle)
    monkeypatch.setattr('launchloom.rendering.validate_media',lambda *a,**kw:{})
    o=BuildOptions(film_provider='comfy',external_data_consent=True,provider_input={'workflow':{'1':{'class_type':'CLIPTextEncode','inputs':{'text':'{{video_prompt}}'}}}})
    path=asyncio.run(ComfyFilm(s,db,'campaign').generate(prompt,o,tmp_path/'film.mp4'))
    assert path.read_bytes()==b'contract-test-media' and len(calls)==3

def test_llm_cannot_overwrite_product_claims(monkeypatch,s):
    brief=Brief.model_validate(SAMPLE_BRIEF)
    def handle(r):
        body=json.loads(r.content);assert body['model']=='operator-selected-model'
        submitted=json.loads(body['messages'][1]['content'])
        assert all('evidence' not in f for f in submitted['approved_features'])
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'concept':'A coherent quiet world','visual_direction':'Soft light','video_prompt':'Original orbit of light','scenes':[{'title':'False million-user claim'}]})}}]})
    install_http(monkeypatch,handle)
    plan=asyncio.run(llm_plan(brief,s));assert plan.source=='configured-llm'
    assert all('million' not in sc.title for sc in plan.scenes)
    assert plan.scenes[1].title==brief.features[0].title

def test_paid_generation_default_disabled(s,db,tmp_path):
    s.enable_paid_generation=False
    with pytest.raises(ValueError,match='disabled'):asyncio.run(FalFilm(s,db,'x').generate('x',BuildOptions(),tmp_path/'file'))

def test_browser_webm_without_duration_can_be_uploaded(tmp_path):
    path=tmp_path/'recorder.webm'
    encoded=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=320x180:rate=10:duration=1','-c:v','libvpx','-threads','1','-f','webm','pipe:1'],capture_output=True,check=True).stdout
    path.write_bytes(encoded)
    raw=json.loads(subprocess.run(['ffprobe','-v','error','-show_format','-of','json',str(path)],capture_output=True,check=True).stdout)
    assert 'duration' not in raw['format']
    normalize_upload(path)
    result=validate_media(path)
    assert .9<=float(result['format']['duration'])<=1.2

from launchloom.rendering import camera_pose

def test_camera_holds_zoom_instead_of_bouncing_back():
    events=[{'time':1.0,'x':.25,'y':.35,'action':'click'},{'time':3.0,'x':.74,'y':.62,'action':'click'}]
    first=camera_pose(2.0,events)
    later=camera_pose(2.7,events)
    assert first[2] > 1.15
    assert abs(later[2]-first[2]) < .01

def test_camera_transition_has_no_start_jump():
    events=[{'time':1.0,'x':.25,'y':.35,'action':'click'}]
    before=camera_pose(.819,events)
    start=camera_pose(.821,events)
    assert abs(start[0]-before[0]) < .002
    assert abs(start[1]-before[1]) < .002
    assert abs(start[2]-before[2]) < .002

def test_camera_ignores_tiny_retarget_jitter():
    events=[{'time':1.0,'x':.50,'y':.50,'action':'click'},{'time':2.0,'x':.53,'y':.52,'action':'click'}]
    a=camera_pose(1.9,events)
    b=camera_pose(2.6,events)
    assert abs(a[0]-b[0]) < .005
    assert abs(a[1]-b[1]) < .005


def test_trim_needs_footage_to_exist(tmp_path,monkeypatch):
    """A start point past the end must fail before an encoder is opened."""
    from launchloom.models import Brief
    from launchloom.planning import make_plan
    from launchloom import rendering
    brief=Brief.model_validate(SAMPLE_BRIEF)
    clip=tmp_path/'clip.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc=size=320x200:rate=24:duration=4',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True)
    with pytest.raises(ValueError,match='past the end'):
        rendering.render(brief,make_plan(brief),tmp_path/'out',clip,[],capture_start=4.0)

def test_trim_shortens_the_proof_section(tmp_path):
    from launchloom.models import Brief
    from launchloom.planning import make_plan
    from launchloom import rendering
    brief=Brief.model_validate(SAMPLE_BRIEF)
    clip=tmp_path/'clip.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc=size=320x200:rate=24:duration=12',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True)
    full=rendering.render(brief,make_plan(brief),tmp_path/'full',clip,[],quality='draft')
    cut=rendering.render(brief,make_plan(brief),tmp_path/'cut',clip,[],quality='draft',capture_start=2.0,capture_length=4.0)
    assert round(full['landscape']['duration'])==18 and round(cut['landscape']['duration'])==10


def audio_file(path,seconds,frequency):
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'sine=frequency={frequency}:duration={seconds}',
                    '-c:a','aac',str(path)],check=True)
    return path

def test_music_and_narration_are_mixed_into_one_track(tmp_path):
    from launchloom.models import Brief
    from launchloom.planning import make_plan
    from launchloom import rendering
    brief=Brief.model_validate(SAMPLE_BRIEF)
    music=audio_file(tmp_path/'music.m4a',20,220)
    narration=audio_file(tmp_path/'voice.m4a',6,440)
    result=rendering.render(brief,make_plan(brief),tmp_path/'out',None,[],quality='draft',
                            audio=music,narration=narration)
    assert result['landscape']['audio']=={'music':True,'narration':True}
    probe=rendering.probe(tmp_path/'out/landscape.mp4')
    streams=[s for s in probe['streams'] if s['codec_type']=='audio']
    assert len(streams)==1 and streams[0]['codec_name']=='aac'
    # The soundtrack is cut to the film, never left running past the last frame.
    assert abs(float(probe['format']['duration'])-15)<1

def test_a_single_track_still_works(tmp_path):
    from launchloom.models import Brief
    from launchloom.planning import make_plan
    from launchloom import rendering
    brief=Brief.model_validate(SAMPLE_BRIEF)
    result=rendering.render(brief,make_plan(brief),tmp_path/'out',None,[],quality='draft',
                            audio=audio_file(tmp_path/'music.m4a',20,220))
    assert result['landscape']['audio']=={'music':True,'narration':False}
    assert [s for s in rendering.probe(tmp_path/'out/landscape.mp4')['streams'] if s['codec_type']=='audio']

def test_a_silent_film_has_no_audio_stream(tmp_path):
    from launchloom.models import Brief
    from launchloom.planning import make_plan
    from launchloom import rendering
    brief=Brief.model_validate(SAMPLE_BRIEF)
    result=rendering.render(brief,make_plan(brief),tmp_path/'out',None,[],quality='draft')
    assert result['landscape']['audio']=={'music':False,'narration':False}
    assert not [s for s in rendering.probe(tmp_path/'out/landscape.mp4')['streams'] if s['codec_type']=='audio']


def test_review_still_skips_a_blank_opening_frame(tmp_path):
    """Screen recordings often open on a white page. A blank still proves nothing,
    so the review gate must sample further in."""
    from PIL import Image, ImageStat
    from launchloom.pipeline import review_still
    clip=tmp_path/'clip.mp4'
    # two seconds of white, then a test pattern
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=white:size=320x200:rate=24:duration=2',
                    '-f','lavfi','-i','testsrc=size=320x200:rate=24:duration=6',
                    '-filter_complex','[0:v][1:v]concat=n=2:v=1[v]','-map','[v]',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True)
    root=tmp_path/'campaign';root.mkdir()
    review_still(root,clip)
    still=root/'review-frame.jpg'
    assert still.is_file()
    assert max(ImageStat.Stat(Image.open(still)).stddev)>12, 'the review still is blank'

def test_review_still_respects_the_chosen_range(tmp_path):
    from launchloom.pipeline import review_still
    clip=tmp_path/'clip.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc=size=320x200:rate=24:duration=6',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True)
    root=tmp_path/'campaign';root.mkdir()
    review_still(root,clip,start=3.0)
    assert (root/'review-frame.jpg').is_file()
