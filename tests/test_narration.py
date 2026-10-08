"""Part 7 internal workflow tests. External contracts are verified separately.

FakeTTS outputs are INTERNAL normalized results, not invented OpenSpeaker JSON.
Live provider test must be run by owner on Windows.
"""
from contextlib import closing
from copy import deepcopy
import json
import logging
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.narration.audio import AudioDownloader
from app.narration.models import NarrationError,PREVIEW_TEXT,script_fingerprint
from app.narration.provider import OpenSpeakerProvider,TTSProvider
from app.settings import SettingsInputError
from test_scripts import studio,run,HEADERS,KEY as SCRIPT_KEY
from test_narration_foundation import wav_data

KEY='synthetic-tts-key-8899'
VOICE={'provider':'edge','voice_id':'fixture-edge-voice','display_name':'Fixture Voice',
       'language':'de','gender':'','preview_url':''}
AUDIO='https://api.openspeaker.ai/fixture-only.wav?token=private-token'
SETTINGS_HEADERS={'X-AI-Video-Studio':'settings'}


class FakeTTS:
    """Internal boundary only; no claim about undocumented remote task states."""
    contract_ready=True
    output_hosts={'api.openspeaker.ai'}
    def __init__(self):self.creations=[];self.polls=[];self.fail=None;self.pending=1
    def synthesize(self,text,voice,options):
        self.creations.append((text,voice,options))
        if self.fail=='create':raise NarrationError('timeout','Görev oluşturma isteği zaman aşımına uğradı.')
        return {'task_id':f'fixture-task-{len(self.creations)}'}
    def get_job_status(self,task_id):
        self.polls.append(task_id)
        if self.fail=='poll':raise NarrationError('timeout','Görev bekleniyor; Devam Et deyin.')
        if self.fail=='schema':raise NarrationError('unexpected_task_schema','AI33 görev yanıtı bu sürümün beklediği biçimden farklı.',502,{'operation':'poll','http_status':200,'top_level_fields':[{'name':'fixture_new_output','type':'object'}],'task_id_presence':True})
        if self.fail=='failed':return {'state':'failed'}
        if self.pending:self.pending-=1;return {'state':'pending'}
        return {'state':'complete','audio_url':AUDIO}
    def list_voices(self,*args):return [VOICE]
    def test_connection(self):return {'status':'Hazır','message':'Taklit okuma başarılı.'}


@pytest.fixture
def narration_studio(studio):
    st=studio;current=run(st)['current']
    assert st[0].post(f'/api/projects/{st[1]["id"]}/script/versions/{current["id"]}/approve',json={'confirm':True}).status_code==200
    settings=st[0].app.state.settings
    settings.save('ai33',{'api_key':KEY,'voice_provider':'edge','speed':1.0})
    tested=settings.tts_config();settings.record_tts_voices(tested,[VOICE])
    settings.save('ai33',{'voice_id':VOICE['voice_id']})
    service=st[0].app.state.narration;fake=FakeTTS();service.factory=lambda settings:fake
    service.poll_interval=.001
    service.downloader=AudioDownloader(service.projects,transport=httpx.MockTransport(lambda request:httpx.Response(200,headers={'Content-Type':'audio/wav'},content=wav_data())))
    return (*st,current,fake)


def base(st):return f'/api/projects/{st[1]["id"]}/narration'
def view(st):
    r=st[0].get(base(st));assert r.status_code==200,r.text;return r.json()
def payload(st,**extra):
    return {'source_script_version_id':st[4]['id'],'voice_provider':VOICE['provider'],'voice_id':VOICE['voice_id'],
            'speed':1.0,'cost_confirmed':True,**extra}
def finish(st,response):
    assert response.status_code==202,response.text
    st[0].app.state.narration.futures[response.json()['job_id']].result(timeout=8)
    return view(st)
def start(st,**extra):return finish(st,st[0].post(base(st)+'/jobs',json=payload(st,**extra)))


def test_official_create_contract_exact_fields_and_no_query_key(caplog):
    caplog.set_level(logging.DEBUG);calls=[]
    def serve(request):
        calls.append(request)
        assert request.method=='POST' and str(request.url)=='https://api.openspeaker.ai/v3/text-to-speech'
        assert request.headers['xi-api-key']==KEY and request.headers['Content-Type']=='application/json'
        assert json.loads(request.content)=={'text':'Approved complete narration.','voice_id':'fixture-edge-voice','speed':1.0}
        assert KEY not in str(request.url)
        return httpx.Response(200,json={'success':True,'task_id':'uuid_task_id'})
    provider=OpenSpeakerProvider(KEY,transport=httpx.MockTransport(serve))
    assert isinstance(provider,TTSProvider)
    assert provider.synthesize('Approved complete narration.','fixture-edge-voice',{'speed':1.0})=={'task_id':'uuid_task_id'}
    assert len(calls)==1 and KEY not in caplog.text


