from contextlib import closing
from copy import deepcopy
import json

import pytest
from app.editor.editorial import read,Preferences,Editorial
from app.editor.advanced import AdvancedEditor
from app.stock.service import fingerprint
from app.rendering.models import options
from test_rendering import ready,await_job,url


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
