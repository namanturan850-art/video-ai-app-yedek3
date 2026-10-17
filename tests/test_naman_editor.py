import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

from app.database import initialize_database
from app.editor.service import EditorService, TRACKS
from app.projects import ProjectService


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

    def handoff(self, _):
        return {'audio_duration':4,'scenes':[{'scene_id':'s1','start':0,'end':4}],
                'stock_slots':[{'slot_id':'v1','start':0,'end':4,'duration':4}]}


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
    assert 'archive/upload' in js and 'MP4, JPG, PNG, WebP, MP3, WAV' in js


def test_local_image_upload_is_content_validated_and_project_scoped(tmp_path):
    initialize_database(tmp_path)
    projects=ProjectService(tmp_path)
    project=projects.create({'name':'Yerel medya','topic':'Test','language':'tr'})
    production=SimpleNamespace(projects=projects)
    editor=EditorService(production,None,None,None)
    source=projects._path(project['id'])/'stock/.upload-test.part'
    source.write_bytes(b'\x89PNG\r\n\x1a\n'+b'synthetic-image-bytes')
    result=editor.import_local(project['id'],source,'ornek.png')['item']
    assert result['provider']=='local' and result['media_type']=='image'
    assert result['title']=='ornek' and len(result['sha256'])==64
    assert Path(editor.archive_file(project['id'],'local',result['media_id'])[0]).is_file()


def test_existing_motion_engine_validates_naman_map_and_infographic_specs():
    from app.motion.templates import validate
    map_spec=validate({'template':'map','data':{'place':'Ankara','label':'Başkent','lat':39.933,'lon':32.86},'emphasis':'Ankara'},'Ankara rotanın başlangıcıdır.')
    card_spec=validate({'template':'stat','data':{'value':'40 km','label':'rota uzunluğu'},'emphasis':'40'},'Rota uzunluğu 40 km olarak açıklandı.')
    assert map_spec['template']=='map'
    assert card_spec['data']['value']=='40 km'


def test_manual_import_rejects_unknown_fields_and_unspoken_motion_data():
    editor=service()
    payload={'schema':'naman.manual-plan.v1','base':{'plan_id':'p1','revision':3},
             'sahneler':[{'scene_id':'s1','motion':'map'}], 'infografikler':[],
             'harita_sahneleri':[{'scene_id':'s1','template':'map','data':{'place':'Paris','label':'x','lat':48.8,'lon':2.3}}],
             'vurgular':[],'katmanlar':[]}
    result=editor.validate_import('a'*32,payload)
    assert not result['valid']
    assert any('transition' not in error and 'animasyon' in error for error in result['errors'])


def test_gemini_frame_analysis_is_bounded_and_maps_descriptions(monkeypatch):
    editor=service(); editor.settings=SimpleNamespace(ai_visual_check=lambda:True)
    editor.archive_file=lambda *args:(Path('/tmp/sample.mp4'),{})
    monkeypatch.setattr('app.editor.service.subprocess.run',lambda *a,**k:SimpleNamespace(stdout=b'jpeg'))
    calls=[]
    class AI:
        def complete_json(self,*args,**kwargs):
            calls.append(kwargs); return {'descriptions':['bir','iki','üç']}
    monkeypatch.setattr('app.providers.factory.make_script_provider',lambda *a,**k:AI())
    clips=[{'sample_at':n,'description':'bekliyor'} for n in range(8)]
    result=editor._gemini_descriptions('p','local','m',clips)
    assert result['gemini_status']=='complete'
    assert len(calls)==1 and len(calls[0]['images'])==3
    assert [x['description'] for x in result['clips'][:3]]==['bir','iki','üç']


def test_generated_motion_is_projected_once_to_its_semantic_track():
    class MotionStock(Stock):
        def view(self, _):
            result=super().view(_)
            result['slots'][0]['selected_media']={'media_id':'g1','provider':'generated','media_type':'video',
                'description':'Ankara rota haritası','source_metadata':{'motion':{'template':'map','data':{'place':'Ankara','label':'Başkent','lat':39.933,'lon':32.86},'emphasis':'Ankara'}}}
            return result
    result=EditorService(Production(),MotionStock(),Subtitles(),None).view('a'*32)
    assert len(result['tracks']['maps'])==1
    assert result['tracks']['maps'][0]['label']=='Harita + işaret'
    assert result['tracks']['maps'][0]['preview_url'].endswith('/v1/preview')
    assert result['tracks']['visuals']==[]  # ana motion klibi ikinci kez katman olarak çizilmez


