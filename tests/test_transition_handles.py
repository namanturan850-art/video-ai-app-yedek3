"""Short video handles keep a reviewable plan and require a per-transition decision."""
from contextlib import closing
from copy import deepcopy
import json

import pytest
from app.editor.advanced import AdvancedEditor
from app.editor.editorial import Editorial
from app.editor.models import EditorError
from app.editor.transition_handles import capacity, problem
from test_plan_intervals import plan, selected
from test_advanced_editing import advanced, change
from test_simple_workflow import workflow


def short_plan(plan,extra=0.):
    editorial,ed,pid,view,payload=plan
    first=view['tracks']['visuals'][0]
    first['media'].update(media_type='video',duration=4.+extra)
    payload['sahneler']=payload['sahneler'][:2]
    return editorial,ed,pid,view,payload


@pytest.mark.parametrize('extra,shorter',[(0.,None),(.05,None),(.12,.1),(.2,None),(None,None)])
def test_handle_preflight_preserves_all_other_proposals_without_saving(plan,extra,shorter):
    editorial,ed,pid,view,payload=short_plan(plan,extra or 0.)
    if extra is None:view['tracks']['visuals'][0]['media']['duration']=None
    original=deepcopy(payload);before=ed.get(pid);sources=deepcopy(view)
    validated=editorial.validate_response(pid,payload)
    assert validated['valid'] and ed.get(pid)==before
    draft=editorial.import_draft(pid,payload)
    assert len(draft['adjustments'])==2 and payload==original and view==sources and ed.get(pid)==before
    if extra==.2:
        assert not draft['transition_issues'] and len(draft['transitions'])==2
    else:
        assert len(draft['transitions'])==1 and draft['transitions'][0]['slot_id']=='slot-2'
        issue=draft['transition_issues'][0]
        assert issue['scene_id']=='scene-1' and issue['time']==4. and '4.000' in issue['message']
        options={o['id']:o['transition'] for o in issue['options']}
        assert options['hard_cut']['kind']=='cut' and options['dip_black']['kind']=='dip_black'
        assert options.get('shorter',{}).get('duration')==shorter
        assert validated['requires_transition_resolution']


@pytest.mark.parametrize('option',['hard_cut','dip_black','shorter'])
def test_only_confirmed_transition_is_changed_and_survives_reopen_approval_undo(plan,option):
    editorial,ed,pid,view,payload=short_plan(plan,.12)
    # Unrelated manual effect/text/transition must survive every stage.
    change(ed,pid,lambda d:d['adjustments'].append({'slot_id':'slot-3','transform':{'rotation':12.}}))
    change(ed,pid,lambda d:d['clips'].append({'id':'a'*32,'kind':'text','track':'layers','text':'Manuel','locked':True,'start':8.,'end':10.}))
    change(ed,pid,lambda d:d['transitions'].append({'slot_id':'slot-7','next_slot_id':'slot-8','kind':'cut'}))
    before=ed.get(pid);sources=deepcopy(view);draft=editorial.import_draft(pid,payload);original=deepcopy(draft)
    issue=draft['transition_issues'][0];request={'confirmed':True,'issue_id':issue['id'],'option_id':option}
    for bad in ({**request,'confirmed':False},{**request,'option_id':'arbitrary'},{**request,'duration':9}):
        with pytest.raises(EditorError):editorial.resolve_transition(pid,draft['id'],bad)
    assert ed.get(pid)==before
    fixed=editorial.resolve_transition(pid,draft['id'],request)
    assert ed.get(pid)==before and original['transitions']==draft['transitions']
    assert fixed['adjustments']==draft['adjustments'] and original['clips']==fixed['clips']
    assert fixed['transition_issues'][0]['status']=='resolved'
    record=next(t for t in fixed['transitions'] if t['slot_id']=='slot-1')
    assert record==next(o['transition'] for o in issue['options'] if o['id']==option)
    reopened=Editorial(ed.editor).drafts(pid)['drafts'][0]
    assert reopened['transitions']==fixed['transitions']
    with pytest.raises(EditorError):editorial.resolve_transition(pid,draft['id'],request)
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(fixed)})
    saved=ed.get(pid);doc=saved['document']
    assert doc['clips']==before['document']['clips'] and before['document']['transitions'][0] in doc['transitions']
    assert next(a for a in doc['adjustments'] if a['slot_id']=='slot-3')==before['document']['adjustments'][0]
    assert view==sources
    ed.history(pid,'undo',{'plan_id':saved['plan_id'],'revision':saved['revision']})
    assert ed.get(pid)['document']==before['document']


