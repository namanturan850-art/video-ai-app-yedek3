"""Owner-live verified contract, synthetic HTTP responses and real local audio.

No owner credentials or paid tasks. Live provider test must be run by owner on Windows.
"""
from contextlib import closing
from copy import deepcopy
import json
import logging
from pathlib import Path
import shutil
import subprocess
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.narration.audio import AudioDownloader,audio_url_host,directory
from app.narration.models import NarrationError,Voice,script_fingerprint
from app.narration.provider import OpenSpeakerProvider
from app.narration.read_client import shape_diagnostic
from test_scripts import studio,HEADERS
from test_settings import settings_client
from test_projects import client
from test_narration_foundation import audio_project,wav_data
from test_narration import narration_studio,base,finish,multipart_fields,KEY

TASK='fixture-tts-task-1'
AUDIO='https://audio.public-example.org/fixture.wav?token=SIGNED_AUDIO_FIXTURE'
VOICE=Voice(provider='elevenlabs',voice_id='elevenlabs_example',display_name='Fixture ElevenLabs Voice').model_dump()
COMPLETED={'id':TASK,'created_at':'fixture-date','status':'done','credit_cost':1,'metadata':{
    'v3':{},'data':{},'query':{},'voice_id':VOICE['voice_id'],'audio_url':AUDIO},
    'progress':100,'type':'tts','updated_at':'fixture-date','text':'PRIVATE_FULL_SCRIPT','text_length':19,'text_truncated':False}


def provider_for(body):
    return OpenSpeakerProvider(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body)))


def test_live_verified_done_tts_audio_mapping_and_diagnostic_secrecy(caplog):
    caplog.set_level(logging.DEBUG);provider=provider_for(COMPLETED)
    result=provider.get_job_status(TASK)
    assert result=={'state':'complete','audio_url':AUDIO,'progress':100}
    assert provider.contract_ready and provider.output_hosts=={'audio.public-example.org'}
    diagnostic=shape_diagnostic(COMPLETED,'inspect_task',200,(KEY,))
    assert diagnostic['status_value']=='done' and diagnostic['type_value']=='tts'
    assert {'name':'audio_url','type':'string'} in diagnostic['metadata_fields']
    for private in (AUDIO,'SIGNED_AUDIO_FIXTURE',KEY,'PRIVATE_FULL_SCRIPT'):
        assert private not in json.dumps(diagnostic) and private not in caplog.text


@pytest.mark.parametrize('patch',[{'metadata':None},{'metadata':{}},{'metadata':{'output_uri':AUDIO}},
    {'metadata':{'audio_url':''}},{'metadata':{'audio_url':None}},{'metadata':{'audio_url':AUDIO+'?key='+KEY}},
    {'type':'text_to_speech'},{'type':'video'},{'type':None},{'id':'different-task'},{'id':'../unsafe'},
    {'status':None},{'status':123},{'status':''}])
def test_invalid_completed_schema_safe_no_fallback_fields_or_url_leaks(patch):
    body={**deepcopy(COMPLETED),**patch};provider=provider_for(body)
    with pytest.raises(NarrationError) as error:provider.get_job_status(TASK)
    assert error.value.category=='unexpected_task_schema' and not provider.output_hosts
    for private in (AUDIO,KEY,'PRIVATE_FULL_SCRIPT','SIGNED_AUDIO_FIXTURE'):
        assert private not in json.dumps(error.value.diagnostic) and private not in str(error.value)


@pytest.mark.parametrize('body',[[],None,'raw provider error',{'success':True}])
def test_task_response_must_be_object_with_status(body):
    with pytest.raises(NarrationError) as error:provider_for(body).get_job_status(TASK)
    assert error.value.category=='unexpected_task_schema'


def test_optional_type_and_returned_id_can_be_absent_request_id_still_valid():
    body=deepcopy(COMPLETED);body.pop('type');body.pop('id')
    assert provider_for(body).get_job_status(TASK)['state']=='complete'


@pytest.mark.parametrize('status',['owner-unverified-state','queued','failed','error','Done','processing'])
def test_only_exact_done_completes_all_other_strings_remain_pending(status):
    result=provider_for({**COMPLETED,'status':status,'metadata':{},'progress':42}).get_job_status(TASK)
    assert result=={'state':'pending','progress':42}


@pytest.mark.parametrize('patch',[{'error_message':KEY+' '+AUDIO},{'success':False}])
def test_explicit_error_is_failed_without_exposing_error_text(patch,caplog):
    caplog.set_level(logging.DEBUG)
    result=provider_for({**COMPLETED,**patch}).get_job_status(TASK)
    assert result=={'state':'failed','progress':100}
    assert KEY not in caplog.text and AUDIO not in caplog.text


