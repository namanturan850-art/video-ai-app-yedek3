"""Independent Part 7 foundation only; no completed live TTS claim."""
from contextlib import closing
from copy import deepcopy
import hashlib
import io
import json
import logging
from pathlib import Path
import wave

import httpx
from pydantic import ValidationError
import pytest

from app.narration.audio import AudioDownloader,audio_path,directory,probe_duration,safe_audio_url
from app.narration.models import (OFFICIAL_BASE,PREVIEW_TEXT,Voice,VOICE_PROVIDERS,
                                 NarrationError,script_fingerprint,validate_input)
from app.narration.read_client import OpenSpeakerReadClient,shape_diagnostic
from app.narration.schema import STATEMENTS
from app.database import initialize_database
from test_projects import client

KEY='synthetic-tts-secret-334455'
URL='https://api.ai33.pro/fixture-only.wav?token=private-fixture-token'


def wav_data():
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as writer:
        writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(8000);writer.writeframes(b'\0\0'*8000)
    return buffer.getvalue()


@pytest.fixture
def audio_project(client):
    response=client.post('/api/projects',json={'name':'Ses denemesi','topic':'Güvenli kayıt'})
    assert response.status_code==201
    return client.app.state.projects,response.json()['id']


@pytest.mark.parametrize('provider',VOICE_PROVIDERS)
def test_internal_voice_optional_metadata(provider):
    voice=Voice(provider=provider,voice_id='fixture-voice').model_dump()
    assert voice['display_name']==voice['language']==voice['gender']==voice['preview_url']==''


@pytest.mark.parametrize('speed',[.5,.75,1,1.25,1.5])
def test_internal_speed_valid(speed):
    item=validate_input({'source_script_version_id':'fixture-version','voice_provider':'edge','voice_id':'fixture-voice','speed':speed})
    assert item.speed==speed


@pytest.mark.parametrize('speed',[.49,1.51,True,'1',float('inf'),float('nan')])
def test_internal_speed_invalid(speed):
    with pytest.raises(NarrationError) as error:
        validate_input({'source_script_version_id':'fixture-version','voice_provider':'edge','voice_id':'fixture-voice','speed':speed})
    assert error.value.category=='invalid_request' and '0,5–1,5' in str(error.value)


def test_preview_languages_exact_script_fingerprint():
    assert set(PREVIEW_TEXT)=={'de','es','en','fr','tr'}
    text=' Approved text.\n Exactly preserved. '
    assert script_fingerprint(text)==hashlib.sha256(text.encode()).hexdigest()
    assert script_fingerprint(text)!=script_fingerprint(text.strip())


def test_read_only_connection_official_base_header_credit_field_not_guessed(caplog):
    calls=[];caplog.set_level(logging.DEBUG)
    def serve(request):
        calls.append(request)
        assert request.method=='GET' and str(request.url)==OFFICIAL_BASE+'/v1/credits'
        assert request.headers['xi-api-key']==KEY
        assert KEY not in str(request.url)
        return httpx.Response(200,json={'unknown_credit_field':123,'nested':{'private':KEY}})
    result=OpenSpeakerReadClient(KEY,transport=httpx.MockTransport(serve)).test_connection()
    assert len(calls)==1 and result['status']=='Hazır' and result['credits'] is None
    assert result['credits_message']=='Kredi bilgisi API tarafından döndürüldü ancak bu sürümde gösterilemiyor.'
    assert KEY not in json.dumps(result) and KEY not in caplog.text
    assert '123' not in json.dumps(result)
    assert result['diagnostic']['top_level_fields']==[{'name':'unknown_credit_field','type':'number'},{'name':'nested','type':'object'}]