def test_valid_proposals_can_be_approved_first_and_problem_is_retained(plan):
    editorial,ed,pid,view,payload=short_plan(plan)
    draft=editorial.import_draft(pid,payload)
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(draft)})
    current=ed.get(pid);assert len(current['document']['adjustments'])==2
    assert not any(t['slot_id']=='slot-1' for t in current['document']['transitions'])
    stored=editorial.drafts(pid)['drafts'][0];assert stored['transition_issues'][0]['status']=='pending' and not stored['stale']
    fixed=editorial.resolve_transition(pid,draft['id'],{'confirmed':True,'issue_id':stored['transition_issues'][0]['id'],'option_id':'hard_cut'})
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':['transition:slot-1']})
    assert len(ed.get(pid)['document']['adjustments'])==2 and len(ed.get(pid)['document']['transitions'])==2


def test_short_handle_guard_remains_strict_and_has_scene_time(plan):
    editorial,ed,pid,view,payload=short_plan(plan)
    before=ed.get(pid)
    with pytest.raises(EditorError,match='scene-1, 4.000 sn') as error:
        change(ed,pid,lambda d:d['transitions'].append({'slot_id':'slot-1','next_slot_id':'slot-2','kind':'cross_dissolve','duration':.2}))
    assert error.value.category=='short_transition' and ed.get(pid)==before


def test_handle_accounts_for_source_in_speed_and_native_frame_clock(plan):
    editorial,ed,pid,view,payload=short_plan(plan)
    first,second=view['tracks']['visuals'][:2]
    first.update(clip_start=1.);first['media']['duration']=9.24
    limits=capacity(first,second,[{'slot_id':first['slot_id'],'transform':{'speed':2.}}])
    assert abs(limits['tail']-.12)<1e-8 and limits['blend_max']==.1
    first.update(start=.01,end=4.02,clip_start=0.);first['media']['duration']=4.12
    assert capacity(first,second,[])['blend_max']<.1  # 121 render frames consume more than 4.01 s.


def test_options_for_tiny_clips_and_stale_draft_are_safe(plan):
    editorial,ed,pid,view,payload=short_plan(plan)
    first,second=view['tracks']['visuals'][:2]
    first['end']=.2;second['start']=.2
    payload['sahneler']=[{'scene_id':'scene-1','start':0.,'end':.2,'transition':'crossfade'}]
    draft=editorial.import_draft(pid,payload);issue=draft['transition_issues'][0]
    assert [o['id'] for o in issue['options']]==['hard_cut']
    first['locked']=True
    with pytest.raises(EditorError,match='değişti'):
        editorial.resolve_transition(pid,draft['id'],{'confirmed':True,'issue_id':issue['id'],'option_id':'hard_cut'})
    assert ed.get(pid)['revision']==0


