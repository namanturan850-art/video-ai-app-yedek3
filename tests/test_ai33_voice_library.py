"""Owner-verified voice field schema; task history is shape-only, never guessed.

External HTTP responses here are synthetic. Live provider test must be run by owner on Windows.
"""
from copy import deepcopy
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.narration.models import NarrationError
from app.narration.provider import OpenSpeakerProvider
from app.narration.voices import public_preview_url
from app.narration.read_client import shape_diagnostic
from test_settings import settings_client,HEADERS
from test_narration import narration_studio,payload,base
from test_scripts import studio

KEY='synthetic-voice-library-key-9922'
PREVIEW='https://media.example.org/fixture-voice.mp3'
RAW_PRIVATE='https://private.example.org/fixture-result.mp3?token=PRIVATE_TASK_TOKEN'
RECORD={'voice_id':'edge_fixture-en-US','name':'Fixture English Voice','description':'Fixture description',
        'language':'English','locale':'en-US','gender':'female','age':'adult','accent':'American',
        'category':'narration','use_cases':['education','narration'],'descriptives':['calm'],
        'tags':['clear'],'languages':['en','de',{'locale':'fr-FR'}],
        'preview_url':PREVIEW,'avatar_url':None}


def response(records):return {'success':True,'format_version':'synthetic-v3','data':records,'pagination':{}}


def install(client,body):
    settings=client.app.state.settings
    settings.save('ai33',{'api_key':KEY,'voice_provider':'edge'})
    calls=[]
    def serve(request):
        calls.append(request)
        assert request.method=='GET' and request.url.host=='api.ai33.pro'
        assert request.headers['xi-api-key']==KEY and KEY not in str(request.url)
        return httpx.Response(200,json=body)
    client.app.state.narration.factory=lambda settings:OpenSpeakerProvider(KEY,secrets=settings.secret_values(),transport=httpx.MockTransport(serve))
    return calls


def discover(client,**options):
    return client.post('/api/settings/ai33/voices',headers=HEADERS,json={'provider':'edge','search':'','page':1,'page_size':30,**options})


def test_verified_schema_normalizes_identity_all_metadata_and_hides_raw_fields(settings_client,caplog):
    caplog.set_level(logging.DEBUG);raw=deepcopy(RECORD)
    raw['undocumented_payload']={'key':KEY,'url':RAW_PRIVATE}
    body=response([raw]);body['unverified_top_field']=KEY
    calls=install(settings_client,body);result=discover(settings_client,search='English',page=2)
    assert result.status_code==200,result.text
    voice=result.json()['voices'][0]
    assert voice['voice_id']==RECORD['voice_id'] and voice['display_name']==RECORD['name']
    assert voice['provider']=='edge' and 'name' not in voice and 'undocumented_payload' not in voice
    for field,value in RECORD.items():
        if field!='name':assert voice[field]==value
    assert voice['avatar_url'] is None and voice['languages']==['en','de',{'locale':'fr-FR'}]
    assert not result.json()['settings']['ai33']['contract_ready']
    assert len(calls)==1 and dict(calls[0].url.params)=={'provider':'edge','search':'English','page':'2','page_size':'30'}
    for secret in (KEY,RAW_PRIVATE,'PRIVATE_TASK_TOKEN'):
        assert secret not in result.text and secret not in caplog.text
    assert 'Fixture description' not in caplog.text and PREVIEW not in caplog.text


def test_missing_optional_metadata_and_empty_list_do_not_fail(settings_client):
    install(settings_client,response([{'voice_id':'edge_fixture-minimal','name':'Minimal Voice'}]))
    r=discover(settings_client);assert r.status_code==200
    voice=r.json()['voices'][0]
    for field in ('description','language','locale','gender','age','accent','category','preview_url'):assert voice[field]==''
    for field in ('use_cases','descriptives','tags','languages'):assert voice[field]==[]
    assert voice['avatar_url'] is None
    settings_client.app.state.narration.factory=lambda settings:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=response([]))))
    assert discover(settings_client).json()['voices']==[]


