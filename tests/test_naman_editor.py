import sqlite3
import threading
import array
import json
from copy import deepcopy
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
    assert {'projects','editor_revisions','media_clip_ranges','archive_analysis_cache','editor_audio_settings'} <= names
    from app.database import SCHEMA_VERSION
    assert version == SCHEMA_VERSION


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


def test_manual_task_zip_contains_full_package_and_output_template():
    editor=service()
    editor.projects.get=lambda _: {'name':'Belgesel','topic':'Konu','language':'tr'}
    editor.archive=lambda _: {'items':[]}
    import io, json, zipfile
    with zipfile.ZipFile(io.BytesIO(editor.task_package_zip('a'*32))) as archive:
        assert {'NAMAN_GOREV_PAKETI.json','NAMAN_CIKTI_SABLONU.json','OKU_BENI.txt','00_TALIMAT.md','01_sahneler_ve_cumleler.txt',
                '02_arsiv.json','03_mevcut_kurgu.json','04_referanslar.md','05_cikti_sablonu.json','TEK_MESAJ.txt'}==set(archive.namelist())
        assert 'NAMAN — BELGESEL KURGU PLANI GÖREVİ' in archive.read('TEK_MESAJ.txt').decode('utf-8')
        package=json.loads(archive.read('NAMAN_GOREV_PAKETI.json'))
        assert package['required_sections']==['sahneler','infografikler','harita_sahneleri','vurgular','katmanlar']


def test_frontend_contains_brand_logo_timeline_and_preview_contract():
    root=Path(__file__).parents[1]
    html=(root/'app/static/index.html').read_text(encoding='utf-8')
    js=(root/'app/static/editor.js').read_text(encoding='utf-8')
    assert 'naman-logo.png' in html and 'editor-content' in html
    for label in ('Video','Motion','Ses','Altyazı'):
        assert label in js
    for behavior in ('currentTime','requestAnimationFrame','Oynat','Saniyeye git','manual/validate'):
        assert behavior in js
    assert 'archive/upload' in js and 'MP4, JPG, PNG, WebP, MP3, WAV' in js
    for tool in ('Görsel düzenleme','JSON ile düzenle','JSON’u kopyala','Dosyaya aktar',
                 'Sözdizimini ve yapıyı kontrol et','Değişiklikleri karşılaştır','AI ile yeniden planla'):
        assert tool in js


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


def test_all_six_local_archive_formats_are_accepted_independently(tmp_path,monkeypatch):
    initialize_database(tmp_path);projects=ProjectService(tmp_path)
    project=projects.create({'name':'Arşiv biçimleri','topic':'Yerel','language':'tr'})
    editor=EditorService(SimpleNamespace(projects=projects),None,None,None)
    monkeypatch.setattr('app.rendering.tools.discover',lambda:{'ffprobe':None})
    samples={'.mp4':b'\x00\x00\x00\x18ftypmp42xxxx','.jpg':b'\xff\xd8\xffxxxx',
             '.png':b'\x89PNG\r\n\x1a\nxxxx','.webp':b'RIFFxxxxWEBPxxxx',
             '.mp3':b'ID3xxxx','.wav':b'RIFFxxxxWAVExxxx'}
    found=[]
    for number,(suffix,content) in enumerate(samples.items()):
        source=projects._path(project['id'])/'stock'/f'.upload-{number}.part';source.write_bytes(content)
        found.append(editor.import_local(project['id'],source,'sample'+suffix)['item']['media_type'])
    assert found==['video','image','image','image','audio','audio']
    assert editor.archive(project['id'])['count']==6


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