def test_timeline_reorder_and_trim_persist_as_stock_plan_revision(tmp_path):
    database=tmp_path/'state.sqlite3'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE editor_revisions(id,project_id,plan_id,parent_plan_id,kind,payload_json,created_at)')
    class Projects:
        lock=threading.RLock()
        def _connection(self):
            connection=sqlite3.connect(database);connection.row_factory=sqlite3.Row;return connection
        def get(self,pid):return {'id':pid}
    projects=Projects()
    plan={'plan_id':'p1','revision':3,'blocks':[{'id':'s1','start':0,'end':4,'narration':'Anlatılan kırk kilometrelik rota.','locked':False,'transition':'fade','motion':'none','overlay_text':'','composition':'wide'}]}
    class P(Production):
        def __init__(self):self.projects=projects
        def view(self,_):return {'plan':plan}
    state={'plan_id':'p1','revision':1,'slots':[
        {'slot_id':'a','scene_id':'s1','order':1,'duration':2,'estimated_start':0,'estimated_end':2,'locked':False,'status':'complete','segment_start':0,'selected_media':{'provider':'local','media_id':'a','media_type':'video','duration':9}},
        {'slot_id':'b','scene_id':'s1','order':2,'duration':2,'estimated_start':2,'estimated_end':4,'locked':False,'status':'complete','segment_start':1,'selected_media':{'provider':'local','media_id':'b','media_type':'video','duration':9}}]}
    class S:
        def _handoff(self,_):return {'project_id':'x','plan_id':'p1','scenes':[{'scene_id':'s1','start_estimate':0,'end_estimate':4}]}
        def _ensure(self,c,h):return state
        def _stamp(self,s,p):assert (p['plan_id'],p['revision'])==('p1',s['revision'])
        def _idle(self,c,p):pass
        def _save(self,c,s):s['revision']+=1
        def _mirror(self,s):pass
        def view(self,_):return {'plan_id':'p1','revision':state['revision'],'slots':state['slots'],'warnings':[],'job':None}
    class T(Subtitles):
        def handoff(self,_):return {'audio_duration':4,'scenes':[{'scene_id':'s1','start':0,'end':4}], 'stock_slots':[]}
    editor=EditorService(P(),S(),T(),None)
    editor.update_timeline('x',{'plan_id':'p1','revision':1,'scene_id':'s1','slots':[
        {'slot_id':'b','start':0,'end':1.5,'source_start':2,'source_end':3.5},
        {'slot_id':'a','start':1.5,'end':4,'source_start':3,'source_end':5.5}]})
    assert [(s['slot_id'],s['order'],s['segment_start'],s['duration']) for s in state['slots']]==[('a',2,3,2.5),('b',1,2,1.5)]
    editor.timeline_history('x','undo',{'plan_id':'p1','revision':2})
    assert [(s['slot_id'],s['order'],s['segment_start'],s['duration']) for s in state['slots']]==[('a',1,0,2),('b',2,1,2)]
    editor.timeline_history('x','redo',{'plan_id':'p1','revision':3})
    assert [(s['slot_id'],s['order'],s['segment_start'],s['duration']) for s in state['slots']]==[('a',2,3,2.5),('b',1,2,1.5)]
    editor.edit_clip('x','a',{'plan_id':'p1','revision':4,'action':'split','at':3})
    pieces=[s for s in state['slots'] if (s.get('selected_media') or {}).get('media_id')=='a']
    assert len(pieces)==2 and pieces[0]['segment_end']==pieces[1]['segment_start']==4.5
    assert pieces[0]['selected_media']==pieces[1]['selected_media']
    with sqlite3.connect(database) as c: assert [r[0] for r in c.execute("SELECT kind FROM editor_revisions ORDER BY created_at")] == ['timeline_edit','timeline_undo','timeline_redo','timeline_edit']


def test_motion_edit_uses_existing_single_slot_regeneration_pipeline():
    calls=[]
    class MotionStock(Stock):
        def start(self,pid,payload,slot_id=None):calls.append((pid,payload,slot_id));return {'job_id':'j1'}
    result=EditorService(Production(),MotionStock(),Subtitles(),None).edit_motion('p','slot',{
        'plan_id':'stock-plan','revision':4,'motion':{'template':'map','data':{'place':'Ankara'},'emphasis':'Ankara'}})
    assert result=={'job_id':'j1'}
    assert calls[0][1]['action']=='motion_edit' and calls[0][2]=='slot'
