"""Quality pass: original captions, visible pixels, truthful counters and history."""
from contextlib import closing
from copy import deepcopy
import json

import pytest

from app.rendering import ass,smart_edit,timeline,tools
from app.rendering.engine import FFmpegRenderProvider
from app.rendering.models import options
from app.rendering.runner import ProcessRunner
from test_rendering import ready,contract,synthetic,url,await_job
from test_smart_edit import handoffs,owner_shape,run_render,pixels,difference
from test_subtitles import wav


@pytest.mark.parametrize('style',['basic','balanced','dynamic'])
def test_normal_captions_exactly_original_part9_in_every_profile(style):
    h,p=handoffs();before=deepcopy(h)
    original,_,_=ass.create(h['subtitles'],h['scenes'],4,overlays=False)
    plan=smart_edit.build(timeline.build(h,p),h,style,'source')
    output,_,_=ass.create(h['subtitles'],h['scenes'],4,editing_style=style,emphasis=plan['emphasis'])
    captions=lambda text:[line for line in text.splitlines() if line.startswith('Style: Subtitle,') or line.startswith('Dialogue: 0,')]
    assert captions(output)==captions(original)
    assert 'Style: Subtitle,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,60,1' in output
    assert all(r'\fad' not in line and r'\t(' not in line for line in captions(output))
    assert h==before
    if style!='basic':
        assert 'Style: EmphasisCenter,' in output and ',8,110,110,120,1' in output
        assert any(line.startswith('Dialogue: 1,') and ',EmphasisCenter,' in line for line in output.splitlines())


@pytest.mark.parametrize('style',['balanced','dynamic'])
def test_emphasis_source_and_timing_independent_of_transition_decisions(style):
    h,p=owner_shape();before=deepcopy(h)
    first=smart_edit.build(timeline.build(h,p),h,style,'source')
    for scene in p['scenes']:scene['transition']='crossfade'
    second=smart_edit.build(timeline.build(h,p),h,style,'source')
    assert first['emphasis']==second['emphasis'] and h==before
    assert [s['transition_out'] for s in first['slots']]!=[s['transition_out'] for s in second['slots']]
    # A meaningful cue inside a scene is eligible without any scene boundary.
    h,p=handoffs(12);h['subtitles']=[{'index':1,'start':5,'end':8,'text':'Im Jahr 2026'}]
    plan=smart_edit.build(timeline.build(h,p),h,style,'source')
    assert plan['emphasis'][0]['start']==5 and plan['slots'][0]['transition_out']=='hard_cut'
    assert plan['emphasis'][0]['text'] in p['scenes'][0]['narration_text']


@pytest.mark.parametrize('style,lower,upper',[('balanced',.04,.05),('dynamic',.06,.08)])
def test_balanced_dynamic_visible_strengths_and_tight_shot_limit(style,lower,upper):
    h,p=handoffs();plan=smart_edit.build(timeline.build(h,p),h,style,'s')
    strength=plan['slots'][0]['segments'][0]['motion_strength']
    assert lower<=strength<=upper and plan['algorithm_version']=='smart_edit_v2'
    p['scenes'][0]['composition']='person'
    assert smart_edit.build(timeline.build(h,p),h,style,'s')['slots'][0]['segments'][0]['motion_strength']<=.012


@pytest.mark.parametrize('style,minimum,maximum',[('balanced',.35,.50),('dynamic',.40,.60)])
def test_transition_visible_duration_stays_inside_existing_master_timeline(style,minimum,maximum):
    h,p=contract(6)
    h['scenes'][0]['end']=h['scenes'][1]['start']=3
    h['stock_slots'][0].update(end=3,duration=3)
    h['stock_slots'][1].update(start=3,duration=3)
    for s in p['scenes']:s.update(transition='crossfade',motion='none',composition='wide',importance=50)
    t=timeline.build(h,p);before=deepcopy(t);plan=smart_edit.build(t,h,style,'s')
    transition=plan['slots'][0]
    assert minimum<=transition['transition_duration']<=maximum and t==before
    assert sum(s['frames'] for item in plan['slots'] for s in item['segments'])==180


@pytest.mark.parametrize('style',['balanced','dynamic'])
def test_actual_ffmpeg_video_motion_pixels_and_duration(style,tmp_path):
    clip=synthetic(tmp_path,'grid.mp4',['-f','lavfi','-i','nullsrc=s=640x360:r=30:d=3,geq=r=80+60*sin(X/11):g=100+40*sin(Y/7):b=90','-c:v','libx264'])
    h,p=handoffs(3);h['subtitles']=[];media={'a'*32:{'path':clip,'type':'video'}}
    basic,_,_=run_render(tmp_path/'basic',h,p,media,'basic')
    smart,plan,_=run_render(tmp_path/'smart',h,p,media,style)
    for when in (.5,1.5,2.6):assert difference(pixels(basic['path'],when),pixels(smart['path'],when))>1
    assert smart['metadata']['smart_edit_applied_summary']['motion_effects']==plan['summary']['motion_effects']==1