def test_finished_video_review_is_opt_in_sampled_and_cached(tmp_path,monkeypatch):
    initialize_database(tmp_path);projects=ProjectService(tmp_path)
    project=projects.create({'name':'Kalite','topic':'Test','language':'tr'});pid=project['id']
    video=tmp_path/'finished.mp4';video.write_bytes(b'finished-video')
    production=Production();production.projects=projects
    stock=Stock();subtitles=Subtitles();settings=SimpleNamespace(ai_visual_check=lambda:True)
    rendering=SimpleNamespace(view=lambda _:{'active':{'id':'r1','status':'completed','video_missing':False,'metadata':{'duration':4}}},export=lambda *_:video)
    editor=EditorService(production,stock,subtitles,settings,rendering)
    monkeypatch.setattr('app.editor.service.subprocess.run',lambda *a,**k:SimpleNamespace(stdout=b'jpeg'))
    calls=[]
    class AI:
        def complete_json(self,*args,**kwargs):calls.append((args,kwargs));return {'summary':'Örnekler temiz.','issues':[]}
    monkeypatch.setattr('app.providers.factory.make_script_provider',lambda *a,**k:AI())
    result=editor.video_review(pid,{'confirm':True,'data_sharing_confirmed':True,'cost_confirmed':True})
    assert result['basis']=='Videonun tamamı değil, 8 örnek kare inceleniyor.' and len(result['sample_timecodes'])==8
    assert editor.video_review(pid,{'confirm':True,'data_sharing_confirmed':True,'cost_confirmed':True})['cached'] is True and len(calls)==1


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


