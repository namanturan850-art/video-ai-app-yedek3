from contextlib import closing
from copy import deepcopy
import json

import pytest
from app.editor.editorial import read,Preferences,Editorial
from app.editor.advanced import AdvancedEditor
from app.stock.service import fingerprint
from app.rendering.models import options
from test_rendering import ready,await_job,url


def install_manual_example(app):
    """Real local Spanish script/voice/subtitle/media data; no providers or TTS."""
    from test_subtitles import seed,no_network
    from test_production import scene
    from test_rendering import synthetic
    from app.production import narration_units,visual_blocks
    from app.stock.models import make_slots
    from app.projects import now
    from hashlib import sha256
    from uuid import uuid4
    import wave,math,struct
    text='Recorremos 40 kilómetros en Roma. Después comparamos el paisaje. Terminamos nuestro recorrido.'
    st=seed(app,text=text,seconds=4,language='es');pid=st['pid'];root=app.state.projects._path(pid)
    voice=root/st['audio']['local_path']
    with wave.open(str(voice),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000)
        f.writeframes(b''.join(struct.pack('<h',round(9000*math.sin(2*math.pi*220*i/8000))) for i in range(32000)))
    with closing(app.state.projects._connection()) as c,c:
        row=c.execute('SELECT id,metadata_json FROM narration_versions WHERE project_id=?',(pid,)).fetchone();meta=json.loads(row['metadata_json']);meta['audio'].update(sha256=sha256(voice.read_bytes()).hexdigest(),file_size=voice.stat().st_size)
        c.execute('UPDATE narration_versions SET metadata_json=? WHERE id=?',(json.dumps(meta),row['id']))
        c.execute('UPDATE editorial_state SET payload_json=? WHERE project_id=?',(json.dumps(Preferences(editing_mode='manual',media_preparation_mode='sources_only',legacy_decorations=False).model_dump()),pid))
    units=narration_units(text);ids=[u['unit_id'] for u in units]
    blocks=visual_blocks({'scenes':[scene(ids[:1]),scene(ids[1:])]},text,'es',135,units=units)
    plan=app.state.production.save_generated(pid,st['sid'],'es',blocks);handoff=app.state.production.handoff(pid)
    video=synthetic(root/'stock',uuid4().hex+'.mp4',['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=5','-c:v','libx264','-threads','1'])
    image=synthetic(root/'stock',uuid4().hex+'.png',['-f','lavfi','-i','color=c=green:s=320x180','-frames:v','1'])
    sound=synthetic(root/'stock',uuid4().hex+'.wav',['-f','lavfi','-i','sine=frequency=660:duration=4','-c:a','pcm_s16le'])
    slots=[];assets=[]
    for i,sc in enumerate(handoff['scenes']):
        path=video if i==0 else image;kind='video' if i==0 else 'image'
        media={'provider':'local','media_id':uuid4().hex,'media_type':kind,'title':'Sentetik video' if i==0 else 'Sentetik görsel',
               'local_path':'stock/'+path.name,'file_size':path.stat().st_size,'sha256':sha256(path.read_bytes()).hexdigest(),
               'duration':5. if i==0 else None,'width':320,'height':180,'has_audio':False,'source_metadata':{'license':'Sentetik yerel test'}}
        assets.append(media)
        for slot in make_slots(sc):slot.update(selected_media=media,locked=False,status='complete',segment_start=0.);slots.append(slot)
    assets.append({'provider':'local','media_id':uuid4().hex,'media_type':'audio','title':'Sentetik müzik','local_path':'stock/'+sound.name,'file_size':sound.stat().st_size,'sha256':sha256(sound.read_bytes()).hexdigest(),'duration':4.,'has_audio':True})
    stock={'project_id':pid,'plan_id':plan['plan_id'],'source_version_id':st['sid'],'handoff_fingerprint':fingerprint(handoff),'slots':slots,'bindings':{},'revision':1}
    with closing(app.state.projects._connection()) as c,c:
        c.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?)',(pid,plan['plan_id'],st['sid'],json.dumps(stock),now()))
        for media in assets:c.execute('INSERT INTO stock_assets VALUES (?,?,?,?,?)',(pid,media['provider'],media['media_id'],media['media_type'],json.dumps(media)))
    app.state.subtitles.create(pid,{'regenerate_confirmed':False})
    for owner,attribute in [(app.state.narration,'factory'),(app.state.stock,'factory'),(app.state.scripts,'provider_factory')]:setattr(owner,attribute,no_network)
    app.state.narration.downloader.download=no_network;app.state.stock.downloader.download=no_network
    st.update(root=root,assets=assets);return st


