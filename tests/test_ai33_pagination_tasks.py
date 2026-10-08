"""Synthetic API evidence only; owner must run the live Windows checks."""
import json
import logging
from pathlib import Path
import shutil
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.narration.provider import OpenSpeakerProvider
from app.narration.read_client import shape_diagnostic
from test_settings import settings_client,HEADERS
from test_ai33_voice_library import install,discover,response,RECORD,KEY,RAW_PRIVATE

TASK_ID='e55d91dc-ff09-414a-bb56-0a7b37846198'  # Synthetic test fixture, never app config.


def inspect(client,task_id=TASK_ID,**extra):
    return client.post('/api/settings/ai33/task/diagnose',headers=HEADERS,json={'task_id':task_id,**extra})


def test_next_page_append_deduplicates_cache_and_selected_voice_persists(settings_client,tmp_path):
    settings=settings_client.app.state.settings;settings.save('ai33',{'api_key':KEY,'voice_provider':'edge','speed':.9})
    calls=[]
    def serve(request):
        calls.append(request);assert request.method=='GET' and request.url.path=='/v3/voices'
        page=request.url.params['page'];return httpx.Response(200,json=response([RECORD] if page=='1' else [RECORD,{**RECORD,'voice_id':'edge_fixture-second','name':'Second'}]))
    settings_client.app.state.narration.factory=lambda s:OpenSpeakerProvider(KEY,secrets=s.secret_values(),transport=httpx.MockTransport(serve))
    assert discover(settings_client).status_code==200
    assert settings_client.put('/api/settings/ai33',headers=HEADERS,json={'voice_id':RECORD['voice_id']}).status_code==200
    page2=discover(settings_client,page=2);assert page2.status_code==200
    assert len(page2.json()['settings']['ai33']['voices'])==2
    assert [r.url.params['page'] for r in calls]==['1','2']
    assert all(r.url.params['page_size']=='30' for r in calls)
    with TestClient(create_app(tmp_path/'data'),headers=HEADERS) as reopened:
        config=reopened.get('/api/settings').json()['ai33']
        assert config['voice_id']==RECORD['voice_id'] and config['voice_name']==RECORD['name'] and config['speed']==.9
        assert len(config['voices'])==2 and not config['contract_ready']


def test_provider_change_clears_cache_search_uses_exact_documented_params(settings_client):
    calls=install(settings_client,response([RECORD]));assert discover(settings_client).status_code==200
    assert settings_client.put('/api/settings/ai33',headers=HEADERS,json={'voice_provider':'minimax'}).status_code==200
    assert settings_client.get('/api/settings').json()['ai33']['voices']==[]
    found={**RECORD,'voice_id':'minimax_fixture','name':'Mini Fixture'}
    def serve(request):
        calls.append(request)
        assert dict(request.url.params)=={'provider':'minimax','search':'Mini','page':'1','page_size':'30'}
        return httpx.Response(200,json=response([found]))
    settings_client.app.state.narration.factory=lambda s:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(serve))
    r=discover(settings_client,provider='minimax',search='Mini')
    assert r.status_code==200 and [v['provider'] for v in r.json()['settings']['ai33']['voices']]==['minimax']


def test_existing_task_read_only_exact_route_safe_values_and_no_raw_response(settings_client,caplog):
    caplog.set_level(logging.DEBUG)
    body={'id':TASK_ID,'status':'done','type':'text_to_speech','created_at':'PRIVATE_DATE','error_message':None,'credit_cost':2,
          'metadata':{'audio_url':RAW_PRIVATE,'with_transcript':False,'private':KEY,'nested':{'DO_NOT_INSPECT':KEY}},'progress':100}
    calls=install(settings_client,body);before=settings_client.app.state.settings.tts_config()
    r=inspect(settings_client);assert r.status_code==200,r.text
    assert len(calls)==1 and calls[0].method=='GET' and calls[0].url.path==f'/v1/task/{TASK_ID}' and not calls[0].url.query
    diagnostic=r.json()['diagnostic']
    assert diagnostic['status_value']=='done' and diagnostic['type_value']=='text_to_speech'
    assert {'name':'status','type':'string'} in diagnostic['top_level_fields']
    assert diagnostic['metadata_fields']==[{'name':'audio_url','type':'string'},{'name':'with_transcript','type':'boolean'},{'name':'private','type':'string'},{'name':'nested','type':'object'}]
    assert 'Canlı TTS görev yapısı doğrulandı: audio_url alanı bulundu.' in r.json()['message']
    for private in (TASK_ID,'PRIVATE_DATE',RAW_PRIVATE,KEY,'PRIVATE_TASK_TOKEN','DO_NOT_INSPECT'):
        assert private not in r.text and private not in caplog.text
    assert settings_client.app.state.settings.tts_config()==before
    assert not settings_client.get('/api/settings').json()['ai33']['contract_ready']