def test_avatar_string_and_preview_preserved(settings_client):
    raw={**RECORD,'avatar_url':'https://media.example.org/fixture-avatar.png'}
    install(settings_client,response([raw]));voice=discover(settings_client).json()['voices'][0]
    assert voice['preview_url']==PREVIEW and voice['avatar_url']==raw['avatar_url']


def test_multiple_pages_voice_selection_and_metadata_survive_restart(settings_client,tmp_path):
    calls=install(settings_client,response([RECORD]));first=discover(settings_client)
    assert first.status_code==200
    other={**RECORD,'voice_id':'edge_fixture-other','name':'Other Voice','languages':['es','tr']}
    settings_client.app.state.narration.factory=lambda settings:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=response([other]))))
    second=discover(settings_client,page=2);assert second.status_code==200
    saved=settings_client.put('/api/settings/ai33',headers=HEADERS,json={'voice_id':RECORD['voice_id'],'speed':.85})
    assert saved.status_code==200 and saved.json()['ai33']['voice_name']==RECORD['name']
    with TestClient(create_app(tmp_path/'data'),headers=HEADERS) as reopened:
        data=reopened.get('/api/settings').json()['ai33']
        assert data['voice_id']==RECORD['voice_id'] and data['voice_name']==RECORD['name'] and data['speed']==.85
        assert len(data['voices'])==2 and data['voices'][0]['languages']==RECORD['languages']
        assert data['voices'][0]['preview_url']==PREVIEW and not data['contract_ready']
        assert KEY not in reopened.get('/api/settings').text


@pytest.mark.parametrize('field,value',[('success',False),('format_version',3),('data',{}),('pagination',[])])
def test_invalid_top_level_never_returns_raw_payload(settings_client,field,value):
    body=response([RECORD]);body[field]=value;body['raw_error']=KEY
    install(settings_client,body);r=discover(settings_client)
    assert r.status_code==502 and r.json()['category']=='unexpected_voice_schema' and KEY not in r.text


@pytest.mark.parametrize('record',[{'id':'edge_guessed','name':'No verified ID'}, {'voice_id':'edge_empty'},
                                  {'voice_id':'arbitrary-unprefixed','name':'Unprefixed'},None])
def test_invalid_identity_is_not_guessed(settings_client,record):
    install(settings_client,response([record]));r=discover(settings_client)
    assert r.status_code==502 and r.json()['category']=='unexpected_voice_schema'
    assert settings_client.app.state.settings.tts_config().get('available_voices',[])==[]


@pytest.mark.parametrize('field',['description','preview_url','languages'])
def test_echoed_secret_not_returned_or_saved(settings_client,field,caplog):
    caplog.set_level(logging.DEBUG);record=deepcopy(RECORD)
    record[field]=[KEY] if field=='languages' else PREVIEW+'?key='+KEY if field=='preview_url' else KEY
    install(settings_client,response([record]));r=discover(settings_client)
    assert r.status_code==502 and KEY not in r.text and KEY not in caplog.text
    assert settings_client.app.state.settings.tts_config().get('available_voices',[])==[]


@pytest.mark.parametrize('url',['http://media.example.org/audio.mp3','https://localhost/audio.mp3',
    'https://127.0.0.1/audio.mp3','https://10.0.0.1/audio.mp3','https://169.254.169.254/audio.mp3',
    'https://2130706433/audio.mp3','https://0x7f.0.0.1/audio.mp3','https://machine.local/audio.mp3',
    'https://user:pass@media.example.org/audio.mp3','javascript:alert(1)','file:///C:/private.mp3',
    'https://media.example.org:444/audio.mp3','https://media.example.org/audio.mp3#private'])
def test_unsafe_preview_url_not_used(url,settings_client):
    assert public_preview_url(url)==''
    install(settings_client,response([{**RECORD,'preview_url':url}]))
    result=discover(settings_client)
    assert result.status_code==200 and result.json()['voices'][0]['preview_url']==''


def test_successful_voice_discovery_does_not_unlock_paid_generation(narration_studio):
    st=narration_studio;install(st[0],response([RECORD]));assert discover(st[0]).status_code==200
    r=st[0].post(base(st)+'/jobs',json=payload(st,voice_id=RECORD['voice_id']))
    assert r.status_code==409 and r.json()['category']=='documentation_required'
    assert st[0].get(base(st)).json()['versions']==[]