def setup_manual(st):
    app=st['client'].app;pid=st['pid']
    with closing(app.state.projects._connection()) as c,c:
        row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone();stock=json.loads(row[0])
        stock['handoff_fingerprint']=fingerprint(app.state.production.handoff(pid));stock['bindings']={}
        for slot in stock['slots']:slot['locked']=False
        c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
    editorial=Editorial(app.state.editor);state=editorial.get(pid)
    state['preferences'].update(editing_mode='manual',legacy_decorations=False)
    editorial.save(pid,state)
    return editorial,AdvancedEditor(app.state.editor)


def test_new_project_manual_and_missing_legacy_row_is_preserved(ready):
    app=ready['client'].app;pid=app.state.projects.create({'name':'Yeni manuel','topic':'Yerel kaynak'})['id']
    assert read(app.state.projects,pid)['preferences']['editing_mode']=='manual'
    with closing(app.state.projects._connection()) as c,c:c.execute('DELETE FROM editorial_state WHERE project_id=?',(pid,))
    assert read(app.state.projects,pid)['preferences']['editing_mode']=='legacy'
    with closing(app.state.projects._connection()) as c:assert c.execute('SELECT 1 FROM editorial_state WHERE project_id=?',(pid,)).fetchone() is None


def test_empty_slot_preserves_source_clock_history_and_real_black_output(ready):
    st=ready;app=st['client'].app;pid=st['pid'];editorial,advanced=setup_manual(st)
    before=app.state.editor.view(pid);slot=next(x for items in before['tracks'].values() for x in items if x.get('slot_id'))
    state=advanced.get(pid);state['document']['empty_slots']=[slot['slot_id']];saved=advanced.save(pid,state)
    view=app.state.editor.view(pid);empty=next(x for items in view['tracks'].values() for x in items if x.get('slot_id')==slot['slot_id'])
    assert empty['media'] is None and empty['intentional_empty']
    assert view['duration']==before['duration'] and view['tracks']['subtitles']==before['tracks']['subtitles']
    plan=app.state.rendering._inputs(pid,options({'encoder':'cpu','editing_style':'adaptive'}),True)
    assert plan['options']['editing_style']=='basic' and plan['options']['montage_engine']=='native'
    assert plan['smart_edit_plan'] is None and plan['sfx']['events']==[]
    assert all(s.get('motion')=='none' and not s.get('overlay_text') for s in plan['timeline']['editing_scenes'])
    response=st['client'].post(url(st)+'/jobs',json={'encoder':'cpu'})
    assert response.status_code==202,response.text
    result=await_job(st);assert result['job']['status']=='completed',result
    from test_advanced_render import decoded_frame
    output=app.state.rendering.export(pid,result['active']['id']);pixel=decoded_frame(output,.1).getpixel((50,50))
    assert max(pixel)<8
    restored=advanced.history(pid,'undo',{'plan_id':saved['plan_id'],'revision':saved['revision']})
    assert restored['document']['empty_slots']==[]
    for name,data in st['originals'].items():assert (st['root']/name).read_bytes()==data


def test_draft_requires_selection_approval_and_does_not_overwrite_manual(ready):
    st=ready;editorial,advanced=setup_manual(st);pid=st['pid']
    state=advanced.get(pid);state['document']['clips'].append({'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':1.,'text':'Manuel karar'})
    before=advanced.save(pid,state);draft=editorial.automatic(pid)
    assert advanced.get(pid)==before and draft['clips']
    applied=editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':[draft['clips'][0]['id']]})
    assert len(applied['document']['clips'])==2 and applied['document']['clips'][0]['text']=='Manuel karar'
    assert read(editorial.projects,pid)['preferences']['editing_mode']=='approved_auto'
    from app.editor.models import EditorError
    with pytest.raises(EditorError):editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':[draft['clips'][0]['id']]})


def test_saved_draft_can_be_partially_approved_in_separate_batches(ready):
    editorial,advanced=setup_manual(ready);pid=ready['pid']
    clips=[{'id':str(i)*32,'kind':'text','track':'layers','start':0.,'end':1.,'text':f'Öneri {i}'} for i in (1,2)]
    draft=editorial.draft(pid,clips,details={'changes':['İki ayrı metin']})
    assert editorial.drafts(pid)['drafts'][0]['changes']==['İki ayrı metin']
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':[clips[0]['id']]})
    pending=Editorial(ready['client'].app.state.editor).drafts(pid)['drafts'][0]
    assert pending['applied_ids']==[clips[0]['id']] and not pending['stale']
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':[clips[1]['id']]})
    assert len(advanced.get(pid)['document']['clips'])==2
    from app.editor.history import History
    history=History(ready['client'].app.state.editor)
    history.apply(pid,'undo',history.snapshot(pid));assert len(advanced.get(pid)['document']['clips'])==1
    history.apply(pid,'redo',history.snapshot(pid));assert len(advanced.get(pid)['document']['clips'])==2