@pytest.mark.parametrize('status,category',[(401,'key_rejected'),(403,'key_rejected'),(429,'rate_limit'),(500,'credits_unavailable'),(404,'credits_unavailable')])
def test_readonly_safe_http_errors(status,category,caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(NarrationError) as error:
        OpenSpeakerReadClient(KEY,transport=httpx.MockTransport(lambda r:httpx.Response(status,text=KEY))).test_connection()
    assert error.value.category==category and KEY not in str(error.value) and KEY not in caplog.text


@pytest.mark.parametrize('exception,category',[(httpx.ReadTimeout,'timeout'),(httpx.ConnectError,'connection_error')])
def test_readonly_safe_network_errors(exception,category):
    def fail(request):raise exception(KEY)
    with pytest.raises(NarrationError) as error:OpenSpeakerReadClient(KEY,transport=httpx.MockTransport(fail)).test_connection()
    assert error.value.category==category and KEY not in str(error.value)


def test_missing_key_no_request():
    with pytest.raises(NarrationError) as error:OpenSpeakerReadClient('').test_connection()
    assert error.value.category=='missing_key'


def test_shape_diagnostic_does_not_copy_values_hostile_names_or_urls():
    result=shape_diagnostic({'task_id':KEY,'status':'UNKNOWN_UNVERIFIED_STATE','output':URL,KEY:'value',URL:'value',' ':KEY},'task',200,(KEY,))
    text=json.dumps(result)
    assert KEY not in text and URL not in text and 'UNKNOWN_UNVERIFIED_STATE' not in text
    assert result['task_id_presence'] and result['http_status']==200
    assert result['top_level_fields']==[{'name':'task_id','type':'string'},{'name':'status','type':'string'},{'name':'output','type':'string'}]


def test_local_audio_download_atomic_no_secrets_no_token_log_and_real_duration(audio_project,caplog):
    projects,pid=audio_project;calls=[];body=wav_data();caplog.set_level(logging.DEBUG)
    def serve(request):
        calls.append(request)
        assert 'xi-api-key' not in request.headers and 'Authorization' not in request.headers
        return httpx.Response(200,headers={'Content-Type':'audio/wav','Content-Length':str(len(body))},content=body)
    result=AudioDownloader(projects,transport=httpx.MockTransport(serve)).download(pid,URL,{'api.ai33.pro'})
    path=audio_path(projects,pid,result)
    assert path.read_bytes()==body and result['duration']==1 and result['format']=='wav'
    assert result['local_path'].startswith('voice/') and not list(path.parent.glob('.audio-*'))
    assert URL not in caplog.text and 'private-fixture-token' not in caplog.text and KEY not in json.dumps(result)
    assert len(calls)==1


@pytest.mark.parametrize('status,mime,body,declared,category',[
    (503,'audio/wav',b'error',None,'audio_download_failed'),
    (200,'text/html',b'not audio',None,'invalid_audio'),
    (200,'audio/wav',b'not audio',None,'invalid_audio'),
    (200,'audio/wav',wav_data(),999999,'invalid_audio'),
    (200,'audio/wav',wav_data(),500000001,'invalid_audio'),
])
def test_bad_audio_download_cleanup_and_preserve_existing(audio_project,status,mime,body,declared,category):
    projects,pid=audio_project;folder=directory(projects,pid);old=folder/'existing-owner-audio.wav';old.write_bytes(wav_data())
    headers={'Content-Type':mime}
    if declared:headers['Content-Length']=str(declared)
    downloader=AudioDownloader(projects,transport=httpx.MockTransport(lambda r:httpx.Response(status,headers=headers,content=body)))
    with pytest.raises(NarrationError) as error:downloader.download(pid,URL,{'api.ai33.pro'})
    assert error.value.category==category and old.read_bytes()==wav_data()
    assert list(folder.iterdir())==[old]


@pytest.mark.parametrize('url',['http://api.ai33.pro/a.wav','https://localhost/a.wav','https://127.0.0.1/a.wav',
                              'https://api.ai33.pro.evil.test/a.wav','https://user:password@api.ai33.pro/a.wav',
                              'https://api.ai33.pro:8443/a.wav','https://api.ai33.pro/a.wav#private'])
def test_audio_only_verified_output_hosts_allowed(url):
    with pytest.raises(NarrationError):safe_audio_url(url,{'api.ai33.pro'})


def test_probe_missing_optional_tools_keeps_audio(audio_project,monkeypatch):
    projects,pid=audio_project;path=directory(projects,pid)/'fixture.mp3';path.write_bytes(b'ID3'+b'\0'*50)
    monkeypatch.setattr('app.narration.audio.shutil.which',lambda *args:None)
    assert probe_duration(path) is None and path.is_file()


def test_additive_v7_upgrade_preserves_existing_data(audio_project):
    projects,pid=audio_project
    with closing(projects._connection()) as connection,connection:
        before=dict(projects._row(connection,pid))
        connection.execute('CREATE TABLE fixture_old_settings (value TEXT)')
        connection.execute("INSERT INTO fixture_old_settings VALUES ('existing masked metadata')")
        for table in ('narration_state','narration_jobs','narration_versions'):connection.execute('DROP TABLE '+table)
        connection.execute("UPDATE app_metadata SET value='7' WHERE key='schema_version'")
    initialize_database(projects.database.parent)
    initialize_database(projects.database.parent)
    with closing(projects._connection()) as connection:
        assert dict(projects._row(connection,pid))==before
        assert connection.execute('SELECT value FROM fixture_old_settings').fetchone()[0]=='existing masked metadata'
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('narration_jobs','narration_versions','narration_state')").fetchone()[0]==3


def test_truncated_wav_rejected_even_if_http_length_matches(audio_project):
    projects,pid=audio_project;body=wav_data()[:60]
    downloader=AudioDownloader(projects,transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Type':'audio/wav'},content=body)))
    with pytest.raises(NarrationError) as error:downloader.download(pid,URL,{'api.ai33.pro'})
    assert error.value.category=='invalid_audio' and list(directory(projects,pid).iterdir())==[]


@pytest.mark.parametrize('records',[None,[],['private-first-value'],[123],[None],{'unexpected':'private'},[{}]])
def test_voice_diagnostic_missing_or_non_object_first_item_safe(records):
    body={'data':records,'success':True}
    result=shape_diagnostic(body,'voices',200,(KEY,))
    assert result['data_first_item_fields']==[]
    assert 'private-first-value' not in json.dumps(result) and 'private' not in json.dumps(result)


def test_nested_diagnostics_bounded_and_not_recursive():
    voice={f'field_{i}':KEY for i in range(100)}
    metadata={f'field_{i}':URL for i in range(100)}
    assert len(shape_diagnostic({'data':[voice]},'voices',200,(KEY,))['data_first_item_fields'])==40
    assert len(shape_diagnostic({'metadata':metadata},'poll',200,(KEY,))['metadata_fields'])==40
    unrelated=shape_diagnostic({'data':[voice],'metadata':metadata},'credits',200,(KEY,))
    assert 'data_first_item_fields' not in unrelated and 'metadata_fields' not in unrelated
    assert KEY not in json.dumps(unrelated) and URL not in json.dumps(unrelated)