@pytest.mark.parametrize('value',[None,'100',True,-1,101,float('inf'),float('nan'),10**500])
def test_optional_progress_is_bounded_without_blocking_completed_audio(value):
    # Non-JSON numbers are represented by direct parser input through _request.
    provider=OpenSpeakerProvider(KEY);provider._request=lambda *a,**k:({**COMPLETED,'progress':value},200)
    assert provider.get_job_status(TASK)=={'state':'complete','audio_url':AUDIO,'progress':None}


@pytest.mark.parametrize('url',['http://audio.public-example.org/a','https://localhost/a','https://machine.local/a',
    'https://127.0.0.1/a','https://10.1.2.3/a','https://169.254.169.254/a','https://192.168.1.1/a',
    'https://100.64.0.1/a','https://0.0.0.0/a','https://224.0.0.1/a','https://192.0.2.1/a',
    'https://[::1]/a','https://[fc00::1]/a','https://[fe80::1]/a','https://[2001:db8::1]/a',
    'https://2130706433/a','https://0x7f.0.0.1/a','https://127.1/a','https://user:password@audio.public-example.org/a',
    'https://audio.public-example.org:8080/a','https://audio.public-example.org/a#token',
    'https://audio.public-example.org\\private/a','https://bad..example.org/a','https://-bad.example.org/a',
    'file:///C:/private.wav','data:audio/wav;base64,x','javascript:alert(1)'])
def test_unsafe_audio_url_rejected_before_download(url,audio_project):
    with pytest.raises(NarrationError):audio_url_host(url)
    projects,pid=audio_project;calls=[]
    downloader=AudioDownloader(projects,transport=httpx.MockTransport(lambda r:calls.append(r)))
    with pytest.raises(NarrationError):downloader.download(pid,url,{'audio.public-example.org'})
    assert calls==[]


@pytest.mark.parametrize('redirect',['/fixture-final.wav?token=REDIRECT_TOKEN','https://second.public-example.org/fixture.wav?token=REDIRECT_TOKEN'])
def test_public_https_redirect_without_key_auth_cookies_or_signed_url_log(audio_project,redirect,caplog):
    projects,pid=audio_project;calls=[];caplog.set_level(logging.DEBUG)
    def serve(request):
        calls.append(request)
        assert not any(h in request.headers for h in ('xi-api-key','authorization','cookie'))
        if len(calls)==1:
            return httpx.Response(302,headers={'Location':redirect,'Set-Cookie':'private_audio_cookie=COOKIE_SECRET; Path=/'})
        return httpx.Response(200,headers={'Content-Type':'audio/wav'},content=wav_data())
    audio=AudioDownloader(projects,transport=httpx.MockTransport(serve)).download(pid,AUDIO,{'audio.public-example.org'})
    assert len(calls)==2 and audio['duration']==1
    for private in (AUDIO,'SIGNED_AUDIO_FIXTURE','REDIRECT_TOKEN','COOKIE_SECRET',KEY):assert private not in caplog.text


@pytest.mark.parametrize('redirect',['http://second.public-example.org/a','https://127.0.0.1/a','https://user:pass@second.public-example.org/a','https://machine.internal/a'])
def test_unsafe_redirect_never_followed(audio_project,redirect):
    projects,pid=audio_project;calls=[]
    def serve(request):calls.append(request);return httpx.Response(302,headers={'Location':redirect})
    with pytest.raises(NarrationError):AudioDownloader(projects,transport=httpx.MockTransport(serve)).download(pid,AUDIO,{'audio.public-example.org'})
    assert len(calls)==1 and list(directory(projects,pid).iterdir())==[]