def test_unverified_voice_schema_safe_diagnostic_exact_search_parameters(caplog):
    caplog.set_level(logging.DEBUG)
    def serve(request):
        assert request.url.path=='/v3/voices'
        assert dict(request.url.params)=={'provider':'edge','search':'Deutsch','page':'2','page_size':'30'}
        assert 'language' not in request.url.params
        return httpx.Response(200,json={'undocumented_voice_records':[{'private_data':KEY}],'other':AUDIO})
    with pytest.raises(NarrationError) as error:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(serve)).list_voices('edge','Deutsch',2,30)
    assert error.value.category=='unexpected_voice_schema'
    assert error.value.diagnostic['top_level_fields']==[{'name':'undocumented_voice_records','type':'array'},{'name':'other','type':'string'}]
    assert KEY not in str(error.value.diagnostic) and KEY not in caplog.text and 'private-token' not in caplog.text


def test_unknown_task_schema_keeps_only_safe_shape(caplog):
    caplog.set_level(logging.DEBUG)
    def serve(request):
        assert request.url.path=='/v1/task/fixture-task'
        return httpx.Response(200,json={'task_id':'fixture-task','unknown_output':{'secret':KEY,'url':AUDIO}})
    with pytest.raises(NarrationError) as error:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(serve)).get_job_status('fixture-task')
    assert error.value.category=='unexpected_task_schema'
    assert KEY not in str(error.value.diagnostic) and 'private-token' not in str(error.value.diagnostic) and 'private-token' not in caplog.text


def test_no_approved_script_no_generation(studio):
    st=studio
    r=st[0].post(base(st)+'/jobs',json={'source_script_version_id':'none','voice_provider':'edge','voice_id':'fixture','cost_confirmed':True})
    assert r.status_code==409 and r.json()['category']=='approval_required'
    assert r.json()['message']=='Önce senaryo sürümünü onaylayın.'


def test_cost_confirmation_required_and_api_key_no_sqlite_or_html(narration_studio):
    st=narration_studio;r=st[0].post(base(st)+'/jobs',json=payload(st,cost_confirmed=False))
    assert r.status_code==422 and r.json()['category']=='cost_confirmation'
    assert not st[5].creations
    assert KEY not in st[0].get('/api/settings').text and KEY not in st[0].get('/settings').text
    assert KEY.encode() not in (st[3]/'app.db').read_bytes()
    assert KEY.encode() not in (st[3]/'secrets/settings.enc').read_bytes()


def test_missing_output_documentation_blocks_paid_create(narration_studio):
    st=narration_studio;provider=OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda request:(_ for _ in ()).throw(AssertionError('No paid call without output contract'))))
    st[0].app.state.narration.factory=lambda settings:provider
    r=st[0].post(base(st)+'/jobs',json=payload(st))
    assert r.status_code==409 and r.json()['category']=='documentation_required' and not view(st)['versions']


def test_one_full_request_exact_approved_text_speed_download_and_handoff(narration_studio):
    st=narration_studio;before=st[0].get(f'/api/projects/{st[1]["id"]}/script').json()
    result=start(st,speed=1.05);assert result['job']['status']=='completed'
    fake=st[5];assert fake.creations==[(st[4]['text'],VOICE['voice_id'],{'speed':1.05})]
    meta=result['active']['metadata']
    assert meta['script_fingerprint']==script_fingerprint(st[4]['text']) and meta['speed']==1.05
    assert meta['audio']['duration']==1 and meta['audio']['format']=='wav'
    assert meta['task_id']=='fixture-task-1'
    assert fake.polls==['fixture-task-1','fixture-task-1']
    assert 'text' not in meta and KEY not in json.dumps(result)
    audio=st[0].get(base(st)+f'/versions/{result["active"]["id"]}/audio')
    assert audio.status_code==200 and audio.content==wav_data()
    assert st[0].get(f'/api/projects/{st[1]["id"]}/script').json()==before
    handoff=st[0].get(base(st)+'/handoff').json()
    assert handoff['ready'] and handoff['audio_duration']==1 and handoff['source_script_version_id']==st[4]['id']
    assert handoff['transcript'] is None and handoff['scene_timing_source']=='estimated'