@pytest.mark.parametrize('task_id',['','../private','a/b','https://private.example.org/task','a?key=value','a#b','a b','a\nsecret','x'*151,None,{},42])
def test_invalid_task_id_rejected_locally_before_any_network(settings_client,task_id):
    calls=install(settings_client,{})
    r=inspect(settings_client,task_id)
    assert r.status_code==422 and r.json()['category']=='invalid_task_id' and calls==[]


def test_missing_or_extra_task_input_rejected(settings_client):
    calls=install(settings_client,{})
    assert inspect(settings_client,extra='unknown').status_code==422
    assert settings_client.post('/api/settings/ai33/task/diagnose',headers=HEADERS,json={}).status_code==422
    assert calls==[]


@pytest.mark.parametrize('value',[RAW_PRIVATE,KEY,KEY.upper(),'Authorization_Bearer_'+KEY,'<script>x</script>','done '+KEY,'x'*81,{},None,123])
def test_status_and_type_never_echo_urls_secrets_or_unbounded_free_text(value):
    diagnostic=shape_diagnostic({'status':value,'type':value,'metadata':{'audio_url':RAW_PRIVATE}},'inspect_task',200,(KEY,))
    assert 'status_value' not in diagnostic and 'type_value' not in diagnostic
    assert KEY not in json.dumps(diagnostic) and RAW_PRIVATE not in json.dumps(diagnostic)


@pytest.mark.parametrize('status,kind,metadata',[('pending','text_to_speech',{'audio_url':RAW_PRIVATE}),('done','other_task',{'audio_url':RAW_PRIVATE}),('done','text_to_speech',{'output_uri':RAW_PRIVATE}),('done','text_to_speech',{'audio_url':None})])
def test_diagnostic_does_not_guess_tts_output_or_unlock_contract(settings_client,status,kind,metadata):
    calls=install(settings_client,{'status':status,'type':kind,'metadata':metadata})
    r=inspect(settings_client);assert r.status_code==200
    assert 'Canlı TTS görev yapısı doğrulandı' not in r.json()['message']
    assert not settings_client.get('/api/settings').json()['ai33']['contract_ready'] and len(calls)==1


def test_history_first_item_safe_state_type_no_guess_or_paid_calls(settings_client,caplog):
    caplog.set_level(logging.DEBUG)
    calls=install(settings_client,{'observed_container':[{'status':'done','type':'text_to_speech','metadata':{'output_uri':RAW_PRIVATE,'key':KEY}}, {'status':'SECOND_RECORD_SECRET','type':'OTHER_PRIVATE_TYPE'}]})
    r=settings_client.post('/api/settings/ai33/tasks/diagnose',headers=HEADERS,json={});assert r.status_code==200
    sample=r.json()['diagnostic']['task_array_samples'][0]
    assert sample['container']=='observed_container' and sample['status_value']=='done' and sample['type_value']=='text_to_speech'
    assert sample['metadata_fields']==[{'name':'output_uri','type':'string'},{'name':'key','type':'string'}]
    assert len(calls)==1 and calls[0].method=='GET' and calls[0].url.path=='/v1/tasks'
    for private in (RAW_PRIVATE,KEY,'SECOND_RECORD_SECRET','OTHER_PRIVATE_TYPE'):
        assert private not in r.text and private not in caplog.text