class ExternalFixture:
    """Production adapter + downloader, synthetic official-shaped responses."""
    def __init__(self):self.calls=[];self.fail_poll=False;self.fail_audio=False;self.waiting=None;self.release=None;self.next=0;self.history=[]
    def serve(self,request):
        self.calls.append(request)
        if request.url.host=='api.ai33.pro':
            assert request.headers['xi-api-key']==KEY
            if request.method=='POST':
                assert request.url.path=='/v3/text-to-speech'
                self.next+=1;return httpx.Response(200,json={'success':True,'task_id':f'fixture-tts-task-{self.next}'})
            if request.method=='GET' and request.url.path=='/v1/tasks':
                # Verified history record; empty unless a test adds tasks.
                return httpx.Response(200,json={'success':True,'data':self.history,'page':1,'limit':20,'total':str(len(self.history))})
            assert request.method=='GET' and request.url.path.startswith('/v1/task/')
            if self.waiting:self.waiting.set();assert self.release.wait(8)
            if self.fail_poll:return httpx.Response(503,text=KEY+AUDIO)
            return httpx.Response(200,json={**COMPLETED,'id':request.url.path.rsplit('/',1)[-1]})
        assert request.url.host=='audio.public-example.org' and request.method=='GET'
        assert not any(h in request.headers for h in ('xi-api-key','authorization','cookie'))
        if self.fail_audio:return httpx.Response(503,text=KEY+AUDIO)
        return httpx.Response(200,headers={'Content-Type':'audio/wav'},content=wav_data())
    def connect(self,client):
        service=client.app.state.narration
        service.factory=lambda settings:OpenSpeakerProvider(KEY,secrets=settings.secret_values(),transport=httpx.MockTransport(self.serve))
        service.downloader=AudioDownloader(service.projects,transport=httpx.MockTransport(self.serve));service.poll_interval=.001
    @property
    def posts(self):return [r for r in self.calls if r.method=='POST']


@pytest.fixture
def verified_studio(narration_studio):
    st=narration_studio;settings=st[0].app.state.settings
    settings.save('ai33',{'voice_provider':'elevenlabs','speed':1.0})
    settings.record_tts_voices(settings.tts_config(),[VOICE]);settings.save('ai33',{'voice_id':VOICE['voice_id']})
    external=ExternalFixture();external.connect(st[0]);return st,external


def start_verified(st,**extra):
    return st[0].post(base(st)+'/jobs',json={'source_script_version_id':st[4]['id'],'voice_provider':'elevenlabs','voice_id':VOICE['voice_id'],'speed':1.0,'cost_confirmed':True,**extra})


def test_real_adapter_creation_download_local_playback_handoff_preserves_part6(verified_studio,caplog):
    st,external=verified_studio;caplog.set_level(logging.DEBUG)
    stock=st[3]/'projects'/st[1]['id']/'stock'/'fixture-pixabay-owner.mp4';stock.write_bytes(b'OWNER_MEDIA_UNCHANGED')
    script=st[0].get(f'/api/projects/{st[1]["id"]}/script').json()
    result=finish(st,start_verified(st));assert result['job']['status']=='completed'
    assert len(external.posts)==1
    assert multipart_fields(external.posts[0])=={'text':st[4]['text'],'voice_id':VOICE['voice_id'],'speed':'1.0','with_transcript':'false'}
    active=result['active'];meta=active['metadata']
    assert meta['task_id']==TASK and meta['voice_name']==VOICE['display_name'] and meta['audio']['duration']==1
    assert meta['script_fingerprint']==script_fingerprint(st[4]['text']) and 'text' not in meta
    local=st[0].get(base(st)+f'/versions/{active["id"]}/audio');assert local.status_code==200 and local.content==wav_data()
    handoff=st[0].get(base(st)+'/handoff').json()
    assert handoff['ready'] and handoff['transcript'] is None and handoff['timing_source']=='audio_duration'
    assert handoff['source_script_version_id']==st[4]['id'] and handoff['narration_version_id']==active['id']
    after=st[0].get(f'/api/projects/{st[1]["id"]}/script').json()
    assert {k:v for k,v in after.items() if k!='narration'}=={k:v for k,v in script.items() if k!='narration'} and stock.read_bytes()==b'OWNER_MEDIA_UNCHANGED'
    assert after['narration']['duration']==1  # the script screen now shows the real narration length
    for private in (KEY,AUDIO,'SIGNED_AUDIO_FIXTURE','PRIVATE_FULL_SCRIPT'):
        assert private not in json.dumps(result) and private not in json.dumps(handoff) and private not in caplog.text
        assert private.encode() not in (st[3]/'app.db').read_bytes()


def test_task_id_checkpoint_precedes_first_poll(verified_studio):
    st,external=verified_studio;external.waiting=Event();external.release=Event()
    response=start_verified(st);assert response.status_code==202 and external.waiting.wait(5)
    try:
        job=st[0].get(base(st)).json()['job'];assert job['progress']['task_id']==TASK
        with closing(st[0].app.state.projects._connection()) as c:
            row=c.execute('SELECT metadata_json FROM narration_versions WHERE id=?',(response.json()['narration_version_id'],)).fetchone()
            assert json.loads(row[0])['task_id']==TASK
        assert len(external.posts)==1
    finally:external.release.set()
    assert finish(st,response)['job']['status']=='completed'


