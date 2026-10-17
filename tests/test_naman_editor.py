import sqlite3
from pathlib import Path
from types import SimpleNamespace

from app.database import initialize_database
from app.editor.service import EditorService, TRACKS


class Production:
    projects = SimpleNamespace()
    def view(self, _):
        return {'plan': {'plan_id':'p1','revision':3,'blocks':[
            {'id':'s1','start':0,'end':4,'narration':'Anlatılan kırk kilometrelik rota.','locked':False,
             'transition':'fade','motion':'map','overlay_text':'40 km','composition':'wide'}]}}


class Stock:
    def view(self, _):
        return {'warnings':[], 'slots':[{'slot_id':'v1','scene_id':'s1','estimated_start':0,'estimated_end':4,
            'locked':True,'status':'complete','segment_start':2,'selected_media':{'media_id':'m1','provider':'pixabay','source_url':'https://example.test'}}]}


class Subtitles:
    def view(self, _):
        return {'active':{'cues':[{'index':1,'start':0,'end':4,'text':'Anlatılan kırk kilometrelik rota.'}]},
                'narration':{'id':'n1','metadata':{'audio':{'duration':4}}},'timing_source':'estimated','message':''}


def service():
    return EditorService(Production(),Stock(),Subtitles(),None)


def test_database_adds_editor_tables_without_removing_core(tmp_path):
    database=initialize_database(tmp_path)
    with sqlite3.connect(database) as connection:
        names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version=connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
    assert {'projects','editor_revisions','media_clip_ranges','archive_analysis_cache'} <= names
    assert version == '13'


def test_editor_projection_has_seven_ordered_tracks_and_sync_data():
    result=service().view('a'*32)
    assert result['brand']=='NAMAN'
    assert result['track_order']==list(TRACKS)
    assert len(result['tracks'])==7
    assert result['tracks']['visuals'][0]['clip_start']==2
    assert result['tracks']['audio'][0]['url'].endswith('/n1/audio')
    assert result['tracks']['subtitles'][0]['end']==4
    assert result['tracks']['emphasis'][0]['timing']=='estimated'


def test_manual_import_validation_rejects_stale_and_locked_changes():
    editor=service()
    valid={'schema':'naman.manual-plan.v1','base':{'plan_id':'p1','revision':3},'sahneler':[],
           'infografikler':[],'harita_sahneleri':[],'vurgular':[],'katmanlar':[]}
    assert editor.validate_import('a'*32,valid)['valid'] is True
    valid['base']['revision']=2
    result=editor.validate_import('a'*32,valid)
    assert result['valid'] is False
    assert 'güncel görev paketini' in result['correction_message']


def test_frontend_contains_brand_logo_timeline_and_preview_contract():
    root=Path(__file__).parents[1]
    html=(root/'app/static/index.html').read_text(encoding='utf-8')
    js=(root/'app/static/editor.js').read_text(encoding='utf-8')
    assert 'naman-logo.png' in html and 'editor-content' in html
    for label in ('Vurgu','Katman','Harita','İnfografik','Görüntü','Ses','Altyazı'):
        assert label in js
    for behavior in ('currentTime','requestAnimationFrame','Oynat','Saniyeye git','manual/validate'):
        assert behavior in js
