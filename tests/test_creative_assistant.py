import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from launchloom.creative import CreativeSpec, creative_revision
from launchloom.creative_assistant import EditPlan, VisualReview, apply_operations, public_context, request_plan, capabilities, endpoint
from launchloom.config import Settings
from test_creative_api import fixture_spec


def spec():
    return CreativeSpec.model_validate(fixture_spec())


def test_multiscene_operations_preserve_semantic_bindings():
    before=spec()
    plan=EditPlan.model_validate({'summary':'Tighter opening and calmer ending', 'operations':[
        {'op':'text','scene_id':'opening','layer_id':'headline','text':'Hello, builders.'},
        {'op':'duration','scene_id':'opening','seconds':2},
        {'op':'camera','scene_id':'closing','camera':'gentle_zoom'},
        {'op':'layout','scene_id':'closing','output':'portrait','y':.7,'size':.045},
        {'op':'order','scene_ids':['closing','opening']},
        {'op':'style','preset':'spotlight','accent':'#123456'}]})
    after,changes=apply_operations(before,plan)
    assert len(changes)==6
    assert after.scenes[0].id=='closing' and after.scenes[1].seconds==2
    assert before.scenes[0].layers[0].text=='Make the moment matter.'
    for current in after.scenes:
        prior=next(s for s in before.scenes if s.id==current.id)
        assert current.purpose==prior.purpose and current.claim_ids==prior.claim_ids


@pytest.mark.parametrize('operation',[
    {'op':'shell','command':'echo malicious'},
    {'op':'text','scene_id':'opening','layer_id':'headline','text':'x','asset_id':'foreign'},
    {'op':'duration','scene_id':'opening','seconds':True},
    {'op':'duration','scene_id':'opening','seconds':'5'},
    {'op':'duration','scene_id':'opening','seconds':float('nan')},
    {'op':'duration','scene_id':'opening','seconds':float('inf')},
    {'op':'layout','scene_id':'opening','output':'portrait','y':.95,'size':.1},
    {'op':'camera','scene_id':'opening','camera':'custom'},
    {'op':'style','preset':'editorial','accent':'url(https://bad.invalid)'},
    {'op':'text','scene_id':'../secret','layer_id':'headline','text':'x'},
])
def test_untrusted_operations_fail_closed(operation):
    with pytest.raises(ValueError):
        EditPlan.model_validate({'summary':'x','operations':[operation]})


@pytest.mark.parametrize('operations',[
    [{'op':'text','scene_id':'unknown','layer_id':'headline','text':'x'}],
    [{'op':'text','scene_id':'opening','layer_id':'unknown','text':'x'}],
    [{'op':'order','scene_ids':['opening','opening']}],
    [{'op':'order','scene_ids':['opening']}],
    [{'op':'duration','scene_id':'opening','seconds':2},{'op':'duration','scene_id':'opening','seconds':3}],
])
def test_atomic_apply_rejects_unknown_targets_and_duplicates(operations):
    original=spec();rev=creative_revision(original)
    with pytest.raises(ValueError):apply_operations(original,EditPlan(summary='x',operations=operations))
    assert creative_revision(original)==rev


def test_public_context_excludes_private_fields():
    brief={'name':'Demo','references':['private'], 'features':[
        {'title':'No','approved':False,'evidence':'PRIVATE'},
        {'title':'Yes','detail':'Visible fact','approved':True,'evidence':'PRIVATE-EVIDENCE'}],
        'product_url':'https://example.invalid/?token=PRIVATE-TOKEN'}
    ctx=public_context(spec(),brief,'Keep it calm')
    text=json.dumps(ctx)
    assert 'PRIVATE' not in text and 'references' not in text and 'asset_sha256' not in text
    assert ctx['approved_features'][0]['id']=='feature-1'


@pytest.mark.parametrize('url',['http://example.org/v1','https://user:secret@example.org/v1',
                               'file:///etc/passwd','https://example.org/v1?key=secret'])
def test_invalid_provider_endpoints(url):
    with pytest.raises(ValueError):endpoint(SimpleNamespace(llm_base=url))


def test_local_provider_is_supported_without_a_key():
    settings=Settings(enable_creative_ai=True,llm_base='http://127.0.0.1:1234/v1',llm_model='local')
    assert capabilities(settings)['enabled'] and endpoint(settings).endswith('/v1/chat/completions')
    assert capabilities(settings)['billing_estimate_usd'] is None


def test_assistant_calls_once_and_locally_validates_response(monkeypatch):
    import asyncio
    calls=[]
    def handler(request):
        calls.append(request)
        payload=json.loads(request.content)
        assert payload['response_format']=={'type':'json_object'}
        assert 'PRIVATE-EVIDENCE' not in request.content.decode()
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'Calmer','operations':[]})}}],
                                        'usage':{'total_tokens':123,'private_debug':'SECRET'}})
    original=httpx.AsyncClient
    monkeypatch.setattr('launchloom.creative_assistant.httpx.AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    settings=Settings(enable_creative_ai=True,llm_base='https://model.example/v1',llm_model='chosen')
    result,usage=asyncio.run(request_plan(settings,public_context(spec(),{},'Calmer')))
    assert len(calls)==1 and result.summary=='Calmer' and usage=={'total_tokens':123}


@pytest.mark.parametrize('status,content',[(500,{}),(302,{}),(200,{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}),
                                         (200,{'choices':[{'message':{'content':'not JSON'}}]})])
def test_failures_are_not_retried_or_applied(monkeypatch,status,content):
    import asyncio
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(status,json=content)
    original=httpx.AsyncClient
    monkeypatch.setattr('launchloom.creative_assistant.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    settings=Settings(enable_creative_ai=True,llm_base='https://model.example/v1',llm_model='chosen')
    with pytest.raises(ValueError):asyncio.run(request_plan(settings,public_context(spec(),{},'Calmer')))
    assert len(calls)==1