@pytest.mark.parametrize('language',['de','es','en','fr','tr'])
def test_target_language_full_and_isolated_preview(narration_studio,language):
    st=narration_studio;service=st[0].app.state.narration
    with closing(service.projects._connection()) as c,c:
        c.execute('UPDATE script_versions SET language=? WHERE id=?',(language,st[4]['id']))
        c.execute('UPDATE projects SET language=? WHERE id=?',(language,st[1]['id']))
    full=start(st)
    preview=start(st,kind='preview')
    assert preview['active']['id']==full['active']['id']
    assert st[5].creations[0][0]==st[4]['text'] and st[5].creations[1][0]==PREVIEW_TEXT[language]
    assert preview['versions'][0]['kind']=='preview' and preview['versions'][0]['metadata']['target_language']==language
    assert preview['versions'][0]['metadata']['audio']['local_path']!=full['active']['metadata']['audio']['local_path']


@pytest.mark.parametrize('failure',['poll','schema'])
def test_task_id_error_persistence_restart_resume_same_task_no_paid_duplicate(narration_studio,failure):
    st=narration_studio;st[5].fail=failure;failed=start(st)
    assert failed['job']['status']=='error' and failed['job']['progress']['task_id']=='fixture-task-1'
    assert failed['versions'][0]['metadata']['task_id']=='fixture-task-1'
    with TestClient(create_app(st[3]),headers=HEADERS) as reopened:
        state=reopened.get(base(st)).json();assert state['versions']==failed['versions']
        fake=FakeTTS();service=reopened.app.state.narration;service.factory=lambda settings:fake;service.poll_interval=.001
        service.downloader=AudioDownloader(service.projects,transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Type':'audio/wav'},content=wav_data())))
        resumed=reopened.post(base(st)+f'/jobs/{state["job"]["id"]}/resume',json={});assert resumed.status_code==202
        service.futures[resumed.json()['job_id']].result(timeout=8)
        after=reopened.get(base(st)).json()
        assert after['job']['status']=='completed' and fake.creations==[] and set(fake.polls)=={'fixture-task-1'}
        assert after['active']['metadata']['task_id']=='fixture-task-1'
    assert len(st[5].creations)==1


def test_creation_timeout_never_retries_paid_request_without_remote_id(narration_studio):
    st=narration_studio;st[5].fail='create';state=start(st)
    assert state['job']['status']=='error' and state['versions'][0]['metadata']['creation_attempted']
    assert len(st[5].creations)==1
    r=st[0].post(base(st)+f'/jobs/{state["job"]["id"]}/resume',json={})
    assert r.status_code==409 and r.json()['category']=='task_create_failed' and len(st[5].creations)==1


def test_regeneration_new_version_preserves_old_audio_and_explicit_active_selection(narration_studio):
    st=narration_studio;first=start(st);old=deepcopy(first['active'])
    r=st[0].post(base(st)+'/jobs',json=payload(st));assert r.status_code==409 and r.json()['category']=='regeneration_confirmation'
    second=start(st,regenerate_confirmed=True)
    assert second['active']['version']==2 and len(second['versions'])==2
    oldafter=next(v for v in second['versions'] if v['id']==old['id'])
    assert oldafter==old
    response=st[0].post(base(st)+f'/versions/{old["id"]}/activate',json={'confirm':True})
    assert response.status_code==200 and response.json()['active']['id']==old['id']
    assert st[0].get(base(st)+f'/versions/{old["id"]}/audio').content==wav_data()


def test_failed_regeneration_preserves_active_old_narration(narration_studio):
    st=narration_studio;old=start(st)['active'];st[5].fail='failed'
    state=start(st,regenerate_confirmed=True)
    assert state['job']['status']=='error' and state['job']['progress']['category']=='task_failed'
    assert state['active']==old and len(state['versions'])==2


def test_stale_after_script_edit_no_automatic_new_task_handoff_not_ready(narration_studio):
    st=narration_studio;state=start(st);service=st[0].app.state.narration
    with closing(service.projects._connection()) as c,c:
        c.execute('UPDATE script_versions SET text=text||? WHERE id=?',(' Added approved words.',st[4]['id']))
    after=view(st)
    assert after['active']['stale'] and after['active']['stale_message']=='Eski senaryo sürümüne ait'
    assert not st[0].get(base(st)+'/handoff').json()['ready']
    assert len(st[5].creations)==1 and after['active']['metadata']['audio']==state['active']['metadata']['audio']


def test_download_failure_resume_same_id_and_no_paid_retry(narration_studio):
    st=narration_studio;service=st[0].app.state.narration
    service.downloader.transport=httpx.MockTransport(lambda r:httpx.Response(503,text=KEY))
    failed=start(st);assert failed['job']['status']=='error' and failed['job']['progress']['category']=='audio_download_failed'
    assert failed['versions'][0]['metadata']['task_id']=='fixture-task-1'
    assert not list((st[3]/'projects'/st[1]['id']/'voice').glob('.audio-*'))
    service.downloader.transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Type':'audio/wav'},content=wav_data()))
    after=finish(st,st[0].post(base(st)+f'/jobs/{failed["job"]["id"]}/resume',json={}))
    assert after['active'] and len(st[5].creations)==1


def test_missing_local_audio_handoff_not_ready(narration_studio):
    st=narration_studio;state=start(st);audio=state['active']['metadata']['audio']
    (st[3]/'projects'/st[1]['id']/audio['local_path']).unlink()
    assert view(st)['active']['audio_missing'] and not st[0].get(base(st)+'/handoff').json()['ready']


def test_safe_unexpected_error_json_and_no_secret_exposed(narration_studio,monkeypatch):
    st=narration_studio
    def fail(*args):raise RuntimeError(KEY)
    monkeypatch.setattr(st[0].app.state.narration,'view',fail)
    r=st[0].get(base(st));assert r.status_code==500 and r.json()['category']=='unexpected_backend'
    assert KEY not in r.text and st[0].get('/api/health').status_code==200


def test_part6_files_and_plan_not_touched(narration_studio):
    st=narration_studio;folder=st[3]/'projects'/st[1]['id'];files={}
    for name in ('stock/existing-owner.mp4','stock/media_slots.json','scenes/existing-plan.json','script/existing-script.txt'):
        path=folder/name;path.write_text('existing fixture data');files[path]=path.read_bytes()
    start(st)
    assert {p:p.read_bytes() for p in files}==files


def test_job_blocks_project_deletion_and_shutdown_preserves_id(narration_studio):
    st=narration_studio;service=st[0].app.state.narration;entered=Event();release=Event();original=st[5].get_job_status
    def pause(task_id):entered.set();assert release.wait(5);return original(task_id)
    st[5].get_job_status=pause
    r=st[0].post(base(st)+'/jobs',json=payload(st));assert r.status_code==202 and entered.wait(5)
    try:
        deletion=st[0].request('DELETE',f'/api/projects/{st[1]["id"]}',json={'confirm':True})
        assert deletion.status_code==409 and 'Seslendirme' in deletion.json()['message']
        assert view(st)['job']['progress']['task_id']=='fixture-task-1'
    finally:release.set()
    service.futures[r.json()['job_id']].result(timeout=8)


def test_unknown_creation_result_keeps_verified_task_id_for_resume(narration_studio):
    st=narration_studio;service=st[0].app.state.narration
    provider=OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'success':'unknown','task_id':'verified-task-8899','other':AUDIO})))
    provider.contract_ready=True  # Internal workflow exercise, not a live contract claim.
    service.factory=lambda settings:provider
    failed=start(st)
    assert failed['job']['status']=='error' and failed['job']['progress']['task_id']=='verified-task-8899'
    assert failed['versions'][0]['metadata']['task_id']=='verified-task-8899'
    assert 'private-token' not in json.dumps(failed) and KEY not in json.dumps(failed)
    fake=FakeTTS();fake.pending=0;service.factory=lambda settings:fake
    resumed=finish(st,st[0].post(base(st)+f'/jobs/{failed["job"]["id"]}/resume',json={}))
    assert resumed['job']['status']=='completed' and fake.creations==[] and fake.polls==['verified-task-8899']


