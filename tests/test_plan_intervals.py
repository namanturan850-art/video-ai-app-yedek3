"""Reported 16/6 shape, constructed fixture (the owner's JSON was not attached)."""
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path

import pytest
from app.editor.editorial import Editorial
from app.editor.advanced import AdvancedEditor
from app.editor.compositor import value_at, expression
from app.editor.models import EditorError
from app.editor.plan_intervals import SceneIntervals
from app.editor.service import EditorService
from test_advanced_editing import advanced, change


@pytest.fixture
def plan(advanced):
    ed,pid,view,_=advanced
    view.update(duration=72.,fps=30)
    view['scenes']=[{'scene_id':f'scene-{i+1}','start':float(i*12),'end':float((i+1)*12),'locked':False,'narration':'Roma 40 km.'} for i in range(6)]
    view['tracks']={'visuals':[{'slot_id':f'slot-{i+1}','scene_id':f'scene-{i//3+1}','start':float(i*4),'end':float((i+1)*4),'locked':False,'media':{'media_type':'image'},'clip_start':0.} for i in range(18)],'subtitles':[{'start':0.,'end':72.,'text':'Kaynak altyazı'}],'audio':[{'id':'voice-original'}]}
    active={'plan_id':'p','revision':1,'blocks':[{'id':s['scene_id'],'narration':s['narration'],'locked':False} for s in view['scenes']]}
    ed.editor._active=lambda _:deepcopy(active)
    ed.editor._diff=lambda *a:[]
    ed.editor.validate_import=lambda p,x:EditorService.validate_import(ed.editor,p,x)
    payload=json.loads((Path(__file__).parent/'fixtures/manual_plan_16_intervals_6_scenes.json').read_text())
    return Editorial(ed.editor),ed,pid,view,payload


def selected(draft):
    return [c['id'] for c in draft['clips']]+['adjustment:'+x['slot_id'] for x in draft['adjustments']]+['transition:'+x['slot_id'] for x in draft['transitions']]


def test_16_records_6_scenes_draft_approval_reopen_and_undo(plan):
    editorial,ed,pid,view,payload=plan
    before=ed.get(pid);sources=deepcopy(view)
    assert len(payload['sahneler'])==16 and len({x['scene_id'] for x in payload['sahneler']})==6
    draft=editorial.import_draft(pid,payload)
    assert ed.get(pid)==before and view==sources
    assert len(draft['adjustments'])==18 and len({a['slot_id'] for a in draft['adjustments']})==18
    assert len(draft['transitions'])==15 and len({t['slot_id'] for t in draft['transitions']})==15
    assert draft['transitions'][0]['slot_id']=='slot-1' and draft['transitions'][0]['next_slot_id']=='slot-2'
    assert '4.000' in '\n'.join(draft['changes'])
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(draft)})
    saved=ed.get(pid);assert len(saved['document']['adjustments'])==18
    assert AdvancedEditor(ed.editor).get(pid)==saved and view==sources
    ed.history(pid,'undo',{'plan_id':'p','revision':saved['revision']})
    assert ed.get(pid)['document']==before['document']


def test_partial_intervals_merge_into_one_adjustment_with_correct_camera_clock(plan):
    editorial,ed,pid,view,payload=plan
    payload['sahneler']=[{'scene_id':'scene-1','object_id':'a','start':.5,'end':1.5,'motion':'pan','transition':'none'},
                         {'scene_id':'scene-1','object_id':'b','start':2.,'end':3.,'motion':'slow_zoom','transition':'none'}]
    draft=editorial.import_draft(pid,payload);assert len(draft['adjustments'])==1
    edit=draft['adjustments'][0];assert edit['slot_id']=='slot-1'
    assert value_at(edit,'x',.25)==0 and value_at(edit,'x',.5)==-100
    assert abs(value_at(edit,'x',1.0))<1e-6
    assert value_at(edit,'x',1.75)==0 and value_at(edit,'scale',1.75)==1
    assert value_at(edit,'scale',2.5)>1 and value_at(edit,'scale',3.25)==1
    # The same keyframe document is consumed by preview scalars and FFmpeg expressions.
    assert 'if(' in expression(edit,'scale','t')
    assert not draft['transitions'] and ed.get(pid)['revision']==0


def test_overlapping_camera_proposals_name_scene_time_and_objects_without_saving(plan):
    editorial,ed,pid,view,payload=plan
    payload['sahneler']=[{'scene_id':'scene-1','object_id':'a','start':0.,'end':2.,'motion':'pan'},
                         {'scene_id':'scene-1','object_id':'b','start':1.,'end':3.,'motion':'slow_zoom'}]
    with pytest.raises(EditorError,match='scene-1, 1.000–2.000.*a ile b') as error:editorial.import_draft(pid,payload)
    assert error.value.category=='interval_conflict' and ed.get(pid)['revision']==0
    with closing(ed.projects._connection()) as c:
        assert not c.execute("SELECT 1 FROM editorial_events WHERE kind='draft' AND project_id=?",(pid,)).fetchone()


