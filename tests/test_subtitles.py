"""Real local audio/files/database; Part 8 has no external provider calls."""
from contextlib import closing
from copy import deepcopy
import hashlib
import io
import json
import logging
from pathlib import Path
import shutil
import sqlite3
import subprocess
from types import SimpleNamespace
from uuid import uuid4
import wave

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.database import initialize_database, SCHEMA_VERSION
from app.narration.models import script_fingerprint
from app.scripts.models import ScriptOptions
from app.subtitles import files
from app.subtitles.duration import discover_duration
from app.subtitles.models import SubtitleError, validate_cues
from app.subtitles.timing import (normalize, words_and_weights, segment, generate, map_scenes, project_slots)

HEADERS={'X-AI-Video-Studio':'projects'}
TEXT='Dies ist ein genehmigter deutscher Text. Zahlen wie 42 und Namen wie Brian bleiben erhalten.\n\nGrüße aus dem lokalen Studio: Genau diese Wörter werden gesprochen, ohne Übersetzung!'


def wav(seconds=13):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*round(seconds*8000))
    return buffer.getvalue()


def seed(app,text=TEXT,seconds=13):
    projects=app.state.projects
    project=projects.create({'name':'Altyazı denemesi','topic':'Yerel zamanlama','language':'de'})
    pid=project['id'];repo=app.state.scripts.repository
    # This shared fixture represents pre-manual-first projects. New-default tests
    # create their own project or explicitly switch these saved legacy sources.
    from app.editor.editorial import Preferences
    with closing(projects._connection()) as c,c:
        c.execute('UPDATE editorial_state SET payload_json=? WHERE project_id=?',(json.dumps(Preferences().model_dump()),pid))
    sid=repo.create_version(pid,text,'ollama','local-fixture',ScriptOptions().model_dump(),'Otomatik',{},confirmed=True)
    repo.approve(pid,sid,True)
    data=wav(seconds);audio_name=uuid4().hex+'.wav';path=projects._path(pid)/'voice'/audio_name;path.write_bytes(data)
    audio={'local_path':'voice/'+audio_name,'format':'wav','content_type':'audio/wav','file_size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'duration':None,'duration_message':'Ses süresi daha sonra hesaplanacak.'}
    vid=uuid4().hex
    meta={'provider':'AI33 / OpenSpeaker','voice_provider':'elevenlabs','voice_id':'elevenlabs_fixture','voice_name':'Local Fixture',
          'speed':1.0,'target_language':'de','source_script_version':1,'character_count':len(text),'script_fingerprint':script_fingerprint(text),
          'text':text,'task_id':'fixture-existing-task','creation_attempted':True,'audio':audio,'status':'completed'}
    with closing(projects._connection()) as c,c:
        stamp=project['created_at']
        c.execute('INSERT INTO narration_versions VALUES (?,?,?,?,?,?,?,?)',(vid,pid,1,'narration',sid,json.dumps(meta),stamp,stamp))
        c.execute('INSERT INTO narration_state VALUES (?,?,?)',(pid,vid,stamp))
    return {'project':project,'pid':pid,'sid':sid,'vid':vid,'path':path,'source':text,'audio':audio}


def no_network(*args,**kwargs):raise AssertionError('Part 8 MUST NOT call any provider or download')


@pytest.fixture
def local_studio(tmp_path,monkeypatch):
    storage=tmp_path/'data'
    with TestClient(create_app(storage),headers=HEADERS) as client:
        st=seed(client.app);st.update(client=client,storage=storage)
        client.app.state.narration.factory=no_network
        client.app.state.narration.downloader.download=no_network
        client.app.state.stock.factory=no_network
        client.app.state.stock.downloader.download=no_network
        client.app.state.scripts.provider_factory=no_network
        yield st


def base(st):return f'/api/projects/{st["pid"]}/subtitles'
def create(st,regenerate=False):
    r=st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':regenerate})
    assert r.status_code==201,r.text
    return r.json()
def get(st):
    r=st['client'].get(base(st));assert r.status_code==200,r.text;return r.json()
def edit(st,item,cues):return st['client'].post(base(st)+f'/versions/{item["id"]}/edit',json={'cues':[{k:c[k] for k in ('start','end','text')} for c in cues]})


@pytest.mark.parametrize('text',[
    TEXT,'Hola, España. ¿Cómo funciona? Los números 42 y 3,14 permanecen.\n\nOtra sección: sin traducción.',
    'Hello, world! This exact script has names, numbers 42 and a long sentence; nothing changes.',
    'Bonjour, français ! Voici un texte fidèle: été, Noël et 42.\n\nLa suite reste inchangée.',
    'Merhaba, dünya! Şu özgün metin; isimleri, 42 sayısını ve sıralamayı korur.\n\nİkinci paragraf.',
    'word '*500,'Supercalifragilisticexpialidocious'*4+' final word.',
    'Quote “names and numbers 1.234,56”; punctuation: exact! A dash — preserved.',
])
def test_segmentation_exact_words_punctuation_multilingual(text):
    cues,bounds=generate(text,193)
    assert normalize(' '.join(c['text'] for c in cues))==normalize(text)
    assert ' '.join(text.split()).split()==(' '.join(c['text'] for c in cues)).split()
    assert len(bounds)==len(text.split())+1
    assert len(cues)>0
    assert all(len(c['text'].splitlines())<=2 for c in cues)
    if max(map(len,text.split()))<=42:
        assert all(len(c['text'].replace('\n',' '))<=84 for c in cues)


@pytest.mark.parametrize('duration',[1,3,13,193,600,.1])
def test_timing_valid_monotonic_end_deterministic(duration):
    cues,boundaries=generate(TEXT*10,duration)
    assert cues[0]['start']==0 and cues[-1]['end']==duration
    assert all(q['start']<q['end'] for q in cues)
    assert all(a['end']<=b['start'] for a,b in zip(cues,cues[1:]))
    assert all(a<=b for a,b in zip(boundaries,boundaries[1:]))
    assert generate(TEXT*10,duration)==(cues,boundaries)


def test_speech_weight_punctuation_paragraph_and_longer_content():
    assert words_and_weights('same,')[1][0]>words_and_weights('same')[1][0]
    assert words_and_weights('same.')[1][0]>words_and_weights('same,')[1][0]
    assert words_and_weights('same.\n\nnext')[1][0]>words_and_weights('same. next')[1][0]
    text='Short but understandable first sentence. '+ 'A much longer sentence with informative words and precise explanations.'
    cues,_=generate(text,20)
    assert len(cues)>=2
    assert cues[0]['end']-cues[0]['start']<cues[-1]['end']-cues[-1]['start']
    assert len({round(q['end']-q['start'],3) for q in cues})>1


def test_readability_minimum_and_ordinary_line_limits():
    cues,_=generate(TEXT*15,193)
    assert all(q['end']-q['start']>=.799 for q in cues)
    assert all(len(line)<=42 for q in cues for line in q['text'].splitlines())
    assert not any(len(q['text'].split())==1 for q in cues)


@pytest.mark.parametrize('duration',[None,0,-1,float('nan'),float('inf'),True,86400])
def test_invalid_audio_duration_rejected(duration):
    with pytest.raises(SubtitleError):generate(TEXT,duration)


@pytest.mark.parametrize('suffix,codec',[('mp3','libmp3lame'),('wav','pcm_s16le'),('m4a','aac'),('ogg','libvorbis'),('flac','flac')])
@pytest.mark.parametrize('fallback',[False,True])
def test_real_audio_formats_ffprobe_and_mutagen(tmp_path,monkeypatch,suffix,codec,fallback):
    executable=shutil.which('ffmpeg')
    if not executable:pytest.skip('Real local codec fixture requires optional ffmpeg')
    path=tmp_path/('voice.'+suffix)
    subprocess.run([executable,'-v','error','-f','lavfi','-i','sine=frequency=440:duration=1.25','-c:a',codec,str(path)],check=True,capture_output=True)
    if fallback:monkeypatch.setattr('app.subtitles.duration.shutil.which',lambda name:None)
    duration,method=discover_duration(path)
    assert 1.2<=duration<=1.4
    assert method==('wav_metadata' if suffix=='wav' else 'mutagen') if fallback else method=='ffprobe'


def test_existing_duration_preferred_no_tool_or_metadata(tmp_path,monkeypatch):
    monkeypatch.setattr('app.subtitles.duration.shutil.which',no_network)
    monkeypatch.setattr('app.subtitles.duration.mutagen.File',no_network)
    assert discover_duration(tmp_path/'nonexistent.mp3',193.1)==(193.1,'stored')


@pytest.mark.parametrize('where',['path','adjacent','known'])
def test_ffprobe_discovery_order(tmp_path,monkeypatch,where):
    ffmpeg=tmp_path/'ffmpeg.exe';ffmpeg.touch()
    probe=tmp_path/'ffprobe.exe';probe.touch();calls=[]
    def which(name):return 'path-probe' if name=='ffprobe' and where=='path' else str(ffmpeg) if name=='ffmpeg' and where=='adjacent' else None
    monkeypatch.setattr('app.subtitles.duration.shutil.which',which)
    monkeypatch.setattr('app.subtitles.duration.subprocess.run',lambda cmd,**kw:(calls.append(cmd) or SimpleNamespace(stdout='193.25',returncode=0)))
    value,method=discover_duration(tmp_path/'existing.mp3',known_ffmpeg_paths=[ffmpeg] if where=='known' else ())
    assert value==193.25 and method=='ffprobe'
    assert calls[0][0]==('path-probe' if where=='path' else str(probe))
    assert calls[0][-1]==str(tmp_path/'existing.mp3')


def test_ffprobe_failure_falls_back_no_upload(tmp_path,monkeypatch):
    path=tmp_path/'existing.wav';path.write_bytes(wav(2))
    monkeypatch.setattr('app.subtitles.duration.shutil.which',lambda name:'missing-tool')
    monkeypatch.setattr('app.subtitles.duration.subprocess.run',lambda *a,**kw:(_ for _ in ()).throw(subprocess.TimeoutExpired('safe',15)))
    assert discover_duration(path)==(2.0,'wav_metadata')


def test_duration_discovered_persisted_existing_audio_no_tts(local_studio):
    st=local_studio;before=st['path'].read_bytes()
    assert st['client'].get(f'/api/projects/{st["pid"]}/narration').json()['active']['metadata']['audio']['duration'] is None
    r=st['client'].post(base(st)+'/duration',json={});assert r.status_code==200
    assert r.json()['duration']==13
    narration=st['client'].get(f'/api/projects/{st["pid"]}/narration').json()
    assert narration['active']['metadata']['audio']['duration']==13
    assert narration['active']['metadata']['task_id']=='fixture-existing-task'
    assert narration['active']['metadata']['audio']['duration_message']==''
    assert st['path'].read_bytes()==before and len(narration['versions'])==1


def test_live_mp3_null_duration_refresh_mutagen_persists_no_task(local_studio,monkeypatch):
    st=local_studio;executable=shutil.which('ffmpeg')
    if not executable:pytest.skip('Optional encoder needed for real MP3 fixture')
    path=st['path'].with_suffix('.mp3')
    subprocess.run([executable,'-v','error','-f','lavfi','-i','sine=duration=3.13','-c:a','libmp3lame',str(path)],check=True,capture_output=True)
    data=path.read_bytes()
    service=st['client'].app.state.narration
    with closing(service.projects._connection()) as c,c:
        meta=service._version(c,st['pid'],st['vid'])['metadata'];meta['audio'].update(local_path='voice/'+path.name,format='mp3',content_type='audio/mpeg',file_size=len(data),sha256=hashlib.sha256(data).hexdigest())
        service._save_metadata(c,st['vid'],meta)
    monkeypatch.setattr('app.subtitles.duration.shutil.which',lambda name:None)
    result=get(st);assert 3.1<result['narration']['metadata']['audio']['duration']<3.3
    assert result['narration']['metadata']['audio']['duration_method']=='mutagen'
    assert len(result['narration']['metadata']['task_id'])>0 and path.read_bytes()==data


def test_create_versions_regenerate_confirmation_and_old_retained(local_studio):
    st=local_studio;first=create(st)['active'];saved=st['client'].get(base(st)+f'/versions/{first["id"]}/files/srt').content
    assert first['version']==1 and first['metadata']['timing_source']=='approximate_audio_duration'
    assert normalize(' '.join(c['text'] for c in first['cues']))==normalize(st['source'])
    assert st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':False}).status_code==409
    second=create(st,True);assert second['active']['version']==2 and len(second['versions'])==2
    assert st['client'].get(base(st)+f'/versions/{first["id"]}/files/srt').content==saved
    r=st['client'].post(base(st)+f'/versions/{first["id"]}/activate',json={'confirm':True})
    assert r.status_code==200 and r.json()['active']['id']==first['id'] and not r.json()['active']['stale']


def test_timestamps_source_and_restart_persistence(local_studio):
    st=local_studio;first=create(st)['active']
    assert first['created_at']==first['updated_at'] and first['created_at'].endswith('+00:00')
    assert first['source_script_version_id']==st['sid'] and first['source_narration_version_id']==st['vid']
    assert first['metadata']['audio_identity']==st['audio']['sha256']
    with TestClient(create_app(st['storage'])) as restarted:
        assert restarted.get(base(st)).json()['active']==first
        assert restarted.get(f'/api/projects/{st["pid"]}/narration/versions/{st["vid"]}/audio').content==st['path'].read_bytes()


def test_valid_manual_timing_text_edit_new_version_source_unchanged(local_studio):
    st=local_studio;first=create(st)['active'];cues=deepcopy(first['cues'])
    cues[0]['start']=.1;cues[0]['end']-=.1;cues[0]['text']='Display customization & <literal> text.'
    r=edit(st,first,cues);assert r.status_code==201,r.text
    active=r.json()['active'];assert active['version']==2 and not active['metadata']['text_matches_narration']
    assert active['metadata']['parent_version_id']==first['id']
    assert len(r.json()['versions'])==2 and active['cues'][0]['start']==.1
    current=st['client'].get(f'/api/projects/{st["pid"]}/script').json()['current']
    assert current['text']==st['source'] and current['status']=='approved'
    assert st['path'].read_bytes()==wav(13)
    vtt=st['client'].get(base(st)+f'/versions/{active["id"]}/files/vtt').text
    assert '&lt;literal&gt;' in vtt and '&amp;' in vtt


@pytest.mark.parametrize('kind',['negative','reversed','overlap','overflow','empty','nan','inf','string','boolean','zero_ms','extra'])
def test_invalid_edits_preserve_active_and_files(local_studio,kind):
    st=local_studio;first=create(st)['active'];cues=deepcopy(first['cues'])
    if kind=='negative':cues[0]['start']=-1
    elif kind=='reversed':cues[0]['end']=cues[0]['start']
    elif kind=='overlap':cues[1]['start']=cues[0]['end']-.1
    elif kind=='overflow':cues[-1]['end']=13.1
    elif kind=='empty':cues[0]['text']=' \n '
    elif kind=='nan':cues[0]['start']=None
    elif kind=='inf':cues[0]['start']='Infinity'
    elif kind=='string':cues[0]['start']='1'
    elif kind=='boolean':cues[0]['start']=True
    elif kind=='zero_ms':cues[0]['end']=.0001
    elif kind=='extra':
        r=st['client'].post(base(st)+f'/versions/{first["id"]}/edit',json={'cues':[{'start':0,'end':1,'text':'safe','api_key':'value'}]})
    if kind!='extra':r=edit(st,first,cues)
    assert r.status_code==422,r.text
    current=get(st);assert current['active']==first and len(current['versions'])==1


def test_stale_script_no_silent_new_text(local_studio):
    st=local_studio;first=create(st)['active']
    repo=st['client'].app.state.scripts.repository
    sid=repo.create_version(st['pid'],'A different exact script.','ollama','fixture',ScriptOptions().model_dump(),'Otomatik',{},confirmed=True)
    repo.approve(st['pid'],sid,True)
    current=get(st);assert current['active']['stale'] and not current['can_generate']
    assert st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':True}).status_code==409
    assert current['active']['cues']==first['cues']
    assert not st['client'].get(base(st)+'/handoff').json()['ready']


def test_stale_narration_new_active_identity_old_version_survives(local_studio):
    st=local_studio;first=create(st)['active'];service=st['client'].app.state.narration
    with closing(service.projects._connection()) as c,c:
        old=service._version(c,st['pid'],st['vid']);new=uuid4().hex
        c.execute('INSERT INTO narration_versions VALUES (?,?,?,?,?,?,?,?)',(new,st['pid'],2,'narration',st['sid'],json.dumps(old['metadata']),old['created_at'],old['updated_at']))
        c.execute('UPDATE narration_state SET active_version_id=? WHERE project_id=?',(new,st['pid']))
    assert get(st)['active']['stale']
    second=create(st,True)['active'];assert not second['stale'] and second['source_narration_version_id']==new
    r=st['client'].post(base(st)+f'/versions/{first["id"]}/activate',json={'confirm':True})
    assert r.status_code==200 and r.json()['active']['stale']


@pytest.mark.parametrize('kind',['fingerprint','snapshot','same_size_audio','missing_audio','symlink_audio'])
def test_source_integrity_and_audio_identity_block_unsafe_generation(local_studio,kind,tmp_path):
    st=local_studio;service=st['client'].app.state.narration
    if kind in ('fingerprint','snapshot'):
        with closing(service.projects._connection()) as c,c:
            meta=service._version(c,st['pid'],st['vid'])['metadata'];meta['script_fingerprint' if kind=='fingerprint' else 'text']='changed'
            service._save_metadata(c,st['vid'],meta)
    elif kind=='same_size_audio':
        data=bytearray(st['path'].read_bytes());data[-1]=1;st['path'].write_bytes(data)
    elif kind=='missing_audio':st['path'].unlink()
    else:
        external=tmp_path/'outside.wav';external.write_bytes(st['path'].read_bytes());st['path'].unlink();st['path'].symlink_to(external)
    r=st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':False})
    assert r.status_code==409 and not get(st)['can_generate']
    assert not get(st)['versions']


@pytest.mark.parametrize('ext',['srt','vtt'])
def test_exports_valid_utf8_local_timestamp(local_studio,ext):
    st=local_studio;first=create(st)['active']
    r=st['client'].get(base(st)+f'/versions/{first["id"]}/files/{ext}')
    assert r.status_code==200 and 'no-store' in r.headers['Cache-Control']
    value=r.content.decode('utf-8');assert 'Grüße' in value
    assert ('WEBVTT\n\n' if ext=='vtt' else '1\n00:00:00,000 --> ') in value
    assert ('00:00:13.000' if ext=='vtt' else '00:00:13,000') in value
    path=st['storage']/'projects'/st['pid']/first['metadata'][f'{ext}_local_path']
    assert path.read_bytes()==r.content
    assert not list(path.parent.glob('.subtitle-*'))


@pytest.mark.parametrize('value',['../secrets/settings.enc','/etc/passwd','subtitles/../voice/audio.wav','C:/secrets.txt','subtitles/subtitles-v0.srt','subtitles/foo.srt','subtitles/subtitles-v1.exe','subtitles/subtitles-v1.srt/../secret'])
def test_file_traversal_rejected(local_studio,value):
    st=local_studio
    with pytest.raises(SubtitleError):files.file_path(st['client'].app.state.projects,st['pid'],value)


@pytest.mark.parametrize('kind',['directory','file'])
def test_subtitle_symlink_escape_rejected(local_studio,tmp_path,kind):
    st=local_studio;project=st['client'].app.state.projects;root=project._path(st['pid'])
    external=tmp_path/'external';external.mkdir();target=external/'owner.txt';target.write_text('Owner preserved')
    if kind=='directory':(root/'subtitles').rmdir();(root/'subtitles').symlink_to(external,target_is_directory=True)
    else:(root/'subtitles'/'subtitles-v1.srt').symlink_to(target)
    if kind=='directory':
        r=st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':False});assert r.status_code==409
    else:
        with pytest.raises(SubtitleError):files.file_path(project,st['pid'],'subtitles/subtitles-v1.srt')
    assert target.read_text()=='Owner preserved'


@pytest.mark.parametrize('failure',['srt','vtt','database'])
def test_atomic_failure_preserves_previous_active(local_studio,monkeypatch,failure):
    st=local_studio;first=create(st)['active'];original=files.atomic_write
    def fail(path,content):
        if path.suffix=='.'+failure:raise OSError('Private failure must not leak')
        return original(path,content)
    monkeypatch.setattr(files,'atomic_write',fail)
    if failure=='database':
        with closing(st['client'].app.state.projects._connection()) as c,c:
            c.execute("CREATE TRIGGER fail_subtitle BEFORE INSERT ON subtitle_versions BEGIN SELECT RAISE(ABORT,'Private database error'); END")
    r=st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':True})
    assert r.status_code==503 and 'Private' not in r.text
    assert get(st)['active']==first and len(get(st)['versions'])==1
    folder=st['storage']/'projects'/st['pid']/'subtitles'
    assert sorted(p.name for p in folder.iterdir())==['subtitles-v1.srt','subtitles-v1.vtt']


def test_orphaned_interrupted_files_not_overwritten(local_studio):
    st=local_studio;folder=st['storage']/'projects'/st['pid']/'subtitles'
    orphan=folder/'subtitles-v1.srt';orphan.write_text('Interrupted output preserved')
    result=create(st);assert result['active']['version']==2 and orphan.read_text()=='Interrupted output preserved'


def test_no_keys_app_start_and_clear_errors(tmp_path):
    with TestClient(create_app(tmp_path/'new'),headers=HEADERS) as client:
        assert client.get('/api/health').status_code==200
        pid=client.post('/api/projects',json={'name':'Empty','topic':'No credentials'}).json()['id']
        assert client.get(f'/projects/{pid}/subtitles').status_code==200
        state=client.get(f'/api/projects/{pid}/subtitles').json();assert not state['can_generate'] and not state['versions']
        assert client.post(f'/api/projects/{pid}/subtitles/versions',json={'regenerate_confirmed':False}).status_code==409
        assert client.get(f'/api/projects/{pid}/subtitles/handoff').json()['ready'] is False


def test_secrets_not_in_edit_error_export_db_log(local_studio,caplog):
    st=local_studio;settings=st['client'].app.state.settings
    key='synthetic-private-ai33-secret-232323';settings.save('ai33',{'api_key':key})
    caplog.set_level(logging.DEBUG)
    first=create(st)['active'];cues=deepcopy(first['cues']);cues[0]['text']=key
    r=edit(st,first,cues);assert r.status_code>=400 and key not in r.text
    assert key not in st['client'].get(base(st)).text and key not in caplog.text
    assert key.encode() not in (st['storage']/'app.db').read_bytes()
    for path in (st['storage']/'projects'/st['pid']/'subtitles').iterdir():assert key.encode() not in path.read_bytes()
    assert 'operation=create category=none elapsed_ms=' in caplog.text


def test_project_delete_cascades_subtitles_only_this_project(local_studio):
    st=local_studio;create(st);other=seed(st['client'].app)
    assert st['client'].request('DELETE',f'/api/projects/{st["pid"]}',json={'confirm':True}).status_code==200
    assert not (st['storage']/'projects'/st['pid']).exists() and other['path'].exists()
    with closing(st['client'].app.state.projects._connection()) as c:
        assert c.execute('SELECT COUNT(*) FROM subtitle_versions').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM subtitle_cues').fetchone()[0]==0


def test_additive_schema8_upgrade_preserves_settings_audio_scripts(local_studio):
    st=local_studio;settings=st['client'].app.state.settings;settings.save('ai33',{'api_key':'synthetic-vault-preserved-key'})
    vault=(st['storage']/'secrets/settings.enc').read_bytes();audio=st['path'].read_bytes()
    with sqlite3.connect(st['storage']/'app.db') as c:
        for table in ('subtitle_state','subtitle_cues','subtitle_versions'):c.execute('DROP TABLE '+table)
        c.execute("UPDATE app_metadata SET value='8' WHERE key='schema_version'")
    initialize_database(st['storage']);initialize_database(st['storage'])
    with sqlite3.connect(st['storage']/'app.db') as c:
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]==SCHEMA_VERSION
        assert c.execute('SELECT COUNT(*) FROM narration_versions').fetchone()[0]==1
        assert c.execute('SELECT text FROM script_versions WHERE id=?',(st['sid'],)).fetchone()[0]==st['source']
    assert (st['storage']/'secrets/settings.enc').read_bytes()==vault and st['path'].read_bytes()==audio
    assert create(st)['active']['version']==1