def test_secret_in_voice_search_or_task_id_never_sent_to_url():
    calls=[]
    provider=OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:calls.append(r)))
    from app.scripts.models import ScriptError
    with pytest.raises(ScriptError):provider.list_voices('edge',KEY)
    with pytest.raises(ScriptError):provider.get_job_status(KEY)
    assert calls==[]


def test_poll_time_budget_preserves_id_resume_does_not_create_again(narration_studio):
    st=narration_studio;service=st[0].app.state.narration;service.max_poll_seconds=0
    failed=start(st)
    assert failed['job']['status']=='error' and failed['job']['progress']['category']=='timeout'
    assert failed['job']['progress']['task_id']=='fixture-task-1' and len(st[5].creations)==1
    service.max_poll_seconds=1800
    done=finish(st,st[0].post(base(st)+f'/jobs/{failed["job"]["id"]}/resume',json={}))
    assert done['active'] and len(st[5].creations)==1


def test_recovery_marks_interrupted_job_without_losing_task_id(narration_studio):
    st=narration_studio;service=st[0].app.state.narration;state=start(st)
    with closing(service.projects._connection()) as c,c:
        c.execute("UPDATE narration_jobs SET status='running' WHERE id=?",(state['job']['id'],))
    service.recover()
    recovered=view(st)
    assert recovered['job']['status']=='error' and recovered['job']['progress']['task_id']=='fixture-task-1'
    assert recovered['versions'][0]['metadata']['status']=='error'
    assert recovered['versions'][0]['metadata']['task_id']=='fixture-task-1'
    assert recovered['active']['metadata']['audio']==state['active']['metadata']['audio']
    assert len(st[5].creations)==1