def test_waveform_peaks_come_from_decoded_audio_samples(monkeypatch):
    editor=service()
    monkeypatch.setattr('app.narration.audio.audio_path',lambda *args:Path('/tmp/synthetic.wav'))
    monkeypatch.setattr('app.rendering.tools.discover',lambda:{'ffmpeg':'ffmpeg'})
    pcm=array.array('h',[0,1000,-2000,8000,-16000,32767]).tobytes()
    monkeypatch.setattr('app.editor.service.subprocess.run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout=pcm))
    peaks=editor._waveform('a'*32,{'sha256':'wave-identity'})
    assert peaks and peaks[-1]==1.0 and max(peaks[:-1])<1


def test_timeline_reorder_and_trim_persist_as_stock_plan_revision(tmp_path):
    database=tmp_path/'state.sqlite3'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE editor_revisions(id,project_id,plan_id,parent_plan_id,kind,payload_json,created_at)')
        c.execute('CREATE TABLE editor_audio_settings(project_id PRIMARY KEY,narration_volume,narration_fade_in,narration_fade_out,sfx_volume,sfx_levels_json,updated_at)')
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
    assert calls[0][1]['action']=='motion_edit' and calls[0][1]['local_only'] is True and calls[0][2]=='slot'


def test_editor_map_motion_forces_local_renderer_even_with_satellite_kit(monkeypatch):
    from copy import deepcopy
    from app.channels import DEFAULT_STYLE
    from app.motion.templates import build
    from app.providers import satellite
    monkeypatch.setattr(satellite,'FACTORY',lambda:(_ for _ in ()).throw(AssertionError('Mapbox çağrılmamalı')))
    kit=deepcopy(DEFAULT_STYLE);kit.update(map_style='satellite',map_style_chosen=True)
    scene=build({'template':'map','data':{'place':'Ankara','label':'Başkent','lat':39.933,'lon':32.86},
                 'emphasis':'Ankara','local_only':True},kit,2,.8,'tr')
    assert any(item['type']=='map' for item in scene['elements'])
    assert not any(item['type']=='relief' for item in scene['elements'])


def test_audio_mix_settings_are_validated_and_persisted(tmp_path):
    database=initialize_database(tmp_path)
    projects=ProjectService(tmp_path)
    project=projects.create({'name':'Ses','topic':'Yerel miks'})
    production=Production();production.projects=projects
    editor=EditorService(production,Stock(),Subtitles(),None)
    saved=editor.save_audio_settings(project['id'],{'narration_volume':1.2,'narration_fade_in':.4,
        'narration_fade_out':.8,'sfx_volume':.16,'sfx_levels':{'clip_1':.07}})
    assert saved['narration_volume']==1.2 and saved['sfx_levels']=={'clip_1':.07}
    assert EditorService(production,Stock(),Subtitles(),None).audio_settings(project['id'])==saved
    from app.editor.models import EditorError
    import pytest
    with pytest.raises(EditorError):
        editor.save_audio_settings(project['id'],{**{k:saved[k] for k in ('narration_volume','narration_fade_in','narration_fade_out','sfx_volume','sfx_levels')},'sfx_volume':.8})


def test_missing_narration_and_subtitle_handoff_do_not_block_editor():
    from app.subtitles.models import SubtitleError
    class Missing(Subtitles):
        def view(self,_):return {'active':None,'narration':None,'timing_source':None,'message':'Seslendirme ve altyazı henüz hazır değil.'}
        def handoff(self,_):raise SubtitleError('not_ready','Hazır değil.',409)
    result=EditorService(Production(),Stock(),Missing(),None).view('a'*32)
    assert result['audio_ready'] is False and result['tracks']['audio']==[] and result['tracks']['subtitles']==[]
    assert len(result['tracks'])==7 and result['duration']==4


def test_all_five_manual_sections_import_and_rollback(tmp_path):
    database=tmp_path/'manual.sqlite3';pid='a'*32
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE editor_revisions(id,project_id,plan_id,parent_plan_id,kind,payload_json,created_at)')
        connection.execute('CREATE TABLE scene_plan_versions(id,project_id,plan_json)')
    projects=SimpleNamespace(lock=threading.RLock(),get=lambda _: {'name':'P','topic':'K','language':'tr'})
    def connect():
        value=sqlite3.connect(database);value.row_factory=sqlite3.Row;return value
    projects._connection=connect
    original={'plan_id':'p1','revision':3,'version_id':'script1','blocks':[{
        'id':'s1','start':0,'end':5,'narration':'Ankara rotası 40 km boyunca önemli katman oluşturur.',
        'locked':False,'transition':'none','motion':'none','overlay_text':'','composition':'wide'}]}
    current={'plan':deepcopy(original)}
    class ManualProduction:
        def __init__(self):self.projects=projects
        def view(self,_):return current
        def editable_plan(self,_,stamp):
            assert {k:stamp[k] for k in ('plan_id','revision')}=={'plan_id':current['plan']['plan_id'],'revision':current['plan']['revision']}
            return current['plan'],None
        def _save(self,_,plan,new_version=False):
            saved=deepcopy(plan);saved['plan_id']='p'+str(int(current['plan']['plan_id'][1:])+1);saved['revision']=current['plan']['revision']+1
            current['plan']=saved;plan.update(saved)
    class ManualStock:
        def _idle(self,*_):pass
        def view(self,_):return {'slots':[]}
    with sqlite3.connect(database) as connection:
        connection.execute('INSERT INTO scene_plan_versions VALUES (?,?,?)',('p1',pid,json.dumps(original)))
    editor=EditorService(ManualProduction(),ManualStock(),Subtitles(),None)
    payload={'schema':'naman.manual-plan.v1','base':{'plan_id':'p1','revision':3},
        'sahneler':[{'scene_id':'s1','transition':'fade','motion':'slow_zoom','composition':'medium'}],
        'infografikler':[{'scene_id':'s1','template':'stat','data':{'value':'40 km','label':'rota'},'emphasis':'40'}],
        'harita_sahneleri':[{'scene_id':'s1','template':'map','data':{'place':'Ankara','label':'Ankara','lat':39.933,'lon':32.86},'emphasis':'Ankara'}],
        'vurgular':[{'scene_id':'s1','text':'önemli','effect':'pulse'}],
        'katmanlar':[{'scene_id':'s1','text':'katman','effect':'none'}]}
    assert editor.validate_import(pid,payload)['valid'] is True
    imported=editor.import_plan(pid,payload);assert imported['imported'] is True
    assert {item['kind'] for item in current['plan']['blocks'][0]['naman_overlays']}=={'infographic','map','emphasis','layer'}
    rolled=editor.rollback(pid,'p1',{'confirm':True,'plan_id':'p2','revision':4})
    assert rolled['rolled_back'] is True and current['plan']['blocks'][0]['transition']=='none'
