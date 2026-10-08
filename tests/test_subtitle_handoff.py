"""Non-destructive scene/stock projection over REAL local narration duration."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
import pytest
from app.subtitles.models import SubtitleError
from app.subtitles.timing import generate, map_scenes, project_slots, normalize
from test_scripts import studio
from test_production import production_studio
from test_stock_media import stock_studio, start as stock_start, view as stock_view, mutate
from test_subtitles import local_studio, seed, no_network, base, create, get, edit
from app.narration.models import script_fingerprint
from app.projects import now


def install_narration(app,pid,seconds=193):
    from test_subtitles import wav
    import hashlib
    current=app.state.scripts.repository.approved_current(pid)
    data=wav(seconds);name=uuid4().hex+'.wav';path=app.state.projects._path(pid)/'voice'/name;path.write_bytes(data)
    audio={'local_path':'voice/'+name,'format':'wav','content_type':'audio/wav','file_size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'duration':None,'duration_message':'Ses süresi daha sonra hesaplanacak.'}
    vid=uuid4().hex;stamp=now()
    meta={'provider':'AI33 / OpenSpeaker','voice_provider':'elevenlabs','voice_id':'elevenlabs_fixture','voice_name':'Fixture',
          'speed':1.0,'target_language':current['language'],'source_script_version':current['version'],'character_count':len(current['text']),
          'script_fingerprint':script_fingerprint(current['text']),'text':current['text'],'task_id':'already-completed-fixture','creation_attempted':True,'audio':audio,'status':'completed'}
    with closing(app.state.projects._connection()) as c,c:
        c.execute('INSERT INTO narration_versions VALUES (?,?,?,?,?,?,?,?)',(vid,pid,1,'narration',current['id'],json.dumps(meta),stamp,stamp))
        c.execute('INSERT INTO narration_state VALUES (?,?,?)',(pid,vid,stamp))
    return path


@pytest.fixture
def handoff_studio(stock_studio):
    client,project,fake,storage=stock_studio
    media=stock_start(stock_studio)
    for slot in media['slots']:
        if not slot['locked']:assert mutate(stock_studio,slot['slot_id'],'lock').status_code==200
    media=stock_view(stock_studio)
    path=install_narration(client.app,project['id'])
    client.app.state.narration.factory=no_network;client.app.state.narration.downloader.download=no_network
    client.app.state.stock.factory=no_network;client.app.state.stock.downloader.download=no_network;client.app.state.scripts.provider_factory=no_network
    return {'client':client,'pid':project['id'],'storage':storage,'media':media,'path':path}


def snapshots(st):
    root=st['storage']/'projects'/st['pid']
    result={str(p.relative_to(root)):p.read_bytes() for folder in ('script','scenes','stock','voice') for p in (root/folder).rglob('*') if p.is_file()}
    with closing(st['client'].app.state.projects._connection()) as c:
        result['stock_rows']=[tuple(row) for row in c.execute('SELECT * FROM stock_plans WHERE project_id=?',(st['pid'],))]
        result['production_rows']=[tuple(row) for row in c.execute('SELECT * FROM project_production WHERE project_id=?',(st['pid'],))]
    return result


def test_authoritative_handoff_scene_and_stock_no_mutation_or_network(handoff_studio):
    st=handoff_studio;before=snapshots(st)
    current=st['client'].app.state.production.handoff(st['pid'])
    subtitles=create(st)['active'];r=st['client'].get(base(st)+'/handoff');assert r.status_code==200,r.text
    handoff=r.json();assert handoff['ready'] and handoff['audio_duration']==193 and handoff['timing_source']=='approximate_audio_duration'
    assert handoff['subtitle_version_id']==subtitles['id']
    assert [s['scene_id'] for s in handoff['scenes']]==[s['scene_id'] for s in current['scenes']]
    assert [s['narration_text'] for s in handoff['scenes']]==[s['narration_text'] for s in current['scenes']]
    assert handoff['scenes'][0]['start']==0 and handoff['scenes'][-1]['end']==193
    assert all(s['start']<s['end'] and s['duration']>0 for s in handoff['scenes'])
    assert [s['slot_id'] for s in handoff['stock_slots']]==[s['slot_id'] for s in st['media']['slots']]
    for old,new in zip(st['media']['slots'],handoff['stock_slots']):
        assert old['locked']==new['locked']
        assert new['selected_media_local_identity']=={k:old['selected_media'][k] for k in ('provider','media_id','media_type','local_path')}
        scene=next(s for s in handoff['scenes'] if s['scene_id']==new['scene_id'])
        assert scene['start']<=new['start']<new['end']<=scene['end']+.000001
        original_total=sum(s['duration'] for s in st['media']['slots'] if s['scene_id']==new['scene_id'])
        assert new['duration']/scene['duration']==pytest.approx(old['duration']/original_total,abs=1e-6)
    assert before==snapshots(st)
    assert 'https://' not in json.dumps(handoff) and '/workspace/' not in json.dumps(handoff)
    # Narration page also sees the locally persisted real duration.
    assert st['client'].get(f'/api/projects/{st["pid"]}/narration').json()['active']['metadata']['audio']['duration']==193


def test_manual_timing_maps_scene_boundaries_using_same_text(handoff_studio):
    st=handoff_studio;first=create(st)['active'];before=st['client'].get(base(st)+'/handoff').json()
    # There are many word-boundary scenes: shifting this cue shifts an internal scene boundary.
    cues=deepcopy(first['cues']);cues[0]['end']-=.1;cues[1]['start']+=.1
    assert edit(st,first,cues).status_code==201
    after=st['client'].get(base(st)+'/handoff').json()
    assert after['ready'] and after['text_matches_narration']
    assert after['scenes'][-1]['end']==193 and after['subtitle_version_id']!=before['subtitle_version_id']
    assert after['scenes']!=before['scenes']


def test_customized_subtitle_text_keeps_semantic_source_projection(handoff_studio):
    st=handoff_studio;first=create(st)['active'];before=st['client'].get(base(st)+'/handoff').json()
    cues=deepcopy(first['cues']);cues[0]['text']='User display customization.'
    assert edit(st,first,cues).status_code==201
    after=st['client'].get(base(st)+'/handoff').json()
    assert after['ready'] and not after['text_matches_narration']
    assert after['scenes']==before['scenes']
    assert any('Altyazı metni seslendirme metninden farklı.' in warning for warning in after['warnings'])


def test_missing_stock_file_readiness_false_no_media_removed(handoff_studio):
    st=handoff_studio;create(st)
    media=st['media']['slots'][0]['selected_media'];path=st['storage']/'projects'/st['pid']/media['local_path'];path.unlink()
    response=st['client'].get(base(st)+'/handoff').json()
    assert not response['ready'] and response['stock_slots'][0]['locked']
    assert response['stock_slots'][0]['selected_media_local_identity']['local_path']==media['local_path']


def test_stale_stock_plan_no_state_changes(handoff_studio):
    st=handoff_studio;create(st);before=snapshots(st)
    with closing(st['client'].app.state.projects._connection()) as c,c:
        c.execute('UPDATE stock_plans SET source_version_id=? WHERE project_id=?',('old-source',st['pid']))
    changed=snapshots(st);handoff=st['client'].get(base(st)+'/handoff').json()
    assert not handoff['ready'] and not handoff['stock_slots'] and handoff['scenes']
    assert snapshots(st)==changed and before['production_rows']==changed['production_rows']


def test_pipeline_subtitle_ready_render_waiting(handoff_studio):
    st=handoff_studio;create(st)
    response=st['client'].get(f'/api/projects/{st["pid"]}');assert response.status_code==200,response.text
    stages={s['name']:s['status'] for s in response.json()['pipeline']}
    assert stages['Altyazı']==stages['Seslendirme']==stages['Stok Medya']=='Hazır'
    assert stages['Render']=='Bekliyor'


def test_scene_mapping_repeated_words_exact_order_and_text():
    text='One repeated word. One repeated word. The final different section.'
    cues,bounds=generate(text,20)
    scenes=[{'scene_id':'a','narration_text':'One repeated word.'},{'scene_id':'b','narration_text':'One repeated word.'},{'scene_id':'c','narration_text':'The final different section.'}]
    result=map_scenes(text,scenes,bounds,20)
    assert result[0]['start']==0 and result[0]['end']==result[1]['start']<result[1]['end']==result[2]['start']
    assert result[-1]['end']==20 and normalize(' '.join(s['narration_text'] for s in result))==normalize(text)
    assert cues[0]['start']<=result[0]['end']<=cues[-1]['end']


@pytest.mark.parametrize('scenes',[[{'scene_id':'a','narration_text':'wrong text'}],[{'scene_id':'a','narration_text':'One'}],[{'scene_id':'a','narration_text':''}]])
def test_scene_mismatch_not_invented(scenes):
    _,bounds=generate('One real full script.',10)
    with pytest.raises(SubtitleError):map_scenes('One real full script.',scenes,bounds,10)


def test_stock_projection_proportions_order_lock_identity():
    scene={'scene_id':'a','start':0,'end':12,'duration':12}
    slots=[{'scene_id':'a','slot_id':f's{i}','order':i,'estimated_start':(i-1)*5,'estimated_end':i*5,'duration':5,'locked':True,'status':'complete','selected_media':{'provider':'pixabay','media_id':str(i),'media_type':'video','local_path':f'stock/{i:032x}.mp4'}} for i in range(1,4)]
    before=deepcopy(slots);result=project_slots([scene],slots)
    assert [(s['start'],s['end']) for s in result]==[(0,4),(4,8),(8,12)]
    assert slots==before and all(s['locked'] for s in result)


def test_subtitle_local_routes_no_remote_resources(local_studio):
    st=local_studio;result=create(st)
    html=st['client'].get(f'/projects/{st["pid"]}/subtitles').text
    js=st['client'].get('/static/subtitles.js').text
    assert '/static/subtitles.js' in html and 'currentTime' in js and 'timeupdate' in js
    assert 'https://' not in js and '/narration/versions/' in js
    assert st['client'].get(f'/api/projects/{st["pid"]}/narration/versions/{st["vid"]}/audio').content==st['path'].read_bytes()