@pytest.mark.parametrize('option',['shorter','hard_cut','dip_black'])
def test_real_json_draft_preview_confirmation_final_render(workflow,option):
    from test_rendering import await_job
    client,pid=workflow;editor=client.app.state.editor;ed=AdvancedEditor(editor)
    base=f'/api/projects/{pid}/editor'
    view=editor.view(pid);first=sorted((s for track in view['tracks'].values() for s in track if s.get('slot_id')),key=lambda s:s['start'])[0]
    # Keep the actual 5-second video and move its in-point near the end.
    native=(round(first['end']*30)-round(first['start']*30))/30
    inpoint=5.-max(first['end']-first['start'],native)-(.12 if option=='shorter' else 0.)
    stock=client.app.state.stock
    with closing(ed.projects._connection()) as c,c:
        state=stock._load(c,pid,view['stock_plan_id'])
        next(s for s in state['slots'] if s['slot_id']==first['slot_id'])['segment_start']=inpoint
        stock._save(c,state)
    before=editor.view(pid);original=ed.get(pid)
    payload=client.get(base+'/manual/package').json()['output_template']
    payload['sahneler']=[{'scene_id':first['scene_id'],'start':first['start'],'end':first['end'],'motion':'slow_zoom','transition':'crossfade','object_id':'ai-camera'}]
    response=client.post(base+'/manual/validate',json=payload)
    assert response.status_code==200 and response.json()['requires_transition_resolution'],response.text
    response=client.post(base+'/manual/response-draft',json={'text':json.dumps(payload)})
    assert response.status_code==201,response.text
    draft=response.json();assert len(draft['adjustments'])==1 and not draft['transitions'] and ed.get(pid)==original
    assert client.get(base+f'/editorial/drafts/{draft["id"]}/preview?time={first["start"]+.1}').status_code==200
    issue=draft['transition_issues'][0]
    endpoint=base+f'/editorial/drafts/{draft["id"]}/resolve-transition'
    assert client.post(endpoint,json={'confirmed':False,'issue_id':issue['id'],'option_id':option}).status_code==422
    response=client.post(endpoint,json={'confirmed':True,'issue_id':issue['id'],'option_id':option})
    assert response.status_code==200,response.text
    fixed=response.json();assert ed.get(pid)==original
    assert client.get(base+f'/editorial/drafts/{draft["id"]}/preview?time={first["end"]+.04}').status_code==200
    response=client.post(base+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':selected(fixed)})
    assert response.status_code==200,response.text
    after=editor.view(pid)
    assert after['tracks']==before['tracks'] and after['subtitle_version_id']==before['subtitle_version_id'] and after['stock_revision']==before['stock_revision']
    response=client.post(f'/api/projects/{pid}/render/jobs',json={'encoder':'cpu'})
    assert response.status_code==202,response.text
    result=await_job({'client':client,'pid':pid})
    assert result['job']['status']=='completed',result


@pytest.mark.parametrize('failure',['cross_filter','fade_filter','cross_execution'])
def test_approved_transition_is_never_silently_replaced_during_render(tmp_path,failure):
    from test_rendering import contract, synthetic
    from test_subtitles import wav
    from app.rendering.engine import FFmpegRenderProvider
    from app.rendering.runner import ProcessRunner
    from app.rendering.models import RenderError, options
    from app.rendering.tools import discover
    from app.rendering.timeline import build
    from app.editor.advanced import Document
    source=synthetic(tmp_path,'source.mp4',['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=3','-c:v','libx264','-threads','1'])
    voice=tmp_path/'voice.wav';voice.write_bytes(wav(2))
    handoff,production=contract(2.);timeline=build(handoff,production)
    document=Document.model_validate({'transitions':[{'slot_id':'1','next_slot_id':'2','kind':'dip_black' if failure=='fade_filter' else 'cross_dissolve','duration':.1}]}).model_dump()
    tools=deepcopy(discover())
    if failure!='cross_execution':tools['filters']=[f for f in tools['filters'] if f!=('fade' if failure=='fade_filter' else 'xfade')]
    class FailCross(ProcessRunner):
        def run(self,args,cwd,*a,**context):
            if context.get('phase')=='crossfade':raise RenderError('render_failed','Sentetik geçiş hatası')
            return super().run(args,cwd,*a,**context)
    plan={'temporary':tmp_path,'timeline':timeline,'handoff':handoff,'options':options({'encoder':'cpu','subtitle_display':'none'}),'audio':voice,'music':None,
          'media':{key:{'path':source,'type':'video','duration':3.} for key in ('1','2')},'advanced_document':document,'advanced_assets':{},'advanced_slots':{s['slot_id']:s for s in timeline['slots']}}
    before=deepcopy(document)
    with pytest.raises(RenderError,match='değiştirilmedi|değiştiril|onaylanan') as error:
        FFmpegRenderProvider(tools,FailCross(),workers=1).render(plan)
    assert error.value.category in ('transition_unavailable','transition_failed') and document==before


def test_correction_rechecks_capacity_instead_of_trusting_a_stored_option(plan):
    editorial,ed,pid,view,payload=short_plan(plan,.12)
    draft=editorial.import_draft(pid,payload);issue=draft['transition_issues'][0]
    view['tracks']['visuals'][0]['media']['duration']=4.01
    with pytest.raises(EditorError) as error:
        editorial.resolve_transition(pid,draft['id'],{'confirmed':True,'issue_id':issue['id'],'option_id':'shorter'})
    assert error.value.category=='short_transition' and ed.get(pid)['revision']==0
    assert editorial.drafts(pid)['drafts'][0]['transition_issues'][0]['status']=='pending'


def test_transition_only_plan_can_be_corrected_without_dummy_edits(plan):
    editorial,ed,pid,view,payload=short_plan(plan)
    payload['sahneler']=payload['sahneler'][:1];payload['sahneler'][0]['motion']='none'
    draft=editorial.import_draft(pid,payload)
    assert not selected(draft) and draft['transition_issues']
    fixed=editorial.resolve_transition(pid,draft['id'],{'confirmed':True,'issue_id':draft['transition_issues'][0]['id'],'option_id':'hard_cut'})
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(fixed)})
    assert not ed.get(pid)['document']['adjustments'] and len(ed.get(pid)['document']['transitions'])==1


def test_correcting_one_issue_leaves_another_issue_pending(plan):
    editorial,ed,pid,view,payload=short_plan(plan)
    view['tracks']['visuals'][1]['media'].update(media_type='video',duration=4.)
    payload['sahneler'][1]['transition']='crossfade'
    draft=editorial.import_draft(pid,payload);assert len(draft['transition_issues'])==2
    first,second=draft['transition_issues']
    fixed=editorial.resolve_transition(pid,draft['id'],{'confirmed':True,'issue_id':first['id'],'option_id':'hard_cut'})
    assert [i['status'] for i in fixed['transition_issues']]==['resolved','pending']
    assert fixed['transition_issues'][1]==second and len(fixed['transitions'])==1
    assert fixed['adjustments']==draft['adjustments'] and ed.get(pid)['revision']==0