def test_manual_map_validation_never_geocodes_an_unknown_place(monkeypatch):
    from app.motion.places import locate,offline
    from app.motion.templates import validate,MotionError
    calls=[]
    monkeypatch.setattr('app.providers.geocoding.geocode',lambda name:calls.append(name))
    with offline():assert locate('NAMAN unknown place xyz') is None
    with pytest.raises(MotionError):validate({'template':'relief','local_only':True,'data':{'mode':'arrow','from':'NAMAN unknown place xyz','to':'Roma'}},'')
    assert calls==[]


def test_draft_visual_preview_does_not_change_document_or_preferences(ready):
    editorial,advanced=setup_manual(ready);pid=ready['pid'];before=advanced.get(pid);prefs=editorial.get(pid)
    draft=editorial.draft(pid,[{'id':'f'*32,'kind':'text','track':'layers','start':0.,'end':1.,'text':'Taslakta kaldı'}])
    path=editorial.preview(pid,draft['id'],.5)
    from PIL import Image
    with Image.open(path) as image:assert image.size==(640,360)
    assert advanced.get(pid)==before and editorial.get(pid)==prefs


def test_long_motion_preview_encodes_only_the_requested_frame(tmp_path):
    from app.editor.compositor import motion_asset
    from app.rendering.probe import metadata
    import shutil
    clip={'motion':{'template':'stat','data':{'value':'40','label':'kilómetros'},'emphasis':''},'start':0.,'end':600.}
    asset=motion_asset(clip,tmp_path,sample_time=300,language='es')
    info=metadata(shutil.which('ffprobe'),asset['path'])
    stream=next(s for s in info['streams'] if s['codec_type']=='video')
    assert int(stream['nb_frames'])==1 and float(info['format']['duration'])<.05


@pytest.mark.parametrize('font',['inter','montserrat','oswald','bebas','lora'])
def test_supported_text_fonts_have_real_bold_pixels(tmp_path,font):
    from app.editor.advanced import Clip
    from app.editor.compositor import text_image
    from PIL import Image
    clip=Clip(id='b'*32,kind='text',track='layers',start=0.,end=1.,text='Roma\nTexto',font=font).model_dump()
    first=Image.open(text_image(clip,tmp_path,640,360)).copy()
    clip['font_weight']='bold';second=Image.open(text_image(clip,tmp_path,640,360))
    assert first.tobytes()!=second.tobytes()


def test_real_ffmpeg_ducking_responds_to_narration(tmp_path):
    import math,struct,wave,subprocess,shutil,array
    from app.editor.advanced import Document
    from app.editor.compositor import compile_graph
    rate=48000;voice=tmp_path/'voice.wav';music=tmp_path/'music.wav'
    for path,freq,amplitude,stop in [(voice,220,16000,1),(music,660,12000,2)]:
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate)
            f.writeframes(b''.join(struct.pack('<h',round(amplitude*math.sin(2*math.pi*freq*i/rate)) if i<stop*rate else 0) for i in range(rate*2)))
    clip={'id':'d'*32,'kind':'media','track':'audio','start':0.,'end':2.,'media':{'provider':'local','media_id':'music','sha256':'0'*64},'transform':{'volume':1.},'ducking':True}
    doc=Document.model_validate({'clips':[clip]}).model_dump();args=[shutil.which('ffmpeg'),'-v','error','-nostdin','-filter_complex_threads','1']
    graph,_,audio=compile_graph(args,doc,{'d'*32:{'path':music,'type':'audio'}},folder=tmp_path,duration=2,narration=voice)
    done=subprocess.run(args+['-filter_complex',graph,'-map',f'[{audio[0]}]','-t','2','-f','f32le','-'],capture_output=True,check=True)
    samples=array.array('f');samples.frombytes(done.stdout)
    assert len(samples)==rate*2
    rms=lambda a,b:math.sqrt(sum(x*x for x in samples[int(a*rate):int(b*rate)])/int((b-a)*rate))
    assert rms(.4,.8)<rms(1.6,1.9)*.5