@pytest.mark.parametrize('kind',['same','conflict','inside','locked'])
def test_multiple_transitions_use_requested_cut_and_never_scene_end(plan,kind):
    editorial,ed,pid,view,payload=plan
    records=[{'scene_id':'scene-1','object_id':'a','start':0.,'end':4.,'transition':'crossfade'},
             {'scene_id':'scene-1','object_id':'b','start':1.,'end':4.,'transition':'crossfade'},
             {'scene_id':'scene-1','object_id':'c','start':4.,'end':8.,'transition':'fade'}]
    if kind=='conflict':records[1]['transition']='hard_cut'
    if kind=='inside':records[0]['end']=3.5
    if kind=='locked':view['tracks']['visuals'][1]['locked']=True
    payload['sahneler']=records
    if kind!='same':
        with pytest.raises(EditorError,match='scene-1, (3.500|4.000)'):editorial.import_draft(pid,payload)
        assert ed.get(pid)['revision']==0
    else:
        draft=editorial.import_draft(pid,payload)
        assert [t['slot_id'] for t in draft['transitions']]==['slot-1','slot-2']
        assert 'tek kayıtta' in '\n'.join(draft['changes'])


def test_existing_manual_adjustment_clips_markers_and_sources_are_preserved(plan):
    editorial,ed,pid,view,payload=plan
    change(ed,pid,lambda doc:doc['adjustments'].append({'slot_id':'slot-1','transform':{'rotation':10.},'keyframes':[{'property':'opacity','time':0.,'value':.8}]}))
    change(ed,pid,lambda doc:doc['clips'].append({'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':3.,'text':'Manuel','locked':True}))
    change(ed,pid,lambda doc:doc['markers'].append({'id':'b'*32,'time':2.,'name':'Manuel not'}))
    before=ed.get(pid);sources=deepcopy(view)
    payload['sahneler']=payload['sahneler'][:1]
    draft=editorial.import_draft(pid,payload)
    assert draft['adjustments'][0]['transform']['rotation']==10.
    assert any(k['property']=='opacity' for k in draft['adjustments'][0]['keyframes'])
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(draft)})
    after=ed.get(pid)['document'];assert len(after['adjustments'])==1
    assert after['clips']==before['document']['clips'] and after['markers']==before['document']['markers'] and view==sources


@pytest.mark.parametrize('conflict',['camera','transition'])
def test_manual_conflicts_are_never_overwritten(plan,conflict):
    editorial,ed,pid,view,payload=plan
    if conflict=='camera':change(ed,pid,lambda d:d['adjustments'].append({'slot_id':'slot-1','keyframes':[{'property':'scale','time':0.,'value':1.1}]}))
    else:change(ed,pid,lambda d:d['transitions'].append({'slot_id':'slot-1','next_slot_id':'slot-2','kind':'dip_black','duration':.5}))
    before=ed.get(pid);payload['sahneler']=payload['sahneler'][:1]
    with pytest.raises(EditorError,match='scene-1.*manuel'):editorial.import_draft(pid,payload)
    assert ed.get(pid)==before


def test_draft_selection_and_staleness_remain_required(plan):
    editorial,ed,pid,view,payload=plan
    draft=editorial.import_draft(pid,payload)
    with pytest.raises(EditorError):editorial.approve(pid,draft['id'],{'confirmed':False,'clip_ids':selected(draft)})
    ids=selected(draft)
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':ids[:1]})
    assert len(ed.get(pid)['document']['adjustments'])==1
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':ids[1:]})
    with pytest.raises(EditorError):editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':ids[:1]})
    # New unrelated edit makes a newly prepared draft stale.
    payload['sahneler']=[];payload['katmanlar']=[{'scene_id':'scene-1','text':'Roma'}]
    next_draft=editorial.import_draft(pid,payload)
    change(ed,pid,lambda d:d['markers'].append({'id':'e'*32,'time':1.,'name':'Yeni not'}))
    with pytest.raises(EditorError,match='Taslak'):editorial.approve(pid,next_draft['id'],{'confirmed':True,'clip_ids':selected(next_draft)})


def test_validation_is_read_only_and_uses_the_same_interval_checks(plan):
    editorial,ed,pid,view,payload=plan
    assert editorial.validate_response(pid,payload)['valid']
    with closing(ed.projects._connection()) as c:
        assert not c.execute("SELECT 1 FROM editorial_events WHERE project_id=? AND kind='draft'",(pid,)).fetchone()
    payload['sahneler'][1]['start']=2.
    result=editorial.validate_response(pid,payload)
    assert not result['valid'] and 'scene-1, 2.000–4.000' in result['correction_message']
    assert ed.get(pid)['revision']==0