@pytest.mark.parametrize('http_status,category',[(401,'key_rejected'),(429,'rate_limit'),(500,'connection_error')])
def test_task_upstream_error_hides_raw_body_preserves_settings(settings_client,http_status,category):
    install(settings_client,response([RECORD]));assert discover(settings_client).status_code==200
    before=settings_client.app.state.settings.tts_config()
    settings_client.app.state.narration.factory=lambda s:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(http_status,text=KEY+RAW_PRIVATE)))
    result=inspect(settings_client)
    assert result.status_code==503 and result.json()['category']==category
    assert KEY not in result.text and RAW_PRIVATE not in result.text
    assert settings_client.app.state.settings.tts_config()==before


JS_CASES={
    'page_1':"await b.page(1);assert.equal(b.state.page,1);assert.equal(b.state.voices.length,30);assert.deepEqual(calls,[{provider:'edge',search:'',page:1,page_size:30}]);",
    'next_page':"await b.page(1);await b.page(2);assert.equal(b.state.page,2);assert.equal(b.state.voices.length,30);assert.equal(b.state.voices[0].voice_id,'edge_2_0');",
    'append_page_2':"await b.page(1);await b.page(2,true);assert.equal(b.state.voices.length,60);assert.equal(b.state.voices[0].voice_id,'edge_1_0');",
    'duplicate_prevention':"duplicate=true;await b.page(1);await b.page(2,true);assert.equal(b.state.voices.length,30);assert.equal(new Set(b.state.voices.map(v=>v.voice_id)).size,30);",
    'provider_change':"await b.page(1);b.reset('minimax');assert.equal(b.state.voices.length,0);assert.equal(b.state.page,1);await b.page(1);assert(b.state.voices.every(v=>v.provider==='minimax'));",
    'search_reset':"await b.page(2);b.reset('edge','Calm');await b.page(1);assert.deepEqual(calls.at(-1),{provider:'edge',search:'Calm',page:1,page_size:30});assert.equal(b.state.page,1);",
    'all_max_10_300':"await b.all();assert.equal(calls.length,10);assert.equal(b.state.page,10);assert.equal(b.state.voices.length,300);assert(b.state.exhausted);await assert.rejects(b.page(11));assert.equal(calls.length,10);",
    'empty_page_stops':"emptyAt=3;await b.all();assert.equal(calls.length,3);assert.equal(b.state.voices.length,60);assert(b.state.exhausted);",
    'empty_first_page':"emptyAt=1;await b.all();assert.equal(calls.length,1);assert.equal(b.state.voices.length,0);assert(b.state.exhausted);",
    'failure_preserves_previous':"await b.page(1);failAt=2;await assert.rejects(b.page(2,true));assert.equal(b.state.voices.length,30);assert.equal(b.state.page,1);",
    'stale_context_not_mixed':"const pending=b.page(1);b.reset('minimax');await assert.rejects(pending);assert.equal(b.state.voices.length,0);assert.equal(b.state.provider,'minimax');",
    'previous_page_after_empty':"emptyAt=3;await b.all();await b.page(2);assert.equal(b.state.page,2);assert(!b.state.exhausted);assert.equal(b.state.voices.length,30);",
}


@pytest.mark.parametrize('case',JS_CASES)
def test_voice_browser_behavior_in_javascript(case):
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed to check browser state behavior.')
    path=Path(__file__).resolve().parents[1]/'app/static/settings-ai33-browser.js'
    script="""
      const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
      vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
      (async()=>{
        const calls=[];let emptyAt=99,failAt=99,duplicate=false;
        const b=createAI33VoiceBrowser(async query=>{
          calls.push(query);if(query.page===failAt)throw new Error('fixture network failure');
          return {voices:query.page>=emptyAt?[]:Array.from({length:30},(_,i)=>({provider:query.provider,voice_id:`${query.provider}_${duplicate?1:query.page}_${i}`,display_name:`Voice ${i}`}))};
        });b.reset('edge');
    """+JS_CASES[case]+"\n})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});"
    result=subprocess.run([node,'-e',script,str(path)],text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