@pytest.mark.parametrize('failure',['poll','audio'])
def test_restart_resume_uses_existing_task_without_second_post(verified_studio,failure):
    st,external=verified_studio;external.fail_poll=failure=='poll';external.fail_audio=failure=='audio'
    failed=finish(st,start_verified(st));assert failed['job']['status']=='error' and failed['job']['progress']['task_id']==TASK
    assert len(external.posts)==1
    external.fail_poll=external.fail_audio=False
    with TestClient(create_app(st[3]),headers=HEADERS) as reopened:
        external.connect(reopened)
        response=reopened.post(base(st)+f'/jobs/{failed["job"]["id"]}/resume',json={});assert response.status_code==202
        reopened.app.state.narration.futures[response.json()['job_id']].result(timeout=8)
        after=reopened.get(base(st)).json();assert after['job']['status']=='completed' and after['active']['metadata']['task_id']==TASK
    assert len(external.posts)==1
    assert {r.url.path for r in external.calls if r.url.path.startswith('/v1/task/')}=={'/v1/task/'+TASK}


def test_real_adapter_versions_preview_and_stale_script_remain_safe(verified_studio):
    st,external=verified_studio;first=finish(st,start_verified(st));path=first['active']['metadata']['audio']['local_path']
    rejected= start_verified(st);assert rejected.status_code==409 and len(external.posts)==1
    second=finish(st,start_verified(st,regenerate_confirmed=True));assert second['active']['version']==2
    assert (st[3]/'projects'/st[1]['id']/path).is_file()
    preview=finish(st,start_verified(st,kind='preview'));assert preview['active']['id']==second['active']['id']
    assert len(external.posts)==3 and preview['versions'][0]['kind']=='preview'
    edit=st[0].post(f'/api/projects/{st[1]["id"]}/script/versions',json={'text':'Changed approved script.','base_version_id':st[4]['id'],'confirm_replace_approved':True})
    assert edit.status_code==201
    after=st[0].get(base(st)).json();assert after['active']['stale'] and len(external.posts)==3
    assert not st[0].get(base(st)+'/handoff').json()['ready']


def test_duration_unavailable_still_completes_and_keeps_local_audio(verified_studio,monkeypatch):
    st,external=verified_studio;monkeypatch.setattr('app.narration.audio.probe_duration',lambda p:None)
    result=finish(st,start_verified(st));assert result['job']['status']=='completed'
    assert result['active']['metadata']['audio']['duration'] is None
    handoff=st[0].get(base(st)+'/handoff').json();assert handoff['ready'] and handoff['timing_source']=='audio_duration' and handoff['audio_duration'] is None


@pytest.mark.parametrize('provider',['elevenlabs','minimax','clone','edge','vbee','fishaudio'])
def test_default_elevenlabs_new_settings_old_provider_selection_preserved(settings_client,provider,tmp_path):
    assert settings_client.get('/api/settings').json()['ai33']['voice_provider']=='elevenlabs'
    settings_client.app.state.settings.save('ai33',{'voice_provider':provider,'speed':.85,'api_key':KEY})
    with TestClient(create_app(tmp_path/'data'),headers=HEADERS) as reopened:
        settings=reopened.get('/api/settings').json()['ai33']
        assert settings['voice_provider']==provider and settings['speed']==.85 and settings['contract_ready']


@pytest.mark.parametrize('suffix,codec,mime',[('mp3','libmp3lame','audio/mpeg'),('wav','pcm_s16le','audio/wav'),('m4a','aac','audio/mp4'),('ogg','libvorbis','audio/ogg'),('flac','flac','audio/flac')])
def test_actual_supported_audio_files_signature_duration_and_atomic_storage(audio_project,tmp_path,suffix,codec,mime):
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:pytest.skip('Optional FFmpeg is required for real encoded fixture audio.')
    source=tmp_path/'source.wav';source.write_bytes(wav_data());encoded=tmp_path/('encoded.'+suffix)
    subprocess.run([ffmpeg,'-v','error','-y','-i',str(source),'-c:a',codec,str(encoded)],check=True,capture_output=True,timeout=15)
    projects,pid=audio_project;body=encoded.read_bytes()
    downloader=AudioDownloader(projects,transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Type':mime},content=body)))
    result=downloader.download(pid,AUDIO,{'audio.public-example.org'})
    assert result['format']==suffix and .9<=result['duration']<=1.3
    assert (projects._path(pid)/result['local_path']).read_bytes()==body
    assert not list(directory(projects,pid).glob('.audio-*'))