def test_intentionally_removed_bad_source_does_not_block_readiness(ready):
    editorial,advanced=setup_manual(ready);pid=ready['pid'];projects=editorial.projects
    with closing(projects._connection()) as c,c:
        row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone();stock=json.loads(row[0]);slot=stock['slots'][0]
        slot['local_validation']={'accepted':False};slot['selected_media']['local_path']='stock/'+'0'*32+'.mp4'
        c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
    state=advanced.get(pid);state['document']['empty_slots']=[slot['slot_id']];advanced.save(pid,state)
    view=ready['client'].app.state.rendering.view(pid)
    assert view['ready'],view['readiness']
    assert not any(b['code']=='quality_rejected' for b in view['readiness']['blockers'])


def test_base_preview_infers_mime_for_older_archive_metadata(ready):
    editorial,_=setup_manual(ready);pid=ready['pid'];projects=editorial.projects
    with closing(projects._connection()) as c,c:
        row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone();stock=json.loads(row[0]);slot=stock['slots'][0]
        slot['selected_media'].pop('content_type',None)
        c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
    response=ready['client'].get(f'/api/projects/{pid}/production/stock/slots/{slot["slot_id"]}/preview')
    assert response.status_code==200 and response.headers['content-type'].startswith('video/')


def test_subtitle_text_timing_versions_and_undo_keep_narration_clock(ready):
    st=ready;app=st['client'].app;pid=st['pid'];editorial,advanced=setup_manual(st)
    before=app.state.subtitles.handoff(pid);active=app.state.subtitles.view(pid)['active']
    cues=[{k:q[k] for k in ('start','end','text')} for q in active['cues']]
    cues[0]['text']='Texto editado';cues[0]['start']+=.05
    result=editorial.subtitles_edit(pid,{'version_id':active['id'],'cues':cues,'important_cues':[1]})
    after=app.state.subtitles.handoff(pid)
    assert before['scenes']==after['scenes'] and before['audio_duration']==after['audio_duration']
    assert result['active']['cues'][0]['text']=='Texto editado'
    source=app.state.rendering._inputs(pid,options({}))
    assert source['editorial']['important_cues']==[1]
    restored=editorial.subtitle_history(pid,'undo',{'version_id':result['active']['id']})
    assert restored['active']['id']==active['id']
    redone=editorial.subtitle_history(pid,'redo',{'version_id':active['id']})
    assert redone['active']['id']==result['active']['id']


def test_all_subtitles_can_be_removed_without_erasing_versions(ready):
    st=ready;app=st['client'].app;pid=st['pid'];editorial,_=setup_manual(st)
    active=app.state.subtitles.view(pid)['active']
    result=editorial.subtitles_edit(pid,{'version_id':active['id'],'cues':[],'important_cues':[]})
    assert result['active']['cues']==[] and len(result['versions'])==2
    assert app.state.rendering._inputs(pid,options({}))['handoff']['subtitles']==[]


def test_json_is_reviewable_independent_deduplicated_and_keeps_manual_mode(ready):
    st=ready;app=st['client'].app;pid=st['pid'];editorial,advanced=setup_manual(st)
    package=app.state.editor.task_package(pid)['output_template']
    for key in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'):package[key]=[]
    scene=app.state.editor.view(pid)['scenes'][0]
    package['katmanlar']=[{'scene_id':scene['scene_id'],'text':scene['narration'].split('.')[0],'start':scene['start'],'end':scene['end']}]
    before=advanced.get(pid);draft=editorial.import_draft(pid,package)
    assert before==advanced.get(pid) and draft['clips'][0]['track']=='layers'
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':[draft['clips'][0]['id']]})
    assert read(editorial.projects,pid)['preferences']['editing_mode']=='manual'
    from app.editor.models import EditorError
    with pytest.raises(EditorError,match='Tekrarlanan'):editorial.import_draft(pid,package)
    renamed=deepcopy(package);renamed['katmanlar'][0]['object_id']='changed-external-id'
    with pytest.raises(EditorError,match='Tekrarlanan'):editorial.import_draft(pid,renamed)
    malformed=deepcopy(package);malformed['katmanlar'][0]['object_id']=['not-a-string']
    with pytest.raises(EditorError,match='object_id'):editorial.import_draft(pid,malformed)
    bad=deepcopy(package);bad['katmanlar'][0]['start']=-1
    with pytest.raises(EditorError):editorial.import_draft(pid,bad)