@pytest.mark.parametrize('payload',[{}, {'regenerate_confirmed':'true'}, {'regenerate_confirmed':1}, {'regenerate_confirmed':False,'api_key':'never-echo'}])
def test_create_payload_strict_and_no_data_created(local_studio,payload):
    st=local_studio;r=st['client'].post(base(st)+'/versions',json=payload)
    assert r.status_code==422 and 'never-echo' not in r.text
    assert not get(st)['versions']


@pytest.mark.parametrize('stdout,returncode',[('nan',0),('Infinity',0),('0',0),('-1',0),('193',1),('private raw text',0)])
def test_invalid_probe_output_falls_back(tmp_path,monkeypatch,stdout,returncode):
    path=tmp_path/'sound.wav';path.write_bytes(wav(2))
    monkeypatch.setattr('app.subtitles.duration.shutil.which',lambda name:'fixture-probe')
    monkeypatch.setattr('app.subtitles.duration.subprocess.run',lambda *a,**kw:SimpleNamespace(stdout=stdout,returncode=returncode))
    assert discover_duration(path)==(2.0,'wav_metadata')


def test_unavailable_duration_safe_page_and_no_version(local_studio,monkeypatch):
    st=local_studio
    monkeypatch.setattr('app.subtitles.service.discover_duration',lambda *a,**kw:(None,'unavailable'))
    assert not get(st)['can_generate'] and 'Ses süresi ölçülemedi.' in get(st)['message']
    r=st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':False})
    assert r.status_code==409 and not get(st)['versions']
    assert st['path'].exists()