@pytest.mark.parametrize('style',['balanced','dynamic'])
def test_actual_selected_transition_has_visible_blend_pixels(style,tmp_path):
    red=synthetic(tmp_path,'red.mp4',['-f','lavfi','-i','color=c=red:s=320x240:r=30:d=4','-c:v','libx264'])
    blue=synthetic(tmp_path,'blue.mp4',['-f','lavfi','-i','color=c=blue:s=320x240:r=30:d=4','-c:v','libx264'])
    h,p=contract(6);h['subtitles']=[]
    h['scenes'][0]['end']=h['scenes'][1]['start']=3
    h['stock_slots'][0].update(end=3,duration=3)
    h['stock_slots'][1].update(start=3,duration=3)
    for s in p['scenes']:s.update(transition='hard_cut',motion='none',composition='wide',importance=50,overlay_text='')
    media={'1':{'path':red,'type':'video'},'2':{'path':blue,'type':'video'}}
    basic,_,_=run_render(tmp_path/'basic',h,p,media,'basic')
    smart,plan,_=run_render(tmp_path/'smart',h,p,media,style)
    for when in (3.1,3.3):assert difference(pixels(basic['path'],when),pixels(smart['path'],when))>3
    assert smart['metadata']['smart_edit_applied_summary']['scene_transitions']==1


def test_mixed_actual_motion_failure_reports_only_successful_output_slots(tmp_path):
    clip=synthetic(tmp_path,'grid.mp4',['-f','lavfi','-i','testsrc2=s=320x240:r=30:d=4','-c:v','libx264'])
    h,p=contract(4);h['subtitles']=[]
    for s in p['scenes']:s.update(transition='hard_cut',motion='none',composition='wide',importance=50,overlay_text='')
    t=timeline.build(h,p);edit=smart_edit.build(t,h,'balanced','s');edit['emphasis']=[]
    folder=tmp_path/'job';folder.mkdir();voice=tmp_path/'voice.wav';voice.write_bytes(wav(4))
    class FailSecond(ProcessRunner):
        failed=False
        def run(self,args,cwd,*a,**context):
            if context.get('phase')=='slot_render' and context.get('slot_index')==1 and not self.failed:
                self.failed=True
                graph=folder/args[args.index('-/filter_complex')+1]
                graph.write_text(graph.read_text().replace('zoompan','invalid_motion'))
            return super().run(args,cwd,*a,**context)
    runner=FailSecond();engine=FFmpegRenderProvider(tools.discover(),runner)
    result=engine.render({'temporary':folder,'timeline':t,'handoff':h,'smart_edit_plan':edit,'options':options({'encoder':'cpu','subtitle_burned':False}),
        'media':{s['slot_id']:{'path':clip,'type':'video'} for s in t['slots']},'audio':voice,'music':None})
    assert runner.failed and edit['summary']['motion_effects']==2
    assert result['metadata']['smart_edit_applied_summary']['motion_effects']==1
    assert result['metadata']['warnings'] and abs(result['metadata']['duration']-4)<=.04


def test_saved_v1_edit_plan_stays_current_and_new_v2_render_preserves_old_video(ready):
    st=ready;c=st['client'];service=c.app.state.rendering
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu','editing_style':'balanced'}).status_code==202
    first=await_job(st)['active'];meta=deepcopy(first['metadata']);old=deepcopy(meta['smart_edit_plan'])
    old['algorithm_version']='smart_edit_v1'
    for slot in old['slots']:
        for segment in slot['segments']:
            if segment['motion_strength']>.012:segment['motion_strength']=.035
        if slot['transition_duration']:slot['transition_duration']=10/30
    old.pop('fingerprint');old['fingerprint']=smart_edit.digest(old);meta['smart_edit_plan']=old
    legacy=service._inputs(st['pid'],meta['options'],stored_edit_plan=old)['fingerprint']
    assert legacy!=service._inputs(st['pid'],meta['options'])['fingerprint']
    original=(st['root']/meta['output_local_path']).read_bytes()
    with closing(service.projects._connection()) as db,db:
        db.execute('UPDATE render_versions SET metadata_json=?,source_fingerprint=? WHERE id=?',(json.dumps(meta),legacy,first['id']))
    state=c.get(url(st)).json()
    assert not state['active']['stale'] and state['active']['metadata']['smart_edit_plan']==old
    assert c.post(url(st)+f'/versions/{first["id"]}/activate').status_code==200
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu','editing_style':'balanced'}).status_code==202
    state=await_job(st);assert state['job']['status']=='completed',state
    assert state['active']['version']==2 and state['active']['metadata']['smart_edit_plan']['algorithm_version']=='smart_edit_v2'
    assert not next(v for v in state['versions'] if v['id']==first['id'])['stale']
    assert (st['root']/meta['output_local_path']).read_bytes()==original
    for name,data in st['originals'].items():assert (st['root']/name).read_bytes()==data