def test_review_requires_both_consents_and_findings_are_project_scoped(ready,monkeypatch):
    from app.editor.reviews import Reviews
    from app.editor.models import EditorError
    from app.editor.service import VIDEO_REVIEW_VERSION
    st=ready;app=st['client'].app;pid=st['pid'];review=Reviews(app.state.editor)
    calls=[];monkeypatch.setattr(app.state.editor,'video_review',lambda *a:calls.append(a) or {'sample':True})
    with pytest.raises(EditorError):review.request(pid,{'confirmed':True})
    with pytest.raises(EditorError):review.request(pid,{'confirmed':True,'data_sharing_confirmed':True,'cost_confirmed':False})
    assert not calls
    assert review.request(pid,{'confirmed':True,'data_sharing_confirmed':True,'cost_confirmed':True})=={'sample':True}
    report={'render_version_id':'r','basis':'8 örnek kare','summary':'Görsel kontrol','issues':[{'timecode':1.,'category':'Metin','message':'Kontrol edin.'}]}
    with closing(app.state.projects._connection()) as c,c:c.execute('INSERT INTO archive_analysis_cache VALUES (?,?,?,?,?)',(pid,'a'*64,VIDEO_REVIEW_VERSION,json.dumps(report),'now'))
    state=review.status(pid,'r','0',{'status':'resolved'})
    assert state['reports'][0]['issues'][0]['status']=='resolved'
    other=app.state.projects.create({'name':'Başka','topic':'Proje kapsamı'})['id']
    assert Reviews(app.state.editor).get(other)['reports']==[]


def test_clean_map_has_no_editorial_text_pin_or_sfx():
    from app.motion.templates import build
    from app.channels import DEFAULT_STYLE
    scene=build({'template':'map','data':{'place':'Rom','label':'Kurgusal başlık','lat':41.9,'lon':12.5},'emphasis':'','local_only':True,'clean_source':True},DEFAULT_STYLE,1.,0)
    assert any(e['type']=='map' for e in scene['elements'])
    assert not any(e['type'] in ('text','counter','pin') for e in scene['elements'])
    assert not scene.get('sound_events')


def test_unified_history_mode_clips_subtitles_and_approved_draft(ready):
    from app.editor.history import History
    st=ready;app=st['client'].app;pid=st['pid'];editorial,advanced=setup_manual(st);history=History(app.state.editor)
    draft=editorial.automatic(pid);editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':[draft['clips'][0]['id']]})
    history.apply(pid,'undo',history.snapshot(pid))
    assert advanced.get(pid)['document']['clips']==[] and editorial.get(pid)['preferences']['editing_mode']=='manual'
    history.apply(pid,'redo',history.snapshot(pid))
    assert len(advanced.get(pid)['document']['clips'])==1 and editorial.get(pid)['preferences']['editing_mode']=='approved_auto'
    prefs=editorial.get(pid);prefs['preferences']['subtitle_display']='none';editorial.save(pid,prefs)
    assert history.apply(pid,'undo',history.snapshot(pid))['domain']=='preferences'
    assert editorial.get(pid)['preferences']['subtitle_display']=='full'
    assert history.apply(pid,'redo',history.snapshot(pid))['domain']=='preferences'
    assert editorial.get(pid)['preferences']['subtitle_display']=='none'


def test_sources_only_preparation_leaves_missing_without_cards_or_ai(ready,monkeypatch):
    from app.stock.director_media import MediaDirector
    from app.editor.models import EditorError
    import time
    st=ready;app=st['client'].app;pid=st['pid'];editorial,advanced=setup_manual(st)
    with closing(app.state.projects._connection()) as c,c:
        row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone();state=json.loads(row[0])
        for slot in state['slots']:slot.update(selected_media=None,status='pending')
        c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(state),pid))
    for name in ('try_local_archive','try_step','extended_search'):monkeypatch.setattr(MediaDirector,name,lambda *a,**k:False)
    monkeypatch.setattr(MediaDirector,'_call_ai',lambda *a,**k:pytest.fail('Manuel kaynak hazırlama ücretli AI çağırmamalı'))
    monkeypatch.setattr('app.motion.clips.render_clip',lambda *a,**k:pytest.fail('Kaynak eksikliği otomatik motion üretmemeli'))
    current=app.state.stock.view(pid)
    job=app.state.stock.start(pid,{'plan_id':current['plan_id'],'revision':current['revision'],'action':'complete_media'})
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        result=app.state.stock.view(pid)
        if result.get('job',{}).get('status') in ('completed','error'):break
        time.sleep(.02)
    assert result['job']['status']=='completed',result['job']
    assert all(s['selected_media'] is None and s['status']!='complete' for s in result['slots'])
    assert advanced.get(pid)['document']['clips']==[]