def test_unexpected_backend_error_returns_json_no_stack_or_secret(local_studio,monkeypatch):
    st=local_studio;service=st['client'].app.state.subtitles
    def fail(*a,**kw):raise RuntimeError('RAW_PRIVATE_KEY_AND_URL')
    monkeypatch.setattr(service,'create',fail)
    r=st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':False})
    assert r.status_code==500 and r.json()['category']=='unexpected_backend'
    assert 'RAW_PRIVATE' not in r.text and 'Traceback' not in r.text


def test_missing_subtitle_export_prevents_ready_pipeline(local_studio):
    st=local_studio;first=create(st)['active'];path=st['storage']/'projects'/st['pid']/first['metadata']['vtt_local_path'];path.unlink()
    r=st['client'].get(base(st)+f'/versions/{first["id"]}/files/vtt')
    assert r.status_code==409
    project=st['client'].get(f'/api/projects/{st["pid"]}').json()
    assert next(s for s in project['pipeline'] if s['name']=='Altyazı')['status']!='Hazır'
    assert not st['client'].get(base(st)+'/handoff').json()['ready']


def test_cross_project_version_and_file_access_rejected(local_studio):
    st=local_studio;first=create(st)['active'];other=seed(st['client'].app);otherbase=f'/api/projects/{other["pid"]}/subtitles'
    assert st['client'].get(otherbase+f'/versions/{first["id"]}/files/srt').status_code==404
    assert st['client'].post(otherbase+f'/versions/{first["id"]}/activate',json={'confirm':True}).status_code==404
    assert st['client'].post(base(st)+f'/versions/{first["id"]}/activate',json={'confirm':'true'}).status_code==422
    assert st['client'].post(base(st)+'/versions',json={'regenerate_confirmed':True},headers={'Origin':'https://untrusted.example'}).status_code==403


def test_schema_marker_upgrade_with_existing_completed_subtitles_idempotent(local_studio):
    st=local_studio;first=create(st)['active']
    with closing(st['client'].app.state.projects._connection()) as c,c:
        c.execute("UPDATE app_metadata SET value='8' WHERE key='schema_version'")
    initialize_database(st['storage'])
    assert get(st)['active']==first