def test_history_read_only_safe_first_item_metadata_no_task_schema_guess(settings_client,caplog):
    caplog.set_level(logging.DEBUG)
    body={'success':True,'unverified_records':[
        {'task_id':'PRIVATE_TASK_ID','unverified_kind':'PRIVATE_TTS_VALUE','metadata':{'unknown_audio':RAW_PRIVATE,'unknown_state':'PRIVATE_COMPLETED_VALUE','secret':KEY,'nested':{'NEVER_INSPECT':KEY}}},
        {'SECOND_ITEM_NEVER_INSPECTED':KEY}], 'other':KEY}
    calls=install(settings_client,body)
    r=settings_client.post('/api/settings/ai33/tasks/diagnose',headers=HEADERS,json={})
    assert r.status_code==200 and len(calls)==1
    assert calls[0].method=='GET' and calls[0].url.path=='/v1/tasks' and not calls[0].url.query
    sample=r.json()['diagnostic']['task_array_samples'][0]
    assert sample['container']=='unverified_records'
    assert sample['first_item_fields']==[{'name':'task_id','type':'string'},{'name':'unverified_kind','type':'string'},{'name':'metadata','type':'object'}]
    assert sample['metadata_fields']==[{'name':'unknown_audio','type':'string'},{'name':'unknown_state','type':'string'},{'name':'secret','type':'string'},{'name':'nested','type':'object'}]
    for private in (KEY,RAW_PRIVATE,'PRIVATE_TASK_TOKEN','PRIVATE_TASK_ID','PRIVATE_TTS_VALUE','PRIVATE_COMPLETED_VALUE','SECOND_ITEM_NEVER_INSPECTED','NEVER_INSPECT'):
        assert private not in r.text and private not in caplog.text
    assert not settings_client.get('/api/settings').json()['ai33']['contract_ready']


@pytest.mark.parametrize('body',[[],{}, {'undocumented_container':{'nested_records':[{'secret':KEY}]}},
                                {'data':['PRIVATE_FIRST_VALUE']},{'data':[]}])
def test_unknown_or_empty_history_shape_safe_without_inventing_fields(body):
    provider=OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body)))
    diagnostic=provider.task_history_diagnostic()
    assert KEY not in json.dumps(diagnostic) and 'PRIVATE_FIRST_VALUE' not in json.dumps(diagnostic)
    assert diagnostic['operation']=='tasks' and not provider.contract_ready


def test_history_rejects_request_parameters_before_network(settings_client):
    calls=install(settings_client,{})
    r=settings_client.post('/api/settings/ai33/tasks/diagnose',headers=HEADERS,json={'type':'guess-tts'})
    assert r.status_code==422 and calls==[]


def test_history_diagnostic_bounds_and_hostile_field_names():
    body={f'list_{i}':[{f'field_{j}':KEY for j in range(80)}, {'SECOND_ITEM':KEY}] for i in range(8)}
    body[KEY]=[{'private':KEY}];body[RAW_PRIVATE]=[{'private':KEY}]
    result=shape_diagnostic(body,'tasks',200,(KEY,))
    assert len(result['task_array_samples'])==4
    assert all(len(s['first_item_fields'])==40 for s in result['task_array_samples'])
    assert KEY not in json.dumps(result) and RAW_PRIVATE not in json.dumps(result) and 'SECOND_ITEM' not in json.dumps(result)


@pytest.mark.parametrize('status,category',[(401,'key_rejected'),(404,'task_history_unavailable'),(429,'rate_limit')])
def test_history_http_errors_safe_keep_voice_settings(settings_client,status,category):
    install(settings_client,response([RECORD]));assert discover(settings_client).status_code==200
    before=settings_client.app.state.settings.tts_config()
    settings_client.app.state.narration.factory=lambda settings:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(status,text=KEY+RAW_PRIVATE)))
    r=settings_client.post('/api/settings/ai33/tasks/diagnose',headers=HEADERS,json={})
    assert r.status_code==503 and r.json()['category']==category
    assert KEY not in r.text and RAW_PRIVATE not in r.text
    assert settings_client.app.state.settings.tts_config()==before