def test_completed_narration_project_deletion_keeps_other_project(narration_studio):
    st=narration_studio;state=start(st)
    other=st[0].post('/api/projects',json={'name':'Other project','topic':'Keep this'}).json()
    r=st[0].request('DELETE',f'/api/projects/{st[1]["id"]}',json={'confirm':True})
    assert r.status_code==200,r.text
    assert st[0].get(f'/api/projects/{other["id"]}').status_code==200
    with closing(st[0].app.state.projects._connection()) as c:
        for table in ('narration_versions','narration_jobs','narration_state'):
            assert c.execute('SELECT COUNT(*) FROM '+table+' WHERE project_id=?',(st[1]['id'],)).fetchone()[0]==0
    assert not (st[3]/'projects'/st[1]['id']).exists()


def test_actual_settings_routes_official_readonly_and_unknown_voice_shape(narration_studio):
    st=narration_studio;settings=st[0].app.state.settings;service=st[0].app.state.narration;calls=[]
    settings.save('ai33',{'base_url':'https://legacy.example.invalid','model':'old-model'})
    def serve(request):
        calls.append(request)
        assert request.method=='GET' and request.url.host=='api.openspeaker.ai'
        assert request.headers['xi-api-key']==KEY and KEY not in str(request.url)
        if request.url.path=='/v1/credits':return httpx.Response(200,json={'unverified_balance':123})
        assert request.url.path=='/v3/voices'
        return httpx.Response(200,json={'unverified_records':[{'secret':KEY,'url':AUDIO}]})
    service.factory=lambda values:OpenSpeakerProvider(KEY,transport=httpx.MockTransport(serve))
    result=st[0].post('/api/settings/ai33/test',headers=SETTINGS_HEADERS)
    assert result.status_code==200 and result.json()['result']['status']=='Hazır'
    assert result.json()['result']['credits'] is None and not result.json()['settings']['ai33']['contract_ready']
    failed=st[0].post('/api/settings/ai33/voices',headers=SETTINGS_HEADERS,json={'provider':'edge','search':'German','page':2,'page_size':30})
    assert failed.status_code==502 and failed.json()['category']=='unexpected_voice_schema'
    assert 'private-token' not in failed.text and KEY not in failed.text
    assert len(calls)==2 and all(request.method=='GET' for request in calls)
    assert settings.tts_config()['base_url']=='https://legacy.example.invalid'


def test_voice_settings_persist_and_new_key_requires_new_discovery(narration_studio):
    st=narration_studio;settings=st[0].app.state.settings
    settings.save('ai33',{'speed':.85})
    with TestClient(create_app(st[3]),headers=HEADERS) as reopened:
        safe=reopened.get('/api/settings').json()['ai33']
        assert safe['speed']==.85 and safe['voice_provider']=='edge' and safe['voice_id']==VOICE['voice_id']
        assert safe['masked_api_key'].endswith('8899') and safe['voices']==[VOICE]
        result=reopened.put('/api/settings/ai33',headers=SETTINGS_HEADERS,json={'api_key':'synthetic-replacement-key-5544'})
        assert result.status_code==200 and result.json()['ai33']['voices']==[]
        assert result.json()['ai33']['masked_api_key'].endswith('5544')
        old=FakeTTS();reopened.app.state.narration.factory=lambda values:old
        failed=reopened.post(base(st)+'/jobs',json=payload(st))
        assert failed.status_code==422 and failed.json()['category']=='invalid_voice' and old.creations==[]