# Real HTTP/SQLite/FFmpeg coverage complements the deterministic 16/6 fixture.
from test_simple_workflow import workflow


def test_http_validate_draft_preview_partial_camera_and_short_final_render(workflow):
    from test_rendering import await_job
    client,pid=workflow;editor=client.app.state.editor;ed=AdvancedEditor(editor)
    base=f'/api/projects/{pid}/editor';before=editor.view(pid)
    slots=sorted((s for values in before['tracks'].values() for s in values if s.get('slot_id')),key=lambda s:s['start'])
    slot=slots[0];length=slot['end']-slot['start'];assert length>.3
    start=slot['start']+length*.1;mid=slot['start']+length*.4;end=slot['start']+length*.8
    payload=client.get(base+'/manual/package').json()['output_template']
    payload['sahneler']=[{'scene_id':slot['scene_id'],'start':start,'end':mid,'object_id':'camera-a','motion':'pan'},
                         {'scene_id':slot['scene_id'],'start':mid,'end':end,'object_id':'camera-b','motion':'slow_zoom'}]
    original=ed.get(pid)
    r=client.post(base+'/manual/validate',json=payload);assert r.status_code==200 and r.json()['valid'],r.text
    assert ed.get(pid)==original
    r=client.post(base+'/manual/response-draft',json={'text':json.dumps(payload)})
    assert r.status_code==201,r.text
    draft=r.json();assert len(draft['adjustments'])==1 and ed.get(pid)==original
    r=client.get(base+f'/editorial/drafts/{draft["id"]}/preview?time={mid}')
    assert r.status_code==200 and r.headers['content-type']=='image/jpeg',r.text[:200] if r.status_code!=200 else ''
    assert ed.get(pid)==original
    r=client.post(base+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':selected(draft)})
    assert r.status_code==200,r.text
    after=editor.view(pid)
    assert after['tracks']==before['tracks'] and after['subtitle_version_id']==before['subtitle_version_id']
    assert after['stock_revision']==before['stock_revision']
    r=client.post(f'/api/projects/{pid}/render/jobs',json={'encoder':'cpu'})
    assert r.status_code==202,r.text
    result=await_job({'client':client,'pid':pid})
    assert result['job']['status']=='completed',result


@pytest.mark.parametrize('change_kind',['range','source','lock'])
def test_base_media_changes_after_draft_prevent_approval(plan,change_kind):
    editorial,ed,pid,view,payload=plan
    draft=editorial.import_draft(pid,payload)
    if change_kind=='range':view['tracks']['visuals'][0]['end']=3.5
    elif change_kind=='source':view['tracks']['visuals'][0]['media']['media_id']='new-source'
    else:view['tracks']['visuals'][0]['locked']=True
    assert editorial.drafts(pid)['drafts'][0]['stale']
    with pytest.raises(EditorError,match='Taslak.*değişti'):editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(draft)})
    assert ed.get(pid)['revision']==0


def test_two_zoom_intervals_in_same_slot_keep_gaps_and_adjacent_boundaries(plan):
    editorial,ed,pid,view,payload=plan
    payload['sahneler']=[{'scene_id':'scene-1','object_id':str(i),'start':a,'end':z,'motion':'slow_zoom'}
        for i,(a,z) in enumerate([(.5,1.5),(1.5,2.5),(3.,4.)])]
    edit=editorial.import_draft(pid,payload)['adjustments'][0]
    assert len({(k['property'],k['time']) for k in edit['keyframes']})==len(edit['keyframes'])
    assert value_at(edit,'scale',1.)>1 and value_at(edit,'scale',1.5)==1
    assert value_at(edit,'scale',2.)>1 and value_at(edit,'scale',2.75)==1
    assert value_at(edit,'scale',3.)==1 and value_at(edit,'scale',3.5)>1


def test_camera_spanning_two_slots_preserves_global_progress_and_excludes_other_slots(plan):
    editorial,ed,pid,view,payload=plan
    payload['sahneler']=[{'scene_id':'scene-1','start':2.,'end':6.,'motion':'pan'}]
    edits=editorial.import_draft(pid,payload)['adjustments']
    assert [x['slot_id'] for x in edits]==['slot-1','slot-2']
    assert value_at(edits[0],'x',1.)==0 and value_at(edits[0],'x',2.)==-100
    assert value_at(edits[1],'x',0.)==0 and value_at(edits[1],'x',1.)==50
    assert value_at(edits[1],'x',2.5)==0
